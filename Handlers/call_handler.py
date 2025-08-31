import os
import asyncio
import logging
from dotenv import load_dotenv
from flask import Flask, Response, request

# ---- LIVEKIT IMPORTS ----
from livekit import api
from livekit.agents import WorkerOptions, cli

from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from twilio.rest import Client

# Add the parent directory to the Python path to import agent.py
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import your agent's entrypoint from the agent.py file
from agent import entrypoint

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
LIVEKIT_URL = os.environ["LIVEKIT_URL"]
LIVEKIT_API_KEY = os.environ["LIVEKIT_API_KEY"] 
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]
FORWARDING_NUMBER = os.environ["FORWARDING_NUMBER"]
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
BASE_URL = os.environ["BASE_URL"]  # Your app's public URL

# --- In-memory store for call statuses ---
call_statuses = {}
active_rooms = {}  # Track active rooms

# --- Flask Application ---
app = Flask(__name__)
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# LiveKit API client will be created in async functions as needed


@app.route("/handle-call", methods=['POST'])
def handle_call():
    """
    Entry point for incoming Twilio calls.
    Creates a LiveKit room and connects via Twilio Media Streams.
    """
    call_sid = request.values["CallSid"]
    caller_number = request.values['From']
    print(f"Incoming call from {caller_number} (CallSid: {call_sid})")

    # Create a unique room name for this call
    room_name = f"twilio-call-{call_sid}"
    
    try:
        # Create room in LiveKit
        asyncio.run(create_livekit_room(room_name))
        
        # Store room info
        active_rooms[call_sid] = room_name
        
        # Generate TwiML response to start media stream
        response = VoiceResponse()
        response.say("Hello! Please wait a moment while I connect you to our assistant.")
        
        # Start a media stream to send audio to your WebSocket endpoint
        connect = Connect()
        stream = Stream(
            url=f"{BASE_URL}/media-stream/{call_sid}",
            track="inbound_track"
        )
        connect.append(stream)
        response.append(connect)
        
        print(f"Created room {room_name} and starting media stream for call {call_sid}")
        return Response(str(response), mimetype='text/xml')
        
    except Exception as e:
        print(f"Error handling call {call_sid}: {e}")
        response = VoiceResponse()
        response.say("Sorry, we're experiencing technical difficulties. Please try again later.")
        response.hangup()
        return Response(str(response), mimetype='text/xml')


async def create_livekit_room(room_name: str):
    """
    Create a LiveKit room for the call.
    """
    try:
        # Create LiveKit API client within async context
        livekit_api = api.LiveKitAPI(
            url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
        
        room_info = await livekit_api.room.create_room(
            api.CreateRoomRequest(
                name=room_name,
                empty_timeout=10 * 60,  # 10 minutes
                max_participants=10
            )
        )
        print(f"Created LiveKit room: {room_name}")
        return room_info
    except Exception as e:
        print(f"Error creating room {room_name}: {e}")
        raise


@app.route("/media-stream/<call_sid>", methods=['GET', 'POST'])
def handle_media_stream(call_sid):
    """
    WebSocket endpoint for Twilio Media Streams.
    This is where Twilio will send the audio data.
    """
    if request.method == 'GET':
        # WebSocket upgrade request
        return "WebSocket endpoint for media stream"
    
    # Handle WebSocket messages from Twilio
    # Note: For a full implementation, you'd need to handle WebSocket
    # connections here and bridge them to your LiveKit room
    print(f"Media stream data received for call {call_sid}")
    return Response(status=200)


@app.route("/start-agent", methods=['POST'])
def start_agent():
    """
    Endpoint to manually start an agent for a specific room.
    This can be called after the room is created.
    """
    data = request.get_json()
    room_name = data.get('room_name')
    
    if not room_name:
        return Response("Missing room_name", status=400)
    
    try:
        # Start the agent worker for this room
        worker_options = WorkerOptions(entrypoint_fnc=entrypoint)
        
        # In a production setup, you'd want to run this in a separate process
        # For now, we'll start it in the background
        def run_agent():
            cli.run_app(worker_options)
        
        # Start in background thread (consider using celery or similar for production)
        import threading
        agent_thread = threading.Thread(target=run_agent, daemon=True)
        agent_thread.start()
        
        print(f"Started agent for room: {room_name}")
        return Response("Agent started", status=200)
        
    except Exception as e:
        print(f"Error starting agent for room {room_name}: {e}")
        return Response(f"Error starting agent: {e}", status=500)


@app.route("/report-status", methods=['POST'])
def report_status():
    """
    Webhook for the agent to report its final status before hanging up.
    """
    data = request.get_json()
    call_sid = data.get('call_sid')
    status = data.get('status')
    
    if call_sid and status:
        print(f"Received final status for {call_sid}: {status}")
        call_statuses[call_sid] = status
        return Response(status=200)
        
    return Response("Missing call_sid or status", status=400)


@app.route("/agent-finished", methods=['POST'])
def agent_finished():
    """
    This webhook is called by Twilio when the call stream is finished.
    """
    call_sid = request.values["CallSid"]
    print(f"Call stream finished for {call_sid}. Checking status...")
    
    final_status = call_statuses.get(call_sid, "completed_normally")
    
    response = VoiceResponse()
    
    if final_status == 'escalation_requested':
        print(f"Transferring call {call_sid} to {FORWARDING_NUMBER}")
        response.say("Thank you for your patience. Connecting you now.")
        response.dial(FORWARDING_NUMBER)
    else:
        print(f"Hanging up call {call_sid}.")
        response.say("Thank you for calling. Goodbye!")
        response.hangup()
    
    # Clean up
    if call_sid in call_statuses:
        del call_statuses[call_sid]
    if call_sid in active_rooms:
        room_name = active_rooms[call_sid]
        # Clean up the room
        asyncio.run(cleanup_room(room_name))
        del active_rooms[call_sid]
        
    return Response(str(response), mimetype='text/xml')


async def cleanup_room(room_name: str):
    """Clean up a LiveKit room after the call ends."""
    try:
        # Create LiveKit API client within async context
        livekit_api = api.LiveKitAPI(
            url=LIVEKIT_URL,
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        )
        
        await livekit_api.room.delete_room(
            api.DeleteRoomRequest(room=room_name)
        )
        print(f"Cleaned up room: {room_name}")
    except Exception as e:
        print(f"Error cleaning up room {room_name}: {e}")


@app.route("/health", methods=['GET'])
def health_check():
    """
    Health check endpoint.
    """
    return Response("OK", status=200)


if __name__ == "__main__":
    app.run(port=5000, debug=True)