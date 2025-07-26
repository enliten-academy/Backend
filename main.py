from flask import Flask, jsonify, request,Response
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from firebase_admin import credentials, firestore, initialize_app, auth as firebase_auth
import firebase_admin
from utils.encryption import Encryption
from config import Config
import json
import pyotp
import requests
from datetime import datetime, timedelta
from services.auth_service import AuthService
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import secrets
from urllib.parse import urlencode,unquote
from services.memory_store import MemoryStore
import os
#from classifier import classification
from werkzeug.middleware.proxy_fix import ProxyFix
from chat_handler import get_chat_response,generate_title
import base64
from jwt_aes_encrypted_session import JWTAESEncryptedSession
from news import CurrentAffairsSearch
import razorpay
import random
import string
from threading import Thread
from time import sleep
import pytz
from smart_news import smart_search,get_news
from utils.admin_encryption import AdminEncryption
from utils.quotes import get_quote

from messages.superbase_chat import SupabaseChatStorage
storage = SupabaseChatStorage()
timezone = pytz.timezone('Asia/Kolkata')
admin = AdminEncryption()
def get_random_string(length):
    # choose from all lowercase letter
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    return result_str
    # print("Random string of length", length, "is:", result_str)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
#razorpay_client = razorpay.Client(auth=("rzp_test_NcyggQ0AwIBtfW", "wAJj9aDmgXuyIdBgEAJdj4C5"))
razorpay_client = razorpay.Client(auth=("rzp_live_cwrYnZah0Ronpj", "RE7NQ6YCyNVJCSQOvV3moQHm"))


# Get environment-specific settings
ENVIRONMENT = os.getenv('VERCEL_ENV', 'development')
ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Local development
    "https://enliten.org.in",  # Production
    "https://www.enliten.org.in",  # Production with www
]

# Configure CORS
CORS(app, 
     resources={
         r"/*": {
             "origins": ALLOWED_ORIGINS,
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "allow_headers": ["Content-Type", "Authorization", "Accept"],
             "supports_credentials": True
         }
     })

# Initialize configurations
app.config.from_object(Config)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=24)  # Set JWT token expiry to 15 minutes
jwt = JWTManager(app)
users = JWTAESEncryptedSession()

# Initialize Firebase Admin based on environment
try:
    if ENVIRONMENT == 'development':
        # For local development, use service account file if it exists
        try:
            cred = credentials.Certificate('firebase-credentials.json')
        except Exception:
            # Fallback to environment variable
            firebase_admin_credentials = os.getenv('FIREBASE_ADMIN_SDK')
            if firebase_admin_credentials:
                cred = credentials.Certificate(json.loads(firebase_admin_credentials))
            else:
                raise ValueError("No Firebase credentials found")
    else:
        # For production, use environment variable
        firebase_admin_credentials = os.getenv('FIREBASE_ADMIN_SDK')
        if not firebase_admin_credentials:
            raise ValueError("FIREBASE_ADMIN_SDK environment variable not set")
        cred = credentials.Certificate(json.loads(firebase_admin_credentials))
    
    # Initialize Firebase
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin initialized successfully")
except Exception as e:
    print(f"Firebase initialization error: {str(e)}")
    if ENVIRONMENT == 'development':
        print("Using mock database for development")
        # You could implement mock database here for local testing
    else:
        raise

# Initialize encryption
encryption = Encryption(Config.RSA_PUBLIC_KEY, Config.RSA_PRIVATE_KEY)

# Replace Redis client with Memory Store
redis_client = MemoryStore()

# Initialize auth service with memory store
auth_service = AuthService(redis_client)

limiter_ip = Limiter(
    app=app,
    key_func=get_remote_address,
    # default_limits=["200 per day", "50 per hour"]
)


# Function to get user role from Firestore
def get_user_role(user_id):
    user_doc = db.collection('users').document(user_id).get()
    if user_doc.exists:
        return user_doc.to_dict().get("subscription_status", "inactive")  # Default to "free"
    return "inactive"

# Custom rate limit per user role
def dynamic_rate_limit():
    user_id = get_jwt_identity()
    user_role = get_user_role(user_id)
    return None if user_role == "active" else "5 per day"  # No limit for premium users
limiter = Limiter(app=app, key_func=lambda: get_jwt_identity())

def dynamic_interview_rate_limit():
    user_id = get_jwt_identity()
    user_role = get_user_role(user_id)
    return "5 per day" if user_role == "active" else "1 per day"  # No limit for premium users
limiter_interview = Limiter(app=app, key_func=lambda: get_jwt_identity())
# limiter = Limiter(
#     get_remote_address,  # Uses client IP to track limits
#     app=app,
#     strategy="fixed-window",  # Uses a fixed window approach
#     storage_uri="memory://"  # No external storage
# )


# Add after CORS configuration
if os.getenv('VERCEL_ENV') == 'production':
    # Configure for production
    app.config['SERVER_NAME'] = os.getenv('VERCEL_URL')
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# Middleware to add security headers
@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none';"
    return response
@app.route("/", methods=['GET'])
def welcome():
	return jsonify({"message": "Hello world! Welcome by Gokul @Enliten Academy"})

@app.route('/ping', methods=['HEAD'])
def ping():
    # No body needed for HEAD response
    return Response(status=200)
@app.route("/protected", methods=["GET"])
@jwt_required()
@limiter.limit(dynamic_rate_limit)  # Apply dynamic rate limit
def protected():
    return jsonify({"message": "Welcome to the protected route!"})

@app.route("/api/health", methods=['GET'])
def health_check():
	return jsonify({"status": "healthy"})

