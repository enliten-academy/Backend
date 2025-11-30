from flask import Blueprint, request, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

admin_bp = Blueprint('admin', __name__)

# Admin login (already handled in auth, but for completeness)
@admin_bp.route('/auth/login', methods=['POST'])
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

# Admin stats
@admin_bp.route('/stats', methods=['GET'])
def get_admin_stats():
    from app import db, admin
    try:
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401
        users_ref = db.collection('users')
        total_users = len(list(users_ref.stream()))
        active_users = len(list(users_ref.where('subscription_status', '==', 'active').stream()))
        payments_ref = db.collection('payments')
        completed_payments = payments_ref.where('payment_status', '==', 'completed').stream()
        total_revenue = sum(payment.to_dict().get('amount', 0) for payment in completed_payments) / 100
        conversion_rate = (active_users / total_users * 100) if total_users > 0 else 0
        recent_users = [ {'id': doc.id, **doc.to_dict()} for doc in users_ref.order_by('register_time', direction='DESCENDING').limit(5).stream() ]
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
        return jsonify({'error': str(e)}), 500

# Admin users
@admin_bp.route('/users', methods=['GET'])
def get_all_users():
    from app import db, admin
    try:
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401
        users_ref = db.collection('users')
        users = []
        for doc in users_ref.stream():
            user_data = doc.to_dict()
            user_data['id'] = doc.id
            users.append(user_data)
        return jsonify({'users': users})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin analytics
@admin_bp.route('/analytics', methods=['GET'])
def get_analytics():
    from app import db, admin
    try:
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401
        users_ref = db.collection('users')
        payments_ref = db.collection('payments')
        all_users = list(users_ref.order_by('register_time').stream())
        user_growth = []
        user_dates = {}
        for user in all_users:
            user_data = user.to_dict()
            date = user_data.get('register_time', '')[:10]
            if date in user_dates:
                user_dates[date] += 1
            else:
                user_dates[date] = 1
        for date, count in user_dates.items():
            user_growth.append({'date': date, 'users': count})
        subject_scores = {
            "Tamil": 0, "English": 0, "History": 0, "Polity": 0, "Economy": 0, "Geography": 0, "General Science": 0, "Current Affairs": 0, "Aptitude & Reasoning": 0
        }
        total_users = len(all_users)
        for user in all_users:
            user_data = user.to_dict()
            subject_analysis = user_data.get('subject_analysis', {})
            for subject, score in subject_analysis.items():
                subject_scores[subject] += score
        subject_performance = [ {'name': subject, 'score': score/total_users if total_users > 0 else 0} for subject, score in subject_scores.items() ]
        completed_payments = payments_ref.where('payment_status', '==', 'completed').stream()
        revenue_data = {}
        for payment in completed_payments:
            payment_data = payment.to_dict()
            date = payment_data.get('created_at', '')[:10]
            amount = payment_data.get('amount', 0) / 100
            if date in revenue_data:
                revenue_data[date] += amount
            else:
                revenue_data[date] = amount
        revenue_trend = [ {'date': date, 'revenue': amount} for date, amount in revenue_data.items() ]
        premium_users = len(list(users_ref.where('subscription_status', '==', 'active').stream()))
        user_distribution = { 'premium': premium_users, 'free': total_users - premium_users }
        return jsonify({
            'userGrowth': sorted(user_growth, key=lambda x: x['date']),
            'subjectPerformance': subject_performance,
            'revenueData': sorted(revenue_trend, key=lambda x: x['date']),
            'userTypeDistribution': user_distribution
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin content
@admin_bp.route('/content', methods=['GET'])
def get_admin_content():
    from app import db, admin
    try:
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401
        news_ref = db.collection('news')
        news = []
        for doc in news_ref.stream():
            news_data = doc.to_dict()
            news_data['id'] = doc.id
            news_data['date'] = doc.id
            if 'last_updated' in news_data:
                try:
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(news_data['last_updated'].replace('Z', '+00:00'))
                    news_data['last_updated'] = date_obj.isoformat()
                except:
                    news_data['last_updated'] = None
            news.append(news_data)
        news.sort(key=lambda x: x.get('date', ''), reverse=True)
        return jsonify({'news': news})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Admin quiz endpoints (GET, POST, PUT, DELETE)
@admin_bp.route('/quiz', methods=['GET'])
def get_admin_quiz():
    from app import db, admin
    try:
        admin_key = request.headers.get('Authorization')
        if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
            return jsonify({'error': 'Unauthorized'}), 401
        quiz_data = {}
        group_docs = db.collection('quiz').list_documents()
        for group_doc in group_docs:
            group_id = group_doc.id
            group_data = {}
            category_refs = group_doc.collections()
            for category_ref in category_refs:
                category_id = category_ref.id
                category_data = {}
                for subcat_doc in category_ref.stream():
                    category_data[subcat_doc.id] = subcat_doc.to_dict()
                group_data[category_id] = category_data
            quiz_data[group_id] = group_data
        return jsonify({'quiz': quiz_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/quiz/<group>/<category>/<subcategory>', methods=['POST', 'PUT', 'DELETE'])
def manage_quiz(group, category, subcategory):
    from app import db, admin
    try:
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
        return jsonify({'error': str(e)}), 500

# Shared Questions (MCQ) API
@admin_bp.route('/shared-questions', methods=['GET', 'POST'])
def admin_shared_questions():
    from app import db, admin
    admin_key = request.headers.get('Authorization')
    if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        if request.method == 'GET':
            docs = db.collection('sharedQuestions').stream()
            questions = []
            for doc in docs:
                q = doc.to_dict()
                q['id'] = doc.id
                questions.append(q)
            return jsonify({'questions': questions})
        if request.method == 'POST':
            data = request.json
            required = ['text', 'options', 'correctOption', 'explanation', 'category', 'subcategory', 'sharedWith']
            if not all(k in data for k in required):
                abort(400, description='Missing required fields')
            new_ref = db.collection('sharedQuestions').document()
            new_ref.set(data)
            return jsonify({'message': 'Question created', 'id': new_ref.id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/shared-questions/<question_id>', methods=['GET', 'PUT', 'DELETE'])
def admin_shared_question_detail(question_id):
    from app import db, admin
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

@admin_bp.route('/shared-questions/<question_id>/map', methods=['POST'])
def admin_map_question_to_groups(question_id):
    from app import db, admin
    admin_key = request.headers.get('Authorization')
    if not admin_key or not admin.verify_token(admin_key.split(' ')[1]):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        ref = db.collection('sharedQuestions').document(question_id)
        doc = ref.get()
        if not doc.exists:
            abort(404, description='Question not found')
        data = request.json
        if 'sharedWith' not in data:
            abort(400, description='Missing sharedWith field')
        ref.update({'sharedWith': data['sharedWith']})
        return jsonify({'message': 'Mapping updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
