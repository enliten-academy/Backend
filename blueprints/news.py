from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from datetime import datetime

news_bp = Blueprint('news', __name__)

@news_bp.route("/hook/news1", methods=['GET'])
def news_hook1():
    from app import timezone
    from services.news import CurrentAffairsSearch
    
    def th():
        date = datetime.now(timezone).strftime("%d%m%Y")
        search = CurrentAffairsSearch("AIzaSyA5R4oAdClKw1JzlCRMKJiw8430k_-_pMk")
        news_data = search.get_current_affairs()
        with open(f'database/news/{date}.json', 'w') as file:
            json.dump(news_data, file, indent=2)
        print("News update Success !!")
    
    th()
    return jsonify({'message': 'News hook received'}), 200

@news_bp.route("/hook/quote", methods=['GET'])
def quote_hook():
    from app import db, timezone
    from utils.quotes import get_quote
    
    try:
        date = datetime.now(timezone).strftime("%d%m%Y")
        quote = get_quote()
        
        quote_ref = db.collection('quotes').document(date)
        quote_ref.set({
            'quote': quote["quote"]
        })
        
        return jsonify({'message': "Quote update Success !!"}), 200
    except Exception as e:
        return jsonify({'message': "Quote update failed !!\nError: "+ str(e)}), 500

@news_bp.route("/hook/news", methods=['GET'])
def news_hook():
    from app import db, timezone
    from services.news import CurrentAffairsSearch
    
    def th():
        try:
            date = datetime.now(timezone).strftime("%d%m%Y")
            search = CurrentAffairsSearch("AIzaSyBQgUq_pscmRRw36Y7HKt3dvDTgKTQvUA4")
            news_data = search.get_current_affairs()
            
            news_ref = db.collection('news').document(date)
            news_ref.set({
                'date': date,
                'news_data': news_data,
                'last_updated': datetime.now().isoformat()
            })
            
            print("News update Success !!")
        except Exception as e:
            print("News update failed !!", str(e))
    
    th()
    return jsonify({'message': 'News hook received'}), 200

@news_bp.route("/ai/<date>", methods=['POST'])
@jwt_required()
def news_ai(date):
    from app import db, users, limiter, dynamic_rate_limit
    from services.chat_handler import get_chat_response
    from services.smart_news import smart_search
    
    with limiter.limit(dynamic_rate_limit):
        try:
            user_id = get_jwt_identity()
            if not user_id:
                return jsonify({'error': 'No user ID found'}), 401
            
            data = request.json
            query = data.get("query")
            isQuizMode = data.get("isQuizMode", False)
            
            if isQuizMode:
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

@news_bp.route("/<date>", methods=['GET'])
@jwt_required()
def get_news(date):
    from app import db, users
    
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'No user ID found'}), 401

        aes_key = users.get_aes_key(user_id)
        if aes_key['status'] == 'error':
            return jsonify({'error': 'Session expired or Invalid'}), 401

        news_ref = db.collection('news').document(date)
        news_doc = news_ref.get()
        
        if not news_doc.exists:
            return jsonify({
                'status': 'error',
                'message': 'No news available for this date'
            }), 200

        news_data = news_doc.to_dict().get('news_data', {})
        encrypted_data = users.encrypt_data(json.dumps(news_data), user_id)
        
        return jsonify({
            'status': 'success',
            'data': encrypted_data
        }), 200

    except Exception as e:
        print(f"Error fetching news: {str(e)}")
        return jsonify({'error': str(e)}), 500
