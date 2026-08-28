# 🗄️ Guia Rápido: Conectar o Turso Cloud (SQLite na Nuvem)

O **Turso** é um banco de dados SQLite distribuído na nuvem, com **9 GB de armazenamento permanente e gratuito**.

---

### Passo 1: Criar sua conta e banco no Turso (1 Minuto)

1. Acesse o site oficial: **[turso.tech](https://turso.tech)**.
2. Clique em **"Sign Up"** (ou faça login com sua conta do **GitHub**).
3. No painel web do Turso, clique em **"Create Database"**:
   - **Nome do Banco:** ex: `hqs-database`
   - **Localização:** Escolha `gru` (São Paulo, Brasil) ou a mais próxima.
   - Clique em **Create Database**.

---

### Passo 2: Copiar a URL e o Token

Na página do banco recém-criado no painel do Turso:
1. Copie o **Database URL** (ex: `libsql://hqs-database-seuusuario.turso.io`).
2. Clique no botão **"Create Token"** (ou **Generate Token**) e copie o token gerado.

---

### Passo 3: Colocar no Streamlit Community Cloud

1. Acesse o painel do seu app no [share.streamlit.io](https://share.streamlit.io).
2. No menu do app (canto inferior direito), clique em **Settings (Configurações)** > **Secrets**.
3. Adicione suas chaves no seguinte formato:

```toml
GEMINI_API_KEY = "sua_chave_do_gemini"

TURSO_DATABASE_URL = "libsql://hqs-database-seuusuario.turso.io"
TURSO_AUTH_TOKEN = "eyJhbGciOi..."
```

4. Clique em **Save**.

---

### ✅ Pronto!
- O Streamlit recarregará o aplicativo automaticamente.
- A barra lateral exibirá o selo verde: **`☁️ Banco: Turso Cloud (Permanente)`**.
- Todas as HQs que você cadastrar agora ficam salvas no banco de dados na nuvem para sempre, independentemente de atualizações ou reinicializações do Streamlit Cloud!
