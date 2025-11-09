import logging
import base64
import struct
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
            "source_format": "unknown",  # Will be determined from first audio chunk
            "conversation_buffer": [],  # Buffer for building complete sentences
            "gpt_response_count": 0,  # Track GPT responses
            "conversation_history": [],  # Track conversation for context
            "gpt_timer": None,  # Timer for delayed GPT processing
            "websocket": websocket,  # WebSocket for sending audio back
            "is_local": websocket and hasattr(websocket, '_is_local_test'),  # Flag for local testing
        }
        self.stats["total_calls"] += 1

        # Log stream parameters at debug level
        stream_params = start_message.get("start", {})
        logger.debug(f"Stream parameters: {stream_params}")

        # Start Deepgram streaming session if enabled
        if self.stt_service.is_enabled():
            success = await self.stt_service.start_stream(
                call_sid=call_sid,
                transcript_callback=self._handle_transcript,
                sample_rate=8000,  # Twilio and our local mic both use 8kHz
                channels=1
            )
            if not success:
                logger.warning(f"[VOICE] Failed to start Deepgram streaming for call {call_sid}")

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
            # Update statistics
            self.active_calls[call_sid]["audio_chunks"] += 1
            self.active_calls[call_sid]["bytes_received"] += len(audio_data)
            self.stats["total_audio_chunks"] += 1
            self.stats["total_bytes_received"] += len(audio_data)
            # Log every 100 chunks at debug level
            if self.active_calls[call_sid]["audio_chunks"] % 100 == 0:
                chunks = self.active_calls[call_sid]["audio_chunks"]
                bytes_received = self.active_calls[call_sid]["bytes_received"]
                logger.debug(f"Call {call_sid}: Received {chunks} chunks, {bytes_received} bytes total")
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
                # Twilio sends μ-law - convert to 16-bit PCM
                pcm_audio = ulaw_decode(audio_data)

                # Calculate RMS for voice activity detection (optional logging)
                rms = calculate_rms(pcm_audio)
                if rms > 500 and self.active_calls[call_sid]["audio_chunks"] % 50 == 0:
                    logger.debug(f"Call {call_sid}: Voice activity detected - RMS: {rms:.0f}")
            else:
                # Local mic already sends PCM
                pcm_audio = audio_data

            # Stream PCM audio directly to Deepgram
            if self.stt_service.is_enabled():
                sent = await self.stt_service.send_audio(call_sid, pcm_audio)
                if not sent and self.active_calls[call_sid]["audio_chunks"] == 1:
                    logger.error(f"[VOICE] Failed to send first audio chunk to Deepgram for {call_sid}")

        except Exception as e:
            logger.error(f"Error processing audio for call {call_sid}: {e}", exc_info=True)

    async def handle_stream_stop(self, call_sid: str):
        """Handle the end of a media stream."""
        if call_sid in self.active_calls:
            call_info = self.active_calls[call_sid]
            duration = (datetime.now() - call_info["start_time"]).total_seconds()
            logger.info(f"Stream stopped - CallSid: {call_sid}")
            logger.info(f"  Duration: {duration:.2f}s")
            logger.info(f"  Total chunks: {call_info['audio_chunks']}")
            logger.info(f"  Total bytes: {call_info['bytes_received']}")
            logger.info(f"  Transcriptions: {call_info['transcription_count']}")
            logger.info(f"  GPT Responses: {call_info['gpt_response_count']}")

            # Stop Deepgram stream
            if self.stt_service.is_enabled():
                await self.stt_service.stop_stream(call_sid)

    async def cleanup_call(self, call_sid: str):
        """Clean up resources for a call."""
        if call_sid in self.active_calls:
            logger.info(f"Cleaning up call: {call_sid}")
            # Ensure Deepgram stream is stopped
            if self.stt_service.is_enabled():
                await self.stt_service.stop_stream(call_sid)
            del self.active_calls[call_sid]

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

        # Update transcription count
        if call_sid in self.active_calls:
            self.active_calls[call_sid]["transcription_count"] += 1

        # Log the transcript
        logger.info(f"[TRANSCRIPT] CallSid: {call_sid}, Text: '{transcript}', Final: {is_final}, SpeechFinal: {speech_final}, Confidence: {confidence:.2f}")

        # Process complete utterances - send to GPT when speech is final OR after collecting final transcripts
        if is_final and transcript.strip() and call_sid in self.active_calls:
            # Add to conversation buffer
            self.active_calls[call_sid]["conversation_buffer"].append(transcript.strip())
            logger.debug(f"[TRANSCRIPT] Added to buffer. Buffer size: {len(self.active_calls[call_sid]['conversation_buffer'])}")

            # If speech is marked as final, process immediately
            if speech_final:
                logger.info(f"[TRANSCRIPT] Speech final detected - processing immediately")
                # Cancel any pending timer
                if "gpt_timer" in self.active_calls[call_sid] and self.active_calls[call_sid]["gpt_timer"]:
                    self.active_calls[call_sid]["gpt_timer"].cancel()
                    logger.debug(f"[TRANSCRIPT] Cancelled pending timer")
                
                # Build the complete user input
                user_input = " ".join(self.active_calls[call_sid]["conversation_buffer"])

                # Send to GPT and get response
                await self._process_with_gpt(call_sid, user_input)

                # Clear buffer after processing
                self.active_calls[call_sid]["conversation_buffer"].clear()
            else:
                # Schedule a delayed processing if more transcripts don't arrive
                logger.debug(f"[TRANSCRIPT] No speech_final - scheduling delayed processing")
                
                # Cancel any existing timer
                if "gpt_timer" in self.active_calls[call_sid] and self.active_calls[call_sid]["gpt_timer"]:
                    self.active_calls[call_sid]["gpt_timer"].cancel()
                    logger.debug(f"[TRANSCRIPT] Cancelled existing timer")

                # Create new timer to process after 1.5 seconds of no new transcripts
                import asyncio
                async def delayed_process():
                    try:
                        logger.debug(f"[TRANSCRIPT] Timer started - waiting 1.5s...")
                        await asyncio.sleep(1.5)
                        logger.debug(f"[TRANSCRIPT] Timer expired - checking buffer")
                        if call_sid in self.active_calls and self.active_calls[call_sid]["conversation_buffer"]:
                            user_input = " ".join(self.active_calls[call_sid]["conversation_buffer"])
                            logger.info(f"[TRANSCRIPT] Timer triggered GPT processing for: '{user_input}'")
                            await self._process_with_gpt(call_sid, user_input)
                            self.active_calls[call_sid]["conversation_buffer"].clear()
                        else:
                            logger.debug(f"[TRANSCRIPT] Timer expired but buffer is empty")
                    except asyncio.CancelledError:
                        logger.debug(f"[TRANSCRIPT] Timer cancelled")
                    except Exception as e:
                        logger.error(f"[TRANSCRIPT] Error in delayed processing: {e}", exc_info=True)

                self.active_calls[call_sid]["gpt_timer"] = asyncio.create_task(delayed_process())
                logger.debug(f"[TRANSCRIPT] New timer created")

    async def _process_with_gpt(self, call_sid: str, user_input: str):
        """
        Process user input with GPT and send audio response.

        Args:
            call_sid: Call identifier
            user_input: The user's complete utterance to send to GPT
        """
        if not self.gpt_service.is_enabled():
            logger.warning(f"[GPT] GPT service not available for call {call_sid}")
            return

        try:
            logger.info(f"[GPT] Sending to GPT - CallSid: {call_sid}, Input: '{user_input}'")

            # Get conversation history for this call
            conversation_history = []
            if call_sid in self.active_calls:
                conversation_history = self.active_calls[call_sid]["conversation_history"]

            # Get response from GPT service
            response_text = await self.gpt_service.get_response(
                user_input=user_input,
                conversation_history=conversation_history,
                model="gpt-5-nano",
                max_completion_tokens=1500,
                stream=True
            )

            # Update response count and conversation history
            if call_sid in self.active_calls:
                self.active_calls[call_sid]["gpt_response_count"] += 1

                # Add to conversation history
                self.active_calls[call_sid]["conversation_history"].append(
                    {"role": "user", "content": user_input}
                )
                self.active_calls[call_sid]["conversation_history"].append(
                    {"role": "assistant", "content": response_text}
                )

                # Keep only last 10 messages (5 exchanges) to manage context window
                if len(self.active_calls[call_sid]["conversation_history"]) > 10:
                    self.active_calls[call_sid]["conversation_history"] = \
                        self.active_calls[call_sid]["conversation_history"][-10:]

            # Log the complete GPT response
            logger.info(f"[GPT RESPONSE] CallSid: {call_sid}, Response: '{response_text}'")
            logger.info(f"[GPT RESPONSE] Length: {len(response_text)} characters")

            # Convert response to speech and send back
            await self._send_audio_response(call_sid, response_text)

        except Exception as e:
            logger.error(f"[GPT] Error processing with GPT for call {call_sid}: {e}", exc_info=True)

    async def _send_audio_response(self, call_sid: str, text: str):
        """
        Convert text to speech and send audio back to the caller.

        Args:
            call_sid: Call identifier
            text: Text to convert to speech
        """
        if not self.tts_service.is_enabled():
            logger.warning(f"[TTS] TTS service not available for call {call_sid}")
            return

        if call_sid not in self.active_calls:
            logger.warning(f"[TTS] Call {call_sid} not found in active calls")
            return

        try:
            call_info = self.active_calls[call_sid]
            websocket = call_info.get("websocket")
            is_local = call_info.get("is_local", False)

            if not websocket:
                logger.warning(f"[TTS] No websocket available for call {call_sid}")
                return

            logger.info(f"[TTS] Generating audio for: '{text[:50]}...' (local={is_local})")

            if is_local:
                # For local testing, send PCM audio to be played through speakers
                audio_data = await self.tts_service.synthesize_for_local(text)
                if audio_data:
                    # Send as a single message to local client for playback
                    await websocket.send_json({
                        "event": "audio_response",
                        "audio": base64.b64encode(audio_data).decode('utf-8'),
                        "encoding": "linear16",
                        "sample_rate": 16000
                    })
                    logger.info(f"[TTS] Sent {len(audio_data)} bytes to local client")
            else:
                # For Twilio, stream mulaw audio chunks
                chunk_count = 0
                async for audio_chunk_base64 in self.tts_service.stream_to_chunks(
                    text=text,
                    chunk_size_ms=20,
                    for_twilio=True
                ):
                    chunk_count += 1
                    # Send media message to Twilio
                    await websocket.send_json({
                        "event": "media",
                        "streamSid": call_info["stream_sid"],
                        "media": {
                            "payload": audio_chunk_base64
                        }
                    })

                    if chunk_count % 25 == 0:  # Log every 500ms
                        logger.debug(f"[TTS] Sent {chunk_count} audio chunks to Twilio")

                logger.info(f"[TTS] Sent {chunk_count} audio chunks to Twilio")

        except Exception as e:
            logger.error(f"[TTS] Error sending audio response for call {call_sid}: {e}", exc_info=True)

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
