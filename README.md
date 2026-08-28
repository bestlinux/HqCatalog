# 📚 Catalogador de Coleção de HQs com Streamlit e Gemini 2.5 Flash

Aplicativo web em Python para catalogar e gerenciar coleções físicas de quadrinhos (HQs, graphic novels, mangás, encadernados e gibis) utilizando fotos tiradas diretamente pela câmera do celular e visão computacional avançada com o modelo **Gemini 2.5 Flash** (`google-genai`).

---

## 🛠️ Stack Utilizada
- **Python 3.10+**
- **Streamlit** (com suporte a `st.camera_input`)
- **SQLite** (`hqs_inventario.db`)
- **Google GenAI SDK** (`gemini-2.5-flash`)
- **Pandas** & **Pillow**

---

## 🚀 Como Instalar e Rodar

### 1. Instalar as Dependências
No terminal (PowerShell ou Command Prompt), navegue até a pasta do projeto e instale os pacotes:

```bash
cd "c:\Users\bestl\OneDrive\Google Antigravity\HqCatalog"
pip install -r requirements.txt
```

### 2. Configurar a Chave da API do Gemini
Você pode configurar a chave de duas formas:
- **Opção A (Recomendada):** Crie um arquivo `.env` na pasta do projeto baseado no `.env.example`:
  ```env
  GEMINI_API_KEY=sua_chave_aqui
  ```
- **Opção B:** Digitar diretamente no campo de senha na barra lateral do app Streamlit ao abrir.

*(Obtenha uma chave gratuita no [Google AI Studio](https://aistudio.google.com)).*

---

## 📱 Como Executar e Acessar pelo Celular na Rede Local

Para que o celular conectado na mesma rede Wi-Fi consiga acessar o aplicativo e usar a câmera nativa:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

### Passo a passo no Smartphone:
1. Verifique o **IP Local** do seu computador (o próprio Streamlit exibirá no terminal como `Network URL: http://192.168.x.x:8501`).
2. Abra o navegador do smartphone (Chrome, Safari, etc.) e digite o endereço:
   ```
   http://192.168.X.X:8501
   ```
3. Defina a **Prateleira Atual** (ex: `Estante Marvel - Prateleira 2`).
4. Toque no botão de câmera (`st.camera_input`), autorize a permissão de câmera no navegador e tire a foto da prateleira.
5. Clique em **"Processar & Salvar HQs"** — o modelo extrai títulos, edições e editoras e grava automaticamente no banco SQLite.

---

## 📁 Estrutura dos Arquivos

```
HqCatalog/
│
├── app.py                # Interface web principal (Streamlit)
├── database.py           # Operações com SQLite (criação, inserção, filtros, exclusão)
├── gemini_service.py     # Integração com Google GenAI (gemini-2.5-flash) e parser JSON
├── requirements.txt      # Dependências do projeto
├── .env.example          # Exemplo de arquivo de configuração da API
└── README.md             # Documentação e instruções de uso
```
