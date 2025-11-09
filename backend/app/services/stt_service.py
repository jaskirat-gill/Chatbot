import logging
import asyncio
from typing import Optional, Callable, Dict

logger = logging.getLogger(__name__)

try:
    from deepgram import (
        DeepgramClient,
        DeepgramClientOptions,
        LiveTranscriptionEvents,
        LiveOptions,
    )
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False
    logger.warning("Deepgram SDK not installed. Install with: pip install deepgram-sdk")


class STTService:
    """
    Speech-to-Text service using Deepgram Nova 3.
    Handles real-time audio transcription from live audio streams (Twilio, local mic, etc.)
    Uses Nova 3 model for high-accuracy transcription.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the STT service with Deepgram Nova 3.

        Args:
            api_key: Deepgram API key. If None, transcription will be disabled.
        """
        self.api_key = api_key
        self.client = None
        self.enabled = False
        self.active_connections: Dict[str, dict] = {}  # call_sid -> {"connection": ..., "task": ...}

        if not DEEPGRAM_AVAILABLE:
            logger.error("Deepgram SDK not available. Transcription disabled.")
            return

        if not api_key:
            logger.warning("No Deepgram API key provided. Transcription disabled.")
            return

        try:
            # Configure client
            config = DeepgramClientOptions(
                options={"keepalive": "true"}
            )
            self.client = DeepgramClient(api_key, config)
            self.enabled = True
            logger.info("Deepgram Nova 3 STT service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Deepgram client: {e}")
            self.enabled = False

    async def start_stream(
        self,
        call_sid: str,
        transcript_callback: Callable[[str, dict], None],
        sample_rate: int = 8000,
        channels: int = 1
    ) -> bool:
        """
        Start a Deepgram Nova 3 streaming transcription session for a call.

        Args:
            call_sid: Unique identifier for the call/stream
            transcript_callback: Async callback function(transcript: str, metadata: dict)
            sample_rate: Audio sample rate in Hz (8000 for Twilio, 16000 for better quality)
            channels: Number of audio channels (default 1 for mono)

        Returns:
            True if stream started successfully, False otherwise
        """
        logger.info(f"[STT] start_stream called for {call_sid}")

        if not self.enabled:
            logger.warning(f"[STT] Cannot start stream for {call_sid}: STT service not enabled")
            return False

        if call_sid in self.active_connections:
            logger.warning(f"[STT] Stream already exists for {call_sid}")
            return False

        try:
            # Use SDK v3 async API: client.listen.asynclive.v("2")
            dg_connection = self.client.listen.asynclive.v("2")

            # Set up event handlers BEFORE starting connection
            async def on_open(self_event=None, open_result=None, **kwargs):
                """Handle connection open"""
                logger.debug(f"[STT] Connection opened for {call_sid}")

            async def on_message(self_event=None, result=None, **kwargs):
                """Handle transcription results from Nova 3"""
                try:
                    if not result:
                        return

                    # Extract transcript from result
                    if hasattr(result, 'channel') and hasattr(result.channel, 'alternatives'):
                        alternatives = result.channel.alternatives
                        if alternatives and len(alternatives) > 0:
                            sentence = alternatives[0].transcript

                            if sentence and sentence.strip():
                                metadata = {
                                    "call_sid": call_sid,
                                    "confidence": alternatives[0].confidence if hasattr(alternatives[0], 'confidence') else 0,
                                    "is_final": result.is_final if hasattr(result, 'is_final') else True,
                                    "speech_final": result.speech_final if hasattr(result, 'speech_final') else False,
                                    "duration": result.duration if hasattr(result, 'duration') else 0,
                                }

                                # Call the callback
                                await transcript_callback(sentence, metadata)

                except Exception as e:
                    logger.error(f"[STT] Error processing transcript for {call_sid}: {e}", exc_info=True)

            async def on_error(self_event=None, error=None, **kwargs):
                """Handle errors"""
                logger.error(f"[STT] Error for {call_sid}: {error}")

            async def on_close(self_event=None, close_result=None, **kwargs):
                """Handle connection close"""
                logger.debug(f"[STT] Connection closed for {call_sid}")

            async def on_unhandled(self_event=None, unhandled=None, **kwargs):
                """Handle unhandled messages"""
                logger.debug(f"[STT] Unhandled event for {call_sid}: {unhandled}")

            # Register event handlers
            dg_connection.on(LiveTranscriptionEvents.Open, on_open)
            dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
            dg_connection.on(LiveTranscriptionEvents.Error, on_error)
            dg_connection.on(LiveTranscriptionEvents.Close, on_close)
            dg_connection.on(LiveTranscriptionEvents.Unhandled, on_unhandled)

            # Configure options for Nova 3 model
            options = LiveOptions(
                model="nova-3",  # Nova 3 model for high-accuracy transcription
                language="en-US",
                smart_format=True,
                punctuate=True,
                encoding="linear16",  # 16-bit PCM
                sample_rate=sample_rate,
                channels=channels,
                interim_results=True,  # Enable interim results to get speech_final events
                vad_events=True,  # Voice activity detection
            )

            # Start the connection
            start_result = await dg_connection.start(options)

            if not start_result:
                logger.error(f"[STT] Failed to start connection for {call_sid}")
                return False

            # Store connection
            self.active_connections[call_sid] = {
                "connection": dg_connection,
                "started": True
            }
            logger.info(f"[STT] Started for {call_sid} (nova-3, {sample_rate}Hz)")
            return True

        except Exception as e:
            logger.error(f"[STT] ❌ Exception starting stream for {call_sid}: {e}", exc_info=True)
            return False

    async def send_audio(self, call_sid: str, pcm_audio_data: bytes) -> bool:
        """
        Send audio data to the streaming transcription session.

        Args:
            call_sid: Unique identifier for the call/stream
            pcm_audio_data: Raw PCM audio data (16-bit linear, little-endian)

        Returns:
            True if audio was sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        if call_sid not in self.active_connections:
            logger.warning(f"No active stream for {call_sid}")
            return False

        try:
            conn_info = self.active_connections[call_sid]
            connection = conn_info["connection"]


            # Send audio data
            await connection.send(pcm_audio_data)
            return True
        except Exception as e:
            logger.error(f"[STT] Error sending audio for {call_sid}: {e}", exc_info=True)
            return False

    async def stop_stream(self, call_sid: str) -> bool:
        """
        Stop a streaming transcription session.

        Args:
            call_sid: Unique identifier for the call/stream

        Returns:
            True if stream was stopped successfully, False otherwise
        """
        if call_sid not in self.active_connections:
            return False

        try:
            conn_info = self.active_connections[call_sid]
            connection = conn_info["connection"]
            await connection.finish()
            del self.active_connections[call_sid]
            logger.debug(f"[STT] Stopped stream for {call_sid}")
            return True
        except Exception as e:
            logger.error(f"Error stopping stream for {call_sid}: {e}")
            return False

    def is_enabled(self) -> bool:
        """Check if the STT service is enabled and ready."""
        return self.enabled

    def get_active_streams(self) -> list:
        """Get list of active stream IDs."""
        return list(self.active_connections.keys())
