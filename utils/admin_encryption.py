from cryptography.fernet import Fernet
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os
from datetime import datetime, timedelta
import jwt

class AdminEncryption:
    def __init__(self):
        self._salt = b'enliten_fixed_salt_123'
        self._fernet = None
        self._key = None
        self._jwt_secret = "enliten_admin_secret_key"  # In production, use environment variable
        
    def login(self, username: str, password: str) -> str | None:
        """Login and generate encryption key. Returns JWT token if successful, None if failed"""
        VALID_USERNAME = "admin"
        VALID_PASSWORD = "admin123"
        
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            # Generate encryption key
            self._key = self._generate_key(password.encode())
            self._fernet = Fernet(self._key)
            
            # Generate JWT token
            token_data = {
                'username': username,
                'exp': datetime.utcnow() + timedelta(hours=24)  # Token expires in 24 hours
            }
            token = jwt.encode(token_data, self._jwt_secret, algorithm='HS256')
            return token
        return None

    def verify_token(self, token: str) -> bool:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=['HS256'])
            # Check if token has expired
            exp_timestamp = payload['exp']
            if datetime.utcnow().timestamp() > exp_timestamp:
                return False
            return True
        except jwt.InvalidTokenError:
            return False

    def _generate_key(self, password: bytes):
        """Generate a key using PBKDF2 with provided password"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

    def encrypt(self, data: str) -> str:
        """Encrypt a string using Fernet symmetric encryption"""
        if not self._fernet:
            raise Exception("Please login first")
        try:
            return self._fernet.encrypt(data.encode()).decode()
        except Exception as e:
            raise Exception(f"Encryption failed: {str(e)}")

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a Fernet-encrypted string"""
        if not self._fernet:
            raise Exception("Please login first")
        try:
            return self._fernet.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            raise Exception(f"Decryption failed: {str(e)}")