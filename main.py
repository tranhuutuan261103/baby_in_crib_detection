import os
import threading
import base64
import numpy as np
import cv2
from datetime import datetime, timezone, timedelta
from PIL import Image
from io import BytesIO
from time import time
from flask import Flask, Response, request, send_file
from flask_cors import CORS
from flask_socketio import SocketIO

from services.baby_in_crib_detection_service import BabyInCribDetectionService
from services.firebase_helper import get_account_infos_by_id, save_file_to_firestore, data_observer, save_log_to_firestore, send_notification_to_device, save_notification_to_firebase

babyInCribDetectionService = BabyInCribDetectionService()

app = Flask(__name__)
from controllers.baby_in_crib_detection_controller import bicd_bp
app.register_blueprint(bicd_bp)

CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app)

image_folder = "media/crib_images/"
os.makedirs(image_folder, exist_ok=True)

video_folder = "media/videos/"
os.makedirs(video_folder, exist_ok=True)

# User-specific data
video_writers = {}       # {system_id: VideoWriter}
video_frames = {}        # {system_id: []}
video_frames_cache = {}  # {system_id: []}
video_frames_stream = {} # {system_id: []}
image_frame = {}         # {system_id: Image}
recording_states = {}    # {system_id: bool}
last_time = {}           # {system_id: float (timestamp)}
locks = {}               # {system_id: threading.Lock}

image_folder = "media/crib_images/"
os.makedirs(image_folder, exist_ok=True)

# Helper Functions
def start_video_recording(system_id):
    """Starts video recording for a specific user."""
    global video_writers, recording_states, locks

    # Ensure lock for the user
    if system_id not in locks:
        locks[system_id] = threading.Lock()

    with locks[system_id]:
        recording_states[system_id] = True

        # Tạo tên file video với ID và timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        print(f"Starting video recording for user {system_id}... {timestamp}")
        
        video_filename = os.path.join(video_folder, f"{system_id}_video_{timestamp}.mp4")

        # Initialize VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*'H264')
        video_writers[system_id] = cv2.VideoWriter(video_filename, fourcc, 30.0, (640, 480))

        if not video_writers[system_id].isOpened():
            print(f"Error: Could not open VideoWriter for user {system_id}.")
            recording_states[system_id] = False
            return

        video_frames[system_id] = []
        video_frames_cache[system_id] = []
        last_time[system_id] = time()  # Initialize the last frame time
        print(f"Recording started for user {system_id}.")

def save_video(system_id):
    """Saves video for a specific user."""
    global video_writers, locks

    with locks[system_id]:
        if system_id in video_writers and video_writers[system_id]:
            # Đóng VideoWriter hiện tại
            video_writers[system_id].release()
            print(f"Video saved for user {system_id}.")
        else:
            print(f"No video to save for user {system_id}.")
        
        # Chỉ cấp phát lại nếu người dùng vẫn đang ghi hình
        # if recording_states.get(system_id, False):
        #     start_video_recording(system_id)

def reset_video_recording(system_id):
    """Resets recording state for a specific user."""
    global recording_states, video_writers, video_frames, locks

    with locks[system_id]:
        recording_states[system_id] = False
        video_writers.pop(system_id, None)
        video_frames.pop(system_id, None)
        video_frames_cache.pop(system_id, None)
        last_time.pop(system_id, None)

def handle_video_data(data, system_id):
    """Processes incoming video data for a specific user."""
    global video_writers, video_frames, video_frames_cache, video_frames_stream, last_time, locks, image_frame

    if 'image' not in data or not data['image']:
        print(f"Error: No image data received for user {system_id}.")
        return

    image_data = str(data['image'])

    if image_data.startswith("data:image/jpeg;base64,"):
        image_data = image_data.split(',')[1]

    try:
        img_data = base64.b64decode(image_data)
        image = Image.open(BytesIO(img_data))

        # Lưu hình ảnh mới nhất
        image_frame[system_id] = image
    except Exception as e:
        print(f"Error processing image frame for system {system_id}: {e}")

    try:
        img_data = base64.b64decode(image_data)
        image = Image.open(BytesIO(img_data))
        frame = np.array(image)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        if system_id not in video_frames_stream:
            video_frames_stream[system_id] = []
        video_frames_stream[system_id].append(frame)
        
        with locks[system_id]:
            # Only process the frame if sufficient time has passed
            # if current_time - last_time.get(system_id, 0) >= FRAME_INTERVAL:
            #     last_time[system_id] = current_time

            # Add frame to system's video frames
            if system_id not in video_frames:
                video_frames[system_id] = []
            video_frames[system_id].append(frame)

            if system_id not in video_frames_cache:
                video_frames_cache[system_id] = []
            video_frames_cache[system_id].append(frame)

            # Write frame to video if recording
            if recording_states.get(system_id, False) and system_id in video_writers:
                video_writers[system_id].write(frame)

    except Exception as e:
        print(f"Error processing video frame for system {system_id}: {e}")

def ensure_resources(system_id):
    if system_id not in locks:
        locks[system_id] = threading.Lock()
    if system_id not in video_frames:
        video_frames[system_id] = []
    if system_id not in video_frames_cache:
        video_frames_cache[system_id] = []
    if system_id not in video_frames_stream:
        video_frames_stream[system_id] = []

# SocketIO event listeners
@socketio.on('start_recording')
def handle_start_recording(data: dict):
    system_id = data.get('system_id', 'unknown')
    print(f"Received start_recording event for system {system_id}.")
    ensure_resources(system_id)
    start_video_recording(system_id)

    threading.Thread(target=detection_thread, args=(system_id,), daemon=True).start()

