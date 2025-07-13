from datetime import datetime, timedelta

class MemoryStore:
    def __init__(self):
        self.store = {}
    
    def setex(self, key, seconds, value):
        expiry = datetime.now() + timedelta(seconds=seconds)
        self.store[key] = {
            'value': value,
            'expiry': expiry
        }
        return True
    
    def get(self, key):
        data = self.store.get(key)
        if not data:
            return None
            
        if datetime.now() > data['expiry']:
            del self.store[key]
            return None
            
        return data['value']
    
    def delete(self, key):
        if key in self.store:
            del self.store[key]
        return True 