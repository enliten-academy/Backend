import hashlib
import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import time
import json
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
from postgrest.exceptions import APIError
import threading
from typing import Optional, Dict, Any

# -------------------------
# Configure Supabase client
# -------------------------
SUPABASE_URL = "https://vtwvmkoywlikcbwpvrbx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ0d3Zta295d2xpa2Nid3B2cmJ4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMjYyODksImV4cCI6MjA2MDgwMjI4OX0.ovdzTWi15dKb18jGvBATin0-s27MvFYYBc9490kAfi8"

# Create a single supabase client instance with connection pooling
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class JWTAESEncryptedSession:
    def __init__(self):
        self.supabase = supabase
        # In-memory cache for AES keys
        self.aes_key_cache = {}
        # Lock for thread-safe cache operations
        self.cache_lock = threading.Lock()
        # Cache TTL in seconds (5 minutes by default)
        self.cache_ttl = 300
        # Track last database access time per user to avoid rapid queries
        self.last_db_access = {}
        # Minimum time between database queries per user (in seconds)
        self.db_query_cooldown = 10
        
    def generate_aes_key(self):
        """Generate a new AES key"""
        return os.urandom(32)
    
    def _format_timestamp(self, unix_timestamp):
        """Convert Unix timestamp to ISO format with timezone for Supabase"""
        dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M:%S+00')
    
    def _get_current_timestamp(self):
        """Get current timestamp in Supabase format"""
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S+00')
    
    def _get_from_cache(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user data from in-memory cache"""
        with self.cache_lock:
            cache_entry = self.aes_key_cache.get(user_id)
            if cache_entry:
                current_time = time.time()
                # Check if cache entry is still valid
                if cache_entry['expiry'] > current_time and \
                   cache_entry['cache_time'] + self.cache_ttl > current_time:
                    print(f"Cache hit for user {user_id}")
                    return cache_entry
                else:
                    # Remove expired entry
                    print(f"Cache expired for user {user_id}")
                    del self.aes_key_cache[user_id]
            return None
    
    def _set_cache(self, user_id: str, aes_key: str, expiry: float):
        """Set user data in cache"""
        with self.cache_lock:
            self.aes_key_cache[user_id] = {
                'aes_key': aes_key,
                'expiry': expiry,
                'cache_time': time.time()
            }
            print(f"Cache set for user {user_id}")
    
    def _clear_cache(self, user_id: str):
        """Clear cache for a specific user"""
        with self.cache_lock:
            if user_id in self.aes_key_cache:
                del self.aes_key_cache[user_id]
                print(f"Cache cleared for user {user_id}")
    
    def _can_query_db(self, user_id: str) -> bool:
        """Check if we can query the database (rate limiting)"""
        current_time = time.time()
        last_access = self.last_db_access.get(user_id, 0)
        if current_time - last_access >= self.db_query_cooldown:
            self.last_db_access[user_id] = current_time
            return True
        return False
    
    def _fetch_from_db_with_retry(self, user_id: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Fetch user session from database with retry logic"""
        for attempt in range(max_retries):
            try:
                current_time = self._get_current_timestamp()
                
                response = (
                    self.supabase.table("user_sessions")
                    .select("aes_key, session_expire")
                    .eq("user_id", user_id)
                    .gte("session_expire", current_time)
                    .limit(1)  # Add limit to reduce load
                    .execute()
                )
                
                if hasattr(response, 'error') and response.error:
                    print(f"Database error (attempt {attempt + 1}): {response.error}")
                    if attempt < max_retries - 1:
                        time.sleep(1 * (attempt + 1))  # Exponential backoff
                        continue
                    return None
                
                if response.data and len(response.data) > 0:
                    session = response.data[0]
                    # Parse expiry time
                    expire_str = session['session_expire']
                    if '+' in expire_str:
                        expire_str = expire_str.split('+')[0]
                    elif 'Z' in expire_str:
                        expire_str = expire_str.replace('Z', '')
                    
                    expiry_dt = datetime.strptime(expire_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                    expiry_timestamp = expiry_dt.replace(tzinfo=timezone.utc).timestamp()
                    
                    # Cache the result
                    self._set_cache(user_id, session['aes_key'], expiry_timestamp)
                    
                    return {
                        'aes_key': session['aes_key'],
                        'expiry': expiry_timestamp
                    }
                
                return None
                
            except (ConnectionError, TimeoutError) as e:
                print(f"Connection error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
                    continue
                return None
            except Exception as e:
                print(f"Unexpected error fetching from DB (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
                    continue
                return None
        
        return None
    
    def add_user(self, user_id, expiry_time):
        """Add a user with AES key to Supabase and cache"""
        aes_key = self.generate_aes_key()
        aes_key_b64 = base64.b64encode(aes_key).decode()
        
        # Store in cache immediately
        self._set_cache(user_id, aes_key_b64, float(expiry_time))
        
        # Convert Unix timestamp to Supabase format
        expiry_datetime = self._format_timestamp(expiry_time)
        
        # Async store to database (don't wait for it)
        def store_to_db():
            try:
                # First, remove any existing sessions for this user
                self.supabase.table("user_sessions").delete().eq("user_id", user_id).execute()
                
                # Insert new session
                response = self.supabase.table("user_sessions").insert({
                    "user_id": user_id,
                    "aes_key": aes_key_b64,
                    "session_expire": expiry_datetime
                }).execute()
                
                if hasattr(response, 'error') and response.error:
                    print(f"Error adding user to DB: {response.error}")
                else:
                    print(f"User {user_id} added to database")
                    
            except Exception as e:
                print(f"Error storing user to DB: {e}")
        
        # Run database operation in background thread
        threading.Thread(target=store_to_db, daemon=True).start()
        
        return True
    
    def remove_user(self, user_id):
        """Remove a user's sessions from cache and Supabase"""
        # Clear from cache first
        self._clear_cache(user_id)
        
        # Then remove from database
        try:
            response = self.supabase.table("user_sessions").delete().eq("user_id", user_id).execute()
            
            if hasattr(response, 'error') and response.error:
                print(f"Error removing user from DB: {response.error}")
                return False
                
            return True
            
        except Exception as e:
            print(f"Error removing user: {e}")
            return False
    
    def get_user(self, user_id):
        """Get user session data from cache or Supabase"""
        # First check cache
        cache_data = self._get_from_cache(user_id)
        if cache_data:
            return {
                "aes_key": base64.b64decode(cache_data['aes_key']),
                "expiry": cache_data['expiry']
            }
        
        # If not in cache and we can query DB, fetch from database
        if self._can_query_db(user_id):
            db_data = self._fetch_from_db_with_retry(user_id)
            if db_data:
                return {
                    "aes_key": base64.b64decode(db_data['aes_key']),
                    "expiry": db_data['expiry']
                }
        else:
            print(f"Rate limited for user {user_id}, skipping DB query")
        
        return None
    def get_active_sessions_id(self,user_id):
        current_time = time.time()

        # 1. Try cache
        cache_data = self._get_from_cache(user_id)
        if cache_data:
            if cache_data['expiry'] > current_time:
                return {'status': 'success'}
            else:
                self._clear_cache(user_id)
                return {'status': 'error', "error": "Session expired"}

        # 2. Try DB if not rate-limited
        if not self._can_query_db(user_id):
            return {'status': 'error', "error": "Rate limited, please try again later"}
        print("Cache failed....")
        db_data = self._fetch_from_db_with_retry(user_id)
        if db_data:
            if db_data['expiry'] > current_time:
                print("DB succes")
                return {'status': 'success'}
            else:
                return {'status': 'error', "error": "Session expired"}

        # 3. If nothing found
        return {'status': 'error', "error": "Session not found"}
    def get_aes_key(self, user_id):
        """Get AES key for a user from cache or Supabase"""
        current_time = time.time()

        # 1. Try cache
        cache_data = self._get_from_cache(user_id)
        if cache_data:
            if cache_data['expiry'] > current_time:
                return {'status': 'success', "aes_key": cache_data['aes_key']}
            else:
                self._clear_cache(user_id)
                return {'status': 'error', "error": "Session expired"}

        # 2. Try DB if not rate-limited
        if not self._can_query_db(user_id):
            return {'status': 'error', "error": "Rate limited, please try again later"}
        print("Cache failed....")
        db_data = self._fetch_from_db_with_retry(user_id)
        if db_data:
            if db_data['expiry'] > current_time:
                return {'status': 'success', "aes_key": db_data['aes_key']}
            else:
                return {'status': 'error', "error": "Session expired"}

        # 3. If nothing found
        return {'status': 'error', "error": "Session not found"}

    
    def encrypt_data(self, plain_text, user_id):
        """Encrypt data using user's AES key"""
        key = self.get_aes_key(user_id)
        if key['status'] == 'error':
            return {'status': 'error', "data": key.get('error', 'Session expired')}
        else:
            key = base64.b64decode(key["aes_key"])
            
        iv = os.urandom(12)  # 12-byte IV for AES-GCM
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
        encryptor = cipher.encryptor()
        
        encrypted_text = encryptor.update(plain_text.encode()) + encryptor.finalize()
        
        return {'status': 'succes', 'data': base64.b64encode(iv + encryptor.tag + encrypted_text).decode()}
    
    def decrypt_data(self, encrypted_text, user_id):
        """Decrypt data using user's AES key"""
        key = self.get_aes_key(user_id)
        if key['status'] == 'error':
            return {'status': 'error', "data": key.get('error', 'Session expired')}
        else:
            key = base64.b64decode(key["aes_key"])
            
        encrypted_data = base64.b64decode(encrypted_text)
        
        # Frontend format: IV (12 bytes) + ciphertext+tag (combined by AES-GCM)
        iv = encrypted_data[:12]
        ciphertext_and_tag = encrypted_data[12:]
        
        # Extract tag (last 16 bytes) and ciphertext
        tag = ciphertext_and_tag[-16:]
        cipher_text = ciphertext_and_tag[:-16]
        
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        
        try:
            decrypted_text = decryptor.update(cipher_text) + decryptor.finalize()
            return {'status': 'succes', 'data': decrypted_text.decode()}
        except Exception as e:
            print(f"[Decryption Error] {str(e)}")
            return {'status': 'error', 'data': f'Decryption failed: {str(e)}'}
    
    def cleanup_expired_cache(self):
        """Periodically clean up expired entries from cache"""
        with self.cache_lock:
            current_time = time.time()
            expired_users = [
                user_id for user_id, data in self.aes_key_cache.items()
                if data['expiry'] < current_time or data['cache_time'] + self.cache_ttl < current_time
            ]
            for user_id in expired_users:
                del self.aes_key_cache[user_id]
                print(f"Cleaned up expired cache for user {user_id}")


# Create a singleton instance
_session_manager = None
_session_lock = threading.Lock()

def get_session_manager() -> JWTAESEncryptedSession:
    """Get or create the singleton session manager"""
    global _session_manager
    if _session_manager is None:
        with _session_lock:
            if _session_manager is None:
                _session_manager = JWTAESEncryptedSession()
    return _session_manager


# Helper functions
def create_session(user_id, expire_minutes=30):
    """Create a new session for a user"""
    session = get_session_manager()
    expiry_time = int(time.time()) + (expire_minutes * 60)
    success = session.add_user(user_id, expiry_time)
    return success

def get_active_sessions(user_id):
    """Get active sessions for a user (from cache first, then DB)"""
    session = get_session_manager()
    
    # Check cache first
    cache_data = session._get_from_cache(user_id)
    if cache_data:
        return [{
            'user_id': user_id,
            'aes_key': cache_data['aes_key'],
            'session_expire': datetime.fromtimestamp(cache_data['expiry'], tz=timezone.utc).isoformat()
        }]
    
    # If not in cache, query database
    try:
        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S+00')
        
        response = (
            supabase.table("user_sessions")
            .select("*")
            .eq("user_id", user_id)
            .gte("session_expire", current_time)
            .limit(1)
            .execute()
        )
        
        if hasattr(response, 'error') and response.error:
            print("Error fetching sessions:", response.error)
            return []
        
        # Cache the results if found
        if response.data and len(response.data) > 0:
            for session_data in response.data:
                expire_str = session_data['session_expire']
                if '+' in expire_str:
                    expire_str = expire_str.split('+')[0]
                elif 'Z' in expire_str:
                    expire_str = expire_str.replace('Z', '')
                
                expiry_dt = datetime.strptime(expire_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                expiry_timestamp = expiry_dt.replace(tzinfo=timezone.utc).timestamp()
                
                session._set_cache(user_id, session_data['aes_key'], expiry_timestamp)
        
        return response.data
        
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []


# Periodic cleanup task (run in background)
def start_cache_cleanup_task(interval_seconds=60):
    """Start a background task to clean up expired cache entries"""
    def cleanup_task():
        session = get_session_manager()
        while True:
            time.sleep(interval_seconds)
            try:
                session.cleanup_expired_cache()
            except Exception as e:
                print(f"Error in cache cleanup task: {e}")
    
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()


# Start the cleanup task when the module is imported
start_cache_cleanup_task()


# Example usage
if __name__ == "__main__":
    # Use singleton session manager
    user = get_session_manager()
    user_id = "test_user_1234"
    
    print("Adding user with 3 minute expiry...")
    success = user.add_user(user_id, int(time.time()) + 180)
    if success:
        print("User added successfully")
    
    # First call - will use cache
    print("\nFirst AES key request (from cache):")
    aes_key_response = user.get_aes_key(user_id)
    print(f"AES Key response: {aes_key_response}")
    
    # Second call - will use cache
    print("\nSecond AES key request (from cache):")
    aes_key_response = user.get_aes_key(user_id)
    print(f"AES Key response: {aes_key_response}")
    
    if aes_key_response['status'] == 'succes':
        # Encrypt data
        print("\nEncrypting data...")
        e = user.encrypt_data("Hello world", user_id)
        print(f'Encrypted: {e}')
        
        if e['status'] == 'succes':
            # Decrypt data
            print("\nDecrypting data...")
            d = user.decrypt_data(e['data'], user_id)
            print(f'Decrypted: {d}')
    
    # Get active sessions
    print("\nGetting active sessions...")
    sessions = get_active_sessions(user_id)
    print(f'Active sessions: {sessions}')