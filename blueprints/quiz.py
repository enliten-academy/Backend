from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json

quiz_bp = Blueprint('quiz', __name__)

@quiz_bp.route("/<group>/<category>/<subcategory>", methods=['GET'])
@jwt_required()
def get_quiz_details(group, category, subcategory):
    from app import db, users
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        quiz_ref = db.collection('quiz').document(group).collection(category).document(subcategory)
        quiz_doc = quiz_ref.get()

        if not quiz_doc.exists:
            return jsonify({'error': 'Quiz details not found'}), 404

        quiz_data = quiz_doc.to_dict()
        quiz_list = [quiz_data] if quiz_data else []

        encrypted_response = users.encrypt_data(json.dumps(quiz_list), user_id)
        return jsonify({'data': encrypted_response}), 200

    except Exception as e:
        print(f"Error fetching quiz details: {str(e)}")
        return jsonify({'error': str(e)}), 500

@quiz_bp.route("/categories/<group>", methods=['GET'])
@jwt_required()
def get_quiz_categories(group):
    from app import db, users
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        quiz_ref = db.collection('quiz').document(group)
        collections = quiz_ref.collections()
        
        categories = {}
        for category_ref in collections:
            category_name = category_ref.id
            subcategories = []
            
            for doc in category_ref.stream():
                subcategory_data = doc.to_dict()
                subcategory_data['id'] = doc.id
                subcategories.append(subcategory_data)
            
            categories[category_name] = subcategories

        encrypted_response = users.encrypt_data(json.dumps(categories), user_id)
        return jsonify({'data': encrypted_response}), 200

    except Exception as e:
        print(f"Error fetching quiz categories: {str(e)}")
        return jsonify({'error': str(e)}), 500

@quiz_bp.route("/questions", methods=['GET'])
def get_mcq_questions():
    from app import db
    group = request.args.get('group')
    category = request.args.get('category')
    subcategory = request.args.get('subcategory')
    try:
        questions_ref = db.collection('sharedQuestions')
        query = questions_ref.where(f'sharedWith.Group_{group}', '==', True)
        if category:
            query = query.where('category', '==', category)
        if subcategory:
            query = query.where('subcategory', '==', subcategory)
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
