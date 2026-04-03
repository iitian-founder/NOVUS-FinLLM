import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
print(f"Key loaded: {api_key[:10]}..." if api_key else "NO KEY")

genai.configure(api_key=api_key)

try:
    print("Testing embedding...")
    res = genai.embed_content(
        model="models/gemini-embedding-001",
        content="Hello world",
        task_type="retrieval_document"
    )
    print("Success! Embedding length:", len(res['embedding']))
except Exception as e:
    print("ERROR:", e)
