import sys, os, time
sys.path.insert(0, r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog")
from dotenv import load_dotenv
load_dotenv(r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog\.env")
import gemini_service

api_key = os.getenv("GEMINI_API_KEY", "")

t0 = time.time()
print("Buscando 'Watchmen' com gemini-3.1-flash-lite...", flush=True)
res1 = gemini_service.buscar_dados_guia_dos_quadrinhos("Watchmen", "1", "Panini", api_key=api_key, modelo="gemini-3.1-flash-lite")
dur1 = time.time() - t0
print(f"Watchmen finalizado em {dur1:.2f}s! Roteiro: {res1.get('roteiro')[:30]} | Metodo: {res1.get('metodo')}", flush=True)

t0 = time.time()
print("Buscando 'Batman' com gemini-3.8-flash...", flush=True)
res2 = gemini_service.buscar_dados_guia_dos_quadrinhos("Batman", "1", "Panini", api_key=api_key, modelo="gemini-3.8-flash")
dur2 = time.time() - t0
print(f"Batman finalizado em {dur2:.2f}s! Roteiro: {res2.get('roteiro')[:30]} | Metodo: {res2.get('metodo')}", flush=True)
