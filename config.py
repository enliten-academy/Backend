from datetime import timedelta
import os
from dotenv import load_dotenv
import json
import logging
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import base64

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.DEBUG)

# Add Vercel-specific environment handling
ENVIRONMENT = os.getenv('VERCEL_ENV', 'development')
ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Local development
    "https://enliten.org.in",  # Production
    "https://www.enliten.org.in",  # Production with www
    "https://enliten-frontend.vercel.app"  # Vercel deployment
]

class Config:
    # Basic configurations with defaults
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'default-jwt-secret')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    RSA_PRIVATE_KEY = base64.b64decode(os.getenv("RSA_PRIVATE_KEY")).decode("utf-8")
    RSA_PUBLIC_KEY = base64.b64decode(os.getenv("RSA_PUBLIC_KEY")).decode("utf-8")
    
    # Parse Firebase Admin SDK JSON from environment variable
    try:
        FIREBASE_ADMIN_SDK = json.loads(os.getenv('FIREBASE_ADMIN_SDK', '{}'))
        if not FIREBASE_ADMIN_SDK:
            logging.warning("FIREBASE_ADMIN_SDK environment variable is not set")
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing FIREBASE_ADMIN_SDK JSON: {str(e)}")
        FIREBASE_ADMIN_SDK = None
    
    # Frontend Firebase configuration
    FIREBASE_CONFIG = {
        "apiKey": os.getenv('FIREBASE_API_KEY'),
        "authDomain": os.getenv('FIREBASE_AUTH_DOMAIN'),
        "projectId": os.getenv('FIREBASE_PROJECT_ID'),
        "storageBucket": os.getenv('FIREBASE_STORAGE_BUCKET'),
        "messagingSenderId": os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
        "appId": os.getenv('FIREBASE_APP_ID')
    }
    
    # Other configurations with defaults
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')
    OTP_SECRET = os.getenv('OTP_SECRET', 'default-otp-secret')
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI')

    @classmethod
    def validate_config(cls):
        if not cls.FIREBASE_ADMIN_SDK:
            if os.getenv('FLASK_DEBUG') == 'production':
                raise ValueError("FIREBASE_ADMIN_SDK is required in production")
            else:
                logging.warning("Running without Firebase configuration in development mode")
                return

        required_fields = [
            'project_id',
            'private_key_id',
            'private_key',
            'client_email',
            'client_id',
            'client_x509_cert_url'
        ]
        
        missing_fields = [
            field for field in required_fields 
            if not cls.FIREBASE_ADMIN_SDK.get(field)
        ]
        
        if missing_fields:
            error_message = "Missing required Firebase credentials:\n- " + "\n- ".join(missing_fields)
            if os.getenv('FLASK_DEBUG') == 'production':
                raise ValueError(error_message)
            else:
                logging.warning(f"Development mode: {error_message}")

    @classmethod
    def init_firebase(cls):
        if not firebase_admin._apps:
            if ENVIRONMENT == 'production':
                # For Vercel, use environment variable
                firebase_creds = os.getenv('FIREBASE_ADMIN_SDK')
                if not firebase_creds:
                    raise ValueError("FIREBASE_ADMIN_SDK environment variable not set")
                cred = credentials.Certificate(json.loads(firebase_creds))
                firebase_admin.initialize_app(cred)
            else:
                # For local development
                try:
                    cred = credentials.Certificate('firebase-credentials.json')
                    firebase_admin.initialize_app(cred)
                except Exception as e:
                    print(f"Firebase initialization error: {str(e)}")
                    if ENVIRONMENT == 'development':
                        print("Using mock database for development")

    @classmethod
    def get_database(cls):
        """Get database instance with proper error handling"""
        try:
            if not firebase_admin._apps:
                cls.init_firebase()
            return firestore.client()
        except Exception as e:
            if ENVIRONMENT == 'production':
                raise
            print(f"Error getting database: {str(e)}")
            return None

try:
    Config.validate_config()
except Exception as e:
    if os.getenv('FLASK_DEBUG') == 'production':
        logging.error(f"Configuration Error: {str(e)}")
        raise
    else:
        logging.warning(f"Development mode: {str(e)}") 