@app.route("/api/auth/login/admin", methods=['POST'])
@limiter_ip.limit("4 per minute")
def admin_login():
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'failed': 'Username and password required'}), 401

        auth = admin.login(username, password)
        if auth:
            return jsonify({'success': auth}), 200
        else:
            return jsonify({'failed': 'Invalid login credentials'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route("/api/auth/login", methods=['POST'])
def login():
    try:
        encrypted_data = request.json
        aes_key = encryption.decrypt_aes_key(encrypted_data['encrypted_aes_key'])
        decrypted_data = encryption.decrypt_data(encrypted_data['data'], aes_key)
        user_data = json.loads(decrypted_data)
        
        # Verify user credentials here
        # ... authentication logic ...
        
        access_token = create_access_token(identity=user_data['uid'])
        users.add_user(user_data["uid"],int((datetime.now() + app.config["JWT_ACCESS_TOKEN_EXPIRES"]).timestamp()))
        
        # Encrypt response
        response_aes_key = encryption.generate_aes_key()
        encrypted_response = encryption.encrypt_data(
            json.dumps({'token': access_token}),
            response_aes_key
        )
        
        return jsonify({
            'encrypted_aes_key': encryption.encrypt_aes_key(response_aes_key),
            'data': encrypted_response
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# @app.route("/api/user/key", methods=['GET'])
@app.route("/api/user/ads", methods=['GET'])
@jwt_required()
def get_key():
    user_id = get_jwt_identity()
    if not user_id:
        # return jsonify({'error': 'No user ID found'}), 401
        return jsonify({'error': 'No Access'}), 401
    aes_key=users.get_aes_key(user_id)
    if aes_key['status']=='error':
        return jsonify({'error': 'Session expired or Invalid'}), 401
    else:
        aes_key["ads_key"] = aes_key.pop("aes_key")
        return jsonify(aes_key),200

@app.route("/api/user/data", methods=['GET'])
@jwt_required()
def get_user_data():
    #try:
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'No user ID found'}), 401

    # Get user data from Firestore
    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        # If user document doesn't exist, create default data
        default_data = {
            'name': '',
            'quote': '',
            'email': '',
            'photo_url': '',  # Make sure this is a full URL if possible
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
            }
        }
        user_ref.set(default_data)
        return jsonify(default_data)

    user_data = user_doc.to_dict()
    
    # Ensure photo_url is a full URL if it exists
    if user_data.get('photo_url'):
        if not user_data['photo_url'].startswith(('http://', 'https://')):
            user_data['photo_url'] = f"{request.url_root.rstrip('/')}{user_data['photo_url']}"
    try:
        date = datetime.now(timezone).strftime("%d%m%Y")
        quote_ref = db.collection('quotes').document(date)
        quote_doc = quote_ref.get()
        
        if not quote_doc.exists:
            quote={'quote': 'No quotes available for this date'}
        else:
            # Get the quotes data from the document
            quote = quote_doc.to_dict().get('quote', {'quote': 'No quotes available for this date'})
    except Exception as e:
        print(f"Error fetching quotes: {str(e)}")
        quote = {'quote': 'No quotes available for this date'}
    # user_data['quote']=get_quote();
    user_data['quote']=quote
    # Encrypt response
    encrypted_response = users.encrypt_data(json.dumps(user_data),user_id)
    if(encrypted_response['status']=='error'):
        response_code=401
    else:
        response_code=200
    response = Response(
        response=json.dumps({'data':encrypted_response}),
        status=response_code,
        mimetype="application/json"
    )
    return response



    #except Exception as e:
        # print(f"Error fetching user data: {str(e)}")
        # return jsonify({'error': str(e)}), 500

@app.route("/api/assessment/user", methods=['GET'])
@jwt_required()
def get_user_assessments():
    try:
        user_id = get_jwt_identity()
        print(f"User ID: {user_id}")
        assessments_ref = db.collection('assessments')
        query = assessments_ref.where('user_id', '==', user_id).stream()
        
        assessments = [doc.to_dict() for doc in query]
        if not assessments:
            encrypted_response = users.encrypt_data(json.dumps({'error': 'No assessments found for this user'}),user_id)
            return json.dumps({'data':encrypted_response}), 404
        encrypted_response = users.encrypt_data(json.dumps({'assessments': assessments}),user_id)
        return json.dumps({'data':encrypted_response})
    except Exception as e:
        print(f"Error fetching user assessments: {str(e)}")
        encrypted_response = users.encrypt_data(json.dumps({'error': str(e)}),user_id)
        return json.dumps({'data':encrypted_response}), 500

@app.route("/api/assessment/submit", methods=['POST'])
@jwt_required()
def submit_assessment():
    try:
        user_id = get_jwt_identity()
        encrypted_data = request.json
        
        aes_key = encryption.decrypt_aes_key(encrypted_data['encrypted_aes_key'])
        decrypted_data = encryption.decrypt_data(encrypted_data['data'], aes_key)
        assessment_data = json.loads(decrypted_data)
        
        # Process and store assessment data
        # ... assessment processing logic ...
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route("/api/auth/request-otp", methods=['POST'])
@limiter.limit("5 per hour")
def request_otp():
    try:
        encrypted_data = request.json
        aes_key = encryption.decrypt_aes_key(encrypted_data['encrypted_aes_key'])
        decrypted_data = encryption.decrypt_data(encrypted_data['data'], aes_key)
        user_data = json.loads(decrypted_data)
        
        phone_number = user_data['phoneNumber']
        
        try:
            otp = auth_service.generate_otp(phone_number)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        
        # TODO: Implement SMS service to send OTP
        # send_sms(phone_number, otp)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route("/api/auth/verify-otp", methods=['POST'])
def verify_otp():
    try:
        encrypted_data = request.json
        aes_key = encryption.decrypt_aes_key(encrypted_data['encrypted_aes_key'])
        decrypted_data = encryption.decrypt_data(encrypted_data['data'], aes_key)
        user_data = json.loads(decrypted_data)
        
        phone_number = user_data['phoneNumber']
        otp = user_data['otp']
        
        # Verify OTP
        stored_otp = redis_client.get(f"otp:{phone_number}")
        if not stored_otp or stored_otp.decode() != otp:
            return jsonify({'error': 'Invalid OTP'}), 400
            
        # Create or get Firebase user
        try:
            user = firebase_auth.get_user_by_phone_number(phone_number)
        except:
            user = firebase_auth.create_user(
                phone_number=phone_number
            )
        
        # Create custom token
        token = create_access_token(identity=user.uid)
        users.add_user(user.uid,int((datetime.now() + app.config["JWT_ACCESS_TOKEN_EXPIRES"]).timestamp()))
        
        # Create user document if not exists
        create_user_document(user.uid, user_info)
        
        return jsonify({'token': token})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route("/api/auth/google-signin-url")
def google_signin_url():
    try:
        state = secrets.token_urlsafe(32)
        redis_client.setex(f"google_oauth_state:{state}", 300, "1")
        
        params = {
            'client_id': Config.GOOGLE_CLIENT_ID,
            'response_type': 'code',
            'scope': 'openid email profile',
            'redirect_uri': Config.GOOGLE_REDIRECT_URI,
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        print("Generated URL:", url)
        return jsonify({'url': url})
    except Exception as e:
        print("Error generating URL:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route("/api/auth/google-signin-callback", methods=['POST'])
def google_signin_callback():
    try:
        code = request.json.get('code')
        if not code:
            return jsonify({'error': 'No authorization code provided'}), 400

        print("Received code:", code)  # Debug log

        # Exchange code for tokens
        token_url = 'https://oauth2.googleapis.com/token'
        token_data = {
            'code': code,
            'client_id': Config.GOOGLE_CLIENT_ID,
            'client_secret': Config.GOOGLE_CLIENT_SECRET,
            'redirect_uri': Config.GOOGLE_REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        
        token_response = requests.post(
            token_url,
            data=token_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            }
        )
        
        if token_response.status_code != 200:
            error_details = token_response.json()
            print("Token Error Details:", error_details)
            return jsonify({
                'error': 'Failed to exchange code for tokens',
                'details': error_details
            }), 400
            
        tokens = token_response.json()
        
        # Get user info from Google
        userinfo_response = requests.get('https://www.googleapis.com/oauth2/v3/userinfo',
                                       headers={'Authorization': f'Bearer {tokens["access_token"]}'})
        if not userinfo_response.ok:
            raise Exception('Failed to get user info from Google')
            
        google_data = userinfo_response.json()
        
        # Try to find existing user by email
        users_ref = db.collection('users')
        existing_users = users_ref.where('email', '==', google_data.get('email')).limit(1).get()
        
        if len(existing_users) > 0:
            # User exists, update their data
            user_doc = existing_users[0]
            user_id = user_doc.id
            user_ref = users_ref.document(user_id)
            user_ref.update({
                'name': google_data.get('name', ''),
                'email': google_data.get('email', ''),
                'photo_url': google_data.get('picture', '')
            })
        else:
            # Create new user
            user_data = {
                'name': google_data.get('name', ''),
                'email': google_data.get('email', ''),
                'photo_url': google_data.get('picture', ''),
                'phone_number': '',
                'total_score': 0,
                'accuracy': 0,
                'rank': 0,
                'assessment_count': 0,
                'register_time': datetime.now().isoformat(),
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
                }
            }
            
            # Add new user to Firestore
            new_user_ref = users_ref.add(user_data)
            user_id = new_user_ref[1].id
        
        # Create JWT token
        token = create_access_token(identity=user_id)
        print(f"Token: {token}")
        users.add_user(user_id,int((datetime.now() + app.config["JWT_ACCESS_TOKEN_EXPIRES"]).timestamp()))
        
        # return jsonify({
        #     'token': token,
        #     'user': {
        #         'id': user_id,
        #         'name': google_data.get('name'),
        #         'email': google_data.get('email'),
        #         'photo_url': google_data.get('picture')
        #     }
        # })
        response=users.encrypt_data(json.dumps({
            'token': token,
            'user': {
                'id': user_id,
                'name': google_data.get('name'),
                'email': google_data.get('email'),
                'photo_url': google_data.get('picture')
            }
        }),user_id)
        return json.dumps({'data':response,'ads_id':token})
        
    except Exception as e:
        print("Error in callback:", str(e))
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

@app.route("/api/config/public-key", methods=['GET'])
def get_public_key():
    return jsonify({
        'publicKey': Config.RSA_PUBLIC_KEY
    })

def create_user_document(uid, user_info):
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

@app.errorhandler(500)
def handle_500_error(e):
    response = jsonify({'error': 'Internal server error'})
    response.headers.add('Access-Control-Allow-Origin', 
        request.headers.get('Origin', '*'))
    return response, 500

# Custom error handler for 429
@app.errorhandler(429)
def ratelimit_exceeded(e):
    return jsonify({
        "error": "rate_limit_exceeded",
        "message": "You have reached the daily request limit. Please upgrade your account for unlimited access."
    }), 429

@app.errorhandler(404)
def handle_404_error(e):
    response = jsonify({'error': 'Not found'})
    response.headers.add('Access-Control-Allow-Origin', 
        request.headers.get('Origin', '*'))
    return response, 404

@app.route("/api/user/create", methods=['POST'])
@jwt_required()
def create_user():
    try:
        user_id = get_jwt_identity()
        user_data = request.json
        email = user_data.get("email")

        if not email:
            return jsonify({'message': 'Email is required'}), 400

        # Check if user document already exists
        user_ref = db.collection('users').document(user_id)
        if user_ref.get().exists:
            return jsonify({'message': 'User document already exists'}), 200

        # Check if email exists in any collection
        collections = db.collections()
        for collection in collections:
            docs = collection.stream()
            for doc in docs:
                if 'email' in doc.to_dict() and doc.to_dict()['email'] == email:
                    print(f"Email already exists in collection: {collection.id}")
                    return jsonify({'message': 'Email already exists in the system'}), 400

        # If email does not exist, create a new user document
            
        # Initialize subject analysis data
        subjects = {
            "Tamil": 0,
            "English": 0,
            "History": 0,
            "Polity": 0,
            "Economy": 0,
            "Geography": 0,
            "General Science": 0,
            "Current Affairs": 0,
            "Aptitude & Reasoning": 0
        }
        
        # Create user document
        user_data = {
            'name': user_data.get('name', ''),
            'email': user_data.get('email', ''),
            'phone_number': user_data.get('phone_number', ''),
            'photo_url': user_data.get('photo_url', ''),
            'total_score': 0,
            'accuracy': 0,
            'rank': 0,
            'assessment_count': 0,
            'subject_analysis': subjects,
            'register_time': datetime.now().isoformat()
        }
        
        user_ref.set(user_data)
        return jsonify({'message': 'User document created successfully'}), 201
        
    except Exception as e:
        print("Error creating user:", str(e))
        return jsonify({'error': str(e)}), 400

@app.route("/api/user/profile", methods=['GET'])
@jwt_required()
def get_user_profile():
    try:
        user_id = get_jwt_identity()
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({'error': 'User not found'}), 404
            
        user_data = user_doc.to_dict()
        user_data['uid'] = user_id
        
        return jsonify(user_data)
    except Exception as e:
        print("Error fetching user profile:", str(e))
        return jsonify({'error': str(e)}), 400

@app.route("/api/auth/google-signin", methods=['GET'])
def google_signin():
    try:
        # Generate state token for security
        state = secrets.token_urlsafe(32)
        redis_client.setex(f"google_oauth_state:{state}", 300, "1")
        
        # Build Google OAuth URL
        params = {
            'client_id': Config.GOOGLE_CLIENT_ID,
            'response_type': 'code',
            'scope': 'openid email profile',
            'redirect_uri': Config.GOOGLE_REDIRECT_URI,
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return jsonify({'url': auth_url})
    except Exception as e:
        print("Error generating Google sign-in URL:", str(e))
        return jsonify({'error': str(e)}), 500

@app.route("/api/notifications", methods=['GET'])
@jwt_required()
def get_notifications():
    try:
        user_id = get_jwt_identity()
        
        # Get notifications from Firestore
        notifications_ref = db.collection('users').document(user_id)\
                            .collection('notifications')\
                            .order_by('timestamp', direction='desc')\
                            .limit(10)
                            
        notifications = []
        for doc in notifications_ref.stream():
            notification = doc.to_dict()
            notification['id'] = doc.id
            notifications.append(notification)
            
        return jsonify(notifications)
    except Exception as e:
        print("Error fetching notifications:", str(e))
        return jsonify({'error': str(e)}), 400

# @app.route('/api/query/<q>')
# def query(q):
#     q = unquote(q)
#     classified = classification(q)
#     label = classified['label']
#     print(f"Query: {q}")
#     if(label == "normal chat"):
#         return {'label': label, 'response': classified['response']}
#     else:
#         print(f"Processed Query: {classified['response']}")
#         result_count = classified.get('result_count', 6)
#         return {
#             'label': label,
#             'response': classified['response']
#         }

@app.route('/chat', methods=['POST'])
@jwt_required()
@limiter.limit(dynamic_rate_limit)
def chat():
    user_id = get_jwt_identity()
    data = request.json
    user_message = data.get("message")
    is_quiz_mode = data.get("isQuizMode", False)
    is_heuristic_mode = data.get("isHeuristicMode", False)
    conversation_id = data.get("conversation_id", False)  # <- FIX: use consistent variable name
    language = data.get("lang", False)  # <- FIX: use consistent variable name

    print(f"Quiz mode: {is_quiz_mode}")
    print(f"User message: {user_message}")

    if not user_message:
        return jsonify({"error": "Missing message"}), 400

    if not conversation_id:
        conversation_id = storage.create_conversation(user_id, generate_title(user_message))

    # Get chat response
    response = get_chat_response(user_id, user_message, is_quiz_mode, is_heuristic_mode, language)

    # Store user message
    storage.add_message(conversation_id, data, "user", user_id)

    # Store AI response
    storage.add_message(conversation_id, response, "ai", user_id, tokens=12)

    response["conversation_id"] = conversation_id
    print(f"Response: {response}")
    return jsonify(response)

@app.route('/conversations',methods=['GET'])
@jwt_required()
def return_conversation():
    user_id=get_jwt_identity()
    encrypted_data=users.encrypt_data(json.dumps(storage.get_conversations(user_id)),user_id)
    return jsonify({'data':encrypted_data}), 200

@app.route('/messages/<id>',methods=['GET'])
@jwt_required()
def return_messages(id):
    user_id=get_jwt_identity()
    encrypted_data=users.encrypt_data(json.dumps(storage.get_messages(conversation_id=id,user_id=user_id)),user_id)
    return jsonify({'data':encrypted_data}), 200


@app.route("/api/auth/logout", methods=['POST'])
@jwt_required()
def logout():
    try:
        # Clear any server-side session data if needed
        user_id = get_jwt_identity()
        users.remove_user(user_id)
        # You might want to invalidate the JWT token here
        # For now, we'll just return success since the frontend
        # will remove the token from localStorage
        
        return jsonify({'message': 'Logged out successfully'})
    except Exception as e:
        print("Error during logout:", str(e))
        return jsonify({'error': str(e)}), 400
@app.route("/api/auth/session",methods=['GET'])
@jwt_required()
def auth_session():
    try:
        user_id=get_jwt_identity()
        user=users.get_user(user_id)
        if(user):
            return jsonify({'status': 'valid'}), 200
        else:
            return jsonify({'status': 'invalid'}), 404
    except Exception as e:
        print("Error during auth session:", str(e))
        return jsonify({'error': str(e)}), 400
@app.route("/api/hook/news1", methods=['GET'])
def news_hook1():
    def th():
        # try:
        date = datetime.now(timezone).strftime("%d%m%Y")
        search = CurrentAffairsSearch("AIzaSyBQgUq_pscmRRw36Y7HKt3dvDTgKTQvUA4")
        news_data = search.get_current_affairs()
        with open(f'database/news/{date}.json', 'w') as file:
            json.dump(news_data, file, indent=2)
        print("News update Success !!")
        # except:
        #     print("News update failed !!")
    def test():
        sleep(10)
        print("Completed")
    # thread = Thread(target=th)
    # thread.start()
    th()
    return jsonify({'message': 'News hook received'}), 200

@app.route("/api/hook/quote", methods=['GET'])
def quote_hook():
    try:
        date = datetime.now(timezone).strftime("%d%m%Y")
        quote = get_quote()
        
        # Store in Firestore
        quote_ref = db.collection('quotes').document(date)
        quote_ref.set({
            'quote': quote["quote"]
        })
        
        return jsonify({'message': "Quote update Success !!"}), 200
    except Exception as e:
        return jsonify({'message': "Quote update failed !!\nError: "+ str(e)}), 500


@app.route("/api/hook/news", methods=['GET'])
def news_hook():
    def th():
        try:
            date = datetime.now(timezone).strftime("%d%m%Y")
            search = CurrentAffairsSearch("AIzaSyBQgUq_pscmRRw36Y7HKt3dvDTgKTQvUA4")
            news_data = search.get_current_affairs()
            
            # Store in Firestore
            news_ref = db.collection('news').document(date)
            news_ref.set({
                'date': date,
                'news_data': news_data,
                'last_updated': datetime.now().isoformat()
            })
            
            print("News update Success !!")
        except Exception as e:
            print("News update failed !!", str(e))
    
    def test():
        sleep(10)
        print("Completed")
    
    th()
    return jsonify({'message': 'News hook received'}), 200

@app.route("/api/news1/ai/<date>",methods=['POST'])
@jwt_required()
def news_ai1(date):
    try:
        user_id=get_jwt_identity()
        if not user_id:
            return jsonify({'error':'No user ID found'}), 401
        data = request.json
        query = data.get("query")
        isQuizMode=data.get("isQuizMode",False)
        if(isQuizMode):
            with open(f'database/news/{date}.json', 'r') as file:
                news_data = json.load(file)
                # Encrypt the data using the user's AES key
                data = json.dumps(news_data)
            print(news_data)
            user_message=f"Today news i given, I will attach toadys news for creating quiz but if user ask to genearte any other date quiz just refuse it and mention change the date setting on top and ask to generate quiz Here is the query:\n\n{query} \n\nTodays news:\n{news_data}"
            response = get_chat_response(user_id, user_message, True, False)
            return jsonify(response),200
        else:
            # sleep(5)
            response=smart_search(query,date)
            return jsonify({'status':'succes','data':response}),200
    except Exception as e:
        print(f"Error fetching Data: {str(e)}")
        return jsonify({'error': str(e)}), 500
@app.route("/api/news/ai/<date>", methods=['POST'])
@jwt_required()
@limiter.limit(dynamic_rate_limit)  # Apply dynamic rate limit
def news_ai(date):
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'No user ID found'}), 401
        
        data = request.json
        query = data.get("query")
        isQuizMode = data.get("isQuizMode", False)
        
        if isQuizMode:
            # Get news from Firestore
            news_ref = db.collection('news').document(date)
            news_doc = news_ref.get()
            
            if not news_doc.exists:
                return jsonify({
                    'status': 'error',
                    'message': 'No news available for this date'
                }), 404
            
            news_data = news_doc.to_dict().get('news_data', {})
            
            user_message = f"""Today's news is given. I will attach today's news for creating quiz. 
                            If user asks to generate any other date quiz, refuse it and mention to change 
                            the date setting on top and ask to generate quiz. 
                            Here is the query:\n\n{query} \n\nToday's news:\n{news_data}"""
            
            response = get_chat_response(user_id, user_message, True, False)
            return jsonify(response), 200
        else:
            response = smart_search(query, date)
            return jsonify({'status': 'success', 'data': response}), 200
            
    except Exception as e:
        print(f"Error fetching Data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/news1/<date>", methods=['GET'])
@jwt_required()
def get_news1(date):
    # date=10032025
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'No user ID found'}), 401

        # Get the AES key for the user
        aes_key = users.get_aes_key(user_id)
        if aes_key['status'] == 'error':
            return jsonify({'error': 'Session expired or Invalid'}), 401

        # For now, read directly from the JSON file
        try:
            with open(f'database/news/{date}.json', 'r') as file:
                news_data = json.load(file)
                # Encrypt the data using the user's AES key
                encrypted_data = users.encrypt_data(json.dumps(news_data), user_id)
                return jsonify({
                    'status': 'success',
                    'data': encrypted_data
                }), 200
        except FileNotFoundError:
            return jsonify({
                'status': 'error',
                'message': 'No news available for this date'
            }), 200

    except Exception as e:
        print(f"Error fetching news: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route("/api/news/<date>", methods=['GET'])
@jwt_required()
def get_news(date):
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'No user ID found'}), 401

        # Get the AES key for the user
        aes_key = users.get_aes_key(user_id)
        if aes_key['status'] == 'error':
            return jsonify({'error': 'Session expired or Invalid'}), 401

        # Get news from Firestore
        news_ref = db.collection('news').document(date)
        news_doc = news_ref.get()
        
        if not news_doc.exists:
            return jsonify({
                'status': 'error',
                'message': 'No news available for this date'
            }), 200

        # Get the news data from the document
        news_data = news_doc.to_dict().get('news_data', {})
        
        # Encrypt the data using the user's AES key
        encrypted_data = users.encrypt_data(json.dumps(news_data), user_id)
        
        return jsonify({
            'status': 'success',
            'data': encrypted_data
        }), 200

    except Exception as e:
        print(f"Error fetching news: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/subscription/create", methods=['POST'])
