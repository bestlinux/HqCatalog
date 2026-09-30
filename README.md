# 📚 Catalogador de Coleção de HQs com Streamlit e Gemini

Aplicativo web completo em Python para catalogar, gerenciar e explorar coleções físicas de quadrinhos (HQs, graphic novels, mangás, encadernados e gibis) utilizando fotos tiradas pela câmera do smartphone e inteligência artificial de última geração com os modelos **Gemini** (`google-genai`).

---

## 🚀 Superpoderes de IA Inclusos

1. 📸 **Visão Computacional & Leitura de Lombadas:** Identifica múltiplos quadrinhos em fotos de prateleiras extraindo título canônico, edição, editora, gênero, autores e sinopse.
2. 🧭 **Guia de Ordem de Leitura & Cronologia de Sagas:** Mapeia a cronologia ideal para qualquer saga ou universo (Marvel, DC, Mangás, Vertigo) cruzando com o que você já possui na estante e apontando volumes faltantes com 1 clique para compra/desejos.
3. 🔍 **Detetive de Coleção & DNA do Colecionador:** Analisa todo o acervo, define seu arquétipo de leitor, detecta volumes faltantes em coleções e gera recomendações cirúrgicas de próximas compras.
4. 🎙️ **Storyteller / Aquecimento de Leitura por Voz:** Cria uma recapitulação dramática e imersiva (*"Previously on..."*) com narração por voz (Web Speech API) antes de você abrir as páginas de uma HQ.
5. 🧠 **Trivia & Quiz Interativo do seu Acervo:** Gera jogos de perguntas e respostas dinâmicos baseados exclusivamente nas tramas, autores e curiosidades das HQs presentes na sua estante.
6. 💬 **Curador Virtual & Assistente por Voz/Texto:** Responde dúvidas temáticas e indica leituras com base nos resumos do seu catálogo.
7. 🛒 **Radar de Preços & Lista de Desejos:** Pesquisa de preços em tempo real no Google Shopping via SerpApi e gerenciamento de lista de compras.

---

## 🛠️ Stack Utilizada
- **Python 3.10+**
- **Streamlit** (com suporte a `st.data_editor`, `st.camera_input`, modais `@st.dialog` e autenticação)
- **SQLite / Turso Cloud** (`hqs_inventario.db`)
- **Google GenAI SDK** (`gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro-preview`)
- **Web Speech API** (síntese de áudio para narrações em português)
- **Pandas**, **Pillow**, **SerpApi**

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

# (Opcional) Chave SerpApi para radar de preços Google Shopping
SERPAPI_API_KEY=sua_chave_serpapi

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

---

## 📁 Estrutura dos Arquivos

```
HqCatalog/
│
├── app.py                # Interface web principal (Streamlit) com Hub de IA, modais e páginas dedicadas
├── auth.py               # Módulo de autenticação e proteção de rotas
├── database.py           # Operações com SQLite / Turso Cloud (migrações, capas, notas, desejos)
├── gemini_service.py     # Integração com Google GenAI (Visão, Storyteller, Ordem de Leitura, DNA, Quiz, Chatbot)
├── test_app.py           # Suíte de 33 testes unitários automatizados com mocks
├── requirements.txt      # Dependências do projeto
├── .env.example          # Modelo de configuração de variáveis de ambiente
└── README.md             # Documentação e instruções de uso
```

