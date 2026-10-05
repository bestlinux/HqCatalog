import sys, os
sys.path.insert(0, r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog")
from dotenv import load_dotenv
load_dotenv(r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog\.env")
import gemini_service

api_key = os.getenv("GEMINI_API_KEY", "")
client_g = gemini_service.get_gemini_client(api_key)

print("Listing supported Gemini models from API...")
try:
    for m in client_g.models.list():
        name = getattr(m, 'name', '') or str(m)
        if 'gemini' in name.lower():
            print("Model:", name)
except Exception as e:
    print("Error listing models:", e)
