from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.route("/", methods=['GET'])
@jwt_required()
def get_notifications():
    from app import db
    try:
        user_id = get_jwt_identity()
        
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
        return jsonify({'error': str(e)}), 400
