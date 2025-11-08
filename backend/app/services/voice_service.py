import logging
import base64
import struct
from typing import Dict, Optional
from datetime import datetime

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

    async def handle_stream_start(self, call_sid: str, stream_sid: str, start_message: dict):
        """Handle the start of a media stream."""
        logger.info(f"Stream started - CallSid: {call_sid}, StreamSid: {stream_sid}")
        self.active_calls[call_sid] = {
            "stream_sid": stream_sid,
            "start_time": datetime.now(),
            "audio_chunks": 0,
            "bytes_received": 0,
            "start_message": start_message
        }
        self.stats["total_calls"] += 1
        # Log stream parameters at debug level
        stream_params = start_message.get("start", {})
        logger.debug(f"Stream parameters: {stream_params}")

    async def handle_media(self, call_sid: str, payload: str):
        """
        Handle incoming audio data from Twilio.
        Payload is base64-encoded μ-law audio at 8kHz.
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
            # Process the audio data
            await self._process_audio(call_sid, audio_data)
        except Exception as e:
            logger.error(f"Error handling media for call {call_sid}: {e}")

    async def _process_audio(self, call_sid: str, audio_data: bytes):
        """
        Process the received audio data.
        Currently just logs it, but this is where you would:
        - Convert μ-law to linear PCM
        - Perform speech recognition
        - Send to AI model
        - Generate responses
        """
        # The audio is in μ-law format, 8kHz, mono
        try:
            # Decode μ-law to 16-bit PCM
            linear_audio = ulaw_decode(audio_data)
            # Calculate RMS (volume level) to detect speech
            rms = calculate_rms(linear_audio)

            # Log when we detect significant audio (simple voice activity detection)
            if rms > 500:  # Threshold for detecting speech (adjust as needed)
                logger.debug(f"Call {call_sid}: Audio detected - RMS: {rms:.0f}")
        except Exception as e:
            logger.error(f"Error processing audio for call {call_sid}: {e}")

    async def handle_stream_stop(self, call_sid: str):
        """Handle the end of a media stream."""
        if call_sid in self.active_calls:
            call_info = self.active_calls[call_sid]
            duration = (datetime.now() - call_info["start_time"]).total_seconds()
            logger.info(f"Stream stopped - CallSid: {call_sid}")
            logger.info(f"  Duration: {duration:.2f}s")
            logger.info(f"  Total chunks: {call_info['audio_chunks']}")
            logger.info(f"  Total bytes: {call_info['bytes_received']}")

    async def cleanup_call(self, call_sid: str):
        """Clean up resources for a call."""
        if call_sid in self.active_calls:
            logger.info(f"Cleaning up call: {call_sid}")
            del self.active_calls[call_sid]

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
