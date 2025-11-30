from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json

interview_bp = Blueprint('interview', __name__)

@interview_bp.route('', methods=['POST'])
@jwt_required()
def create_interview():
    from app import db, users, limiter_interview, dynamic_interview_rate_limit, timezone
    from services.interview_service import InterviewService
    
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    with limiter_interview.limit(dynamic_interview_rate_limit):
        try:
            encrypted_data = request.json
            
            data = users.decrypt_data(encrypted_data['data'], user_id)
            
            # Check if data is already a dict or needs parsing
            if isinstance(data, dict):
                if 'data' in data:
                    data = json.loads(data['data'])
                else:
                    # data is already the decrypted dict
                    pass
            else:
                data = json.loads(data)
            
            
            username = data.get('username')
            description = data.get('description')
            phone_number = data.get('phone_number')

            if not phone_number:
                return jsonify({'error': 'Phone number is required'}), 400

            # Use interview service
            interview_service = InterviewService()
            result = interview_service.schedule_interview(
                user_id=user_id,
                phone_number=phone_number,
                username=username,
                description=description,
                db=db,
                timezone=timezone
            )

            if result['success']:
                return jsonify({
                    "message": "Interview scheduled successfully",
                    "data": result['data']
                }), 200
            else:
                return jsonify({'error': result['error']}), 500

        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