@jwt_required()
def create_subscription():
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        # Get user details from Firestore
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({'error': 'User not found'}), 404
            
        user_data = user_doc.to_dict()

        # Create payment link with only supported fields
        payment_link_data = {
            "amount": 36500,  # Amount in paise (₹365)
            "currency": "INR",
            "description": "Enliten Academy Premium Subscription",
            # "reference_id": user_id,
            "reference_id":get_random_string(20),
            "customer": {
                "name": user_data.get('name', ''),
                "email": user_data.get('email', ''),
                "contact": user_data.get('phone_number', '')
            },
            "notify": {
                "sms": True,
                "email": True
            },
            "notes": {
                "user_id": user_id,
                "subscription_type": "yearly"
            }
        }

        # Create payment link
        payment_link = razorpay_client.payment_link.create(data=payment_link_data)

        # Store payment details in Firestore
        payment_ref = db.collection('payments').document(payment_link['id'])
        payment_ref.set({
            'user_id': user_id,
            'payment_link_id': payment_link['id'],
            'amount': 36500,
            'status': payment_link['status'],
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(days=7)).isoformat(),
            'payment_status': 'pending',
            'subscription_status': 'inactive'
        })

        # Return payment link details
        response_data = {
            'payment_link_id': payment_link['id'],
            'short_url': payment_link['short_url'],
            'status': payment_link['status']
        }
        
        encrypted_response = users.encrypt_data(json.dumps(response_data), user_id)
        return jsonify({'data': encrypted_response})

    except Exception as e:
        print(f"Error creating payment link: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/subscription/verify-payment", methods=['POST'])
