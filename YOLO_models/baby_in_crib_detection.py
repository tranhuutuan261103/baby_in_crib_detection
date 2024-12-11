import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Tắt log của TensorFlow (nếu được sử dụng)
from absl import logging
logging.set_verbosity(logging.ERROR)  # Chỉ hiển thị log mức ERROR
from ultralytics import YOLO
import mediapipe as mp

class BabyInCribDetection:
    def __init__(self):
        self.current_path = os.path.dirname(os.path.realpath(__file__))
        self.model = YOLO(os.path.join(self.current_path, "best_models", "last.pt"), verbose=False)

    def detect(self, image) -> int:
        # Khởi tạo MediaPipe Pose
        mp_pose = mp.solutions.pose
        pose = mp_pose.Pose()

        # Xử lý ảnh và lấy kết quả pose
        baby_pose = pose.process(image)

        if baby_pose.pose_landmarks:
            # Lấy tọa độ các điểm quan trọng
            left_shoulder = baby_pose.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = baby_pose.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_hip = baby_pose.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_HIP]
            right_hip = baby_pose.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_HIP]
            
            # Chuyển đổi tọa độ từ hệ tỷ lệ chuẩn sang pixel
            left_shoulder_x = int(left_shoulder.x * image.shape[1])  # Tọa độ x vai trái
            left_shoulder_y = int(left_shoulder.y * image.shape[0])  # Tọa độ y vai trái
            
            right_shoulder_x = int(right_shoulder.x * image.shape[1])  # Tọa độ x vai phải
            right_shoulder_y = int(right_shoulder.y * image.shape[0])  # Tọa độ y vai phải
            
            left_hip_x = int(left_hip.x * image.shape[1])  # Tọa độ x hông trái
            left_hip_y = int(left_hip.y * image.shape[0])  # Tọa độ y hông trái
            
            right_hip_x = int(right_hip.x * image.shape[1])  # Tọa độ x hông phải
            right_hip_y = int(right_hip.y * image.shape[0])  # Tọa độ y hông phải

            results = self.model.predict(source=image, conf=0.3)  # conf là ngưỡng tin cậy

            # Hiển thị bounding box và các thông tin
            for result in results:
                for box in result.boxes:
                    # Kiểm tra lớp (class) của bounding box (lớp của thành nôi có thể là 0)
                    if box.cls == 0:  # Lớp của thành nôi, ví dụ lớp 'crib'
                        # Lấy tọa độ của bounding box (x1, y1) là góc trên bên trái và (x2, y2) là góc dưới bên phải
                        x1, y1, x2, y2 = map(int, box.xyxy[0])  # Tọa độ của bounding box
                        conf = box.conf[0]  # Độ tin cậy của bounding box
                        
                        # Gán tọa độ của bounding box vào các biến tương ứng
                        crib_left_x = x1
                        crib_top_y = y1
                        crib_right_x = x2
                        crib_bottom_y = y2

            is_safe = BabyInCribDetection.check_safety(left_shoulder_x, left_shoulder_y, right_shoulder_x, right_shoulder_y, 
                                left_hip_x, left_hip_y, right_hip_x, right_hip_y, 
                                crib_left_x, crib_top_y, crib_right_x, crib_bottom_y)
            
            if is_safe:
                return 1 # Trẻ an toàn
            else:
                return 0 # Trẻ không an toàn

        else:
            raise Exception("Không xác định được cơ thể trẻ")

    @staticmethod
    # Kiểm tra xem các tọa độ của các điểm cơ thể có nằm trong bounding box của nôi hay không
    def check_safety(left_shoulder_x, left_shoulder_y, right_shoulder_x, right_shoulder_y, 
                    left_hip_x, left_hip_y, right_hip_x, right_hip_y, 
                    crib_left_x, crib_top_y, crib_right_x, crib_bottom_y):
        # Kiểm tra xem các điểm cơ thể có nằm trong bounding box của nôi không
        is_safe = (
            crib_left_x <= left_shoulder_x <= crib_right_x and crib_top_y <= left_shoulder_y <= crib_bottom_y and
            crib_left_x <= right_shoulder_x <= crib_right_x and crib_top_y <= right_shoulder_y <= crib_bottom_y and
            crib_left_x <= left_hip_x <= crib_right_x and crib_top_y <= left_hip_y <= crib_bottom_y and
            crib_left_x <= right_hip_x <= crib_right_x and crib_top_y <= right_hip_y <= crib_bottom_y
        )
        return is_safe