from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from datetime import datetime

user_bp = Blueprint('user', __name__)

@user_bp.route("/data", methods=['GET'])
@jwt_required()
def get_user_data():
    from app import db, users, timezone
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'No user ID found'}), 401

    user_ref = db.collection('users').document(user_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        default_data = {
            'name': '',
            'quote': '',
            'email': '',
            'photo_url': '',
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
            quote = quote_doc.to_dict().get('quote', {'quote': 'No quotes available for this date'})
    except Exception as e:
        quote = {'quote': 'No quotes available for this date'}

    user_data['quote']=quote
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

@user_bp.route("/create", methods=['POST'])
@jwt_required()
def create_user():
    from app import db
    try:
        user_id = get_jwt_identity()
        user_data = request.json
        email = user_data.get("email")

        if not email:
            return jsonify({'message': 'Email is required'}), 400

        user_ref = db.collection('users').document(user_id)
        if user_ref.get().exists:
            return jsonify({'message': 'User document already exists'}), 200

        collections = db.collections()
        for collection in collections:
            docs = collection.stream()
            for doc in docs:
                if 'email' in doc.to_dict() and doc.to_dict()['email'] == email:
                    return jsonify({'message': 'Email already exists in the system'}), 400

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
        return jsonify({'error': str(e)}), 400

@user_bp.route("/profile", methods=['GET'])
@jwt_required()
def get_user_profile():
    from app import db
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
        return jsonify({'error': str(e)}), 400

@user_bp.route("/ads", methods=['GET'])
@jwt_required()
def get_key():
    from app import users, public_key
    import base64
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'No Access'}), 401

    aes_key = users.get_aes_key(user_id)

    if aes_key['status'] == 'error':
        return jsonify({'error': 'Session expired or Invalid'}), 401
    else:
        raw_aes_key = base64.b64decode(aes_key.pop("aes_key"))

        encrypted_aes_key = public_key.encrypt(
            raw_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        aes_key["ads_key"] = base64.b64encode(encrypted_aes_key).decode()
        return jsonify(aes_key), 200
