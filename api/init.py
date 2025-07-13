from config import Config

def init_app():
    """Initialize application dependencies"""
    try:
        # Initialize Firebase
        Config.init_firebase()
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Error initializing Firebase: {str(e)}")
        if Config.ENVIRONMENT != 'production':
            print("Continuing in development mode without Firebase")
        else:
            raise 