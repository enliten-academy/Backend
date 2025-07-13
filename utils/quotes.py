import google.generativeai as genai
import json
import re

def get_quote():
    genai.configure(api_key='AIzaSyBQgUq_pscmRRw36Y7HKt3dvDTgKTQvUA4')
    model = genai.GenerativeModel('gemini-2.0-flash')

    response = model.generate_content("""
    You are a creative and emotionally intelligent AI assistant. Your task is to generate **short, powerful, and highly motivational quotes** specifically tailored for **students preparing for the TNPSC (Tamil Nadu Public Service Commission) exams**.

    These quotes must be:

    * Emotionally impactful and inspiring.
    * Written in simple and powerful language.
    * Specifically aimed at TNPSC aspirants who are feeling low, tired, or demotivated.
    * Culturally relevant and relatable to Indian or Tamil Nadu students.

    **Return the output in the following strict JSON format only json output no extra text:**
    {
      "quote": "Your motivational quote here"
    }

    ✅ Rules:

    * Quote should be **maximum 20 words**.
    * Avoid generic phrases like "Never give up" unless uniquely reworded.
    * Add Tamil Nadu or TNPSC relevance subtly (e.g., mention “dream job,” “Group exams,” “public service,” etc.).
    * You may include emotional or poetic metaphors (e.g., “Even the darkest clouds can’t stop the sunrise”).
    * Always return only **one quote per response** in **valid JSON format**.

    ---

    ### ✅ Sample Output

    {
      "quote": "Your dream badge is earned not in the exam hall, but in every late-night you didn’t quit."
    }
    """)

    # Extract JSON from text
    text = response.text.strip()

    # Optional: remove translation or anything inside parentheses
    text = re.sub(r'\([^)]*\)', '', text)

    # Parse JSON
    try:
        quote_data = json.loads(text)
    except json.JSONDecodeError:
        # Try fixing malformed JSON
        match = re.search(r'{\s*"quote"\s*:\s*"([^"]+)"\s*}', text)
        if match:
            quote_data = {"quote": match.group(1).strip()}
        else:
            quote_data={"quote":"Could not parse valid JSON from model response."}

    return quote_data
