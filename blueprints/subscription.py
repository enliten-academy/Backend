from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
from datetime import datetime, timedelta

subscription_bp = Blueprint('subscription', __name__)

@subscription_bp.route("/create", methods=['POST'])
@jwt_required()
def create_subscription():
    from app import db, users, razorpay_client
    from utils.utils import get_random_string
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({'error': 'User not found'}), 404
            
        user_data = user_doc.to_dict()

        payment_link_data = {
            "amount": 36500,
            "currency": "INR",
            "description": "Enliten Academy Premium Subscription",
            "reference_id": get_random_string(20),
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

        payment_link = razorpay_client.payment_link.create(data=payment_link_data)

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

@subscription_bp.route("/verify-payment", methods=['POST'])
@jwt_required()
def verify_payment():
    from app import db, users, razorpay_client
    try:
        user_id = get_jwt_identity()
        data = request.json
        
        payment_link_id = data.get('payment_link_id')
        
        if not payment_link_id:
            return jsonify({'error': 'Missing payment link ID'}), 400

        payment_link = razorpay_client.payment_link.fetch(payment_link_id)
        
        if payment_link['status'] != 'paid':
            return jsonify({
                'status': 'pending',
                'message': 'Payment not completed yet'
            }), 200

        payment_ref = db.collection('payments').document(payment_link_id)
        payment_doc = payment_ref.get()

        if not payment_doc.exists:
            return jsonify({'error': 'Payment record not found'}), 404

        payment_data = payment_doc.to_dict()
        
        if payment_data.get('payment_status') == 'completed':
            return jsonify({
                'status': 'success',
                'message': 'Payment already processed',
                'redirect': True
            })

        payment_ref.update({
            'status': 'completed',
            'payment_status': 'completed',
            'paid_at': datetime.now().isoformat(),
            'subscription_status': 'active'
        })

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

@subscription_bp.route("/check-payment", methods=['POST'])
@jwt_required()
def check_payment_status():
    from app import razorpay_client
    try:
        user_id = get_jwt_identity()
        data = request.json
        payment_link_id = data.get('payment_link_id')

        if not payment_link_id:
            return jsonify({'error': 'Missing payment link ID'}), 400

        payment_link = razorpay_client.payment_link.fetch(payment_link_id)
        
        if payment_link['status'] == 'paid':
            return verify_payment()
        
        return jsonify({
            'status': payment_link['status'],
            'message': 'Payment pending'
        })

    except Exception as e:
        print(f"Error checking payment status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@subscription_bp.route("/status", methods=['GET'])
@jwt_required()
def get_subscription_status():
    from app import db, users, razorpay_client
    try:
        user_id = get_jwt_identity()
        if not user_id:
            return jsonify({'error': 'Unauthorized'}), 401

        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return jsonify({'error': 'User not found'}), 404

        user_data = user_doc.to_dict()
        
        if user_data.get('payment_link_id'):
            try:
                payment_link = razorpay_client.payment_link.fetch(user_data['payment_link_id'])
                if payment_link['status'] == 'paid':
                    pass
            except Exception as e:
                print(f"Error checking payment link: {str(e)}")

        subscription_status = {
            'status': user_data.get('subscription_status', 'inactive'),
            'start_date': user_data.get('subscription_start_date'),
            'end_date': user_data.get('subscription_end_date'),
            'next_payment_date': user_data.get('next_payment_date'),
            'payment_link_id': user_data.get('payment_link_id')
        }

        if subscription_status['status'] == 'active' and subscription_status['end_date']:
            end_date = datetime.fromisoformat(subscription_status['end_date'])
            if end_date < datetime.now():
                subscription_status['status'] = 'expired'
                user_ref.update({
                    'subscription_status': 'expired'
                })

        encrypted_response = users.encrypt_data(json.dumps(subscription_status), user_id)
        return jsonify({'data': encrypted_response})

    except Exception as e:
        print(f"Error getting subscription status: {str(e)}")
        return jsonify({'error': str(e)}), 500