@jwt_required()
def verify_payment():
    try:
        user_id = get_jwt_identity()
        data = request.json
        
        payment_link_id = data.get('payment_link_id')
        
        if not payment_link_id:
            return jsonify({'error': 'Missing payment link ID'}), 400

        # Fetch payment link details from Razorpay
        payment_link = razorpay_client.payment_link.fetch(payment_link_id)
        
        # Verify payment status
        if payment_link['status'] != 'paid':
            return jsonify({
                'status': 'pending',
                'message': 'Payment not completed yet'
            }), 200

        # Get payment details from Firestore
        payment_ref = db.collection('payments').document(payment_link_id)
        payment_doc = payment_ref.get()

        if not payment_doc.exists:
            return jsonify({'error': 'Payment record not found'}), 404

        payment_data = payment_doc.to_dict()
        
        # Check if payment is already processed
        if payment_data.get('payment_status') == 'completed':
            return jsonify({
                'status': 'success',
                'message': 'Payment already processed',
                'redirect': True
            })

        # Update payment status in Firestore
        payment_ref.update({
            'status': 'completed',
            'payment_status': 'completed',
            'paid_at': datetime.now().isoformat(),
            'subscription_status': 'active'
        })

        # Update user's subscription status
        user_ref = db.collection('users').document(user_id)
        subscription_start = datetime.now()
        subscription_end = subscription_start + timedelta(days=365)
        
        user_ref.update({
            'subscription_status': 'active',
            'subscription_start_date': subscription_start.isoformat(),
            'subscription_end_date': subscription_end.isoformat(),
            'last_payment_date': datetime.now().isoformat(),
            'next_payment_date': subscription_end.isoformat()
        })

        response_data = {
            'status': 'success',
            'message': 'Payment verified successfully',
            'subscription_end_date': subscription_end.isoformat(),
            'redirect': True
        }
        
        encrypted_response = users.encrypt_data(json.dumps(response_data), user_id)
        return jsonify({'data': encrypted_response})

    except Exception as e:
        print(f"Error verifying payment: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/subscription/check-payment", methods=['POST'])
