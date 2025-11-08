#!/usr/bin/env python3
"""
Simple CLI tool to test voice service by streaming audio from your local microphone.
Usage: python test_local_mic.py [--call-id CALL_ID] [--url WS_URL]
"""

import asyncio
import websockets
import json
import base64
import argparse
import sys
from datetime import datetime

try:
    import pyaudio
except ImportError:
    print("ERROR: pyaudio is required. Install it with: pip install pyaudio")
    sys.exit(1)


class MicrophoneStreamer:
    def __init__(self, call_id: str, ws_url: str):
        self.call_id = call_id
        self.ws_url = ws_url
        self.ws = None
        self.audio = None
        self.stream = None
        self.is_streaming = False

        # Audio configuration (matching Twilio's format)
        self.CHUNK = 160  # 20ms of audio at 8kHz
        self.FORMAT = pyaudio.paInt16  # 16-bit PCM
        self.CHANNELS = 1  # Mono
        self.RATE = 8000  # 8kHz sample rate (Twilio uses 8kHz)

        self.chunk_count = 0
        self.start_time = None

    def log(self, message: str, level: str = "INFO"):
        """Simple logging function."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{level}] {message}")

    async def connect(self):
        """Connect to the WebSocket server."""
        self.log(f"Connecting to: {self.ws_url}")
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.log("WebSocket connected", "SUCCESS")

            # Send start event
            start_message = {
                "event": "start",
                "start": {
                    "streamSid": f"local-{self.call_id}",
                    "callSid": self.call_id
                }
            }
            await self.ws.send(json.dumps(start_message))
            self.log("Sent start event")

            return True
        except Exception as e:
            self.log(f"Connection failed: {e}", "ERROR")
            return False

    def setup_audio(self):
        """Initialize PyAudio and open audio stream."""
        self.log("Initializing audio...")
        try:
            self.audio = pyaudio.PyAudio()

            # List available input devices (for debugging)
            info = self.audio.get_host_api_info_by_index(0)
            numdevices = info.get('deviceCount')
            self.log(f"Found {numdevices} audio devices")

            # Open audio stream
            self.stream = self.audio.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )

            self.log(f"Audio stream opened (rate={self.RATE}Hz, chunk={self.CHUNK})")
            return True
        except Exception as e:
            self.log(f"Audio setup failed: {e}", "ERROR")
            return False

    async def stream_audio(self):
        """Stream audio from microphone to WebSocket."""
        self.log("Starting audio streaming... (Press Ctrl+C to stop)")
        self.is_streaming = True
        self.start_time = datetime.now()

        try:
            while self.is_streaming:
                # Read audio chunk from microphone
                audio_data = self.stream.read(self.CHUNK, exception_on_overflow=False)

                # Encode to base64
                encoded_audio = base64.b64encode(audio_data).decode('utf-8')

                # Send to WebSocket
                message = {
                    "event": "media",
                    "payload": encoded_audio
                }
                await self.ws.send(json.dumps(message))

                self.chunk_count += 1

                # Log progress every 100 chunks (~2 seconds)
                if self.chunk_count % 100 == 0:
                    elapsed = (datetime.now() - self.start_time).total_seconds()
                    self.log(f"Streamed {self.chunk_count} chunks ({elapsed:.1f}s)")

                # Small delay to match real-time streaming
                await asyncio.sleep(0.001)

        except KeyboardInterrupt:
            self.log("\nStopping stream (KeyboardInterrupt)...")
        except Exception as e:
            self.log(f"Streaming error: {e}", "ERROR")
        finally:
            await self.stop()

    async def stop(self):
        """Stop streaming and clean up resources."""
        self.log("Stopping streaming...")
        self.is_streaming = False

        # Send stop event
        if self.ws:
            try:
                stop_message = {"event": "stop"}
                await self.ws.send(json.dumps(stop_message))
                await self.ws.close()
                self.log("WebSocket closed")
            except Exception as e:
                self.log(f"Error closing WebSocket: {e}", "ERROR")

        # Clean up audio
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.log("Audio stream closed")

        if self.audio:
            self.audio.terminate()

        # Print summary
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            self.log(f"Session summary: {self.chunk_count} chunks, {duration:.2f}s duration", "INFO")

    async def run(self):
        """Main run loop."""
        print("\n" + "="*60)
        print("  JD AI Voice Service - Local Microphone Test")
        print("="*60)
        print(f"Call ID: {self.call_id}")
        print(f"WebSocket URL: {self.ws_url}")
        print("="*60 + "\n")

        # Setup audio
        if not self.setup_audio():
            return

        # Connect to WebSocket
        if not await self.connect():
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()
            return

        # Start streaming
        await self.stream_audio()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test voice service by streaming audio from your microphone"
    )
    parser.add_argument(
        "--call-id",
        default="test-call-001",
        help="Call ID to use (default: test-call-001)"
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/v1/api/voice/local-mic",
        help="WebSocket URL (default: ws://localhost:8000/v1/api/voice/local-mic)"
    )

    args = parser.parse_args()

    # Build full WebSocket URL
    ws_url = f"{args.url}/{args.call_id}"

    # Create and run streamer
    streamer = MicrophoneStreamer(args.call_id, ws_url)

    try:
        await streamer.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        print("\nTest completed.\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)

