import logging
import base64
import struct
import time
from typing import Dict, Optional
from datetime import datetime
from app.config import settings
from app.services.stt_service import STTService
from app.services.gpt_service import GPTService
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)
# μ-law decoding table (since audioop was removed in Python 3.13)
ULAW_BIAS = 0x84
ULAW_CLIP = 32635


def ulaw_to_linear(ulaw_byte: int) -> int:
    """Convert a single μ-law byte to linear PCM (16-bit)."""
    ulaw_byte = ~ulaw_byte
    sign = (ulaw_byte & 0x80)
    exponent = (ulaw_byte >> 4) & 0x07
    mantissa = ulaw_byte & 0x0F
    sample = mantissa << (exponent + 3)
    sample += ULAW_BIAS << exponent
    if sign != 0:
        sample = -sample
    return sample


def ulaw_decode(ulaw_data: bytes) -> bytes:
    """Convert μ-law encoded audio to 16-bit PCM."""
    pcm_samples = [ulaw_to_linear(b) for b in ulaw_data]
    # Pack as 16-bit signed integers (little-endian)
    return struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)


def calculate_rms(pcm_data: bytes) -> float:
    """Calculate RMS (Root Mean Square) of 16-bit PCM audio."""
    # Unpack 16-bit signed integers
    sample_count = len(pcm_data) // 2
    if sample_count == 0:
        return 0.0
    samples = struct.unpack(f'<{sample_count}h', pcm_data)
    # Calculate RMS
    sum_squares = sum(s * s for s in samples)
    return (sum_squares / sample_count) ** 0.5