@jwt_required()
def check_payment_status():
    try:
        user_id = get_jwt_identity()
        data = request.json
        payment_link_id = data.get('payment_link_id')

        if not payment_link_id:
            return jsonify({'error': 'Missing payment link ID'}), 400

        # Fetch payment link status from Razorpay
        payment_link = razorpay_client.payment_link.fetch(payment_link_id)
        
        # If payment is successful, update the status
        if payment_link['status'] == 'paid':
            return verify_payment()
        
        return jsonify({
            'status': payment_link['status'],
            'message': 'Payment pending'
        })

    except Exception as e:
        print(f"Error checking payment status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/subscription/status", methods=['GET'])
@jwt_required()
def get_subscription_status():
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        # Get user's subscription status from Firestore
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({'error': 'User not found'}), 404

        user_data = user_doc.to_dict()
        
        # Check if there's a pending payment
        if user_data.get('payment_link_id'):
            try:
                # Fetch payment link status from Razorpay
                payment_link = razorpay_client.payment_link.fetch(user_data['payment_link_id'])
                if payment_link['status'] == 'paid':
                    pass
                    # If paid but not updated, update the status
                    # subscription_start = datetime.now()
                    # subscription_end = subscription_start + timedelta(days=365)
                    
                    # user_ref.update({
                    #     'subscription_status': 'active',
                    #     'subscription_start_date': subscription_start.isoformat(),
                    #     'subscription_end_date': subscription_end.isoformat(),
                    #     'last_payment_date': datetime.now().isoformat(),
                    #     'next_payment_date': subscription_end.isoformat()
                    # })
                    
                    # user_data.update({
                    #     'subscription_status': 'active',
                    #     'subscription_start_date': subscription_start.isoformat(),
                    #     'subscription_end_date': subscription_end.isoformat()
                    # })
            except Exception as e:
                print(f"Error checking payment link: {str(e)}")
                # Continue with current status if payment check fails

        subscription_status = {
            'status': user_data.get('subscription_status', 'inactive'),
            'start_date': user_data.get('subscription_start_date'),
            'end_date': user_data.get('subscription_end_date'),
            'next_payment_date': user_data.get('next_payment_date'),
            'payment_link_id': user_data.get('payment_link_id')
        }

        # Check if subscription has expired
        if subscription_status['status'] == 'active' and subscription_status['end_date']:
            end_date = datetime.fromisoformat(subscription_status['end_date'])
            if end_date < datetime.now():
                subscription_status['status'] = 'expired'
                user_ref.update({
                    'subscription_status': 'expired'
                })

        # Encrypt the response
        encrypted_response = users.encrypt_data(json.dumps(subscription_status), user_id)
        return jsonify({'data': encrypted_response})

    except Exception as e:
        print(f"Error getting subscription status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/admin/stats", methods=['GET'])
