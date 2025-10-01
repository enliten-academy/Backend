from supabase import create_client, Client
from datetime import datetime, timedelta
import uuid
import os
# Import APIError to catch exceptions from older client versions
from postgrest.exceptions import APIError

# -------------------------
# Configure Supabase client
# -------------------------
# It's better practice to load these from environment variables
# For example: os.environ.get("SUPABASE_URL")
SUPABASE_URL = "https://vtwvmkoywlikcbwpvrbx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ0d3Zta295d2xpa2Nid3B2cmJ4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMjYyODksImV4cCI6MjA2MDgwMjI4OX0.ovdzTWi15dKb18jGvBATin0-s27MvFYYBc9490kAfi8"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Function 1: Create a session
# -------------------------
def create_session(user_id, aes_key_b64, expire_minutes=None):
    """
    Inserts a new session into Supabase.
    """
    # Convert expire_minutes to ISO string
    session_expire = None
    if expire_minutes:
        session_expire = (datetime.utcnow() + timedelta(minutes=expire_minutes)).isoformat()

    data_to_insert = {
        "user_id": user_id,
        "aes_key": aes_key_b64
    }
    if session_expire:
        data_to_insert["session_expire"] = session_expire

    try:
        response = supabase.table("user_sessions").insert(data_to_insert).execute()

        # For newer supabase-py versions (v1+), check the .error attribute.
        # hasattr() prevents an error if the attribute doesn't exist.
        if hasattr(response, 'error') and response.error:
            print("Error creating session:", response.error)
            return None

        # On success, the data is in the .data attribute
        if response.data:
            return response.data[0]
        
        return None
    # --- CORRECTION ---
    # Older versions of the client (< v1.0) raise an APIError exception
    # instead of having an .error attribute on the response object.
    except APIError as e:
        print(f"Error creating session: {e.message}")
        return None
    except Exception as e:
        # Catch any other unexpected errors
        print(f"An unexpected error occurred: {e}")
        return None


# -------------------------
# Function 2: Retrieve active sessions
# -------------------------
def get_active_sessions(user_id):
    """
    Retrieves all non-expired sessions for a given user.
    """
    try:
        response = (
            supabase.table("user_sessions")
            .select("*")
            .eq("user_id", user_id)
            .gt("session_expire", datetime.utcnow().isoformat())
            .execute()
        )
        
        # For newer supabase-py versions (v1+), check the .error attribute.
        if hasattr(response, 'error') and response.error:
            print("Error fetching sessions:", response.error)
            return []

        return response.data
    # --- CORRECTION ---
    # Older versions of the client (< v1.0) raise an APIError exception.
    except APIError as e:
        print(f"Error fetching sessions: {e.message}")
        return []
    except Exception as e:
        # Catch any other unexpected errors
        print(f"An unexpected error occurred: {e}")
        return []


# -------------------------
# Example usage
# -------------------------
# if __name__ == "__main__":
#     test_user_id = f"firebase-user-{uuid.uuid4()}"
#     test_aes_key = "randomAESKeyForTesting123"

#     print(f"Creating a session for user: {test_user_id}")
#     # Create a session (expires in 60 minutes)
#     session = create_session(test_user_id, test_aes_key, expire_minutes=60)
    
#     if session:
#         print("Successfully created session:", session)

#         # Fetch active sessions
#         print(f"\nFetching active sessions for user: {test_user_id}")
#         active_sessions = get_active_sessions(test_user_id)
#         print("Found active sessions:", active_sessions)
#     else:
#         print("Failed to create a session.")

