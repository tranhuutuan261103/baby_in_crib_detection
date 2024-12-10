from flask import Blueprint, jsonify, request
import os
import cv2
import numpy as np
from datetime import datetime, timezone, timedelta

# Import services
from services.baby_in_crib_detection_service import BabyInCribDetectionService
from services.firebase_helper import get_account_infos_by_id, save_file_to_firestore, data_observer, save_log_to_firestore, send_notification_to_device, save_notification_to_firebase

bicd_bp = Blueprint("baby_in_crib_detection", __name__, url_prefix="/api/baby_in_crib_detection")

image_folder = "media/crib_images/"
if not os.path.exists(image_folder):
    os.makedirs(image_folder)

babyInCribDetectionService = BabyInCribDetectionService()

@bicd_bp.route("/predict", methods=["POST"])
def predict_baby_in_crib_detection():
    try:
        if "image" not in request.files:
            return jsonify({"message": "No image part in the request"}), 400
        
        if "system_id" not in request.form:
            return jsonify({"message": "No system_id part in the request"}), 400

        image_file = request.files["image"]
        system_id = request.form["system_id"]

        if image_file.filename == '':
            return jsonify({"message": "No image selected for uploading"}), 400
        
        # Get account info by system_id
        account_infos = get_account_infos_by_id(system_id)
        if len(account_infos) == 0:
            return jsonify({"message": "No account found with system_id"}), 400
        
        # Read and process the image file
        image_bytes = np.frombuffer(image_file.stream.read(), np.uint8)
        image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

        if image is None:
            return jsonify({"message": "Image decoding failed"}), 400
        
        # Save temporary image with unique name
        temp_image_name = f"{system_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        cv2.imwrite(os.path.join(image_folder, temp_image_name), image)

        # Upload image to Firebase
        image_url = save_file_to_firestore(os.path.join(image_folder, temp_image_name), f"{system_id}_image_crib.jpg")
        if image_url is None:
            print("Error saving image to Firestore")
        data_observer(f"data_observer/{system_id}/is_updated_image", True)

        # Predict
        result = babyInCribDetectionService.predict(image)

        if result["id"] == 0:
            save_log_to_firestore("image_crib", image_url, "Baby is not in crib", system_id, (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000'))
        elif result["id"] == 1:
            save_log_to_firestore("image_crib", image_url, "Baby is in crib", system_id, (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000'))
        else:
            save_log_to_firestore("image_crib", image_url, f"Error {result['message']}", system_id, (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000'))

        if result["id"] == 0:
            # Send notification to user
            for account_info in account_infos:
                if account_info["enableNotification"] == True:
                    print("Sending notification to user...")
                    send_notification_to_device(account_info["deviceToken"], "Thông báo từ hệ thống", "Trẻ đang không an toàn. Vui lòng kiểm tra.")
                    save_notification_to_firebase("Trẻ đang không an toàn. Vui lòng kiểm tra.", system_id, (datetime.now(timezone.utc) + timedelta(hours=7)).strftime('%Y-%m-%dT%H:%M:%S.000'))

        return jsonify(result)
    
    except Exception as e:
        return jsonify({"message": "An error occurred", "error": str(e)})