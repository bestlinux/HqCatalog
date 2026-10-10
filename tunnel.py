import os
import sys
import time
from dotenv import load_dotenv

# Configura encoding UTF-8 no terminal Windows para evitar UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import ngrok

load_dotenv()

def connect_ngrok(port: int = 8501):
    authtoken = os.getenv("NGROK_AUTHTOKEN")
    domain = os.getenv("NGROK_DOMAIN", "banister-wife-drinking.ngrok-free.dev")
    
    if not authtoken:
        print("\n[!] AVISO: NGROK_AUTHTOKEN nao configurado no arquivo .env!")
        print("Adicione a chave no seu .env: NGROK_AUTHTOKEN=seu_token_aqui")
        print("Voce pode obter seu token em: https://dashboard.ngrok.com/get-started/your-authtoken\n")
        return None

    try:
        print(f"Iniciando tunel ngrok para localhost:{port} (dominio: {domain})...")
        forwarder = ngrok.forward(
            f"localhost:{port}",
            authtoken=authtoken,
            domain=domain
        )
        print("\n" + "=" * 60)
        print("TÚNEL NGROK ATIVO COM SUCESSO!")
        print(f"Acesse no celular: {forwarder.url()}")
        print("=" * 60 + "\n")
        return forwarder
    except Exception as e:
        print(f"Erro ao conectar o tunel ngrok: {e}")
        return None

if __name__ == "__main__":
    forwarder = connect_ngrok()
    if forwarder:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nTunel ngrok encerrado pelo usuario.")
