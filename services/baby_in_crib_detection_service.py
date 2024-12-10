from YOLO_models.baby_in_crib_detection import BabyInCribDetection

class BabyInCribDetectionService:
    def __init__(self):
        self.model = BabyInCribDetection()

    def predict(self, image) -> dict:
        try:
            result = self.model.detect(image)
            if result == 1:
                return {
                    "id": 1,
                    "message": "Baby is in crib",
                    "message_vn": "Trẻ đang an toàn"
                }
            else:
                return {
                    "id": 0,
                    "message": "Baby is not in crib",
                    "message_vn": "Trẻ không an toàn"
                }
        except Exception as e:
            return {
                "id": -1,
                "message": str(e),
            }