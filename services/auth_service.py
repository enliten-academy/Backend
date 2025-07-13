from firebase_admin import auth, firestore
import pyotp
from datetime import datetime, timedelta
import re

class AuthService:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.otp_expiry = 300  # 5 minutes
        # Use the existing Firestore client from Firebase Admin
        self.db = firestore.client()

    def validate_phone_number(self, phone_number):
        # Remove any non-digit characters
        clean_number = re.sub(r'\D', '', phone_number)
        
        # Check if it's a valid Indian phone number
        phone_regex = r'^(?:(?:\+|0{0,2})91)?[6789]\d{9}$'
        return bool(re.match(phone_regex, clean_number))

    def generate_otp(self, phone_number):
        if not self.validate_phone_number(phone_number):
            raise ValueError("Invalid phone number format")

        totp = pyotp.TOTP(pyotp.random_base32(), interval=self.otp_expiry)
        otp = totp.now()
        
        # Store OTP in Redis with expiration
        self.redis_client.setex(
            f"otp:{phone_number}",
            self.otp_expiry,
            otp
        )
        return otp

    def verify_otp(self, phone_number, otp):
        stored_otp = self.redis_client.get(f"otp:{phone_number}")
        if not stored_otp or stored_otp.decode() != otp:
            return False
        
        self.redis_client.delete(f"otp:{phone_number}")
        return True

    async def create_or_get_user(self, phone_number=None, email=None, display_name=None):
        try:
            if phone_number:
                user = auth.get_user_by_phone_number(phone_number)
            elif email:
                user = auth.get_user_by_email(email)
        except:
            user_data = {}
            if phone_number:
                user_data['phone_number'] = phone_number
            if email:
                user_data['email'] = email
            if display_name:
                user_data['display_name'] = display_name
                
            user = auth.create_user(**user_data)
        
        return user 

    def create_notification(self, user_id, message, notification_type='info'):
        """Create a new notification for the user"""
        try:
            notifications_ref = self.db.collection('users').document(user_id)\
                                .collection('notifications')
            
            notification_data = {
                'message': message,
                'type': notification_type,
                'timestamp': datetime.now().isoformat(),
                'read': False
            }
            
            notifications_ref.add(notification_data)
            return True
        except Exception as e:
            print("Error creating notification:", str(e))
            return False

    def get_user_notifications(self, user_id, limit=10):
        """Get user's notifications"""
        try:
            notifications_ref = self.db.collection('users').document(user_id)\
                                .collection('notifications')\
                                .order_by('timestamp', direction='desc')\
                                .limit(limit)
                                
            notifications = []
            for doc in notifications_ref.stream():
                notification = doc.to_dict()
                notification['id'] = doc.id
                notifications.append(notification)
                
            return notifications
        except Exception as e:
            print("Error fetching notifications:", str(e))
            return [] 