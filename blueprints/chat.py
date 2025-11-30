from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('', methods=['POST'])
@jwt_required()
def chat():
    from app import storage, get_chat_response, generate_title, limiter, dynamic_rate_limit
    with limiter.limit(dynamic_rate_limit):
        user_id = get_jwt_identity()
        data = request.json
        user_message = data.get("message")
        is_quiz_mode = data.get("isQuizMode", False)
        is_heuristic_mode = data.get("isHeuristicMode", False)
        conversation_id = data.get("conversation_id", False)
        language = data.get("lang", "English")

        if not user_message:
            return jsonify({"error": "Missing message"}), 400

        if not conversation_id:
            conversation_id = storage.create_conversation(user_id, generate_title(user_message))

        response = get_chat_response(user_id, user_message, is_quiz_mode, is_heuristic_mode, language)

        storage.add_message(conversation_id, data, "user", user_id)

        storage.add_message(conversation_id, response, "ai", user_id, tokens=12)

        response["conversation_id"] = conversation_id
        return jsonify(response)