def detection_thread(system_id: str):
    try:
        socketio.sleep(5)
        while True:
            socketio.sleep(1)
            with locks[system_id]:
                if not recording_states.get(system_id, False):
                    return
                try:
                    if len(video_frames_cache[system_id]) == 0:
                        print("0", end="", flush=True)
                        continue
                    else:
                        print(len(video_frames_cache[system_id]))
                except Exception as e:
                    print(f"Error emitting tests event: {e}")
                    continue

                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                print(f"Detection event for system {system_id} {timestamp}.")
                video_filename = os.path.join(video_folder, f"{system_id}_video_{timestamp}.mp4")

                # Initialize VideoWriter
                fourcc = cv2.VideoWriter_fourcc(*'H264')
                video_writer_cache = cv2.VideoWriter(video_filename, fourcc, 30.0, (640, 480))

                if not video_writer_cache.isOpened():
                    print(f"Error: Could not open VideoWriter for system {system_id}.")
                    return
                
                for frame in video_frames_cache[system_id]:
                    video_writer_cache.write(frame)

                video_frames_cache[system_id] = []
                video_writer_cache.release()

                # handle detection
                if image_frame.get(system_id):
                    handle_detection(image_frame[system_id], video_filename, system_id)
    except Exception as e:
        print(f"Error detection thread: {e}")

def handle_detection(image, video_url: str, system_id: str):
    try:
        account_infos = get_account_infos_by_id(system_id)

        if not account_infos:
            logging_error(f"No account found with system_id {system_id}")
            return
        
        if not isinstance(image, np.ndarray):
            image = np.array(image)
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        
        # Lưu ảnh tạm thời với tên duy nhất
        temp_image_name = f"{system_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        temp_image_path = os.path.join(image_folder, temp_image_name)
        if not cv2.imwrite(temp_image_path, image):
            logging_error("Failed to save image to {temp_image_path}")
            return

        image_url = save_file_to_firestore(temp_image_path, f"{system_id}_image_crib.jpg")

        if not image_url:
            logging_error("Error saving image to Firestore")
            return
        
        data_observer(f"data_observer/{system_id}/is_updated_image", True)

        # Gọi dịch vụ dự đoán
        result = babyInCribDetectionService.predict(image)

        socketio.emit('detection_result', {
            'system_id': system_id,
            'result': result
        })

        video_url_saved = None

        # Lưu kết quả vào Firestore
        timestamp = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000')
        if result["id"] == 0:
            save_log_to_firestore("image_crib", image_url, "Baby is not in crib", system_id, timestamp)

            try:
                video_url_saved = save_file_to_firestore(
                        video_url, 
                        f"iot/{system_id}/video_{os.path.basename(video_url)}"
                    )
                save_log_to_firestore("video_crib", video_url_saved, f"Error {result['message']}", system_id, (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000'))
            except Exception as e:
                logging_error(f"Error saving video to Firestore: {e}")

        elif result["id"] == 1:
            save_log_to_firestore("image_crib", image_url, "Baby is in crib", system_id, timestamp)
        else:
            save_log_to_firestore("image_crib", image_url, f"Error {result['message']}", system_id, timestamp)

        if result["id"] == 0:
            for account_info in account_infos:
                if account_info.get("enableNotification"):
                    send_notification_to_device(
                        account_info.get("deviceToken"),
                        "Thông báo từ hệ thống",
                        "Trẻ đang không an toàn. Vui lòng kiểm tra."
                    )
                    save_notification_to_firebase("Trẻ đang không an toàn. Vui lòng kiểm tra.", system_id, timestamp, video_url_saved)

    except Exception as e:
        logging_error(f"Error handling detection: {e}")

def logging_error(message: str):
    socketio.emit('error', {
        'message': message
    })
    print(f"Error: {message}")

@socketio.on('video')
def handle_video(data: dict):
    system_id = data.get('system_id', 'unknown')
    handle_video_data(data, system_id)

@socketio.on('stop_recording')
def handle_disconnect():
    system_id = request.args.get('system_id', 'unknown')
    print(f"Client with system_id {system_id} disconnected.")
    
    # Cleanup resources
    with locks.get(system_id, threading.Lock()):
        reset_video_recording(system_id)
        locks.pop(system_id, None)
        video_frames.pop(system_id, None)
        video_frames_cache.pop(system_id, None)
        video_frames_stream.pop(system_id, None)
        image_frame.pop(system_id, None)
        recording_states.pop(system_id, None)

@socketio.on('connect')
def handle_connect():
    print("Client connected")
    socketio.emit('response', {'message': 'Server: Connection established!'})

@app.route('/video_streaming/<system_id>')
def video_streaming(system_id):
    if system_id not in video_frames_stream:
        return Response("User not found", status=404)
    return Response(video_stream(system_id), mimetype='multipart/x-mixed-replace; boundary=frame')

def video_stream(system_id):
    global video_frames_stream, locks

    while True:
        if system_id not in video_frames_stream:
            continue

        if len(video_frames_stream[system_id]) == 0:
            continue

        frame = video_frames_stream[system_id].pop(0)
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/image/<system_id>')
def image_view(system_id):
    """Trả về hình ảnh mới nhất."""
    if system_id not in image_frame:
        return Response("User not found", status=404)
    if image_frame:
        img_io = BytesIO()
        image_frame[system_id].save(img_io, 'JPEG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/jpeg')
    return "No image available", 404

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=5123,debug=True)