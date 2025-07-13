import google.generativeai as genai

def ai_chat(query):
    genai.configure(api_key='AIzaSyBQgUq_pscmRRw36Y7HKt3dvDTgKTQvUA4')
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Generate response
    response = model.generate_content(query)
    
    return response.text