import os
import threading
import base64
import numpy as np
import cv2
from datetime import datetime
from PIL import Image
from io import BytesIO
from time import time
from flask import Flask, Response, request, send_file
from flask_cors import CORS
from flask_socketio import SocketIO

app = Flask(__name__)
from controllers.baby_in_crib_detection_controller import bicd_bp
app.register_blueprint(bicd_bp)

CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app)

# Video storage folder
video_folder = "media/videos/"
if not os.path.exists(video_folder):
    os.makedirs(video_folder)

# User-specific data
video_writers = {}       # {user_id: VideoWriter}
video_frames = {}        # {user_id: []}
image_frame = {}         # {user_id: Image}
recording_states = {}    # {user_id: bool}
last_time = {}           # {user_id: float (timestamp)}
locks = {}               # {user_id: threading.Lock}

FRAME_INTERVAL = 1 / 30  # 30 FPS

# Helper Functions
def start_video_recording(user_id):
    """Starts video recording for a specific user."""
    global video_writers, recording_states, locks

    # Ensure lock for the user
    if user_id not in locks:
        locks[user_id] = threading.Lock()

    with locks[user_id]:
        recording_states[user_id] = True

        # Tạo tên file video với ID và timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        print(f"Starting video recording for user {user_id}... {timestamp}")
        
        video_filename = os.path.join(video_folder, f"{user_id}_video_{timestamp}.mp4")

        # Initialize VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writers[user_id] = cv2.VideoWriter(video_filename, fourcc, 20.0, (640, 480))

        if not video_writers[user_id].isOpened():
            print(f"Error: Could not open VideoWriter for user {user_id}.")
            recording_states[user_id] = False
            return

        video_frames[user_id] = []
        last_time[user_id] = time()  # Initialize the last frame time
        print(f"Recording started for user {user_id}.")

def save_video(user_id):
    """Saves video for a specific user."""
    global video_writers, locks

    with locks[user_id]:
        if user_id in video_writers and video_writers[user_id]:
            # Đóng VideoWriter hiện tại
            video_writers[user_id].release()
            print(f"Video saved for user {user_id}.")
        else:
            print(f"No video to save for user {user_id}.")
        
        # Chỉ cấp phát lại nếu người dùng vẫn đang ghi hình
        if recording_states.get(user_id, False):
            start_video_recording(user_id)

def reset_video_recording(user_id):
    """Resets recording state for a specific user."""
    global recording_states, video_writers, video_frames, locks

    with locks[user_id]:
        recording_states[user_id] = False
        video_writers.pop(user_id, None)
        video_frames.pop(user_id, None)
        last_time.pop(user_id, None)

def handle_video_data(data, user_id):
    """Processes incoming video data for a specific user."""
    global video_writers, video_frames, last_time, locks, image_frame

    if 'image' not in data or not data['image']:
        print(f"Error: No image data received for user {user_id}.")
        return

    image_data = str(data['image'])

    if image_data.startswith("data:image/jpeg;base64,"):
        image_data = image_data.split(',')[1]

    try:
        img_data = base64.b64decode(image_data)
        image = Image.open(BytesIO(img_data))

        # Lưu hình ảnh mới nhất
        image_frame[user_id] = image
    except Exception as e:
        print(f"Error processing image frame for user {user_id}: {e}")

    try:
        img_data = base64.b64decode(image_data)
        image = Image.open(BytesIO(img_data))
        frame = np.array(image)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        current_time = time()
        with locks[user_id]:
            # Only process the frame if sufficient time has passed
            # if current_time - last_time.get(user_id, 0) >= FRAME_INTERVAL:
            #     last_time[user_id] = current_time

            # Add frame to user's video frames
            if user_id not in video_frames:
                video_frames[user_id] = []
            video_frames[user_id].append(frame)

            # Write frame to video if recording
            if recording_states.get(user_id, False) and user_id in video_writers:
                video_writers[user_id].write(frame)

    except Exception as e:
        print(f"Error processing video frame for user {user_id}: {e}")

# SocketIO event listeners
@socketio.on('start_recording')
def handle_start_recording(data: dict):
    user_id = data.get('user_id', 'unknown')
    print(f"Received start_recording event for user {user_id}.")
    start_video_recording(user_id)

@socketio.on('video')
def handle_video(data):
    user_id = data.get('user_id', 'unknown')
    handle_video_data(data, user_id)

@socketio.on('stop_recording')
def handle_stop_recording(data):
    user_id = data.get('user_id', 'unknown')
    print(f"Received stop_recording event for user {user_id}.")
    save_video(user_id)

def handle_stop_recording2(user_id):
    print(f"Received stop_recording event for user {user_id}.")
    save_video(user_id)

@socketio.on('connect')
def handle_connect():
    print("Client connected")
    socketio.emit('response', {'message': 'Server: Connection established!'})

@app.route('/video_streaming/<user_id>')
def video_streaming(user_id):
    if user_id not in video_frames:
        return Response("User not found", status=404)
    return Response(video_stream(user_id), mimetype='multipart/x-mixed-replace; boundary=frame')

def video_stream(user_id):
    global video_frames, locks

    while True:
        if user_id not in video_frames:
            continue

        with locks[user_id]:
            if len(video_frames[user_id]) == 0:
                continue

            frame = video_frames[user_id].pop(0)
            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/image/<user_id>')
def image_view(user_id):
    """Trả về hình ảnh mới nhất."""
    if user_id not in image_frame:
        return Response("User not found", status=404)
    if image_frame:
        img_io = BytesIO()
        image_frame[user_id].save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    return "No image available", 404

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=5123,debug=True)