from flask import Blueprint, jsonify, request
import os
import cv2
import numpy as np
import requests
import glob
from datetime import datetime, timezone, timedelta

# Import services
from services.baby_in_crib_detection_service import BabyInCribDetectionService
from services.firebase_helper import get_account_infos_by_id, save_file_to_firestore, data_observer, save_log_to_firestore, send_notification_to_device, save_notification_to_firebase

bicd_bp = Blueprint("baby_in_crib_detection", __name__, url_prefix="/api/baby_in_crib_detection")

image_folder = "media/crib_images/"
os.makedirs(image_folder, exist_ok=True)

video_folder = "media/videos/"
os.makedirs(video_folder, exist_ok=True)

babyInCribDetectionService = BabyInCribDetectionService()

def stop_recording_event(user_id: str):
    try:
        # Import socketio locally to avoid circular import
        from main import handle_stop_recording2
        
        handle_stop_recording2(user_id)
    except Exception as e:
        print(f"Error emitting tests event: {e}")

@bicd_bp.route("/predict", methods=["POST"])
def predict_baby_in_crib_detection():
    try:
        # Lấy dữ liệu JSON từ request
        data = request.get_json()
        if not data:
            return jsonify({"message": "Invalid JSON format"}), 400

        image_url = data.get("image_url")
        system_id = data.get("system_id")

        if not image_url:
            return jsonify({"message": "Missing 'image_url' in request"}), 400

        if not system_id:
            return jsonify({"message": "Missing 'system_id' in request"}), 400

        # Lấy thông tin tài khoản từ system_id
        account_infos = get_account_infos_by_id(system_id)
        if not account_infos:
            return jsonify({"message": "No account found with system_id"}), 400

        # Tải ảnh từ URL
        try:
            response = requests.get(image_url, timeout=10)
            if response.status_code != 200:
                raise ValueError(f"Failed to fetch image. Status code: {response.status_code}")
            image_array = np.frombuffer(response.content, np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Image decoding failed")
        except Exception as e:
            return jsonify({"message": "Failed to fetch or decode image", "error": str(e)}), 400

        # Lưu ảnh tạm thời với tên duy nhất
        temp_image_name = f"{system_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        temp_image_path = os.path.join(image_folder, temp_image_name)
        cv2.imwrite(temp_image_path, image)

        # Upload ảnh lên Firebase
        image_url = save_file_to_firestore(temp_image_path, f"{system_id}_image_crib.jpg")
        if not image_url:
            return jsonify({"message": "Error saving image to Firestore"}), 500
        data_observer(f"data_observer/{system_id}/is_updated_image", True)

        # Gọi dịch vụ dự đoán
        result = babyInCribDetectionService.predict(image)

        video_files = glob.glob(os.path.join(video_folder, f"{system_id}_video_*.mp4"))
        latest_video_file = max(video_files, key=os.path.getctime)  # File mới nhất theo thời gian

        stop_recording_event(system_id)

        video_url = None

        # Lưu kết quả vào Firestore
        timestamp = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000')
        if result["id"] == 0:
            save_log_to_firestore("image_crib", image_url, "Baby is not in crib", system_id, timestamp)
            try:
                if latest_video_file:
                    video_url = save_file_to_firestore(
                        latest_video_file, 
                        f"iot/{system_id}/video_{os.path.basename(latest_video_file)}"
                    )
                else:
                    print(f"No video found for system_id: {system_id}")
                    video_url = None
                if video_url is None:
                    print("Error saving video to Firestore")
                save_log_to_firestore("video_crib", video_url, f"Error {result['message']}", system_id, (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000'))
            except Exception as e:
                print(f"Error saving video to Firestore: {e}")
        elif result["id"] == 1:
            save_log_to_firestore("image_crib", image_url, "Baby is in crib", system_id, timestamp)
        else:
            save_log_to_firestore("image_crib", image_url, f"Error {result['message']}", system_id, timestamp)

        # Gửi thông báo nếu cần
        if result["id"] == 0:
            for account_info in account_infos:
                if account_info.get("enableNotification"):
                    send_notification_to_device(
                        account_info.get("deviceToken"),
                        "Thông báo từ hệ thống",
                        "Trẻ đang không an toàn. Vui lòng kiểm tra."
                    )
                    save_notification_to_firebase("Trẻ đang không an toàn. Vui lòng kiểm tra.", system_id, timestamp, video_url)

        return jsonify(result)

    except Exception as e:
        return jsonify({"message": "An error occurred", "error": str(e)}), 500
