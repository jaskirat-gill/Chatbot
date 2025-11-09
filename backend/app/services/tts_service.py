import logging
import asyncio
from typing import Optional, Callable
import base64
import io

logger = logging.getLogger(__name__)

try:
    from deepgram import DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False
    logger.warning("Deepgram SDK not installed for TTS")


class TTSService:
    """
    Text-to-Speech service using Deepgram.
    Converts text to audio for voice responses.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the TTS service with Deepgram.

        Args:
            api_key: Deepgram API key. If None, TTS will be disabled.
        """
        self.api_key = api_key
        self.client = None
        self.enabled = False

        if not DEEPGRAM_AVAILABLE:
            logger.error("Deepgram SDK not available. TTS disabled.")
            return

        if not api_key:
            logger.warning("No Deepgram API key provided. TTS disabled.")
            return

        try:
            self.client = DeepgramClient(api_key=api_key)
            self.enabled = True
            logger.info("Deepgram TTS service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Deepgram TTS client: {e}")
            self.enabled = False

    async def synthesize_speech(
        self,
        text: str,
        model: str = "aura-asteria-en",
        encoding: str = "mulaw",
        sample_rate: int = 8000,
        container: str = "none"
    ) -> Optional[bytes]:
        """
        Synthesize speech from text using Deepgram TTS.

        Args:
            text: The text to convert to speech
            model: Deepgram TTS model (aura-asteria-en is natural female voice)
            encoding: Audio encoding (mulaw for Twilio, linear16 for local)
            sample_rate: Sample rate in Hz (8000 for Twilio, 16000+ for better quality)
            container: Audio container format ("none" for raw audio)

        Returns:
            Audio data as bytes, or None if failed
        """
        if not self.enabled:
            logger.warning("TTS service not enabled")
            return None

        try:
            # Generate speech using the speak v1 API
            response = self.client.speak.v1.audio.generate(
                text=text,
                model=model,
                encoding=encoding,
                sample_rate=sample_rate,
                container=container
            )

            # In v5, response has a stream attribute (BytesIO)
            if hasattr(response, 'stream'):
                audio_data = response.stream.getvalue()
                return audio_data if audio_data else None

            # Fallback: if response is iterable, collect chunks
            try:
                audio_data = b''
                for chunk in response:
                    audio_data += chunk
                return audio_data if audio_data else None
            except TypeError:
                logger.error(f"[TTS] Unknown response format: {type(response)}")
                return None


        except Exception as e:
            logger.error(f"[TTS] Error synthesizing speech: {e}", exc_info=True)
            return None

    async def synthesize_for_twilio(self, text: str) -> Optional[str]:
        """
        Synthesize speech optimized for Twilio (8kHz mulaw, base64 encoded).

        Args:
            text: The text to convert to speech

        Returns:
            Base64-encoded mulaw audio, or None if failed
        """
        audio_data = await self.synthesize_speech(
            text=text,
            model="aura-asteria-en",
            encoding="mulaw",
            sample_rate=8000,
            container="none"
        )

        if audio_data:
            # Encode to base64 for Twilio
            return base64.b64encode(audio_data).decode('utf-8')
        return None

    async def synthesize_for_local(self, text: str) -> Optional[bytes]:
        """
        Synthesize speech optimized for local playback (16kHz linear16).

        Args:
            text: The text to convert to speech

        Returns:
            Raw PCM audio data, or None if failed
        """
        return await self.synthesize_speech(
            text=text,
            model="aura-asteria-en",
            encoding="linear16",
            sample_rate=16000,
            container="none"
        )

    async def stream_to_chunks(
        self,
        text: str,
        chunk_size_ms: int = 20,
        for_twilio: bool = True
    ):
        """
        Generate audio and split into chunks for streaming.

        Args:
            text: Text to synthesize
            chunk_size_ms: Chunk duration in milliseconds (20ms for Twilio)
            for_twilio: If True, use Twilio format; else use local format

        Yields:
            Audio chunks as bytes (base64-encoded if for_twilio)
        """
        if for_twilio:
            audio_data = await self.synthesize_speech(
                text=text,
                encoding="mulaw",
                sample_rate=8000,
                container="none"
            )
            sample_rate = 8000
            bytes_per_sample = 1  # mulaw is 1 byte per sample
        else:
            audio_data = await self.synthesize_speech(
                text=text,
                encoding="linear16",
                sample_rate=16000,
                container="none"
            )
            sample_rate = 16000
            bytes_per_sample = 2  # linear16 is 2 bytes per sample

        if not audio_data:
            logger.warning("[TTS] No audio data generated")
            return

        # Calculate chunk size in bytes
        samples_per_chunk = (sample_rate * chunk_size_ms) // 1000
        chunk_size_bytes = samples_per_chunk * bytes_per_sample


        # Split into chunks
        for i in range(0, len(audio_data), chunk_size_bytes):
            chunk = audio_data[i:i + chunk_size_bytes]

            if for_twilio:
                # Encode for Twilio
                yield base64.b64encode(chunk).decode('utf-8')
            else:
                # Raw bytes for local
                yield chunk

            # Small delay to simulate real-time streaming
            await asyncio.sleep(chunk_size_ms / 1000.0)

    def is_enabled(self) -> bool:
        """Check if the TTS service is enabled and ready."""
        return self.enabled

