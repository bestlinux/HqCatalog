import sys, time, os, re, urllib.parse
sys.path.insert(0, r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog")

# Carrega chave do .env se existir
from dotenv import load_dotenv
load_dotenv(r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog\.env")

import gemini_service

api_key = os.getenv("GEMINI_API_KEY", "")
print(f"[1] API KEY configurada: {bool(api_key)} (len={len(api_key)})", flush=True)

titulo = "Watchmen"
edicao = "1"
editora = "Panini"

# TESTE 1: Scraping direto do Guia dos Quadrinhos
t_start = time.time()
print("\n--- TESTE ETAPA 1: Scraping HTTP Guia dos Quadrinhos ---", flush=True)
t0 = time.time()
query_params = {
    "tit": titulo,
    "num": "1",
    "edi": editora,
    "cat": "", "gen": "", "sta": "", "for": "", "capa": "0", "mesi": "", "anoi": "", "mesf": "", "anof": ""
}
url_gq = f"http://www.guiadosquadrinhos.com/busca-avancada-resultado.aspx?{urllib.parse.urlencode(query_params)}"
import requests
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "http://www.guiadosquadrinhos.com/"
}
try:
    r = requests.get(url_gq, headers=headers, timeout=6)
    print(f"Scraping status: {r.status_code}, length: {len(r.text)} in {time.time()-t0:.2f}s", flush=True)
except Exception as e:
    print(f"Scraping error: {e} in {time.time()-t0:.2f}s", flush=True)

# TESTE 2: Modelos Gemini com Google Search
print("\n--- TESTE ETAPA 2: Modelos Gemini com Google Search ---", flush=True)
from google import genai
from google.genai import types

client_g = gemini_service.get_gemini_client(api_key)

test_models = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

prompt_test = f"""Consulte no Guia dos Quadrinhos: site:guiadosquadrinhos.com "Watchmen" 1 Panini
Retorne JSON com: roteiro, desenho, preco_capa, resumo, capa_url"""

for mod in test_models:
    t_mod = time.time()
    try:
        print(f"Testando model: '{mod}' com Search Grounding...", end="", flush=True)
        resp = client_g.models.generate_content(
            model=mod,
            contents=prompt_test,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1
            )
        )
        dur = time.time() - t_mod
        txt = (resp.text or "")[:100].replace("\n", " ")
        print(f" -> SUCESSO em {dur:.2f}s! ({txt})", flush=True)
        break
    except Exception as ex_m:
        dur = time.time() - t_mod
        print(f" -> FALHA em {dur:.2f}s: {type(ex_m).__name__}: {str(ex_m)[:80]}", flush=True)

# TESTE 3: Buscar Capas Online (SerpApi / iTunes / OpenLibrary)
print("\n--- TESTE ETAPA 3: Buscar Capas Online ---", flush=True)
t_capas = time.time()
capas = gemini_service.buscar_capas_online(titulo, edicao, editora, limite=4)
print(f"Capas encontradas: {len(capas)} em {time.time()-t_capas:.2f}s", flush=True)

print(f"\nTEMPO TOTAL DO BENCHMARK: {time.time()-t_start:.2f}s", flush=True)