def get_admin_stats():
    try:
        # Verify admin authentication
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401

        # Get users collection
        users_ref = db.collection('users')
        
        # Get total users count
        total_users = len(list(users_ref.stream()))
        print(f"Total users: {total_users}")
        # Get active users (users with active subscription)
        active_users = len(list(users_ref.where('subscription_status', '==', 'active').stream()))
        
        # Calculate total revenue from payments
        payments_ref = db.collection('payments')
        completed_payments = payments_ref.where('payment_status', '==', 'completed').stream()
        total_revenue = sum(payment.to_dict().get('amount', 0) for payment in completed_payments) / 100  # Convert from paise to rupees
        
        # Calculate conversion rate
        conversion_rate = (active_users / total_users * 100) if total_users > 0 else 0
        
        # Get recent users
        recent_users = [
            {
                'id': doc.id,
                **doc.to_dict()
            }
            for doc in users_ref.order_by('register_time', direction='DESCENDING').limit(5).stream()
        ]
        
        # Get recent activities (payments, registrations, etc.)
        activities = []
        recent_payments = payments_ref.order_by('created_at', direction='DESCENDING').limit(5).stream()
        for payment in recent_payments:
            payment_data = payment.to_dict()
            activities.append({
                'type': 'payment',
                'amount': payment_data.get('amount', 0) / 100,
                'status': payment_data.get('payment_status', ''),
                'timestamp': payment_data.get('created_at', ''),
                'user_id': payment_data.get('user_id', '')
            })

        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'total_revenue': total_revenue,
            'conversion_rate': round(conversion_rate, 2),
            'recent_users': recent_users,
            'recent_activities': activities
        })

    except Exception as e:
        print(f"Error fetching admin stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/admin/users", methods=['GET'])
def get_all_users():
    try:
        # Verify admin authentication
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401

        # Get users collection
        users_ref = db.collection('users')
        users = []
        
        # Get all users
        for doc in users_ref.stream():
            user_data = doc.to_dict()
            user_data['id'] = doc.id
            users.append(user_data)
        
        return jsonify({
            'users': users
        })

    except Exception as e:
        print(f"Error fetching users: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/admin/analytics", methods=['GET'])
