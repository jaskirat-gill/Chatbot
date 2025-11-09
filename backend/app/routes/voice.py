from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import PlainTextResponse
import logging
import json
import base64
from typing import Dict, Set
from app.services.voice_service import VoiceService

logger = logging.getLogger(__name__)

router = APIRouter()
voice_service = VoiceService()

# Track active WebSocket connections
active_connections: Dict[str, WebSocket] = {}


@router.post("/voice/incoming")
async def handle_incoming_call(request: Request):
    """
    Twilio webhook endpoint for incoming calls.
    Returns TwiML to connect the call to a WebSocket stream.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")

    logger.info(f"Incoming call - CallSid: {call_sid}, From: {from_number}, To: {to_number}")

    # Get the base URL for the WebSocket connection
    # In production, this should be your public domain
    # For local testing with ngrok, you'll need to update this
    host = request.headers.get("host", "localhost:8000")
    protocol = "wss" if "https" in str(request.url) else "ws"
    ws_url = f"{protocol}://{host}/v1/api/voice/stream/{call_sid}"

    # TwiML response to connect the call to our WebSocket
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="callSid" value="{call_sid}" />
        </Stream>
    </Connect>
</Response>"""

    logger.info(f"Sending TwiML response with WebSocket URL: {ws_url}")

    return Response(content=twiml, media_type="application/xml")


@router.websocket("/voice/stream/{call_sid}")
async def websocket_stream(websocket: WebSocket, call_sid: str):
    """
    WebSocket endpoint for Twilio Media Streams.
    Handles bidirectional audio streaming with Twilio.
    """
    await websocket.accept()
    active_connections[call_sid] = websocket

    logger.info(f"WebSocket connection established for call: {call_sid}")

    message_count = 0
    media_count = 0

    try:
        while True:
            # Receive messages from Twilio
            data = await websocket.receive_text()
            message = json.loads(data)
            message_count += 1

            event_type = message.get("event")

            if event_type == "start":
                logger.info(f"Stream started for call {call_sid}")
                logger.debug(f"Stream start details: {message}")
                stream_sid = message.get("streamSid")
                await voice_service.handle_stream_start(call_sid, stream_sid, message, websocket=websocket)

            elif event_type == "media":
                # Audio data from Twilio (base64 encoded μ-law audio)
                media_count += 1
                payload = message.get("media", {}).get("payload")
                if payload:
                    await voice_service.handle_media(call_sid, payload)
                else:
                    logger.warning(f"Received media event with no payload for call {call_sid}")

                # Log every 50 media messages at debug level to track activity
                if media_count % 50 == 0:
                    logger.debug(f"Call {call_sid}: Received {media_count} media messages, {message_count} total messages")

            elif event_type == "stop":
                logger.info(f"Stream stopped for call {call_sid} - Total messages: {message_count}, Media: {media_count}")
                await voice_service.handle_stream_stop(call_sid)
                break

            elif event_type == "mark":
                # Mark events are sent when custom marks are reached
                logger.debug(f"Mark event received: {message}")

            else:
                logger.warning(f"Unknown event type '{event_type}' for call {call_sid}: {message}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for call: {call_sid}")
    except Exception as e:
        logger.error(f"Error in WebSocket connection for call {call_sid}: {e}")
    finally:
        if call_sid in active_connections:
            del active_connections[call_sid]
        await voice_service.cleanup_call(call_sid)


@router.websocket("/voice/local-mic/{call_sid}")
async def local_mic_stream(websocket: WebSocket, call_sid: str):
    """
    WebSocket endpoint for local microphone testing.
    Allows you to stream audio from your local microphone to the voice service.
    """
    await websocket.accept()
    logger.info(f"Local mic connection established for call: {call_sid}")

    try:
        while True:
            # Receive audio data from local client
            data = await websocket.receive_text()
            message = json.loads(data)

            event_type = message.get("event")

            if event_type == "start":
                logger.info(f"Local mic stream started for call {call_sid}")
                # Mark websocket as local test for TTS handling
                websocket._is_local_test = True
                await voice_service.handle_stream_start(call_sid, f"local-{call_sid}", message, websocket=websocket)

            elif event_type == "media":
                # Audio data from local microphone (already PCM format)
                payload = message.get("payload")
                if payload:
                    await voice_service.handle_media(call_sid, payload, is_mulaw=False)

            elif event_type == "stop":
                logger.info(f"Local mic stream stopped for call {call_sid}")
                await voice_service.handle_stream_stop(call_sid)
                break

    except WebSocketDisconnect:
        logger.info(f"Local mic WebSocket disconnected for call: {call_sid}")
    except Exception as e:
        logger.error(f"Error in local mic WebSocket for call {call_sid}: {e}")
    finally:
        await voice_service.cleanup_call(call_sid)


@router.get("/voice/status")
async def voice_status():
    """Get the status of active voice connections."""
    return {
        "active_connections": len(active_connections),
        "call_sids": list(active_connections.keys()),
        "service_stats": voice_service.get_stats()
    }

