import requests
from datetime import datetime
from firebase_admin import firestore

class InterviewService:
    def __init__(self):
        self.api_url = "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"
        self.api_key = "sk_8498e709110a6917293ba34bd2277beed6a74febbb3e6f65"
        self.agent_id = "agent_01jz7k73ywe69trm2ek80shae4"
        self.agent_phone_number_id = "phnum_01jz7qnkfqfe1rb854gbdhns4r"

    def schedule_interview(self, user_id, phone_number, username=None, description=None, db=None, timezone=None):
        """
        Schedule an interview call via ElevenLabs API
        
        Args:
            user_id: User ID from JWT
            phone_number: Phone number to call
            username: Optional username
            description: Optional description
            db: Firestore database instance
            timezone: Timezone for timestamp
            
        Returns:
            dict: Success status and response data or error
        """
        try:
            # Make API call to ElevenLabs
            response = requests.post(
                self.api_url,
                headers={
                    "xi-api-key": self.api_key
                },
                json={
                    "agent_id": self.agent_id,
                    "agent_phone_number_id": self.agent_phone_number_id,
                    "to_number": phone_number
                },
            )

            res_json = response.json()
            
            # Update user's interview history in Firestore
            if db:
                db.collection('users').document(user_id).update({
                    "interviews": firestore.ArrayUnion([
                        {
                            "created_at": datetime.now(timezone).isoformat() if timezone else datetime.now().isoformat(),
                            "id": res_json.get("conversation_id", "unknown"),
                            "status": "success" if res_json.get("success", False) else "failed",
                            "phone_number": phone_number,
                            "username": username
                        }
                    ])
                })

            return {
                'success': True,
                'data': res_json
            }

        except Exception as e:
            print(f"[InterviewService] Error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
