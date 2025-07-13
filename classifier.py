import google.generativeai as genai
import json

global model

def create_cache():
    genai.configure(api_key='AIzaSyBQgUq_pscmRRw36Y7HKt3dvDTgKTQvUA4')

    try:
        document = genai.upload_file(path="database/mcet_infra.pdf")
        cache = genai.caching.CachedContent.create(
            model="gemini-1.5-flash-001",
            system_instruction="""
    Classify the given text into one of the following categories: ["normal chat", "book search / book recommendation"].  

    **Classification Rules:**  
    1. **"normal chat"** (Generate a direct response) if the query involves:  
    - Asking about an **author** (e.g., "Who is <author>?", "Tell me about <author>").  
    - Requesting a **book summary** (e.g., "Summarize <book>", "What is <book> about?").  
    - General literary discussions (e.g., "What is the theme of <book>?", "What are the best books by <author>?").  
    - Classify as "normal chat" if the query is general conversation, greetings, unrelated topics, or discussions outside book-related context.  
    2. **"book search / book recommendation"** (Redirect to FAISS) if the query involves:  
    - Searching for books by **title, author, genre, ISBN**.  
    - Asking for book recommendations.  
    - Queries explicitly mentioning "Find", "Search", "Recommend", "List books by <author/genre>", "Show books related to <topic>", etc.  


    **Return JSON with the following fields:**  
    - `category`: The identified category.  
    - `confidence`: A confidence score (0-1) for classification accuracy.  
    - `response`:  
    - If `"category": "normal chat"`, generate a relevant response.  
    - If `"category": "book search / book recommendation"`, detaily reframe the query to fit into FAISS search.  
    - `result_count`: If the user explicitly requests a specific number of book results, include that number. Otherwise, give 0.  

    **Additional Handling:**  
    For queries involving personal details, use this predefined information:  
    - **Name**: Libo - A Specialized AI Model for Libraries  
    - **Developer Name**: Gokulakrishnan  
    - **Department**: CSE - Cyber Security  
    - **Gender**: Male  
    - **Institution**: Dr. Mahalingam College of Engineering and Technology, Pollachi  

    **User Query:**
    """,
            contents=[document],
        )

        global model
        model = genai.GenerativeModel.from_cached_content(cache)
        return True
    except Exception as e:
        print(f"Cache creation failed: {e}")
        return False

# model = genai.GenerativeModel('gemini-1.5-flash',system_instruction="""
# Classify the given text into one of the following categories: ["normal chat", "book search / book recommendation"].  

# **Classification Rules:**  
# 1. **"normal chat"** (Generate a direct response) if the query involves:  
#    - Asking about an **author** (e.g., "Who is <author>?", "Tell me about <author>").  
#    - Requesting a **book summary** (e.g., "Summarize <book>", "What is <book> about?").  
#    - General literary discussions (e.g., "What is the theme of <book>?", "What are the best books by <author>?").  
#    - Classify as "normal chat" if the query is general conversation, greetings, unrelated topics, or discussions outside book-related context.  
# 2. **"book search / book recommendation"** (Redirect to FAISS) if the query involves:  
#    - Searching for books by **title, author, genre, ISBN**.  
#    - Asking for book recommendations.  
#    - Queries explicitly mentioning "Find", "Search", "Recommend", "List books by <author/genre>", "Show books related to <topic>", etc.  


# **Return JSON with the following fields:**  
# - `category`: The identified category.  
# - `confidence`: A confidence score (0-1) for classification accuracy.  
# - `response`:  
#   - If `"category": "normal chat"`, generate a relevant response.  
#   - If `"category": "book search / book recommendation"`, detaily reframe the query to fit into FAISS search.  
# - `result_count`: If the user explicitly requests a specific number of book results, include that number. Otherwise, give 0.  

# **Additional Handling:**  
# For queries involving personal details, use this predefined information:  
# - **Name**: Libo - A Specialized AI Model for Libraries  
# - **Developer Name**: Gokulakrishnan  
# - **Department**: CSE - Cyber Security  
# - **Gender**: Male  
# - **Institution**: Dr. Mahalingam College of Engineering and Technology, Pollachi  

# **User Query:**
# """)



create_cache()
def classification(query):
    count = 0
    max_retries = 2
    
    while count < max_retries:
        try:
            # prompt = f"""Classify the given text into one of the following categories: [normal chat,book search / book recommendation]. 
            # Return the result in JSON format with fields: category, confidence and response only if the category is normal chat,give the replay response to the query. else leave the response blank.if the query is related to personal details use this details:\n
            # Name: Libo - An Specialized AI modal for library\n
            # Developer Name: Gokulakrishnan\n
            # Department: CSE - Cyber Security\n
            # Gender: Male\n
            # Instution:Dr. Mahalingam College of Engineering and Technology at Pollachi

            # text: {query}"""
            

            response = model.generate_content(query)
            result = json.loads(response.text.replace('```json', '').replace('```', '').strip())
            
            return {
                'label': result['category'],
                'confidence': result['confidence'],
                'response': result['response'],
                'result_count': result.get('result_count', 3)  # Use .get() with default
            }
        except Exception as e:
            count += 1
            print(f"Classification error: {e}")
            print(f"Retrying {count}/{max_retries}")
            
            # Add retry loop for cache creation
            cache_retries = 0
            while cache_retries < max_retries:
                if create_cache():  # If cache creation succeeds
                    break  # Exit cache retry loop and continue with query
                cache_retries += 1
                print(f"Cache creation retry {cache_retries}/{max_retries}")
            
            if cache_retries == max_retries:  # If all cache retries failed
                break  # Exit main retry loop
    
    # Improved fallback response
    return {
        'label': 'normal chat',  # Default to one category
        'confidence': 0.5,  # Lower confidence for fallback
        'response': 'I apologize, but I encountered an error processing your request.',
        'result_count': 0
    } 