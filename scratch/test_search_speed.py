import sys, os, time
sys.path.insert(0, r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog")
from dotenv import load_dotenv
load_dotenv(r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog\.env")
import gemini_service
from google.genai import types

api_key = os.getenv("GEMINI_API_KEY", "")
client_g = gemini_service.get_gemini_client(api_key)

models_to_test = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest"
]

prompt = "site:guiadosquadrinhos.com \"Watchmen\" Panini. Retorne em 1 linha o roteirista e desenhista."

for m in models_to_test:
    t0 = time.time()
    try:
        chat = client_g.chats.create(
            model=m,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1
            )
        )
        resp = chat.send_message(prompt)
        print(f"[{m}] SUCCESS in {time.time()-t0:.2f}s: {resp.text[:80].strip()}")
    except Exception as e:
        print(f"[{m}] FAILED in {time.time()-t0:.2f}s: {type(e).__name__}: {e}")
