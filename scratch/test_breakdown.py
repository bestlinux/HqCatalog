import sys, os, time
sys.path.insert(0, r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog")
from dotenv import load_dotenv
load_dotenv(r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog\.env")
import gemini_service

api_key = os.getenv("GEMINI_API_KEY", "")

# Instrumenting inside gemini_service
orig_baixar = gemini_service.baixar_imagem_url_base64
def logged_baixar(url, *args, **kwargs):
    t0 = time.time()
    res = orig_baixar(url, *args, **kwargs)
    print(f"  [IMG_DOWNLOAD] {url[:60]}... took {time.time()-t0:.2f}s (res len={len(res)})", flush=True)
    return res
gemini_service.baixar_imagem_url_base64 = logged_baixar

orig_capas = gemini_service.buscar_capas_online
def logged_capas(*args, **kwargs):
    t0 = time.time()
    res = orig_capas(*args, **kwargs)
    print(f"  [BUSCAR_CAPAS] took {time.time()-t0:.2f}s (found {len(res)})", flush=True)
    return res
gemini_service.buscar_capas_online = logged_capas

t_tot = time.time()
print("Starting buscar_dados_guia_dos_quadrinhos('Watchmen', '1', 'Panini')...", flush=True)
res = gemini_service.buscar_dados_guia_dos_quadrinhos("Watchmen", "1", "Panini", api_key=api_key)
print(f"TOTAL: {time.time()-t_tot:.2f}s", flush=True)
