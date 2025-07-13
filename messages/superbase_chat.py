from supabase import create_client
import os
from typing import List, Dict

class SupabaseChatStorage:
    def __init__(self):
        self.client = create_client(
            supabase_url="https://vtwvmkoywlikcbwpvrbx.supabase.co",
            supabase_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ0d3Zta295d2xpa2Nid3B2cmJ4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyMjYyODksImV4cCI6MjA2MDgwMjI4OX0.ovdzTWi15dKb18jGvBATin0-s27MvFYYBc9490kAfi8"
        )
    
    def create_conversation(self, user_id: str, title: str = "New Chat") -> str:
        """Create a new conversation and return its ID"""
        response = self.client.table('conversations').insert({
            "user_id": user_id,
            "title": title
        }).execute()
        return response.data[0]['id']
    
    def add_message(self, conversation_id: str, content: str, sender: str, user_id: str, tokens: int = None) -> Dict:
        """Add a message to a conversation"""
        message_data = {
            "conversation_id": conversation_id,
            "content": content,
            "sender": sender,
            "tokens": tokens,
            "user_id":user_id
        }
        
        # Insert message
        message_response = self.client.table('messages').insert(message_data).execute()
        
        # Update conversation's updated_at
        self.client.table('conversations').update({
            "updated_at": "now()"
        }).eq('id', conversation_id).execute()
        
        return message_response.data[0]
    
    def get_messages(self, conversation_id: str,user_id: str, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Retrieve messages from a conversation"""
        response = self.client.table('messages').select("*").eq(
            'conversation_id', conversation_id
        ).eq('user_id', user_id).order('created_at', desc=False).limit(limit).offset(offset).execute()
        return response.data
    
    def get_conversations(self, user_id: str, limit: int = 20) -> List[Dict]:
        """Get all conversations for a user"""
        response = self.client.table('conversations').select("*").eq(
            'user_id', user_id
        ).order('updated_at', desc=True).limit(limit).execute()
        return response.data
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all its messages (cascade)"""
        response = self.client.table('conversations').delete().eq(
            'id', conversation_id
        ).execute()
        return len(response.data) > 0