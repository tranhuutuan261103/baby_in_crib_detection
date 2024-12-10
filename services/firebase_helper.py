import os
import firebase_admin
from firebase_admin import credentials, db, messaging, storage

# Get the absolute path of the current file (firebase_helper.py)
current_directory = os.path.dirname(os.path.abspath(__file__))
service_account_path = os.path.join(current_directory, 'serviceAccountKey.json')

# Initialize Firebase
cred = credentials.Certificate(service_account_path)
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://pbl6-519c3-default-rtdb.firebaseio.com/'
})

ref = db.reference('/')

def save_log_to_firestore(type: str, file_name: str, result: str, account_id: str, timestamp: str):
    try:
        # Reference to the `logs` node
        logs_ref = db.reference(f'logs/{account_id}/{type}')
        
        logs_ref.set({
            'file_name': file_name,
            'result': result,
            'timestamp': timestamp
        })
    except Exception as e:
        print(f"Exception: {str(e)}")

def save_notification_to_firebase(message: str, account_id: str, timestamp: str, video_url: str = None):
    try:
        # Reference to the `logs` node
        notifications_ref = db.reference(f'notification/{account_id}')
        
        notifications_ref.push({
            'content': message,
            'createAt': timestamp,
            'videoURL': video_url
        })
    except Exception as e:
        print(f"Exception: {str(e)}")

# Hàm lấy thông tin tài khoản dựa trên code
def get_account_info_by_code(code):
    try:
        # Tham chiếu tới node `account`
        accounts_ref = db.reference('account')
        
        # Lấy tất cả dữ liệu trong `account`
        accounts = accounts_ref.get()

        # Duyệt qua từng tài khoản để tìm `code` khớp
        for account_id, account_info in accounts.items():
            if account_info.get('code') == code:
                return account_info
        
        # Nếu không tìm thấy
        return None
    except Exception as e:
        print(f"Exception: {str(e)}")
        return None
    
def get_account_infos_by_id(account_id):
    try:
        # Reference to the specific account using its ID
        account_ref = db.reference(f'accounts/{account_id}')
        
        # Get data for the specific account
        account_data = account_ref.get()
        
        # Check if account data is found
        if account_data:
            account_data_list = []
            for key, value in account_data.items():
                account_data_list.append(value)
            return account_data_list
        else:
            print("Account not found")
            return None
    except Exception as e:
        print(f"Exception: {str(e)}")
        return None
    
def save_file_to_firestore(file_path: str, file_name: str):
    try:
        # Reference to the storage bucket
        bucket = storage.bucket(
            name="pbl6-519c3.appspot.com",
        )
        
        # Reference to the specific file in the storage bucket
        blob = bucket.blob(file_name)
        
        # Upload the file to the storage bucket
        blob.upload_from_filename(file_path)

        # make the file public
        blob.make_public()
        
        # Get the URL of the uploaded file
        url = blob.public_url
        
        return url
    except Exception as e:
        print(f"Exception: {str(e)}")
        return None
    
def data_observer(url: str, state: bool):
    try:
        # Reference to the `data` node
        data_ref = db.reference(url)

        current_state = data_ref.get()
        
        # Set the data
        data_ref.set(not current_state)
    except Exception as e:
        print(f"Exception: {str(e)}")

# Hàm gửi thông báo FCM
def send_notification_to_device(device_token, title, body):
    # Tạo nội dung thông báo
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        token=device_token
    )

    # Gửi thông báo
    try:
        response = messaging.send(message)
        print('Successfully sent message:', response)
    except Exception as e:
        print('Error sending message:', e)

# Thông tin thông báo và deviceToken
device_token = "ddXgPB0ZSR-mcpS1IGQKmR:APA91bG6Ohoyxu5Y1fCnTHlxjhD6okzZtrSBBSxZ_azF4FLFEQm67tQj5lDrPrqj6HATs15uToBAFNt3d7RXVDBlWQvCsbPE_C9PJHFHmFjxKbQ4L_7QdyE"
title = "Thông báo từ hệ thống"
body = "Đây là thông báo thử nghiệm đến thiết bị của bạn."

# Gửi thông báo
# send_notification_to_device(device_token, title, body)