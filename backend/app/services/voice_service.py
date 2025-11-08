import logging
import base64
import struct
from typing import Dict, Optional
from datetime import datetime
from app.config import settings
from app.services.stt_service import STTService

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

    async def handle_stream_start(self, call_sid: str, stream_sid: str, start_message: dict):
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

        # Update transcription count
        if call_sid in self.active_calls:
            self.active_calls[call_sid]["transcription_count"] += 1

        # Log to console (as requested - print transcripts)
        logger.info(f"[TRANSCRIPT] Text: {transcript}")

        # Here you could also:
        # - Send transcript to RAG service for response generation
        # - Store transcript in database
        # - Send to websocket for real-time display
        # - etc.

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
