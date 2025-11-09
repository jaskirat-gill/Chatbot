import logging
import asyncio
from typing import Optional, Callable, Dict

logger = logging.getLogger(__name__)

try:
    from deepgram import AsyncDeepgramClient
    from deepgram.core.events import EventType
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False
    logger.warning("Deepgram SDK not installed. Install with: pip install deepgram-sdk")


class STTService:
    """
    Speech-to-Text service using Deepgram Flux.
    Handles real-time audio transcription from live audio streams (Twilio, local mic, etc.)
    Uses Flux model with eager end-of-turn detection for low latency.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the STT service with Deepgram Flux.

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
            # Initialize client with v5 SDK (async client)
            self.client = AsyncDeepgramClient(api_key=api_key)
            self.enabled = True
            logger.info("Deepgram Flux STT service initialized successfully")
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
        Start a Deepgram Flux streaming transcription session for a call.

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
            # Create async context manager for v5 AsyncDeepgramClient
            logger.info(f"[STT] Creating Deepgram connection for {call_sid}...")
            context = self.client.listen.v2.connect(
                model="flux-general-en",
                encoding="linear16",
                sample_rate=str(sample_rate),
            )
            logger.info(f"[STT] Context created, entering async context...")

            # Enter the async context to get connection
            connection = await context.__aenter__()
            logger.info(f"[STT] Context entered, setting up handlers...")

            # Set up event handlers
            def on_message(message):
                """Handle transcription results from Flux"""
                try:
                    # Check message type
                    msg_type = getattr(message, "type", "Unknown")

                    # Handle Flux v2 TurnInfo events (this is where transcripts are!)
                    if msg_type == "TurnInfo":
                        # Flux v2 structure: message has 'transcript' and 'words' directly
                        transcript = getattr(message, 'transcript', '')
                        words = getattr(message, 'words', [])
                        event = getattr(message, 'event', 'Unknown')
                        turn_index = getattr(message, 'turn_index', 0)
                        end_of_turn_confidence = getattr(message, 'end_of_turn_confidence', 0)

                        # Only log events with transcripts or important events (skip empty Updates)
                        if transcript or event in ['StartOfTurn', 'TurnEnd', 'EndOfTurn']:
                            logger.info(f"[STT] TurnInfo event='{event}', turn={turn_index}, transcript='{transcript}', eot_conf={end_of_turn_confidence:.4f}")

                        if transcript and transcript.strip():
                            # Calculate confidence from words if available
                            confidence = 0.0
                            if words:
                                confidence = sum(getattr(w, 'confidence', 0) for w in words) / len(words)

                            # Determine if this is final based on event type
                            # Flux v2 events: StartOfTurn, Update, TurnEnd, EndOfTurn
                            is_final = event in ['TurnEnd', 'EndOfTurn']
                            speech_final = event in ['TurnEnd', 'EndOfTurn']

                            # Only process on final events or high-confidence updates
                            should_process = is_final or (event == 'Update' and end_of_turn_confidence > 0.7)

                            if should_process:
                                metadata = {
                                    "call_sid": call_sid,
                                    "confidence": confidence,
                                    "is_final": is_final,
                                    "speech_final": speech_final,
                                    "duration": 0,
                                    "turn_index": turn_index,
                                    "event": event,
                                }

                                logger.info(f"[STT] Processing transcript: '{transcript}' (event={event}, final={is_final}, eot_conf={end_of_turn_confidence:.4f})")

                                # Schedule callback as a task
                                asyncio.create_task(transcript_callback(transcript, metadata))

                    # Log other message types for debugging
                    elif msg_type == "Connected":
                        logger.debug(f"[STT] Deepgram connected for {call_sid}")
                    else:
                        logger.debug(f"[STT] Other message type: {msg_type}")

                except Exception as e:
                    logger.error(f"[STT] Error processing message for {call_sid}: {e}", exc_info=True)

            # Register event handlers
            connection.on(EventType.OPEN, lambda _: logger.info(f"[STT] ✅ WebSocket OPENED for {call_sid}"))
            connection.on(EventType.MESSAGE, on_message)
            connection.on(EventType.CLOSE, lambda _: logger.info(f"[STT] WebSocket CLOSED for {call_sid}"))
            connection.on(EventType.ERROR, lambda error: logger.error(f"[STT] ❌ WebSocket ERROR for {call_sid}: {error}"))
            logger.info(f"[STT] Event handlers registered, starting listening...")

            # Create and store listening task
            listening_task = asyncio.create_task(connection.start_listening())
            logger.info(f"[STT] start_listening() task created and running in background")

            # Store connection, context, and listening task
            self.active_connections[call_sid] = {
                "connection": connection,
                "context": context,
                "listening_task": listening_task,
                "started": True
            }
            logger.info(f"[STT] Started for {call_sid} (flux-general-en, {sample_rate}Hz)")
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

            # Track chunks sent
            if "chunks_sent" not in conn_info:
                conn_info["chunks_sent"] = 0
            conn_info["chunks_sent"] += 1

            # Log first few chunks to verify it's working
            if conn_info["chunks_sent"] <= 3:
                logger.info(f"[STT] Sending audio chunk #{conn_info['chunks_sent']} ({len(pcm_audio_data)} bytes) for {call_sid}")

            # Send raw audio bytes directly - SDK wraps internally
            await connection.send_media(pcm_audio_data)

            # Log every 200 chunks
            if conn_info["chunks_sent"] % 200 == 0:
                logger.debug(f"[STT] Sent {conn_info['chunks_sent']} audio chunks for {call_sid}")

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
            context = conn_info.get("context")
            chunks_sent = conn_info.get("chunks_sent", 0)

            logger.info(f"[STT] Stopping stream for {call_sid} - sent {chunks_sent} audio chunks total")

            # Send close stream control message
            try:
                from deepgram.extensions.types.sockets import ListenV2ControlMessage
                await connection.send_control(ListenV2ControlMessage(type="CloseStream"))
            except Exception as e:
                logger.debug(f"[STT] Error sending close control: {e}")

            # Exit the async context manager if present
            if context:
                await context.__aexit__(None, None, None)

            del self.active_connections[call_sid]
            logger.debug(f"[STT] Stream stopped and cleaned up for {call_sid}")
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
