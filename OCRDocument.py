from groq import Groq
import re

class OCRDocument:
    def __init__(self):
        self.client = Groq(api_key= "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")

    def extract_text(self, file: str) -> str:
        """Extract raw OCR text from base64 image"""
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Return ONLY the raw OCR content from this image. "
                                "Do not explain, do not identify language, do not add headers. "
                                "Just output the plain text exactly as seen."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{file}",
                            },
                        },
                    ],
                }
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
        )

        response = chat_completion.choices[0].message.content or ""

        if "The final answer is:" in response:
            response = response.split("The final answer is:")[-1].strip()

        response = re.sub(r"##.*\n", "", response)

        # Remove leading/trailing whitespace
        response = response.strip()

        return response
