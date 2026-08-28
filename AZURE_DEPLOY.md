# ☁️ Guia de Hospedagem no Microsoft Azure

Sim! É totalmente possível e muito recomendado hospedar este aplicativo no **Microsoft Azure**.

---

## 🌟 Vantagens de Hospedar no Azure
1. **HTTPS Automático Gratuito (`https://seu-app.azurewebsites.net`):**
   - No celular, navegadores (Chrome, Safari, iOS e Android) liberam a câmera instantaneamente (`st.camera_input` e captura nativa) sem qualquer bloqueio de segurança.
2. **Acesso de Qualquer Lugar:** Você e quem você autorizar podem escanear quadrinhos sem precisar estar no mesmo Wi-Fi de casa.
3. **Segurança da Chave da IA:** A `GEMINI_API_KEY` fica armazenada de forma segura nas *Variáveis de Ambiente / Configurações do Azure*.

---

## 🚀 Opção 1: Azure App Service (Recomendada)

O **Azure App Service (Linux)** é a forma mais simples e direta.

### Passo 1: Criar o App Service no Portal Azure
1. Acesse o [Portal do Azure](https://portal.azure.com).
2. Busque por **App Services** > Clique em **+ Criar (+ Create)** > **Web App**.
3. Preencha as configurações básicas:
   - **Assinatura / Subscription:** Sua assinatura.
   - **Resource Group:** Crie um novo (ex: `rg-hqcatalog`).
   - **Name (Nome da Aplicação):** Ex: `meu-catalogo-hqs` (ficará `https://meu-catalogo-hqs.azurewebsites.net`).
   - **Publish:** *Code* ou *Docker Container*.
   - **Runtime Stack:** `Python 3.11` ou `Python 3.12`.
   - **Operating System:** `Linux`.
   - **Pricing Plan:** *Basic B1* (ou *Free F1* para testes).

### Passo 2: Configurar o Comando de Inicialização (Startup Command)
Se você fizer deploy via código (Git, Zip ou VS Code):
- No menu lateral do App Service no Azure, vá em **Configuration** (ou **Settings** > **Configuration**).
- Na aba **General settings**, no campo **Startup Command**, insira:
  ```bash
  streamlit run app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true
  ```
  *(Nota: O Azure App Service Linux roteia o tráfego interno na porta 8000).*

### Passo 3: Configurar as Variáveis de Ambiente
No menu **Settings** > **Environment variables** (ou **Configuration** > **Application Settings**), adicione:
- `GEMINI_API_KEY` = `sua_chave_do_google_ai_studio`
- `DB_PATH` = `/home/hqs_inventario.db` *(Garante que o banco SQLite seja salvo no disco persistente `/home` do Azure)*
- `WEBSITES_PORT` = `8501` *(ou `8000`, dependendo da porta configurada no startup)*
- `WEBSITES_ENABLE_APP_SERVICE_STORAGE` = `true`

### Passo 4: Fazer o Deploy do Código
Você pode enviar o código de 3 formas:
- **Pelo VS Code:** Extensão **Azure App Service** > Clique com botão direito na pasta `HqCatalog` > **Deploy to Web App**.
- **Pelo GitHub Actions:** Conecte o repositório GitHub na aba **Deployment Center**.
- **Via Azure CLI (Linha de Comando):**
  ```bash
  az webapp up --name meu-catalogo-hqs --resource-group rg-hqcatalog --runtime "PYTHON:3.11"
  ```

---

## 🐳 Opção 2: Azure Container Apps (Serverless com Docker)

Se preferir utilizar o `Dockerfile` incluído no projeto:

1. **Construir e enviar a imagem para o Azure Container Registry (ACR):**
   ```bash
   az acr build --registry meuregistry --image hqcatalog:latest .
   ```
2. **Criar o Container App:**
   ```bash
   az containerapp create \
     --name hq-catalog-app \
     --resource-group rg-hqcatalog \
     --environment meu-ambiente-container \
     --image meuregistry.azurecr.io/hqcatalog:latest \
     --target-port 8501 \
     --ingress external \
     --env-vars GEMINI_API_KEY="sua_chave" DB_PATH="/data/hqs_inventario.db"
   ```
3. **Persistência do SQLite:** Conecte um volume **Azure File Share** montado em `/data` para que o banco SQLite nunca seja perdido ao reiniciar containers.

---

## 💾 Dica Importante sobre o SQLite na Nuvem

O SQLite salva todos os dados em um único arquivo (`hqs_inventario.db`). Na nuvem:
- No **Azure App Service**, a pasta `/home/` é montada em um storage permanente da sua conta Azure, logo definindo `DB_PATH=/home/hqs_inventario.db`, seus dados ficam seguros mesmo após reinicializações.
- Você também pode fazer download do backup do banco a qualquer momento clicando no botão **"Exportar Inventário (CSV)"** na barra lateral do app.
