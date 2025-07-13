from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
import base64

class Encryption:
    def __init__(self, rsa_public_key, rsa_private_key):
        self.rsa_public_key = RSA.import_key(rsa_public_key)
        self.rsa_private_key = RSA.import_key(rsa_private_key)
        
    def generate_aes_key(self):
        return get_random_bytes(32)
    
    def encrypt_aes_key(self, aes_key):
        cipher_rsa = PKCS1_OAEP.new(self.rsa_public_key)
        return cipher_rsa.encrypt(aes_key)
    
    def decrypt_aes_key(self, encrypted_aes_key):
        cipher_rsa = PKCS1_OAEP.new(self.rsa_private_key)
        return cipher_rsa.decrypt(encrypted_aes_key)
    
    def encrypt_data(self, data, aes_key):
        cipher = AES.new(aes_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data.encode())
        return {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'nonce': base64.b64encode(cipher.nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8')
        }
    def encrypt_data_base64(self, data, aes_key):
        print(f'Data:{data}')
        """
        Encrypts data using AES encryption and returns a Base64-encoded string.
        """
        cipher = AES.new(aes_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        return {
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
            'nonce': base64.b64encode(cipher.nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8')
        }

    def decrypt_data(self, encrypted_data, aes_key):
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=base64.b64decode(encrypted_data['nonce']))
        plaintext = cipher.decrypt_and_verify(
            base64.b64decode(encrypted_data['ciphertext']),
            base64.b64decode(encrypted_data['tag'])
        )
        return plaintext.decode('utf-8') 