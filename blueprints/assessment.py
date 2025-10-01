from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json

assessment_bp = Blueprint('assessment', __name__)

@assessment_bp.route("/user", methods=['GET'])
@jwt_required()
def get_user_assessments():
    from app import db, users
    try:
        user_id = get_jwt_identity()
        assessments_ref = db.collection('assessments')
        query = assessments_ref.where('user_id', '==', user_id).stream()
        
        assessments = [doc.to_dict() for doc in query]
        if not assessments:
            encrypted_response = users.encrypt_data(json.dumps({'error': 'No assessments found for this user'}),user_id)
            return json.dumps({'data':encrypted_response}), 404
        encrypted_response = users.encrypt_data(json.dumps({'assessments': assessments}),user_id)
        return json.dumps({'data':encrypted_response})
    except Exception as e:
        encrypted_response = users.encrypt_data(json.dumps({'error': str(e)}),user_id)
        return json.dumps({'data':encrypted_response}), 500

@assessment_bp.route("/submit", methods=['POST'])
@jwt_required()
def submit_assessment():
    from app import encryption
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
