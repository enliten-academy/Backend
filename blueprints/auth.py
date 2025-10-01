from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import requests
import secrets
from urllib.parse import urlencode
import json
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login/admin", methods=['POST'])
def admin_login():
    from app import admin, limiter_ip
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

@auth_bp.route("/login", methods=['POST'])
def login():
    from app import app, encryption, users
    try:
        encrypted_data = request.json
        aes_key = encryption.decrypt_aes_key(encrypted_data['encrypted_aes_key'])
        decrypted_data = encryption.decrypt_data(encrypted_data['data'], aes_key)
        user_data = json.loads(decrypted_data)
        
        access_token = create_access_token(identity=user_data['uid'])
        users.add_user(user_data["uid"],int((datetime.now() + app.config["JWT_ACCESS_TOKEN_EXPIRES"]).timestamp()))
        
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

@auth_bp.route("/request-otp", methods=['POST'])
def request_otp():
    from app import encryption, auth_service, limiter
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
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@auth_bp.route("/verify-otp", methods=['POST'])
def verify_otp():
    from app import redis_client, users, app
    from flask_jwt_extended import create_access_token
    from firebase_admin import auth as firebase_auth
    try:
        encrypted_data = request.json
        aes_key = encryption.decrypt_aes_key(encrypted_data['encrypted_aes_key'])
        decrypted_data = encryption.decrypt_data(encrypted_data['data'], aes_key)
        user_data = json.loads(decrypted_data)
        
        phone_number = user_data['phoneNumber']
        otp = user_data['otp']
        
        stored_otp = redis_client.get(f"otp:{phone_number}")
        if not stored_otp or stored_otp.decode() != otp:
            return jsonify({'error': 'Invalid OTP'}), 400
            
        try:
            user = firebase_auth.get_user_by_phone_number(phone_number)
        except:
            user = firebase_auth.create_user(
                phone_number=phone_number
            )
        
        token = create_access_token(identity=user.uid)
        users.add_user(user.uid,int((datetime.now() + app.config["JWT_ACCESS_TOKEN_EXPIRES"]).timestamp()))
        
        create_user_document(user.uid, user_data)
        
        return jsonify({'token': token})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@auth_bp.route("/google-signin-url")
def google_signin_url():
    from app import redis_client
    from config import Config
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
        return jsonify({'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route("/google-signin-callback", methods=['POST'])
def google_signin_callback():
    from app import db, users, app
    from flask_jwt_extended import create_access_token
    from config import Config
    try:
        code = request.json.get('code')
        if not code:
            return jsonify({'error': 'No authorization code provided'}), 400

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
            return jsonify({
                'error': 'Failed to exchange code for tokens',
                'details': error_details
            }), 400
            
        tokens = token_response.json()
        
        userinfo_response = requests.get('https://www.googleapis.com/oauth2/v3/userinfo',
                                       headers={'Authorization': f'Bearer {tokens["access_token"]}'})
        if not userinfo_response.ok:
            raise Exception('Failed to get user info from Google')
            
        google_data = userinfo_response.json()
        
        users_ref = db.collection('users')
        existing_users = users_ref.where('email', '==', google_data.get('email')).limit(1).get()
        
        if len(existing_users) > 0:
            user_doc = existing_users[0]
            user_id = user_doc.id
            user_ref = users_ref.document(user_id)
            user_ref.update({
                'name': google_data.get('name', ''),
                'email': google_data.get('email', ''),
                'photo_url': google_data.get('picture', '')
            })
        else:
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
            
            new_user_ref = users_ref.add(user_data)
            user_id = new_user_ref[1].id
        
        token = create_access_token(identity=user_id)
        users.add_user(user_id,int((datetime.now() + app.config["JWT_ACCESS_TOKEN_EXPIRES"]).timestamp()))
        
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
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

@auth_bp.route("/logout", methods=['POST'])
@jwt_required()
def logout():
    from app import users
    try:
        user_id = get_jwt_identity()
        users.remove_user(user_id)
        return jsonify({'message': 'Logged out successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@auth_bp.route("/session",methods=['GET'])
@jwt_required()
def session():
    return jsonify(True)
