import sys
sys.path.insert(0, r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog")
from dotenv import load_dotenv
load_dotenv(r"c:\Users\bestl\OneDrive\HqCatalog\HqCatalog\.env")
from gemini_service import get_gemini_client

client = get_gemini_client()

prompt = """No catálogo da enciclopédia Guia dos Quadrinhos (guiadosquadrinhos.com), qual é a URL exata da edição:
Título: Wolverine
Número: 21
Editora: Abril

Retorne a URL exata no formato https://www.guiadosquadrinhos.com/edicao/...
"""

resp = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt
)
print("RESP DIRETA:", resp.text)