class VoiceService:
    """
    Service to handle voice call processing with Twilio.
    Manages audio streaming, processing, and state for active calls.
    """

    def __init__(self):
        self.active_calls: Dict[str, dict] = {}
        self.stats = {
            "total_calls": 0,
            "total_audio_chunks": 0,
            "total_bytes_received": 0
        }
        # Initialize STT service with Deepgram
        self.stt_service = STTService(api_key=settings.deepgram_api_key)
        if self.stt_service.is_enabled():
            logger.info("Voice service initialized with Deepgram transcription enabled")
        else:
            logger.warning("Voice service initialized without transcription (Deepgram not available)")

        # Initialize GPT service for generating responses
        self.gpt_service = GPTService()
        if self.gpt_service.is_enabled():
            logger.info("Voice service initialized with GPT streaming enabled")
        else:
            logger.warning("Voice service initialized without GPT (OpenAI not available)")

        # Initialize TTS service with Deepgram
        self.tts_service = TTSService(api_key=settings.deepgram_api_key)
        if self.tts_service.is_enabled():
            logger.info("Voice service initialized with Deepgram TTS enabled")
        else:
            logger.warning("Voice service initialized without TTS (Deepgram not available)")

    async def handle_stream_start(self, call_sid: str, stream_sid: str, start_message: dict, websocket=None):
        """Handle the start of a media stream."""
        logger.info(f"Stream started - CallSid: {call_sid}, StreamSid: {stream_sid}")
        self.active_calls[call_sid] = {
            "stream_sid": stream_sid,
            "start_time": datetime.now(),
            "audio_chunks": 0,
            "bytes_received": 0,
            "start_message": start_message,
            "transcription_count": 0,
            "source_format": "unknown",
            "conversation_buffer": [],
            "gpt_response_count": 0,
            "conversation_history": [],
            "gpt_timer": None,
            "websocket": websocket,
            "is_local": websocket and hasattr(websocket, '_is_local_test'),
            # Latency tracking
            "latency_metrics": {
                "last_audio_timestamp": None,
                "last_transcript_timestamp": None,
                "transcript_start": None,
                "gpt_start": None,
                "gpt_end": None,
                "tts_start": None,
                "tts_end": None,
            },
            "processing_lock": False,  # Prevent duplicate processing
            "last_processed_text": None,  # Track last processed utterance
            "duplicate_prevention_count": 0,  # Count prevented duplicates
        }
        self.stats["total_calls"] += 1

        # Start Deepgram streaming session if enabled
        if self.stt_service.is_enabled():
            success = await self.stt_service.start_stream(
                call_sid=call_sid,
                transcript_callback=self._handle_transcript,
                sample_rate=8000,
                channels=1
            )
            if not success:
                logger.error(f"Failed to start STT for {call_sid}")

    async def handle_media(self, call_sid: str, payload: str, is_mulaw: bool = True):
        """
        Handle incoming audio data.
        Payload is base64-encoded audio - μ-law from Twilio or PCM from local mic.

        Args:
            call_sid: Call identifier
            payload: Base64-encoded audio data
            is_mulaw: True for Twilio (μ-law), False for local mic (PCM)
        """
        if call_sid not in self.active_calls:
            logger.warning(f"Received media for unknown call: {call_sid}")
            return
        try:
            # Decode the base64 audio payload
            audio_data = base64.b64decode(payload)

            # Track timestamp for latency measurement
            self.active_calls[call_sid]["latency_metrics"]["last_audio_timestamp"] = time.time()

            # Update statistics
            self.active_calls[call_sid]["audio_chunks"] += 1
            self.active_calls[call_sid]["bytes_received"] += len(audio_data)
            self.stats["total_audio_chunks"] += 1
            self.stats["total_bytes_received"] += len(audio_data)

            # Process the audio data with format information
            await self._process_audio(call_sid, audio_data, is_mulaw=is_mulaw)
        except Exception as e:
            logger.error(f"Error handling media for call {call_sid}: {e}")

    async def _process_audio(self, call_sid: str, audio_data: bytes, is_mulaw: bool = True):
        """
        Process received audio data and stream to Deepgram.
        Handles format conversion from μ-law (Twilio) or PCM (local mic).

        Args:
            call_sid: Call identifier
            audio_data: Raw audio data (μ-law from Twilio, or PCM from local mic)
            is_mulaw: True if audio_data is μ-law encoded, False if already PCM
        """
        try:
            # Convert to PCM if needed
            if is_mulaw:
                pcm_audio = ulaw_decode(audio_data)
            else:
                pcm_audio = audio_data

            # Stream PCM audio directly to Deepgram
            if self.stt_service.is_enabled():
                await self.stt_service.send_audio(call_sid, pcm_audio)

        except Exception as e:
            logger.error(f"Error processing audio for call {call_sid}: {e}", exc_info=True)

    async def handle_stream_stop(self, call_sid: str):
        """Handle the end of a media stream."""
        if call_sid in self.active_calls:
            call_info = self.active_calls[call_sid]
            duration = (datetime.now() - call_info["start_time"]).total_seconds()

            logger.info(f"Stream stopped - {call_sid}")
            logger.info(f"  Duration: {duration:.2f}s | Chunks: {call_info['audio_chunks']} | "
                       f"Transcripts: {call_info['transcription_count']} | "
                       f"GPT Responses: {call_info['gpt_response_count']} | "
                       f"Duplicates Prevented: {call_info['duplicate_prevention_count']}")

            # Stop Deepgram stream
            if self.stt_service.is_enabled():
                await self.stt_service.stop_stream(call_sid)

    async def cleanup_call(self, call_sid: str):
        """Clean up resources for a call."""
        if call_sid in self.active_calls:
            # Ensure Deepgram stream is stopped
            if self.stt_service.is_enabled():
                await self.stt_service.stop_stream(call_sid)
            del self.active_calls[call_sid]
            logger.debug(f"Cleaned up call: {call_sid}")

    async def _handle_transcript(self, transcript: str, metadata: dict):
        """
        Handle transcription results from Deepgram.
        This is called as a callback when Deepgram produces a transcript.

        Args:
            transcript: The transcribed text
            metadata: Metadata about the transcription (confidence, timing, etc.)
        """
        call_sid = metadata.get("call_sid", "unknown")
        confidence = metadata.get("confidence", 0.0)
        is_final = metadata.get("is_final", False)
        speech_final = metadata.get("speech_final", False)

        if call_sid not in self.active_calls:
            return

        # Track latency
        transcript_time = time.time()
        call_info = self.active_calls[call_sid]
        metrics = call_info["latency_metrics"]

        if metrics["last_audio_timestamp"]:
            audio_to_transcript = (transcript_time - metrics["last_audio_timestamp"]) * 1000
            logger.debug(f"[LATENCY] Audio->Transcript: {audio_to_transcript:.0f}ms")

        metrics["last_transcript_timestamp"] = transcript_time
        if not metrics["transcript_start"]:
            metrics["transcript_start"] = transcript_time

        # Update transcription count
        call_info["transcription_count"] += 1

        # Log transcript with key metadata
        logger.info(f"[STT] '{transcript}' (final={is_final}, speech_final={speech_final}, conf={confidence:.2f})")

        # Process complete utterances - send to GPT when speech is final OR after collecting final transcripts
        if is_final and transcript.strip():
            # Add to conversation buffer
            call_info["conversation_buffer"].append(transcript.strip())

            # If speech is marked as final, process immediately
            if speech_final:
                # Cancel any pending timer
                if call_info["gpt_timer"]:
                    call_info["gpt_timer"].cancel()

                # Build the complete user input
                user_input = " ".join(call_info["conversation_buffer"])

                # Check for duplicate processing
                if call_info["processing_lock"]:
                    call_info["duplicate_prevention_count"] += 1
                    logger.warning(f"[DUPLICATE] Already processing, skipped duplicate #{call_info['duplicate_prevention_count']}")
                    return

                if call_info["last_processed_text"] == user_input:
                    call_info["duplicate_prevention_count"] += 1
                    logger.warning(f"[DUPLICATE] Same text already processed, skipped duplicate #{call_info['duplicate_prevention_count']}")
                    return

                # Send to GPT and get response
                await self._process_with_gpt(call_sid, user_input)

                # Clear buffer after processing
                call_info["conversation_buffer"].clear()
            else:
                # Schedule a delayed processing if more transcripts don't arrive
                # Cancel any existing timer
                if call_info["gpt_timer"]:
                    call_info["gpt_timer"].cancel()

                # Create new timer to process after 1.5 seconds of no new transcripts
                import asyncio
                async def delayed_process():
                    try:
                        await asyncio.sleep(1.5)
                        if call_sid in self.active_calls and call_info["conversation_buffer"]:
                            user_input = " ".join(call_info["conversation_buffer"])

                            # Check for duplicate before processing
                            if call_info["processing_lock"]:
                                call_info["duplicate_prevention_count"] += 1
                                logger.warning(f"[DUPLICATE] Timer: already processing, skipped")
                                return

                            if call_info["last_processed_text"] == user_input:
                                call_info["duplicate_prevention_count"] += 1
                                logger.warning(f"[DUPLICATE] Timer: same text, skipped")
                                return

                            logger.debug(f"[TIMER] Triggered GPT processing")
                            await self._process_with_gpt(call_sid, user_input)
                            call_info["conversation_buffer"].clear()
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"Error in delayed processing: {e}", exc_info=True)

                call_info["gpt_timer"] = asyncio.create_task(delayed_process())

    async def _process_with_gpt(self, call_sid: str, user_input: str):
        """
        Process user input with GPT and send audio response.

        Args:
            call_sid: Call identifier
            user_input: The user's complete utterance to send to GPT
        """
        if not self.gpt_service.is_enabled():
            logger.warning(f"GPT service not available for {call_sid}")
            return

        if call_sid not in self.active_calls:
            return

        call_info = self.active_calls[call_sid]
        metrics = call_info["latency_metrics"]

        try:
            # Set processing lock
            call_info["processing_lock"] = True
            call_info["last_processed_text"] = user_input

            # Track GPT start
            gpt_start = time.time()
            metrics["gpt_start"] = gpt_start

            # Log latency from transcript to GPT
            if metrics["transcript_start"]:
                transcript_to_gpt = (gpt_start - metrics["transcript_start"]) * 1000
                logger.info(f"[LATENCY] Transcript->GPT: {transcript_to_gpt:.0f}ms")

            logger.info(f"[GPT] Input: '{user_input}'")

            # Get conversation history for this call
            conversation_history = call_info["conversation_history"]

            # Get response from GPT service
            response_text = await self.gpt_service.get_response(
                user_input=user_input,
                conversation_history=conversation_history,
                model="gpt-4o-mini",
                max_completion_tokens=150,
                stream=True
            )

            # Track GPT end
            gpt_end = time.time()
            metrics["gpt_end"] = gpt_end
            gpt_duration = (gpt_end - gpt_start) * 1000
            logger.info(f"[LATENCY] GPT duration: {gpt_duration:.0f}ms")

            # Update response count and conversation history
            call_info["gpt_response_count"] += 1
            call_info["conversation_history"].append({"role": "user", "content": user_input})
            call_info["conversation_history"].append({"role": "assistant", "content": response_text})

            # Keep only last 10 messages (5 exchanges) to manage context window
            if len(call_info["conversation_history"]) > 10:
                call_info["conversation_history"] = call_info["conversation_history"][-10:]

            logger.info(f"[GPT] Response: '{response_text}'")

            # Convert response to speech and send back
            await self._send_audio_response(call_sid, response_text)

        except Exception as e:
            logger.error(f"Error processing with GPT for {call_sid}: {e}", exc_info=True)
        finally:
            # Release processing lock
            call_info["processing_lock"] = False

    async def _send_audio_response(self, call_sid: str, text: str):
        """
        Convert text to speech and send audio back to the caller.

        Args:
            call_sid: Call identifier
            text: Text to convert to speech
        """
        if not self.tts_service.is_enabled():
            logger.warning(f"TTS service not available for {call_sid}")
            return

        if call_sid not in self.active_calls:
            return

        call_info = self.active_calls[call_sid]
        metrics = call_info["latency_metrics"]

        try:
            websocket = call_info.get("websocket")
            is_local = call_info.get("is_local", False)

            if not websocket:
                logger.warning(f"No websocket available for {call_sid}")
                return

            # Track TTS start
            tts_start = time.time()
            metrics["tts_start"] = tts_start

            # Log latency from GPT to TTS
            if metrics["gpt_end"]:
                gpt_to_tts = (tts_start - metrics["gpt_end"]) * 1000
                logger.debug(f"[LATENCY] GPT->TTS: {gpt_to_tts:.0f}ms")

            logger.info(f"[TTS] Generating audio ({len(text)} chars)")

            if is_local:
                # For local testing, send PCM audio to be played through speakers
                audio_data = await self.tts_service.synthesize_for_local(text)
                if audio_data:
                    await websocket.send_json({
                        "event": "audio_response",
                        "audio": base64.b64encode(audio_data).decode('utf-8'),
                        "encoding": "linear16",
                        "sample_rate": 16000
                    })

                    # Track TTS end and total latency
                    tts_end = time.time()
                    metrics["tts_end"] = tts_end
                    tts_duration = (tts_end - tts_start) * 1000
                    total_latency = (tts_end - metrics["transcript_start"]) * 1000 if metrics["transcript_start"] else 0

                    logger.info(f"[LATENCY] TTS duration: {tts_duration:.0f}ms")
                    logger.info(f"[LATENCY] ⏱️  TOTAL (Transcript->Audio): {total_latency:.0f}ms")
                    logger.info(f"[TTS] Sent {len(audio_data)} bytes")
            else:
                # For Twilio, stream mulaw audio chunks
                chunk_count = 0
                async for audio_chunk_base64 in self.tts_service.stream_to_chunks(
                    text=text,
                    chunk_size_ms=20,
                    for_twilio=True
                ):
                    chunk_count += 1
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": call_info["stream_sid"],
                        "media": {
                            "payload": audio_chunk_base64
                        }
                    })

                # Track TTS end and total latency
                tts_end = time.time()
                metrics["tts_end"] = tts_end
                tts_duration = (tts_end - tts_start) * 1000
                total_latency = (tts_end - metrics["transcript_start"]) * 1000 if metrics["transcript_start"] else 0

                logger.info(f"[LATENCY] TTS duration: {tts_duration:.0f}ms")
                logger.info(f"[LATENCY] ⏱️  TOTAL (Transcript->Audio): {total_latency:.0f}ms")
                logger.info(f"[TTS] Sent {chunk_count} chunks")

        except Exception as e:
            logger.error(f"Error sending audio response for {call_sid}: {e}", exc_info=True)

    def get_stats(self) -> dict:
        """Get statistics about the voice service."""
        return {
            "active_calls": len(self.active_calls),
            "total_calls": self.stats["total_calls"],
            "total_audio_chunks": self.stats["total_audio_chunks"],
            "total_bytes_received": self.stats["total_bytes_received"],
            "call_details": {
                call_sid: {
                    "chunks": info["audio_chunks"],
                    "bytes": info["bytes_received"],
                    "duration_seconds": (datetime.now() - info["start_time"]).total_seconds()
                }
                for call_sid, info in self.active_calls.items()
            }
        }
