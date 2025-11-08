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
import queue
import numpy as np
from datetime import datetime

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice is required. Install it with: pip install sounddevice")
    sys.exit(1)


class MicrophoneStreamer:
    def __init__(self, call_id: str, ws_url: str):
        self.call_id = call_id
        self.ws_url = ws_url
        self.ws = None
        self.stream = None
        self.is_streaming = False
        self.audio_queue = queue.Queue()

        # Audio configuration (matching Twilio's format)
        self.CHUNK = 160  # 20ms of audio at 8kHz
        self.CHANNELS = 1  # Mono
        self.RATE = 8000  # 8kHz sample rate (Twilio uses 8kHz)
        self.DTYPE = np.int16  # 16-bit PCM

        self.chunk_count = 0
        self.start_time = None

        # Audio level tracking
        self.rms_values = []
        self.silent_chunks = 0
        self.active_chunks = 0
        self.SILENCE_THRESHOLD = 100  # Adjust based on your environment

    def log(self, message: str, level: str = "INFO"):
        """Simple logging function."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{level}] {message}")

    def calculate_rms(self, audio_data: np.ndarray) -> float:
        """Calculate RMS (Root Mean Square) of audio data."""
        # Audio data is already int16, calculate RMS
        return np.sqrt(np.mean(audio_data.astype(np.float64) ** 2))

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

    def audio_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice to handle incoming audio data."""
        if status:
            self.log(f"Audio status: {status}", "WARNING")
        # Put audio data into queue
        self.audio_queue.put(indata.copy())

    def setup_audio(self):
        """Initialize sounddevice and open audio stream."""
        self.log("Initializing audio...")
        try:
            # List available input devices (for debugging)
            devices = sd.query_devices()
            default_input = sd.query_devices(kind='input')
            self.log(f"Using input device: {default_input['name']}")

            # Open audio stream with callback
            self.stream = sd.InputStream(
                samplerate=self.RATE,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self.CHUNK,
                callback=self.audio_callback
            )

            self.log(f"Audio stream configured (rate={self.RATE}Hz, chunk={self.CHUNK})")
            return True
        except Exception as e:
            self.log(f"Audio setup failed: {e}", "ERROR")
            return False

    async def stream_audio(self):
        """Stream audio from microphone to WebSocket."""
        self.log("Starting audio streaming... (Press Ctrl+C to stop)")
        self.is_streaming = True
        self.start_time = datetime.now()

        # Start the audio stream
        self.stream.start()
        self.log("Audio stream started")

        try:
            while self.is_streaming:
                # Get audio chunk from queue (with timeout to allow checking is_streaming)
                try:
                    audio_data = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Calculate audio level (RMS)
                rms = self.calculate_rms(audio_data)
                self.rms_values.append(rms)

                # Track silence vs active audio
                if rms > self.SILENCE_THRESHOLD:
                    self.active_chunks += 1
                else:
                    self.silent_chunks += 1

                # Convert numpy array to bytes
                audio_bytes = audio_data.tobytes()

                # Encode to base64
                encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')

                # Send to WebSocket
                message = {
                    "event": "media",
                    "payload": encoded_audio
                }
                await self.ws.send(json.dumps(message))

                self.chunk_count += 1

                # Log progress every 100 chunks (~2 seconds) with audio level stats
                if self.chunk_count % 100 == 0:
                    elapsed = (datetime.now() - self.start_time).total_seconds()
                    recent_rms = self.rms_values[-100:] if len(self.rms_values) >= 100 else self.rms_values
                    avg_rms = sum(recent_rms) / len(recent_rms) if recent_rms else 0
                    max_rms = max(recent_rms) if recent_rms else 0
                    self.log(f"Streamed {self.chunk_count} chunks ({elapsed:.1f}s) | Avg level: {avg_rms:.0f}, Peak: {max_rms:.0f}")


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
            self.stream.stop()
            self.stream.close()
            self.log("Audio stream closed")


        # Print summary with audio statistics
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            self.log(f"\n{'='*60}", "INFO")
            self.log(f"SESSION SUMMARY", "INFO")
            self.log(f"{'='*60}", "INFO")
            self.log(f"Duration: {duration:.2f}s", "INFO")
            self.log(f"Total chunks: {self.chunk_count}", "INFO")

            if self.rms_values:
                avg_rms = sum(self.rms_values) / len(self.rms_values)
                max_rms = max(self.rms_values)
                min_rms = min(self.rms_values)

                self.log(f"\nAUDIO LEVELS:", "INFO")
                self.log(f"  Average RMS: {avg_rms:.0f}", "INFO")
                self.log(f"  Peak RMS: {max_rms:.0f}", "INFO")
                self.log(f"  Min RMS: {min_rms:.0f}", "INFO")

                active_pct = (self.active_chunks / self.chunk_count * 100) if self.chunk_count > 0 else 0
                silent_pct = (self.silent_chunks / self.chunk_count * 100) if self.chunk_count > 0 else 0

                self.log(f"\nACTIVITY (threshold={self.SILENCE_THRESHOLD}):", "INFO")
                self.log(f"  Active chunks: {self.active_chunks} ({active_pct:.1f}%)", "INFO")
                self.log(f"  Silent chunks: {self.silent_chunks} ({silent_pct:.1f}%)", "INFO")

                # Provide interpretation
                if avg_rms < 50:
                    self.log(f"\n⚠️  WARNING: Very low audio levels detected!", "WARNING")
                    self.log(f"   Your microphone may not be working or volume is too low.", "WARNING")
                elif avg_rms < self.SILENCE_THRESHOLD:
                    self.log(f"\n⚠️  Low audio levels - mostly silent.", "WARNING")
                elif active_pct > 10:
                    self.log(f"\n✅ Good audio levels detected!", "INFO")

            self.log(f"{'='*60}\n", "INFO")

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
            if self.stream:
                self.stream.stop()
                self.stream.close()
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

