from firebase_admin import credentials, firestore, initialize_app
import json

def setup_firebase_collections():
    # Initialize Firebase Admin
    cred = credentials.Certificate('firebase-credentials.json')
    initialize_app(cred)
    db = firestore.client()
    
    # Create collections if they don't exist
    # Note: In Firebase, collections are created automatically when you add documents
    
    # Example document for testing
    test_subscription = {
        'user_id': 'test_user',
        'subscription_id': 'test_sub_123',
        'plan_id': 'plan_Q16Wi5XcnzlSAH',
        'status': 'created',
        'payment_status': 'pending',
        'created_at': '2024-03-21T00:00:00Z',
        'updated_at': '2024-03-21T00:00:00Z'
    }
    
    # Add test document (optional)
    # db.collection('subscriptions').document('test_sub_123').set(test_subscription)
    
    print("Firebase collections setup complete!")

if __name__ == '__main__':
    setup_firebase_collections() 