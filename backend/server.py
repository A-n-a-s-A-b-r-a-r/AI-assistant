import os
from livekit import api
from flask import Flask, request
from dotenv import load_dotenv
from flask_cors import CORS
from livekit.api import LiveKitAPI, ListRoomsRequest
import uuid
import multiprocessing
import signal
import sys

# Import your assistant components
from assistant import entrypoint, WorkerOptions
from livekit.agents import cli

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

def run_assistant():
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))

def signal_handler(sig, frame):
    print("\nShutting down gracefully...")
    if 'assistant_process' in globals() and assistant_process.is_alive():
        assistant_process.terminate()
        assistant_process.join()
    sys.exit(0)

async def generate_room_name():
    name = "room-" + str(uuid.uuid4())[:8]
    rooms = await get_rooms()
    while name in rooms:
        name = "room-" + str(uuid.uuid4())[:8]
    return name

async def get_rooms():
    api = LiveKitAPI()
    rooms = await api.room.list_rooms(ListRoomsRequest())
    await api.aclose()
    return [room.name for room in rooms.rooms]

@app.route("/getToken")
async def get_token():
    name = request.args.get("name", "my name")
    room = request.args.get("room", None)
    
    if not room:
        room = await generate_room_name()
        
    token = api.AccessToken(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET")) \
        .with_identity(name)\
        .with_name(name)\
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room
        ))
    
    return token.to_jwt()

if __name__ == "__main__":
    # Set up signal handling in the main thread
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start the assistant in a separate process - NOT as a daemon
    assistant_process = multiprocessing.Process(target=run_assistant)
    assistant_process.daemon = False  # This is critical - do not make it a daemon
    assistant_process.start()
    print(f"✅ Voice Assistant started (PID: {assistant_process.pid})")
    
    # Run the Flask server in the main thread
    print("✅ Web Server starting...")
    try:
        app.run(host="0.0.0.0", port=5001, debug=False)  # Set debug=False to avoid auto-reloading issues
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Make sure we clean up the assistant process
        if assistant_process.is_alive():
            print("Terminating assistant process...")
            assistant_process.terminate()
            assistant_process.join(timeout=5)
            # If it's still alive, force kill it
            if assistant_process.is_alive():
                print("Force killing assistant process...")
                os.kill(assistant_process.pid, signal.SIGKILL)
    

