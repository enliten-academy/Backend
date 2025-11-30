from google import genai
from google.genai import types
import json
from datetime import datetime
import pytz
timezone = pytz.timezone('Asia/Kolkata')

class CurrentAffairsSearch:
    def __init__(self, api_key):
        self.client = genai.Client(api_key=api_key)
        self.categories = [
            "Politics",
            "Economy",
            "Sports",
            "Science_Technology",
            "Environment",
            "Education",
            "Culture",
            "Health",
            "Infrastructure",
            "International_Relations"
        ]
    
    def generate_search_query(self, category):
        return f"Latest Tamil Nadu {category} news and developments on {datetime.now(timezone).strftime('%Y-%m-%d')}."

    def format_response(self, response_text):
        # Basic cleaning and formatting of the response
        if not response_text:
            return []
        
        # Split by newlines and filter empty lines
        items = [item.strip() for item in response_text.split('\n') if item.strip()]
        
        # Format each item with date if available
        formatted_items = []
        for item in items:
            # Try to extract date if present
            date_str = datetime.now(timezone).strftime("%Y-%m-%d")
            formatted_items.append({
                "date": date_str,
                "content": item
            })
        
        return formatted_items

    def get_current_affairs(self):
        current_affairs = {
            "timestamp": datetime.now(timezone).isoformat(),
            "region": "Tamil Nadu",
            "categories": {}
        }

        for category in self.categories:
            try:
                response = self.client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=self.generate_search_query(category),
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(
                            google_search=types.GoogleSearchRetrieval
                        )],
                        temperature=0.2  # Keep responses factual
                    )
                )
                
                # Extract text from response
                category_content = response.candidates[0].content.parts[0].text
                
                # Format the response
                formatted_content = self.format_response(category_content)
                
                current_affairs["categories"][category] = {
                    "news_items": formatted_content,
                    "total_items": len(formatted_content)
                }
                
            except Exception as e:
                current_affairs["categories"][category] = {
                    "error": str(e),
                    "news_items": [],
                    "total_items": 0
                }

        return current_affairs

# def main():
#     # Initialize with your API key
#     api_key = "AIzaSyBQgUq_pscmRRw36Y7HKt3dvDTgKTQvUA4"
#     search = CurrentAffairsSearch(api_key)
    
#     # Get current affairs
#     results = search.get_current_affairs()
    
#     # Save to JSON file
#     with open('current_affairs.json', 'w', encoding='utf-8') as f:
#         json.dump(results, f, ensure_ascii=False, indent=2)
    
#     return results

# if __name__ == "__main__":
#     main()
