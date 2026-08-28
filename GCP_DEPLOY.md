# 🚀 Guia de Deploy no Google Cloud & Streamlit Cloud

O ecossistema do **Google Cloud (Cloud Run)** e o **Streamlit Community Cloud** são infinitamente mais simples, rápidos e modernos para rodar aplicações Streamlit do que o Azure.

---

## 🌟 Opção 1: Google Cloud Run (Recomendada no GCP)

O **Cloud Run** é o serviço serverless do Google. Ele compila o código na nuvem e entrega uma URL com HTTPS gratuito em **apenas 1 comando**.

### Pré-requisito:
Ter o [Google Cloud SDK (gcloud CLI)](https://cloud.google.com/sdk/docs/install) instalado no computador.

### Passo a Passo no Terminal:

1. **Faça login na sua conta do Google Cloud:**
   ```powershell
   gcloud auth login
   ```

2. **Selecione o seu projeto no Google Cloud:**
   ```powershell
   gcloud config set project SEU_PROJECT_ID
   ```

3. **Execute o Deploy:**
   Navegue até a pasta do projeto e rode um único comando:
   ```powershell
   cd "c:\Users\bestl\OneDrive\Google Antigravity\HqCatalog"
   gcloud run deploy catalogo-hqs --source . --region southamerica-east1 --allow-unauthenticated --set-env-vars GEMINI_API_KEY="sua_chave_aqui"
   ```

*(Nota: `southamerica-east1` é o data center do Google em São Paulo. Você também pode usar `us-central1`).*

---

### O que o Cloud Run faz automaticamente para você:
- ✅ Constrói o container Docker na nuvem usando o `Dockerfile`.
- ✅ Configura o WebSockets e as portas automaticamente.
- ✅ Gera uma URL **HTTPS** oficial (ex: `https://catalogo-hqs-xyz.a.run.app`).
- ✅ **Câmera do celular:** Como a URL é HTTPS, a câmera abre direto sem avisos de segurança.
- ✅ **Custo:** O Cloud Run tem um plano gratuito generoso (2 milhões de requisições por mês grátis).

---

## 🎈 Opção 2: Streamlit Community Cloud (100% Gratuito e o Mais Fácil do Mundo)

Se você utiliza o **GitHub**, o próprio time do Streamlit oferece hospedagem gratuita na nuvem do Google/AWS:

1. Crie um repositório no seu GitHub (pode ser privado) e suba a pasta `HqCatalog`.
2. Acesse [share.streamlit.io](https://share.streamlit.io) e faça login com seu GitHub.
3. Clique em **"New app"** e selecione:
   - **Repository:** seu repositório
   - **Main file path:** `app.py`
4. Em **Advanced settings** > **Secrets**, adicione:
   ```toml
   GEMINI_API_KEY = "sua_chave_do_google_ai_studio"
   ```
5. Clique em **Deploy!** Em 30 segundos seu app está no ar com HTTPS gratuito e sem precisar gerenciar nenhum servidor.