def get_analytics():
    try:
        # Verify admin authentication
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401

        users_ref = db.collection('users')
        payments_ref = db.collection('payments')

        # Calculate user growth over time
        all_users = list(users_ref.order_by('register_time').stream())
        user_growth = []
        user_dates = {}
        
        for user in all_users:
            user_data = user.to_dict()
            date = user_data.get('register_time', '')[:10]  # Get just the date part
            if date in user_dates:
                user_dates[date] += 1
            else:
                user_dates[date] = 1

        for date, count in user_dates.items():
            user_growth.append({
                'date': date,
                'users': count
            })

        # Calculate subject performance
        subject_scores = {
            "Tamil": 0,
            "English": 0,
            "History": 0,
            "Polity": 0,
            "Economy": 0,
            "Geography": 0,
            "General Science": 0,
            "Current Affairs": 0,
            "Aptitude & Reasoning": 0
        }
        
        total_users = len(all_users)
        for user in all_users:
            user_data = user.to_dict()
            subject_analysis = user_data.get('subject_analysis', {})
            for subject, score in subject_analysis.items():
                subject_scores[subject] += score

        subject_performance = [
            {'name': subject, 'score': score/total_users if total_users > 0 else 0}
            for subject, score in subject_scores.items()
        ]

        # Calculate revenue trends
        completed_payments = payments_ref.where('payment_status', '==', 'completed').stream()
        revenue_data = {}
        
        for payment in completed_payments:
            payment_data = payment.to_dict()
            date = payment_data.get('created_at', '')[:10]
            amount = payment_data.get('amount', 0) / 100  # Convert from paise to rupees
            if date in revenue_data:
                revenue_data[date] += amount
            else:
                revenue_data[date] = amount

        revenue_trend = [
            {'date': date, 'revenue': amount}
            for date, amount in revenue_data.items()
        ]

        # Calculate user type distribution
        premium_users = len(list(users_ref.where('subscription_status', '==', 'active').stream()))
        user_distribution = {
            'premium': premium_users,
            'free': total_users - premium_users
        }

        return jsonify({
            'userGrowth': sorted(user_growth, key=lambda x: x['date']),
            'subjectPerformance': subject_performance,
            'revenueData': sorted(revenue_trend, key=lambda x: x['date']),
            'userTypeDistribution': user_distribution
        })

    except Exception as e:
        print(f"Error fetching analytics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/admin/content", methods=['GET'])
def get_admin_content():
    try:
        # Verify admin authentication
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401

        # Get news collection
        news_ref = db.collection('news')
        news = []
        
        # Get all news items
        for doc in news_ref.stream():
            news_data = doc.to_dict()
            news_data['id'] = doc.id
            news_data['date'] = doc.id  # Use document ID as date
            # Format last_updated if it exists
            if 'last_updated' in news_data:
                try:
                    # Convert to ISO format if it's not already
                    date_obj = datetime.fromisoformat(news_data['last_updated'].replace('Z', '+00:00'))
                    news_data['last_updated'] = date_obj.isoformat()
                except:
                    news_data['last_updated'] = None
            news.append(news_data)

        # Sort news by date
        news.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return jsonify({
            'news': news
        })

    except Exception as e:
        print(f"Error fetching content: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/quiz/<group>/<category>/<subcategory>", methods=['GET'])
@jwt_required()
def get_quiz_details(group, category, subcategory):
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        # Fetch quiz details from Firestore
        quiz_ref = db.collection('quiz').document(group).collection(category).document(subcategory)
        quiz_doc = quiz_ref.get()

        if not quiz_doc.exists:
            return jsonify({'error': 'Quiz details not found'}), 404

        quiz_data = quiz_doc.to_dict()
        
        # Convert quiz_data to list format if it's a single item
        quiz_list = [quiz_data] if quiz_data else []

        # Encrypt the response
        encrypted_response = users.encrypt_data(json.dumps(quiz_list), user_id)
        return jsonify({'data': encrypted_response}), 200

    except Exception as e:
        print(f"Error fetching quiz details: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/quiz/categories/<group>", methods=['GET'])
@jwt_required()
def get_quiz_categories(group):
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        # Get all categories for this group
        quiz_ref = db.collection('quiz').document(group)
        collections = quiz_ref.collections()
        
        categories = {}
        for category_ref in collections:
            category_name = category_ref.id
            subcategories = []
            
            # Get all subcategories for this category
            for doc in category_ref.stream():
                subcategory_data = doc.to_dict()
                subcategory_data['id'] = doc.id
                subcategories.append(subcategory_data)
            
            categories[category_name] = subcategories

        # Encrypt the response
        encrypted_response = users.encrypt_data(json.dumps(categories), user_id)
        return jsonify({'data': encrypted_response}), 200

    except Exception as e:
        print(f"Error fetching quiz categories: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/temp/migrate-quiz-data", methods=['GET'])
