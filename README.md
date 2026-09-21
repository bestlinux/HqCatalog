# 📚 Catalogador de Coleção de HQs com Streamlit e Gemini

Aplicativo web em Python para catalogar e gerenciar coleções físicas de quadrinhos (HQs, graphic novels, mangás, encadernados e gibis) utilizando fotos tiradas diretamente pela câmera do celular e visão computacional avançada com o modelo **Gemini 2.5 Flash / 3.6 Flash** (`google-genai`).

---

## 🛠️ Stack Utilizada
- **Python 3.10+**
- **Streamlit** (com suporte a `st.data_editor`, `st.camera_input` e autenticação)
- **SQLite / Turso Cloud** (`hqs_inventario.db`)
- **Google GenAI SDK** (`gemini-3.6-flash` / `gemini-2.5-flash`)
- **Pandas** & **Pillow**

---

## 🚀 Como Instalar e Rodar

### 1. Instalar as Dependências
No terminal (PowerShell ou Command Prompt), navegue até a pasta do projeto e instale os pacotes:

```bash
cd HqCatalog
pip install -r requirements.txt
```

### 2. Configurar o Arquivo `.env` (Chave Gemini e Login)
Crie um arquivo `.env` baseado no `.env.example`:

```env
# Chave de API do Gemini (obtenha em https://aistudio.google.com)
GEMINI_API_KEY=sua_chave_aqui

# Credenciais de Acesso (Login)
APP_USERNAME=admin
APP_PASSWORD=sua_senha_segura

# (Opcional) Banco Turso Cloud
# TURSO_DATABASE_URL=libsql://seu-banco.turso.io
# TURSO_AUTH_TOKEN=seu_token_aqui
```

> **Credenciais Padrão (Fallback):** Caso não defina no `.env`, o acesso inicial padrão é `admin` / `admin123`.

---

## 📱 Como Executar e Acessar pelo Celular na Rede Local

Para que o celular conectado na mesma rede Wi-Fi consiga acessar o aplicativo:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
*(Ou execute o arquivo `iniciar.bat` no Windows).*

### Passo a passo:
1. Abra no navegador (computador ou celular) o endereço fornecido no terminal (ex: `http://192.168.X.X:8501`).
2. Digite seu **Usuário** e **Senha** na tela de login.
3. Use a câmera para fotografar as prateleiras e catalogar em lote com IA.
4. Use o botão **`📷 Cadastrar Capa`** para fotografar capas individuais e o **Grid Editável** para gerenciar ou excluir dados em lote.

---

## 📁 Estrutura dos Arquivos

```
HqCatalog/
│
├── app.py                # Interface web principal (Streamlit) com grid editável e ações
├── auth.py               # Módulo de autenticação e proteção de rotas
├── database.py           # Operações com SQLite / Turso Cloud (migrações, capas, notas)
├── gemini_service.py     # Integração com Google GenAI e extração multimodal
├── test_app.py           # Suíte de testes unitários automatizados
├── requirements.txt      # Dependências do projeto
├── .env.example          # Modelo de configuração de variáveis de ambiente
└── README.md             # Documentação e instruções de uso
```
