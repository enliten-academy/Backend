import random
import string
from datetime import datetime

def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str

def get_user_role(db, user_id):
    user_doc = db.collection('users').document(user_id).get()
    if user_doc.exists:
        return user_doc.to_dict().get("subscription_status", "inactive")
    return "inactive"

def create_user_document(db, uid, user_info):
    user_ref = db.collection('users').document(uid)
    if not user_ref.get().exists:
        user_ref.set({
            'name': user_info.get('name', ''),
            'email': user_info.get('email', ''),
            'phone_number': user_info.get('phone_number', ''),
            'photo_url': user_info.get('picture', ''),
            'total_score': 0,
            'accuracy': 0,
            'rank': 0,
            'assessment_count': 0,
            'subject_analysis': {
                "Tamil": 0,
                "English": 0,
                "History": 0,
                "Polity": 0,
                "Economy": 0,
                "Geography": 0,
                "General Science": 0,
                "Current Affairs": 0,
                "Aptitude & Reasoning": 0
            },
            'register_time': datetime.now().isoformat()
        })