def migrate_quiz_data():
    try:
        # Static quiz data from frontend
        quiz_data = {
            "Group1": {
                "General Science": {
                    "Scientific Knowledge": {
                        "topic": "Scientific Knowledge",
                        "subtopics": [
                            "Scientific Knowledge and Scientific Temper",
                            "Power of Reasoning",
                            "Rote Learning Vs Conceptual Learning",
                            "Science as a tool to understand the past, present, and future"
                        ]
                    }
                },
                "Physics": {
                    "Mechanics": {
                        "topic": "Mechanics",
                        "subtopics": [
                            "Nature of Universe",
                            "General Scientific Laws",
                            "Properties of Matter",
                            "Force",
                            "Motion and Energy"
                        ]
                    }
                }
                # Add more categories and subtopics as needed
            }
            # Add more groups as needed
        }

        # Migrate data to Firestore
        for group, categories in quiz_data.items():
            for category, subcategories in categories.items():
                for subcategory, data in subcategories.items():
                    # Create reference path
                    quiz_ref = db.collection('quiz').document(group).collection(category).document(subcategory)
                    # Set the data
                    quiz_ref.set(data)

        return jsonify({
            'status': 'success',
            'message': 'Quiz data successfully migrated to Firestore'
        }), 200

    except Exception as e:
        print(f"Error migrating quiz data: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Function to check if quiz data exists
def check_quiz_data_exists():
    try:
        # Check if any quiz data exists
        quiz_ref = db.collection('quiz')
        docs = quiz_ref.limit(1).get()
        return len(list(docs)) > 0
    except Exception:
        return False

# Add this to your app startup code
@app.before_first_request
def initialize_quiz_data():
    try:
        if not check_quiz_data_exists():
            print("No quiz data found, initializing from static data...")
            migrate_quiz_data()
    except Exception as e:
        print(f"Error initializing quiz data: {str(e)}")

@app.route("/api/admin/quiz", methods=['GET'])
def get_admin_quiz():
    try:
        # Verify admin authentication
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401

        quiz_data = {}
        # Get all group documents under 'quiz'
        group_docs = db.collection('quiz').list_documents()
        for group_doc in group_docs:
            group_id = group_doc.id
            group_data = {}
            # Get all category collections under this group document
            category_refs = group_doc.collections()
            for category_ref in category_refs:
                category_id = category_ref.id
                category_data = {}
                # Get all subcategory documents under this category collection
                for subcat_doc in category_ref.stream():
                    category_data[subcat_doc.id] = subcat_doc.to_dict()
                group_data[category_id] = category_data
            quiz_data[group_id] = group_data

        return jsonify({'quiz': quiz_data})

    except Exception as e:
        print(f"Error fetching quiz data: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/admin/quiz/<group>/<category>/<subcategory>", methods=['POST', 'PUT', 'DELETE'])
def manage_quiz(group, category, subcategory):
    try:
        # Verify admin authentication
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401

        quiz_ref = db.collection('quiz').document(group).collection(category).document(subcategory)

        if request.method == 'POST':
            quiz_data = request.json
            quiz_ref.set(quiz_data)
            return jsonify({'message': 'Quiz created successfully'})

        elif request.method == 'PUT':
            quiz_data = request.json
            quiz_ref.update(quiz_data)
            return jsonify({'message': 'Quiz updated successfully'})

        elif request.method == 'DELETE':
            quiz_ref.delete()
            return jsonify({'message': 'Quiz deleted successfully'})

    except Exception as e:
        print(f"Error managing quiz: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ------------------ Shared Questions (MCQ) API ------------------

from flask import abort

@app.route('/api/admin/shared-questions', methods=['GET', 'POST'])
def admin_shared_questions():
    # Only admin can access
    admin_key = request.headers.get('Authorization')
    if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        if request.method == 'GET':
            # List all shared questions
            docs = db.collection('sharedQuestions').stream()
            questions = []
            for doc in docs:
                q = doc.to_dict()
                q['id'] = doc.id
                questions.append(q)
            return jsonify({'questions': questions})
        if request.method == 'POST':
            # Create a new shared question
            data = request.json
            # Required fields: text, options, correctOption, explanation, category, subcategory, sharedWith
            required = ['text', 'options', 'correctOption', 'explanation', 'category', 'subcategory', 'sharedWith']
            if not all(k in data for k in required):
                abort(400, description='Missing required fields')
            new_ref = db.collection('sharedQuestions').document()
            new_ref.set(data)
            return jsonify({'message': 'Question created', 'id': new_ref.id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/shared-questions/<question_id>', methods=['GET', 'PUT', 'DELETE'])

def admin_shared_question_detail(question_id):
    admin_key = request.headers.get('Authorization')
    if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        ref = db.collection('sharedQuestions').document(question_id)
        if request.method == 'GET':
            doc = ref.get()
            if not doc.exists:
                abort(404, description='Question not found')
            q = doc.to_dict()
            q['id'] = doc.id
            return jsonify(q)
        elif request.method == 'PUT':
            data = request.json
            ref.update(data)
            return jsonify({'message': 'Question updated'})
        elif request.method == 'DELETE':
            ref.delete()
            return jsonify({'message': 'Question deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/shared-questions/<question_id>/map', methods=['POST'])

def admin_map_question_to_groups(question_id):
    """Update the sharedWith field to map question to groups."""
    admin_key = request.headers.get('Authorization')
    if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        ref = db.collection('sharedQuestions').document(question_id)
        doc = ref.get()
        if not doc.exists:
            abort(404, description='Question not found')
        data = request.json
        # expects { "sharedWith": { "Group_1": true, ... } }
        if 'sharedWith' not in data:
            abort(400, description='Missing sharedWith field')
        ref.update({'sharedWith': data['sharedWith']})
        return jsonify({'message': 'Mapping updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/questions', methods=['GET'])
def get_mcq_questions():
    """User fetches MCQs by group, category, subcategory."""
    group = request.args.get('group')
    category = request.args.get('category')
    subcategory = request.args.get('subcategory')
    try:
        # Query sharedQuestions where sharedWith[group]==True and category/subcategory match
        questions_ref = db.collection('sharedQuestions')
        query = questions_ref.where(f'sharedWith.Group_{group}', '==', True)
        if category:
            query = query.where('category', '==', category)
            print(f"Category: {category}")
        if subcategory:
            query = query.where('subcategory', '==', subcategory)
            print(f"Subcategory: {subcategory}")
        docs = query.stream()
        questions = []
        for doc in docs:
            q = doc.to_dict()
            q['id'] = doc.id
            questions.append(q)
        return jsonify({'questions': questions})
    except Exception as e:
        print(f"Error in /api/quiz/questions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/interview', methods=['POST'])
@jwt_required()
@limiter_interview.limit(dynamic_interview_rate_limit)

def interview():
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    encrypted_data = request.json
    print(f"Encrypted data: {encrypted_data}")
    data = users.decrypt_data(encrypted_data['data'],user_id)
    data = json.loads(data['data'])
    print(f"Decrypted data: {data}")
    username = data.get('username')
    description = data.get('description')
    phone_number = data.get('phone_number')

    try:
        response = requests.post(
            "https://api.elevenlabs.io/v1/convai/twilio/outbound-call",
            headers={
                "xi-api-key": "sk_8498e709110a6917293ba34bd2277beed6a74febbb3e6f65"
            },
            json={
                "agent_id": "agent_01jz7k73ywe69trm2ek80shae4",
                "agent_phone_number_id": "phnum_01jz7qnkfqfe1rb854gbdhns4r",
                "to_number": phone_number
            },
        )

        res_json = response.json()

        db.collection('users').document(user_id).update({
            "interviews": firestore.ArrayUnion([
                {
                    "created_at": datetime.now(timezone).isoformat(),
                    "id": res_json.get("conversation_id", "unknown"),
                    "status": "success" if res_json.get("success", "failed") else "failed"  
                }
            ])
        })

        return jsonify({"message": "Interview added", "data": res_json})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
if __name__ == '__main__':
        app.run(host='0.0.0.0',debug=True)