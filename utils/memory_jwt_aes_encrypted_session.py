import hashlib
import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import time
import json
import datetime

class JWTAESEncryptedSession:
    def __init__(self):
        # self.rsa_public_key = RSA.import_key(rsa_public_key)
        # self.rsa_private_key = RSA.import_key(rsa_private_key)
        self.aes_key_store = {}

    def add_user(self,user_id,expiry_time):
        aes_key=self.generate_aes_key()
        self.aes_key_store[user_id]={"aes_key": aes_key, "expiry": expiry_time}
    def remove_user(self,user_id):
        self.aes_key_store.pop(user_id, None)    
    def get_user(self,user_id):
        return self.aes_key_store.get(user_id)
    def get_aes_key(self,user_id):
        ct = datetime.datetime.now()

        key_data = self.aes_key_store.get(user_id)
        if not key_data or key_data["expiry"] < int(ct.timestamp()):  # If expired, remove from memory
            self.aes_key_store.pop(user_id, None)
            return {'status':'error',"error": "Session expired"}
        else:
            # return {'status':'succes',"aes_key": base64.b64encode(key_data["aes_key"]).decode()}
            return {'status':'succes',"aes_key": base64.b64encode(key_data["aes_key"]).decode()}
    def generate_aes_key(self):
        return os.urandom(32)

    def encrypt_data(self,plain_text,user_id):
        key=self.get_aes_key(user_id)
        if(key['status']=='error'):
            return {'status':'error',"data": "Session expired"}
        else:
            key=base64.b64decode(key["aes_key"])
        iv = os.urandom(12)  # 12-byte IV for AES-GCM
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
        encryptor = cipher.encryptor()
        
        encrypted_text = encryptor.update(plain_text.encode()) + encryptor.finalize()
        
        return {'status':'succes','data':base64.b64encode(iv + encryptor.tag + encrypted_text).decode()}

    def decrypt_data(self,encrypted_text,user_id):
        key=self.get_aes_key(user_id)
        if(key['status']=='error'):
            return {'status':'error',"data": "Session expired"}
        else:
            key=base64.b64decode(key["aes_key"])
        encrypted_data = base64.b64decode(encrypted_text)
        iv, tag, cipher_text = encrypted_data[:12], encrypted_data[12:28], encrypted_data[28:]

        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        
        decrypted_text = decryptor.update(cipher_text) + decryptor.finalize()
        return {'status':'succes','data':decrypted_text.decode()}

# key=generate_aes_key()
# print(f'AES Key: {key}')
# encrypted_data=encrypt_data(json.dumps({'Name':'Gokul'}),key)
# print(f'Encrypted data: {encrypted_data}')
# decrypted_data=decrypt_data(encrypted_data,key)
# print(f'decrypted data : {decrypted_data}')

# user=JWTAESEncryptedSession()
# user_id="1234"
# user.add_user(user_id,int(time.time())+180)
# print(user.get_aes_key(user_id))
# e=user.encrypt_data("Hello world",user_id)
# print(f'Encrypted: {e}')
# d=user.decrypt_data(e,"12")
# print(f'Decrypt: {d}')
