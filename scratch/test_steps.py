import sys, os, time
sys.path.insert(0, r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog")
from dotenv import load_dotenv
load_dotenv(r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog\.env")
import gemini_service

api_key = os.getenv("GEMINI_API_KEY", "")

print("[1] Iniciando teste passo a passo...", flush=True)

# Passo A: Gemini call
t0 = time.time()
print("[A] Testando chamada Gemini IA...", flush=True)
from google.genai import types
client_g = gemini_service.get_gemini_client(api_key)

chat = client_g.chats.create(
    model="gemini-3.1-flash-lite",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1
    )
)
resp_chat = chat.send_message('Consulte no Guia dos Quadrinhos: site:guiadosquadrinhos.com "Watchmen" 1 Panini')
print(f"[A] Gemini IA concluído em {time.time()-t0:.2f}s! Text len={len(resp_chat.text or '')}", flush=True)

# Passo B: Buscar capas online
t0 = time.time()
print("[B] Testando buscar_capas_online...", flush=True)
capas = gemini_service.buscar_capas_online("Watchmen", "1", "Panini", limite=4)
print(f"[B] buscar_capas_online concluído em {time.time()-t0:.2f}s! Encontrou {len(capas)} capas", flush=True)
for c in capas:
    print(f"   -> Fonte: {c.get('fonte')} | URL: {c.get('url')[:60]}", flush=True)

# Passo C: Baixar imagens
t0 = time.time()
print("[C] Testando download das capas encontradas...", flush=True)
for i, c in enumerate(capas):
    t_c = time.time()
    b64 = gemini_service.baixar_imagem_url_base64(c.get('url'), timeout=5)
    print(f"   -> Capa #{i+1} baixada em {time.time()-t_c:.2f}s (b64={b64.startswith('data:image')})", flush=True)
print(f"[C] Total download capas em {time.time()-t0:.2f}s", flush=True)
