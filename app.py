import os
import json
import base64
from datetime import timedelta
import pytz
import razorpay

from flask import Flask, jsonify, Response
from flask_cors import CORS
from flask_jwt_extended import JWTManager, get_jwt_identity, jwt_required
from firebase_admin import credentials, firestore
import firebase_admin
from werkzeug.middleware.proxy_fix import ProxyFix
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# --- Local Imports ---
from config import Config
from utils.encryption import Encryption
from utils.admin_encryption import AdminEncryption
from utils.jwt_aes_encrypted_session import JWTAESEncryptedSession
from utils.utils import get_user_role
# from utils.fetch_news import fetch_and_store_news

from services.auth_service import AuthService
from services.memory_store import MemoryStore
from services.superbase_chat import SupabaseChatStorage
from services.OCRDocument import OCRDocument
from services.chat_handler import get_chat_response, generate_title
# news BackgroundScheduler import
# from apscheduler.schedulers.background import BackgroundScheduler

# --- Blueprints ---
from blueprints.auth import auth_bp
from blueprints.user import user_bp
from blueprints.assessment import assessment_bp
from blueprints.chat import chat_bp
from blueprints.ocr import ocr_bp
from blueprints.notifications import notifications_bp
from blueprints.subscription import subscription_bp
from blueprints.quiz import quiz_bp
from blueprints.interview import interview_bp
from blueprints.news import news_bp
from blueprints.admin import admin_bp
from blueprints.test import test_bp

# --- Initialization ---
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# --- Configuration ---
ENVIRONMENT = os.getenv('VERCEL_ENV', 'development')
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "https://enliten.org.in",
    "https://www.enliten.org.in",
]

CORS(app,
     resources={
         r"/*": {
             "origins": ALLOWED_ORIGINS,
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization", "Accept"],
             "supports_credentials": True
         }
     })

app.config.from_object(Config)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)

if os.getenv('VERCEL_ENV') == 'production':
    app.config['SERVER_NAME'] = os.getenv('VERCEL_URL')
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# --- Extensions Initialization ---
jwt = JWTManager(app)
limiter = Limiter(app=app, key_func=lambda: get_jwt_identity())
limiter_ip = Limiter(app=app, key_func=get_remote_address)

# --- Firebase Initialization ---
try:
    if ENVIRONMENT == 'development':
        try:
            cred = credentials.Certificate('firebase-credentials.json')
        except Exception:
            firebase_admin_credentials = os.getenv('FIREBASE_ADMIN_SDK')
            if firebase_admin_credentials:
                cred = credentials.Certificate(json.loads(firebase_admin_credentials))
            else:
                raise ValueError("No Firebase credentials found for development")
    else:
        firebase_admin_credentials = os.getenv('FIREBASE_ADMIN_SDK')
        if not firebase_admin_credentials:
            raise ValueError("FIREBASE_ADMIN_SDK environment variable not set for production")
        cred = credentials.Certificate(json.loads(firebase_admin_credentials))
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    app.db = db
    print("Firebase Admin initialized successfully")
except Exception as e:
    print(f"Firebase initialization error: {str(e)}")
    if ENVIRONMENT != 'development':
        raise

# --- Global Variables & Services ---
public_key_pem = base64.b64decode(os.getenv("RSA_PUBLIC_KEY")).decode("utf-8")
public_key = serialization.load_pem_public_key(public_key_pem.encode(), backend=default_backend())

private_key_pem = base64.b64decode(os.getenv("RSA_PRIVATE_KEY")).decode("utf-8")
private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None, backend=default_backend())

encryption = Encryption(Config.RSA_PUBLIC_KEY, Config.RSA_PRIVATE_KEY)
admin = AdminEncryption()
redis_client = MemoryStore()
auth_service = AuthService(redis_client)
storage = SupabaseChatStorage()
ocr_service = OCRDocument()
users = JWTAESEncryptedSession()
timezone = pytz.timezone('Asia/Kolkata')
razorpay_client = razorpay.Client(auth=("rzp_live_cwrYnZah0Ronpj", "RE7NQ6YCyNVJCSQOvV3moQHm"))

# --- Rate Limiting ---
def dynamic_rate_limit():
    user_id = get_jwt_identity()
    user_role = get_user_role(db, user_id)
    return None if user_role == "active" else "5 per day"

def dynamic_interview_rate_limit():
    user_id = get_jwt_identity()
    user_role = get_user_role(db, user_id)
    return "5 per day" if user_role == "active" else "1 per day"

limiter_interview = Limiter(app=app, key_func=lambda: get_jwt_identity())

# --- Middleware ---
@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none';"
    return response

# --- Error Handlers ---
@app.errorhandler(404)
def handle_404_error(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(422)
def handle_422_error(e):
    print(f"[422 Error] {str(e)}")
    return jsonify({'error': 'Unprocessable entity', 'details': str(e)}), 422

@app.errorhandler(429)
def ratelimit_exceeded(e):
    return jsonify({
        "error": "rate_limit_exceeded",
        "message": "You have reached your request limit. Please upgrade your account for more access."
    }), 429

@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# JWT error handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    print("[JWT] Token expired")
    return jsonify({'error': 'Token has expired'}), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    print(f"[JWT] Invalid token: {error}")
    return jsonify({'error': 'Invalid token'}), 422

@jwt.unauthorized_loader
def missing_token_callback(error):
    print(f"[JWT] Missing token: {error}")
    return jsonify({'error': 'Authorization token is missing'}), 401

# --- Base Routes ---
@app.route("/", methods=['GET'])
def welcome():
	return jsonify({"message": "Hello world! Welcome by Gokul @Enliten Academy"})

@app.route('/ping', methods=['HEAD'])
def ping():
    return Response(status=200)

@app.route("/api/health", methods=['GET'])
def health_check():
	return jsonify({"status": "healthy"})

@app.route("/api/config/public-key", methods=['GET'])
def get_public_key():
    return jsonify({'publicKey': Config.RSA_PUBLIC_KEY})

@app.route('/conversations', methods=['GET'])
@jwt_required()
def return_conversation():
    user_id = get_jwt_identity()
    encrypted_data = users.encrypt_data(json.dumps(storage.get_conversations(user_id)), user_id)
    return jsonify({'data': encrypted_data}), 200

@app.route('/messages/<id>', methods=['GET'])
@jwt_required()
def return_messages(id):
    user_id = get_jwt_identity()
    encrypted_data = users.encrypt_data(json.dumps(storage.get_messages(conversation_id=id, user_id=user_id)), user_id)
    return jsonify({'data': encrypted_data}), 200

# --- Blueprint Registration ---
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(user_bp, url_prefix='/api/user')
app.register_blueprint(assessment_bp, url_prefix='/api/assessment')
app.register_blueprint(chat_bp, url_prefix='/chat')
app.register_blueprint(ocr_bp, url_prefix='/ocr')
app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
app.register_blueprint(subscription_bp, url_prefix='/api/subscription')
app.register_blueprint(quiz_bp, url_prefix='/api/quiz')
app.register_blueprint(interview_bp, url_prefix='/api/interview')
app.register_blueprint(news_bp, url_prefix='/api')
app.register_blueprint(admin_bp, url_prefix='/api/admin')
app.register_blueprint(test_bp, url_prefix='/api/test')

# scheduler to fetch daily news every 1 hr
# scheduler = BackgroundScheduler()
# scheduler.add_job(lambda: fetch_and_store_news(db), "interval", hours=1)
# scheduler.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render provides PORT env var
    app.run(host="0.0.0.0", port=port, debug=True)