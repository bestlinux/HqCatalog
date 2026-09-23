"""
Módulo de Gerenciamento do Banco de Dados para o Inventário de HQs.
Suporta de forma híbrida e transparente:
  1. Turso Cloud (SQLite distribuído na nuvem com libsql-client) quando TURSO_DATABASE_URL e TURSO_AUTH_TOKEN estiverem configurados.
  2. SQLite Local (hqs_inventario.db) como fallback automático para desenvolvimento local.
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import libsql_client
except ImportError:
    libsql_client = None

DB_DEFAULT_PATH = os.getenv("DB_PATH", "hqs_inventario.db")


def get_turso_credentials() -> tuple[Optional[str], Optional[str]]:
    """Recupera as credenciais do Turso do ambiente ou dos secrets do Streamlit."""
    url = os.getenv("TURSO_DATABASE_URL") or os.getenv("TURSO_DB_URL")
    token = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_TOKEN")

    if not url or not token:
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if "TURSO_DATABASE_URL" in st.secrets:
                    url = st.secrets["TURSO_DATABASE_URL"]
                elif "TURSO_DB_URL" in st.secrets:
                    url = st.secrets["TURSO_DB_URL"]
                
                if "TURSO_AUTH_TOKEN" in st.secrets:
                    token = st.secrets["TURSO_AUTH_TOKEN"]
                elif "TURSO_TOKEN" in st.secrets:
                    token = st.secrets["TURSO_TOKEN"]
        except Exception:
            pass

    return url, token


def is_using_turso() -> bool:
    """Verifica se o banco está configurado para usar o Turso Cloud."""
    url, token = get_turso_credentials()
    return bool(url and token and libsql_client is not None)


import time

def get_turso_client():
    """Retorna um cliente síncrono do Turso."""
    url, token = get_turso_credentials()
    if not url or not token:
        raise ValueError("Credenciais do Turso não configuradas.")
    # Converte libsql:// para https:// se necessário para compatibilidade HTTP
    clean_url = url.replace("libsql://", "https://")
    return libsql_client.create_client_sync(url=clean_url, auth_token=token)


def executar_turso_query(sql: str, params: Optional[List[Any]] = None, max_retries: int = 3) -> Any:
    """
    Executa uma consulta no Turso Cloud com retentativa automática e backoff para falhas transitórias de rede
    (ex: WinError 121, timeouts, instabilidades temporárias de conexão com aiohttp).
    """
    clean_params = params if params is not None else []
    ultimo_erro = None

    for tentativa in range(1, max_retries + 1):
        client = None
        try:
            client = get_turso_client()
            res = client.execute(sql, clean_params)
            return res
        except Exception as ex:
            ultimo_erro = ex
            if tentativa < max_retries:
                time.sleep(0.3 * tentativa)
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    raise ultimo_erro


def get_sqlite_connection(db_path: str = DB_DEFAULT_PATH) -> sqlite3.Connection:
    """Retorna uma conexão SQLite local padrão."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_DEFAULT_PATH) -> None:
    """Inicializa a tabela hqs caso ainda não exista e aplica migrações de schema."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS hqs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        edicao TEXT,
        editora TEXT,
        genero TEXT DEFAULT 'Outro',
        escritor TEXT DEFAULT 'Não informado',
        ilustrador TEXT DEFAULT 'Não informado',
        prateleira TEXT NOT NULL,
        lido TEXT DEFAULT 'Não Lido',
        avaliacao INTEGER DEFAULT 0,
        capa TEXT DEFAULT '',
        resenha TEXT DEFAULT '',
        resumo TEXT DEFAULT '',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    create_table_desejos_sql = """
    CREATE TABLE IF NOT EXISTS lista_desejos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        edicao TEXT DEFAULT '',
        editora TEXT DEFAULT '',
        melhor_preco REAL DEFAULT 0.0,
        melhor_loja TEXT DEFAULT '',
        link_oferta TEXT DEFAULT '',
        observacoes TEXT DEFAULT '',
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    create_table_prateleiras_sql = """
    CREATE TABLE IF NOT EXISTS prateleiras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL,
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    seed_prateleiras_sql = """
    INSERT OR IGNORE INTO prateleiras (nome)
    SELECT DISTINCT TRIM(prateleira)
    FROM hqs
    WHERE prateleira IS NOT NULL AND TRIM(prateleira) != '' AND TRIM(prateleira) != 'Não especificada' AND TRIM(prateleira) != 'Estante 1 - Prateleira 1';
    """
    if is_using_turso():
        try:
            executar_turso_query(create_table_sql)
            executar_turso_query(create_table_desejos_sql)
            executar_turso_query(create_table_prateleiras_sql)
            try:
                executar_turso_query(seed_prateleiras_sql)
            except Exception:
                pass
            # Migrações seguras no Turso
            try:
                res = executar_turso_query("PRAGMA table_info(hqs)")
                cols = [r[1] for r in res.rows]
                if "lido" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN lido TEXT DEFAULT 'Não Lido'")
                if "genero" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN genero TEXT DEFAULT 'Outro'")
                if "escritor" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN escritor TEXT DEFAULT 'Não informado'")
                if "ilustrador" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN ilustrador TEXT DEFAULT 'Não informado'")
                if "avaliacao" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN avaliacao INTEGER DEFAULT 0")
                if "capa" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN capa TEXT DEFAULT ''")
                    if "capa_url" in cols:
                        executar_turso_query("UPDATE hqs SET capa = capa_url WHERE (capa IS NULL OR capa = '') AND capa_url IS NOT NULL")
                if "resenha" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN resenha TEXT DEFAULT ''")
                if "resumo" not in cols:
                    executar_turso_query("ALTER TABLE hqs ADD COLUMN resumo TEXT DEFAULT ''")
            except Exception:
                pass
        except Exception as e:
            print(f"Aviso ao inicializar Turso: {e}")
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
            cursor.execute(create_table_desejos_sql)
            cursor.execute(create_table_prateleiras_sql)
            try:
                cursor.execute(seed_prateleiras_sql)
            except Exception:
                pass
            cursor.execute("PRAGMA table_info(hqs)")
            columns = [row["name"] for row in cursor.fetchall()]
            
            if "lido" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN lido TEXT DEFAULT 'Não Lido'")
            if "genero" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN genero TEXT DEFAULT 'Outro'")
            if "escritor" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN escritor TEXT DEFAULT 'Não informado'")
            if "ilustrador" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN ilustrador TEXT DEFAULT 'Não informado'")
            if "avaliacao" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN avaliacao INTEGER DEFAULT 0")
            if "capa" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN capa TEXT DEFAULT ''")
                if "capa_url" in columns:
                    cursor.execute("UPDATE hqs SET capa = capa_url WHERE (capa IS NULL OR capa = '') AND capa_url IS NOT NULL")
            if "resenha" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN resenha TEXT DEFAULT ''")
            if "resumo" not in columns:
                cursor.execute("ALTER TABLE hqs ADD COLUMN resumo TEXT DEFAULT ''")

            conn.commit()
        finally:
            conn.close()


import re
import unicodedata


def normalizar_texto(texto: Optional[str]) -> str:
    """
    Remove acentos, pontuações desnecessárias e normaliza espaços para comparação.
    """
    if not texto:
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = s.encode("ASCII", "ignore").decode("ASCII").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalizar_edicao(edicao: Optional[str]) -> str:
    """
    Normaliza a representação de uma edição / volume para fins de comparação e detecção de duplicatas.
    Exemplos de equivalência:
    - "Vol. 1", "Vol 1", "Volume 1", "v. 1", "v1", "1", "01", "#1", "Nº 1", "Edição 1", "Ed. 1" -> "1"
    - "Vol. 2", "2", "Volume 2", "#2" -> "2"
    - "Edição Especial", "Edicao Especial" -> "edicao especial"
    - "", "Volume Único", "Única", "Edição Única", "One-Shot", "Vazia" -> "volume_unico"
    """
    if edicao is None:
        return "volume_unico"
    
    s = str(edicao).strip()
    if not s:
        return "volume_unico"
    
    # Remove acentos e converte para minúsculas
    s_ascii = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII").lower().strip()
    if not s_ascii:
        return "volume_unico"

    # Sinônimos de volume único / edição única / sem edição
    s_clean = re.sub(r"[^\w\s]", " ", s_ascii)
    s_clean = re.sub(r"\s+", " ", s_clean).strip()
    if s_clean in ("", "volume unico", "edicao unica", "unica", "unico", "one shot", "oneshot", "single volume", "sem edicao", "nao informada", "nao informado", "desconhecida", "vazia", "none", "null"):
        return "volume_unico"

    # Caso 1: Apenas número com ou sem prefixo comum (ex: "Vol. 1", "Vol 1", "1", "#1", "Volume 01", "v. 1", "v1", "Nº 1", "Ed. 1", "Parte 1", "Livro 1")
    padrao_simples = re.match(
        r"^(?:vol(?:ume)?|v|ed(?:i(?:c(?:a|ao)?)?)?|n[oº°]?|num(?:ero)?|#|livro|book|tomo|parte|pt|fasc(?:iculo)?|cap(?:itulo)?)[\s\.\-#º°:]*(\d+(?:[\.,/]\d+)?)$",
        s_ascii,
        re.IGNORECASE
    )
    if padrao_simples:
        num_str = padrao_simples.group(1).replace(",", ".")
        if "/" in num_str:
            return num_str
        try:
            num_val = float(num_str)
            return str(int(num_val)) if num_val.is_integer() else str(num_val)
        except ValueError:
            return num_str

    # Caso 2: Se for puramente dígitos (ex: "1", "02", "104")
    if s_ascii.isdigit():
        return str(int(s_ascii))

    # Caso 3: Textos compostos como "Edição Definitiva Vol. 1", "Edição Especial #2", "Ano Um - Parte 1"
    def _sub_num_inner(match):
        num_str = match.group(1).replace(",", ".")
        if "/" in num_str:
            return f" {num_str} "
        try:
            num_val = float(num_str)
            num_formatted = str(int(num_val)) if num_val.is_integer() else str(num_val)
            return f" {num_formatted} "
        except ValueError:
            return f" {num_str} "

    # Substitui prefixos comuns de volume antes de número pelo próprio número
    s_sub = re.sub(
        r"\b(?:vol(?:ume)?|v|ed(?:icao)?|ed|n[oº°]?|num(?:ero)?|livro|book|tomo|parte|pt|#)[\s\.\-#º°:]*(\d+(?:[\.,/]\d+)?)\b",
        _sub_num_inner,
        s_ascii,
        flags=re.IGNORECASE
    )
    
    # Remove pontuações e colapsa espaços
    s_sub = re.sub(r"[^\w\s]", " ", s_sub)
    s_sub = re.sub(r"\s+", " ", s_sub).strip()

    # Normaliza números com zeros à esquerda isolados (ex: "01" -> "1")
    tokens = []
    for t in s_sub.split():
        if t.isdigit():
            tokens.append(str(int(t)))
        else:
            tokens.append(t)

    return " ".join(tokens)


def normalizar_editora(editora: Optional[str]) -> str:
    """
    Normaliza o nome da editora para comparação de duplicatas.
    Termos genéricos retornam string vazia.
    """
    if not editora:
        return ""
    s = normalizar_texto(editora)
    termos_genericos = {
        "desconhecida", "desconhecido", "nao informada", "nao informado",
        "outra", "outro", "indefinida", "indefinido", "nenhuma", "nenhum", "sem editora"
    }
    if s in termos_genericos:
        return ""
    return s


def editoras_sao_compativeis(editora1: Optional[str], editora2: Optional[str]) -> bool:
    """
    Verifica se duas editoras são compatíveis para fins de detecção de duplicata.
    Se uma das editoras for desconhecida/vazia, considera compatível.
    Se ambas forem informadas, compara nomes normalizados ou contenção (ex: 'Panini' e 'Panini Comics').
    """
    ed1 = normalizar_editora(editora1)
    ed2 = normalizar_editora(editora2)

    if not ed1 or not ed2:
        return True
    
    if ed1 == ed2:
        return True

    if ed1 in ed2 or ed2 in ed1:
        return True

    return False


def normalizar_titulo_e_edicao(titulo: Optional[str], edicao: Optional[str]) -> tuple[str, str]:
    """
    Normaliza conjuntamente o título e a edição, extraindo e padronizando volumes que estejam
    no título ou no campo de edição.
    Exemplos:
    - ("Paraíso: O Vampiro que Ri 2", "") -> ("paraiso o vampiro que ri", "2")
    - ("Paraíso: O Vampiro que Ri", "2") -> ("paraiso o vampiro que ri", "2")
    - ("Paraíso: O Vampiro que Ri", "Vol. 2") -> ("paraiso o vampiro que ri", "2")
    - ("Meu Amigo Kim Jong-un", "") -> ("meu amigo kim jong un", "volume_unico")
    - ("Ouroboros", "Volume Único") -> ("ouroboros", "volume_unico")
    - ("Ouroboros", "") -> ("ouroboros", "volume_unico")
    - ("Sandman - Edição Definitiva Vol. 1", "") -> ("sandman edicao definitiva", "1")
    """
    tit_str = str(titulo or "").strip()
    ed_str = str(edicao or "").strip()

    tit_norm = normalizar_texto(tit_str)
    ed_norm = normalizar_edicao(ed_str)

    titulos_numericos_conhecidos = {"1984", "2001", "300", "100", "20th", "21st"}

    if tit_norm in titulos_numericos_conhecidos:
        return tit_norm, ed_norm

    # Se a edição já tem número explícito ou texto específico (que não seja volume_unico)
    if ed_norm and ed_norm != "volume_unico":
        padrao_sufixo_ed = re.search(r"^(.*?)\s+(?:vol|volume|v|ed|edicao|#|no)?\s*" + re.escape(ed_norm) + r"$", tit_norm)
        if padrao_sufixo_ed:
            base = padrao_sufixo_ed.group(1).strip()
            if len(base) > 2 and base not in titulos_numericos_conhecidos:
                tit_norm = base

    # Se a edição é volume_unico / vazia, tenta extrair volume explícito ou número no final do título
    elif ed_norm == "volume_unico":
        padrao_vol = re.search(
            r"^(.*?)\s+(?:vol(?:ume)?|v|ed(?:i(?:c(?:a|ao)?)?)?|#|n[oº°]?|tomo|livro|parte)\s*(\d+(?:[\.,]\d+)?)$",
            tit_norm
        )
        padrao_num = re.search(r"^(.*?)\s+(\d{1,3})$", tit_norm)

        if padrao_vol:
            base = padrao_vol.group(1).strip()
            num = padrao_vol.group(2).strip()
            if base and base not in titulos_numericos_conhecidos:
                tit_norm = base
                ed_norm = normalizar_edicao(num)
        elif padrao_num:
            base = padrao_num.group(1).strip()
            num = padrao_num.group(2).strip()
            if base and len(base) > 2 and base not in titulos_numericos_conhecidos:
                tit_norm = base
                ed_norm = normalizar_edicao(num)

    return tit_norm, ed_norm


def verificar_hq_duplicada(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    db_path: str = DB_DEFAULT_PATH
) -> Optional[Dict[str, Any]]:
    """
    Verifica se já existe uma HQ cadastrada com o mesmo Título, Edição/Número e Editora.
    Reconhece variações de grafia na edição e desmembra volumes do título.
    """
    tit_clean = (titulo or "").strip()
    if not tit_clean:
        return None

    tit_norm, ed_norm = normalizar_titulo_e_edicao(tit_clean, edicao)

    # 1. Busca candidatos pelo título no banco de dados
    sql = """
    SELECT id, titulo, edicao, editora, prateleira, criado_em
    FROM hqs
    WHERE LOWER(TRIM(titulo)) = LOWER(?)
    ORDER BY id DESC
    """
    params = [tit_clean]

    candidatos = []
    if is_using_turso():
        try:
            res = executar_turso_query(sql, params)
            if res.rows:
                candidatos = [dict(zip(res.columns, r)) for r in res.rows]
        except Exception:
            candidatos = []
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            if rows:
                candidatos = [dict(r) for r in rows]
        finally:
            conn.close()

    # Se não encontrou candidatos com match exato case-insensitive de título, busca flexível
    if not candidatos:
        sql_todos = "SELECT id, titulo, edicao, editora, prateleira, criado_em FROM hqs ORDER BY id DESC"
        if is_using_turso():
            try:
                res = executar_turso_query(sql_todos, [])
                if res.rows:
                    todos = [dict(zip(res.columns, r)) for r in res.rows]
                    candidatos = [c for c in todos if normalizar_titulo_e_edicao(c.get("titulo"), c.get("edicao"))[0] == tit_norm]
            except Exception:
                candidatos = []
        else:
            conn = get_sqlite_connection(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(sql_todos)
                rows = cursor.fetchall()
                if rows:
                    candidatos = [dict(r) for r in rows if normalizar_titulo_e_edicao(r["titulo"], r["edicao"])[0] == tit_norm]
            finally:
                conn.close()

    # 2. Avalia duplicidade com base no título e edição normalizados
    candidato_mesmo_titulo_edicao = None

    for cand in candidatos:
        cand_tit_norm, cand_ed_norm = normalizar_titulo_e_edicao(cand.get("titulo"), cand.get("edicao"))
        cand_editora = cand.get("editora")

        if cand_tit_norm == tit_norm and cand_ed_norm == ed_norm:
            if editoras_sao_compativeis(cand_editora, editora):
                return cand
            if candidato_mesmo_titulo_edicao is None:
                candidato_mesmo_titulo_edicao = cand

    # Se encontrou registro com mesmo título e edição (mesmo que a IA tenha alucinado a editora)
    if candidato_mesmo_titulo_edicao is not None:
        return candidato_mesmo_titulo_edicao

    return None


def buscar_hqs_por_titulo_ou_edicao(
    termo: str,
    edicao: Optional[str] = None,
    db_path: str = DB_DEFAULT_PATH
) -> List[Dict[str, Any]]:
    """
    Busca HQs no banco de dados por título (correspondência exata ou parcial) e opcionalmente por edição.
    Retorna uma lista de dicionários com os registros encontrados.
    """
    tit_clean = (termo or "").strip()
    if not tit_clean:
        return []

    ed_clean = (edicao or "").strip()
    ed_norm = normalizar_edicao(ed_clean) if ed_clean else ""

    # 1. Tentativa de correspondência exata de título (+ edição se fornecida)
    if ed_clean:
        sql_exata = """
        SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
        FROM hqs
        WHERE LOWER(TRIM(titulo)) = LOWER(?)
          AND LOWER(TRIM(COALESCE(edicao, ''))) = LOWER(?)
        ORDER BY id DESC
        """
        params_exata = [tit_clean, ed_clean]
    else:
        sql_exata = """
        SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
        FROM hqs
        WHERE LOWER(TRIM(titulo)) = LOWER(?)
        ORDER BY id DESC
        """
        params_exata = [tit_clean]

    resultados_exata = []
    if is_using_turso():
        try:
            res = executar_turso_query(sql_exata, params_exata)
            if res.rows:
                resultados_exata = [dict(zip(res.columns, r)) for r in res.rows]
        except Exception:
            pass
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql_exata, tuple(params_exata))
            rows = cursor.fetchall()
            if rows:
                resultados_exata = [dict(r) for r in rows]
        finally:
            conn.close()

    if resultados_exata:
        return resultados_exata

    # 2. Se especificou edição mas não bateu texto exato, busca título exato e filtra por edição normalizada
    if ed_clean and ed_norm:
        sql_tit_so = """
        SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
        FROM hqs
        WHERE LOWER(TRIM(titulo)) = LOWER(?)
        ORDER BY id DESC
        """
        cands = []
        if is_using_turso():
            try:
                res = executar_turso_query(sql_tit_so, [tit_clean])
                if res.rows:
                    cands = [dict(zip(res.columns, r)) for r in res.rows]
            except Exception:
                pass
        else:
            conn = get_sqlite_connection(db_path)
            try:
                cursor = conn.cursor()
                cursor.execute(sql_tit_so, (tit_clean,))
                rows = cursor.fetchall()
                if rows:
                    cands = [dict(r) for r in rows]
            finally:
                conn.close()

        match_norm = [c for c in cands if normalizar_edicao(c.get("edicao")) == ed_norm]
        if match_norm:
            return match_norm

    # 3. Se não encontrou correspondência exata, busca parcial com LIKE
    termo_like = f"%{tit_clean}%"
    if ed_clean:
        sql_like = """
        SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
        FROM hqs
        WHERE LOWER(titulo) LIKE LOWER(?)
          AND LOWER(COALESCE(edicao, '')) LIKE LOWER(?)
        ORDER BY id DESC
        """
        params_like = [termo_like, f"%{ed_clean}%"]
    else:
        sql_like = """
        SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
        FROM hqs
        WHERE LOWER(titulo) LIKE LOWER(?)
        ORDER BY id DESC
        """
        params_like = [termo_like]

    if is_using_turso():
        try:
            res = executar_turso_query(sql_like, params_like)
            return [dict(zip(res.columns, r)) for r in res.rows] if res.rows else []
        except Exception:
            return []
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql_like, tuple(params_like))
            rows = cursor.fetchall()
            return [dict(r) for r in rows] if rows else []
        finally:
            conn.close()


def salvar_hqs(
    itens: Optional[List[Dict[str, Any]]] = None,
    prateleira: Optional[str] = None,
    db_path: str = DB_DEFAULT_PATH,
    lido_padrao: str = "Não Lido",
    ignorar_duplicadas: bool = True,
    retornar_detalhes: bool = False,
    **kwargs
) -> Any:
    """
    Insere uma lista de quadrinhos identificados no banco de dados.
    Por padrão, ignora edições duplicadas (mesmo Título, Edição/Número equivalente e Editora).
    Aceita 'hqs' como alias de 'itens' e 'prateleira_padrao' como alias de 'prateleira'.
    """
    if itens is None and "hqs" in kwargs:
        itens = kwargs.pop("hqs")
    if prateleira is None and "prateleira_padrao" in kwargs:
        prateleira = kwargs.pop("prateleira_padrao")

    itens = itens or []
    prateleira = prateleira or ""

    if not itens:
        if retornar_detalhes:
            return {"salvos": 0, "duplicados": 0, "itens_salvos": [], "itens_duplicados": []}
        return 0

    registros_para_inserir = []
    itens_salvos = []
    itens_duplicados = []

    for item in itens:
        titulo = (item.get("titulo") or "").strip()
        if not titulo:
            continue
        
        edicao = str(item.get("edicao") or "").strip()
        editora = (item.get("editora") or "").strip()
        genero = (item.get("genero") or "Outro").strip()
        escritor = (item.get("escritor") or "Não informado").strip()
        ilustrador = (item.get("ilustrador") or "Não informado").strip()
        prateleira_val = (item.get("prateleira") or prateleira or "Não especificada").strip()
        lido_val = (item.get("lido") or lido_padrao).strip()
        try:
            avaliacao_raw = int(item.get("avaliacao") or 0)
        except (ValueError, TypeError):
            avaliacao_raw = 0
        avaliacao_val = max(0, min(5, avaliacao_raw))
        capa = (item.get("capa") or item.get("capa_url") or "").strip()
        resenha = (item.get("resenha") or "").strip()
        resumo = (item.get("resumo") or "").strip()

        tit_norm, ed_norm = normalizar_titulo_e_edicao(titulo, edicao)

        if ignorar_duplicadas:
            # 1. Verifica duplicidade no mesmo lote da foto
            item_duplicado_no_lote = False
            for prev_item in itens_salvos:
                prev_tit_norm, prev_ed_norm = normalizar_titulo_e_edicao(prev_item.get("titulo"), prev_item.get("edicao"))
                if (prev_tit_norm == tit_norm and
                    prev_ed_norm == ed_norm and
                    editoras_sao_compativeis(prev_item.get("editora"), editora)):
                    itens_duplicados.append({
                        **item,
                        "motivo_duplicata": f"Duplicada na mesma foto: '{titulo}' ({edicao})"
                    })
                    item_duplicado_no_lote = True
                    break

            if item_duplicado_no_lote:
                continue

            # 2. Verifica duplicidade no banco de dados
            hq_existente = verificar_hq_duplicada(titulo, edicao, editora, db_path)
            if hq_existente:
                ed_cadastrada = hq_existente.get("edicao") or "Sem Edição"
                edit_cadastrada = hq_existente.get("editora") or "Desconhecida"
                itens_duplicados.append({
                    **item,
                    "id_existente": hq_existente["id"],
                    "prateleira_existente": hq_existente["prateleira"],
                    "motivo_duplicata": f"Já cadastrada no ID #{hq_existente['id']} (Edição: '{ed_cadastrada}', Editora: '{edit_cadastrada}', Prateleira: '{hq_existente['prateleira']}')"
                })
                continue

        item_preparado = {
            "titulo": titulo,
            "edicao": edicao,
            "editora": editora,
            "genero": genero,
            "escritor": escritor,
            "ilustrador": ilustrador,
            "prateleira": prateleira_val,
            "lido": lido_val,
            "avaliacao": avaliacao_val,
            "capa": capa,
            "resenha": resenha,
            "resumo": resumo
        }
        itens_salvos.append(item_preparado)
        registros_para_inserir.append((
            titulo, edicao, editora, genero, escritor, ilustrador,
            prateleira_val, lido_val, avaliacao_val, capa, resenha, resumo
        ))

    if registros_para_inserir:
        prateleiras_unicas = set()
        if prateleira and prateleira.strip() and prateleira.strip() != "Não especificada":
            prateleiras_unicas.add(prateleira.strip())
        for it in itens_salvos:
            p_it = (it.get("prateleira") or "").strip()
            if p_it and p_it != "Não especificada":
                prateleiras_unicas.add(p_it)
        for p_cad in prateleiras_unicas:
            try:
                cadastrar_prateleira(p_cad, db_path)
            except Exception:
                pass
        if is_using_turso():
            for reg in registros_para_inserir:
                executar_turso_query(
                    """
                    INSERT INTO hqs (titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, capa, resenha, resumo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    list(reg)
                )
        else:
            conn = get_sqlite_connection(db_path)
            try:
                cursor = conn.cursor()
                cursor.executemany(
                    """
                    INSERT INTO hqs (titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, capa, resenha, resumo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    registros_para_inserir,
                )
                conn.commit()
            finally:
                conn.close()

    if retornar_detalhes:
        return {
            "salvos": len(itens_salvos),
            "duplicados": len(itens_duplicados),
            "itens_salvos": itens_salvos,
            "itens_duplicados": itens_duplicados
        }

    return len(itens_salvos)


def listar_todas_hqs(
    busca: Optional[str] = None,
    prateleira_filtro: Optional[str] = None,
    genero_filtro: Optional[str] = None,
    status_leitura_filtro: Optional[str] = None,
    avaliacao_filtro: Optional[int] = None,
    ordem_por: str = "titulo_asc",
    db_path: str = DB_DEFAULT_PATH
) -> Any:
    """
    Consulta o banco e retorna todas as HQs em formato pandas DataFrame ou lista de dicts.
    """
    query = "SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em FROM hqs WHERE 1=1"
    params = []

    if prateleira_filtro and prateleira_filtro != "Todas":
        query += " AND prateleira = ?"
        params.append(prateleira_filtro)

    if genero_filtro and genero_filtro != "Todos":
        query += " AND genero = ?"
        params.append(genero_filtro)

    if status_leitura_filtro and status_leitura_filtro in ["Lido", "Não Lido"]:
        query += " AND lido = ?"
        params.append(status_leitura_filtro)

    if avaliacao_filtro is not None and avaliacao_filtro != -1:
        query += " AND avaliacao = ?"
        params.append(avaliacao_filtro)

    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        query += " AND (titulo LIKE ? OR editora LIKE ? OR edicao LIKE ? OR genero LIKE ? OR escritor LIKE ? OR ilustrador LIKE ? OR resumo LIKE ? OR resenha LIKE ?)"
        params.extend([termo, termo, termo, termo, termo, termo, termo, termo])

    # Ordenação dos registros
    mapa_ordenacao = {
        "titulo_asc": " ORDER BY LOWER(TRIM(titulo)) ASC, id ASC",
        "titulo_desc": " ORDER BY LOWER(TRIM(titulo)) DESC, id ASC",
        "id_desc": " ORDER BY id DESC",
        "id_asc": " ORDER BY id ASC",
        "avaliacao_desc": " ORDER BY avaliacao DESC, LOWER(TRIM(titulo)) ASC",
        "editora_asc": " ORDER BY LOWER(TRIM(editora)) ASC, LOWER(TRIM(titulo)) ASC",
        "prateleira_asc": " ORDER BY LOWER(TRIM(prateleira)) ASC, LOWER(TRIM(titulo)) ASC"
    }
    query += mapa_ordenacao.get(ordem_por, " ORDER BY LOWER(TRIM(titulo)) ASC, id ASC")

    if is_using_turso():
        try:
            res = executar_turso_query(query, params)
            rows = [dict(zip(res.columns, r)) for r in res.rows]
            if pd is not None:
                return pd.DataFrame(rows)
            return rows
        except Exception as ex:
            print(f"Aviso Turso listar_todas_hqs: {ex}")
            return pd.DataFrame() if pd is not None else []
    else:
        conn = get_sqlite_connection(db_path)
        try:
            if pd is not None:
                df = pd.read_sql_query(query, conn, params=params)
                return df
            else:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        finally:
            conn.close()


def cadastrar_prateleira(nome: str, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Cadastra uma nova prateleira no banco de dados."""
    nome_limpo = str(nome or "").strip()
    if not nome_limpo:
        return False

    if is_using_turso():
        try:
            executar_turso_query("INSERT OR IGNORE INTO prateleiras (nome) VALUES (?)", [nome_limpo])
            return True
        except Exception as e:
            print(f"Erro Turso cadastrar_prateleira: {e}")
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO prateleiras (nome) VALUES (?)", (nome_limpo,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erro SQLite cadastrar_prateleira: {e}")
            return False
        finally:
            conn.close()


def obter_prateleiras(db_path: str = DB_DEFAULT_PATH) -> List[str]:
    """Retorna uma lista única de todas as prateleiras cadastradas."""
    sql = """
    SELECT DISTINCT nome FROM (
        SELECT nome FROM prateleiras
        UNION
        SELECT DISTINCT prateleira as nome FROM hqs WHERE prateleira IS NOT NULL AND prateleira != ''
    ) ORDER BY LOWER(nome) ASC
    """
    if is_using_turso():
        try:
            res = executar_turso_query(sql)
            return [r[0] for r in res.rows if r[0]]
        except Exception as ex:
            print(f"Aviso Turso obter_prateleiras: {ex}")
            return []
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [row["nome"] for row in rows]
        finally:
            conn.close()


def listar_prateleiras_detalhadas(db_path: str = DB_DEFAULT_PATH) -> List[Dict[str, Any]]:
    """
    Retorna a lista de todas as prateleiras com a quantidade de HQs, lidos e média de avaliação.
    Inclui prateleiras criadas mesmo sem HQs cadastradas.
    """
    sql = """
    SELECT nome_prateleira, total_hqs, total_lidos, total_nao_lidos, media_avaliacao FROM (
        SELECT 
            p.nome as nome_prateleira,
            COUNT(h.id) as total_hqs,
            SUM(CASE WHEN h.lido = 'Lido' THEN 1 ELSE 0 END) as total_lidos,
            SUM(CASE WHEN h.id IS NOT NULL AND (h.lido != 'Lido' OR h.lido IS NULL) THEN 1 ELSE 0 END) as total_nao_lidos,
            AVG(CASE WHEN h.avaliacao > 0 THEN h.avaliacao ELSE NULL END) as media_avaliacao
        FROM prateleiras p
        LEFT JOIN hqs h ON TRIM(h.prateleira) = TRIM(p.nome)
        GROUP BY p.nome
        UNION
        SELECT 
            COALESCE(NULLIF(TRIM(prateleira), ''), 'Não especificada') as nome_prateleira,
            COUNT(*) as total_hqs,
            SUM(CASE WHEN lido = 'Lido' THEN 1 ELSE 0 END) as total_lidos,
            SUM(CASE WHEN lido != 'Lido' OR lido IS NULL THEN 1 ELSE 0 END) as total_nao_lidos,
            AVG(CASE WHEN avaliacao > 0 THEN avaliacao ELSE NULL END) as media_avaliacao
        FROM hqs
        WHERE TRIM(COALESCE(prateleira, '')) NOT IN (SELECT TRIM(nome) FROM prateleiras)
          AND TRIM(COALESCE(prateleira, '')) != ''
        GROUP BY COALESCE(NULLIF(TRIM(prateleira), ''), 'Não especificada')
    ) ORDER BY LOWER(nome_prateleira) ASC
    """
    if is_using_turso():
        try:
            res = executar_turso_query(sql)
            itens = []
            for r in res.rows:
                med = round(float(r[4]), 1) if r[4] is not None else 0.0
                itens.append({
                    "prateleira": r[0],
                    "total_hqs": r[1] or 0,
                    "total_lidos": r[2] or 0,
                    "total_nao_lidos": r[3] or 0,
                    "media_avaliacao": med
                })
            return itens
        except Exception as ex:
            print(f"Aviso Turso listar_prateleiras_detalhadas: {ex}")
            return []
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            itens = []
            for r in rows:
                med = round(float(r["media_avaliacao"]), 1) if r["media_avaliacao"] is not None else 0.0
                itens.append({
                    "prateleira": r["nome_prateleira"],
                    "total_hqs": r["total_hqs"] or 0,
                    "total_lidos": r["total_lidos"] or 0,
                    "total_nao_lidos": r["total_nao_lidos"] or 0,
                    "media_avaliacao": med
                })
            return itens
        finally:
            conn.close()


def renomear_prateleira(nome_antigo: str, nome_novo: str, db_path: str = DB_DEFAULT_PATH) -> int:
    """
    Renomeia uma prateleira, atualizando a tabela de prateleiras e todas as HQs associadas.
    Retorna a quantidade de HQs atualizadas.
    """
    antigo = nome_antigo.strip()
    novo = nome_novo.strip()
    if not antigo or not novo:
        return 0

    if is_using_turso():
        try:
            executar_turso_query("INSERT OR IGNORE INTO prateleiras (nome) VALUES (?)", [novo])
            executar_turso_query("DELETE FROM prateleiras WHERE TRIM(nome) = ? OR nome = ?", [antigo, antigo])
            res = executar_turso_query("UPDATE hqs SET prateleira = ? WHERE TRIM(prateleira) = ? OR prateleira = ?", [novo, antigo, antigo])
            return res.rows_affected
        except Exception as ex:
            print(f"Erro Turso renomear_prateleira: {ex}")
            return 0
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO prateleiras (nome) VALUES (?)", (novo,))
            cursor.execute("DELETE FROM prateleiras WHERE TRIM(nome) = ? OR nome = ?", (antigo, antigo))
            cursor.execute("UPDATE hqs SET prateleira = ? WHERE TRIM(prateleira) = ? OR prateleira = ?", (novo, antigo, antigo))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


def obter_generos(db_path: str = DB_DEFAULT_PATH) -> List[str]:
    """Retorna uma lista única de gêneros cadastrados."""
    sql = "SELECT DISTINCT genero FROM hqs WHERE genero IS NOT NULL AND genero != '' ORDER BY genero ASC"
    if is_using_turso():
        try:
            res = executar_turso_query(sql)
            return [r[0] for r in res.rows if r[0]]
        except Exception as ex:
            print(f"Aviso Turso obter_generos: {ex}")
            return []
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [row["genero"] for row in rows]
        finally:
            conn.close()


def obter_estatisticas(db_path: str = DB_DEFAULT_PATH) -> Dict[str, Any]:
    """Retorna métricas gerais da coleção em uma única consulta ultra-otimizada."""
    sql_stats = """
    SELECT 
        COUNT(*) as total_hqs,
        COUNT(DISTINCT CASE WHEN editora IS NOT NULL AND editora != '' THEN editora END) as total_edit,
        COUNT(DISTINCT CASE WHEN genero IS NOT NULL AND genero != '' THEN genero END) as total_gen,
        SUM(CASE WHEN lido = 'Lido' THEN 1 ELSE 0 END) as total_lidos,
        AVG(CASE WHEN avaliacao > 0 THEN avaliacao ELSE NULL END) as media_aval,
        COUNT(CASE WHEN avaliacao > 0 THEN 1 ELSE NULL END) as total_avaliados
    FROM hqs
    """
    sql_prats = """
    SELECT COUNT(DISTINCT nome) as total_prat FROM (
        SELECT nome FROM prateleiras
        UNION
        SELECT DISTINCT prateleira as nome FROM hqs WHERE prateleira IS NOT NULL AND prateleira != ''
    )
    """
    if is_using_turso():
        try:
            res = executar_turso_query(sql_stats)
            res_p = executar_turso_query(sql_prats)
            total_prats = res_p.rows[0][0] if res_p.rows and res_p.rows[0][0] is not None else 0
            if res.rows:
                r = res.rows[0]
                tot_hqs = r[0] or 0
                tot_lidos = r[3] or 0
                med_aval = round(float(r[4]), 1) if r[4] is not None else 0.0
                return {
                    "total_hqs": tot_hqs,
                    "total_prateleiras": total_prats,
                    "total_editoras": r[1] or 0,
                    "total_generos": r[2] or 0,
                    "total_lidos": tot_lidos,
                    "total_nao_lidos": tot_hqs - tot_lidos,
                    "media_avaliacao": med_aval,
                    "total_avaliados": r[5] or 0,
                }
            return {"total_hqs": 0, "total_prateleiras": total_prats, "total_editoras": 0, "total_generos": 0, "total_lidos": 0, "total_nao_lidos": 0, "media_avaliacao": 0.0, "total_avaliados": 0}
        except Exception as ex:
            print(f"Aviso Turso obter_estatisticas: {ex}")
            return {"total_hqs": 0, "total_prateleiras": 0, "total_editoras": 0, "total_generos": 0, "total_lidos": 0, "total_nao_lidos": 0, "media_avaliacao": 0.0, "total_avaliados": 0}
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql_stats)
            row = cursor.fetchone()
            cursor.execute(sql_prats)
            row_p = cursor.fetchone()
            total_prats = row_p["total_prat"] if row_p and row_p["total_prat"] is not None else 0
            if row:
                tot_hqs = row["total_hqs"] or 0
                tot_lidos = row["total_lidos"] or 0
                med_aval = round(float(row["media_aval"]), 1) if row["media_aval"] is not None else 0.0
                return {
                    "total_hqs": tot_hqs,
                    "total_prateleiras": total_prats,
                    "total_editoras": row["total_edit"] or 0,
                    "total_generos": row["total_gen"] or 0,
                    "total_lidos": tot_lidos,
                    "total_nao_lidos": tot_hqs - tot_lidos,
                    "media_avaliacao": med_aval,
                    "total_avaliados": row["total_avaliados"] or 0,
                }
            return {"total_hqs": 0, "total_prateleiras": total_prats, "total_editoras": 0, "total_generos": 0, "total_lidos": 0, "total_nao_lidos": 0, "media_avaliacao": 0.0, "total_avaliados": 0}
        finally:
            conn.close()


def deletar_hq(hq_id: int, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Exclui um registro específico por ID."""
    if is_using_turso():
        try:
            res = executar_turso_query("DELETE FROM hqs WHERE id = ?", [hq_id])
            return res.rows_affected > 0
        except Exception:
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hqs WHERE id = ?", (hq_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def deletar_hqs_em_massa(hq_ids: List[int], db_path: str = DB_DEFAULT_PATH) -> int:
    """Exclui múltiplos registros de HQs em lote por ID."""
    if not hq_ids:
        return 0

    placeholders = ", ".join(["?"] * len(hq_ids))
    sql = f"DELETE FROM hqs WHERE id IN ({placeholders})"
    params = [int(i) for i in hq_ids]

    if is_using_turso():
        try:
            res = executar_turso_query(sql, params)
            return res.rows_affected if hasattr(res, "rows_affected") else len(hq_ids)
        except Exception as ex:
            print(f"Erro Turso deletar_hqs_em_massa: {ex}")
            return 0
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


def atualizar_status_leitura_em_massa(hq_ids: List[int], novo_status: str, db_path: str = DB_DEFAULT_PATH) -> int:
    """Atualiza o status de leitura ('Lido' ou 'Não Lido') de múltiplos registros em lote."""
    if not hq_ids:
        return 0

    status_limpo = "Lido" if str(novo_status).strip().lower() == "lido" else "Não Lido"
    placeholders = ", ".join(["?"] * len(hq_ids))
    sql = f"UPDATE hqs SET lido = ? WHERE id IN ({placeholders})"
    params = [status_limpo] + [int(i) for i in hq_ids]

    if is_using_turso():
        try:
            res = executar_turso_query(sql, params)
            return res.rows_affected if hasattr(res, "rows_affected") else len(hq_ids)
        except Exception as ex:
            print(f"Erro Turso atualizar_status_leitura_em_massa: {ex}")
            return 0
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()


def atualizar_prateleira_em_massa(hq_ids: List[int], nova_prateleira: str, db_path: str = DB_DEFAULT_PATH) -> int:
    """Atualiza a prateleira de múltiplos registros de HQs em lote."""
    if not hq_ids:
        return 0

    prat_limpa = str(nova_prateleira or "").strip()
    if not prat_limpa:
        return 0

    # Garante que a nova prateleira esteja registrada
    cadastrar_prateleira(prat_limpa, db_path)

    placeholders = ", ".join(["?"] * len(hq_ids))
    sql = f"UPDATE hqs SET prateleira = ? WHERE id IN ({placeholders})"
    params = [prat_limpa] + [int(i) for i in hq_ids]

    if is_using_turso():
        try:
            res = executar_turso_query(sql, params)
            return res.rows_affected if hasattr(res, "rows_affected") else len(hq_ids)
        except Exception as ex:
            print(f"Erro Turso atualizar_prateleira_em_massa: {ex}")
            return 0
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()



def obter_hq_por_id(hq_id: int, db_path: str = DB_DEFAULT_PATH) -> Optional[Dict[str, Any]]:
    """Busca os dados de uma HQ específica pelo seu ID."""
    sql = "SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em FROM hqs WHERE id = ?"
    if is_using_turso():
        try:
            res = executar_turso_query(sql, [hq_id])
            if res.rows:
                return dict(zip(res.columns, res.rows[0]))
            return None
        except Exception:
            return None
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (hq_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()


def obter_hq_aleatoria(excluir_id: Optional[int] = None, db_path: str = DB_DEFAULT_PATH) -> Optional[Dict[str, Any]]:
    """
    Busca uma HQ cadastrada aleatoriamente no banco de dados.
    Permite opcionalmente excluir um ID específico para evitar repetições consecutivas.
    """
    if excluir_id is not None:
        sql = """
        SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
        FROM hqs
        WHERE id != ?
        ORDER BY RANDOM()
        LIMIT 1
        """
        params = [excluir_id]
    else:
        sql = """
        SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
        FROM hqs
        ORDER BY RANDOM()
        LIMIT 1
        """
        params = []

    if is_using_turso():
        try:
            res = executar_turso_query(sql, params)
            if res.rows:
                return dict(zip(res.columns, res.rows[0]))
            if excluir_id is not None:
                return obter_hq_aleatoria(excluir_id=None, db_path=db_path)
            return None
        except Exception as ex:
            print(f"Aviso Turso obter_hq_aleatoria: {ex}")
            return None
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            row = cursor.fetchone()
            if row:
                return dict(row)
            if excluir_id is not None:
                cursor.execute(
                    """
                    SELECT id, capa, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, avaliacao, resumo, resenha, criado_em
                    FROM hqs
                    ORDER BY RANDOM()
                    LIMIT 1
                    """
                )
                row_fallback = cursor.fetchone()
                if row_fallback:
                    return dict(row_fallback)
            return None
        finally:
            conn.close()



def atualizar_hq(
    hq_id: int,
    titulo: str,
    edicao: str,
    editora: str,
    prateleira: str,
    genero: str = "Outro",
    escritor: str = "Não informado",
    ilustrador: str = "Não informado",
    lido: str = "Não Lido",
    avaliacao: int = 0,
    capa: str = "",
    resenha: str = "",
    resumo: str = "",
    db_path: str = DB_DEFAULT_PATH
) -> bool:
    """Atualiza os campos de um registro de HQ existente."""
    try:
        val_avaliacao = max(0, min(5, int(avaliacao or 0)))
    except (ValueError, TypeError):
        val_avaliacao = 0

    sql = """
    UPDATE hqs
    SET titulo = ?, edicao = ?, editora = ?, genero = ?, escritor = ?, ilustrador = ?, prateleira = ?, lido = ?, avaliacao = ?, capa = ?, resenha = ?, resumo = ?
    WHERE id = ?
    """
    params = [
        titulo.strip(),
        edicao.strip(),
        editora.strip(),
        genero.strip(),
        escritor.strip(),
        ilustrador.strip(),
        prateleira.strip(),
        lido.strip(),
        val_avaliacao,
        capa.strip(),
        resenha.strip(),
        resumo.strip(),
        hq_id
    ]

    if is_using_turso():
        try:
            res = executar_turso_query(sql, params)
            return res.rows_affected > 0
        except Exception:
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def definir_capa(hq_id: int, capa: str, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Salva diretamente a imagem/foto da capa de uma HQ."""
    sql = "UPDATE hqs SET capa = ? WHERE id = ?"
    url_clean = (capa or "").strip()
    if is_using_turso():
        try:
            res = executar_turso_query(sql, [url_clean, hq_id])
            return res.rows_affected > 0
        except Exception:
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (url_clean, hq_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def remover_capa_hq(hq_id: int, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Remove a foto da capa de uma HQ cadastrada."""
    return definir_capa(hq_id, "", db_path)


def definir_avaliacao(hq_id: int, avaliacao: int, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Atualiza diretamente a nota/avaliação de uma HQ (1 a 5, ou 0 para sem avaliação)."""
    try:
        val_avaliacao = max(0, min(5, int(avaliacao or 0)))
    except (ValueError, TypeError):
        val_avaliacao = 0

    sql = "UPDATE hqs SET avaliacao = ? WHERE id = ?"
    if is_using_turso():
        try:
            res = executar_turso_query(sql, [val_avaliacao, hq_id])
            return res.rows_affected > 0
        except Exception:
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (val_avaliacao, hq_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def definir_resenha(hq_id: int, resenha: str, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Atualiza diretamente a resenha/opinião de uma HQ."""
    sql = "UPDATE hqs SET resenha = ? WHERE id = ?"
    resenha_clean = (resenha or "").strip()
    if is_using_turso():
        try:
            res = executar_turso_query(sql, [resenha_clean, hq_id])
            return res.rows_affected > 0
        except Exception:
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (resenha_clean, hq_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def definir_resumo(hq_id: int, resumo: str, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Atualiza diretamente o resumo/sinopse da história de uma HQ."""
    sql = "UPDATE hqs SET resumo = ? WHERE id = ?"
    resumo_clean = (resumo or "").strip()
    if is_using_turso():
        try:
            res = executar_turso_query(sql, [resumo_clean, hq_id])
            return res.rows_affected > 0
        except Exception:
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (resumo_clean, hq_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()



def alternar_status_leitura(hq_id: int, db_path: str = DB_DEFAULT_PATH) -> Optional[str]:
    """Alterna rapidamente o status de leitura entre 'Lido' e 'Não Lido'."""
    hq = obter_hq_por_id(hq_id, db_path)
    if not hq:
        return None
    
    novo_status = "Não Lido" if hq.get("lido") == "Lido" else "Lido"
    atualizar_hq(
        hq_id=hq_id,
        titulo=hq["titulo"],
        edicao=hq["edicao"],
        editora=hq["editora"],
        genero=hq.get("genero", "Outro"),
        escritor=hq.get("escritor", "Não informado"),
        ilustrador=hq.get("ilustrador", "Não informado"),
        prateleira=hq["prateleira"],
        lido=novo_status,
        avaliacao=int(hq.get("avaliacao") or 0),
        capa=hq.get("capa") or "",
        resenha=hq.get("resenha") or "",
        resumo=hq.get("resumo") or "",
        db_path=db_path
    )
    return novo_status


def obter_contexto_hqs_para_chat(db_path: str = DB_DEFAULT_PATH) -> List[Dict[str, Any]]:
    """Retorna todas as HQs do banco em formato de lista de dicionários para alimentar o chatbot."""
    df_ou_lista = listar_todas_hqs(db_path=db_path)
    if pd is not None and isinstance(df_ou_lista, pd.DataFrame):
        return df_ou_lista.to_dict(orient="records")
    elif isinstance(df_ou_lista, list):
        return df_ou_lista
    return []


# -------------------------------------------------------------
# FUNÇÕES DA LISTA DE DESEJOS (WISHLIST)
# -------------------------------------------------------------
def adicionar_item_lista_desejos(
    titulo: str,
    edicao: str = "",
    editora: str = "",
    melhor_preco: float = 0.0,
    melhor_loja: str = "",
    link_oferta: str = "",
    observacoes: str = "",
    db_path: str = DB_DEFAULT_PATH
) -> int:
    """Insere um novo título na Lista de Desejos."""
    tit_clean = (titulo or "").strip()
    if not tit_clean:
        return 0

    ed_clean = (edicao or "").strip()
    edit_clean = (editora or "").strip()
    loja_clean = (melhor_loja or "").strip()
    link_clean = (link_oferta or "").strip()
    obs_clean = (observacoes or "").strip()
    try:
        preco_val = float(melhor_preco or 0.0)
    except (ValueError, TypeError):
        preco_val = 0.0

    sql = """
    INSERT INTO lista_desejos (titulo, edicao, editora, melhor_preco, melhor_loja, link_oferta, observacoes)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    params = [tit_clean, ed_clean, edit_clean, preco_val, loja_clean, link_clean, obs_clean]

    if is_using_turso():
        try:
            executar_turso_query(sql, params)
            res_id = executar_turso_query("SELECT last_insert_rowid()").rows[0][0]
            return int(res_id) if res_id else 1
        except Exception as e:
            print(f"Erro ao adicionar na lista de desejos (Turso): {e}")
            return 0
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()


def listar_lista_desejos(db_path: str = DB_DEFAULT_PATH) -> Any:
    """Retorna todos os itens da Lista de Desejos."""
    sql = "SELECT id, titulo, edicao, editora, melhor_preco, melhor_loja, link_oferta, observacoes, criado_em FROM lista_desejos ORDER BY id DESC"
    if is_using_turso():
        try:
            res = executar_turso_query(sql)
            rows = [dict(zip(res.columns, r)) for r in res.rows]
            if pd is not None:
                return pd.DataFrame(rows)
            return rows
        except Exception:
            return pd.DataFrame() if pd is not None else []
    else:
        conn = get_sqlite_connection(db_path)
        try:
            if pd is not None:
                return pd.read_sql_query(sql, conn)
            else:
                cursor = conn.cursor()
                cursor.execute(sql)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        finally:
            conn.close()


def deletar_item_lista_desejos(item_id: int, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Remove um item da Lista de Desejos."""
    sql = "DELETE FROM lista_desejos WHERE id = ?"
    if is_using_turso():
        try:
            res = executar_turso_query(sql, [item_id])
            return res.rows_affected > 0
        except Exception:
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (item_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def obter_item_lista_desejos(item_id: int, db_path: str = DB_DEFAULT_PATH) -> Optional[Dict[str, Any]]:
    """Obtém um item específico da Lista de Desejos por ID."""
    sql = "SELECT id, titulo, edicao, editora, melhor_preco, melhor_loja, link_oferta, observacoes, criado_em FROM lista_desejos WHERE id = ?"
    if is_using_turso():
        try:
            res = executar_turso_query(sql, [item_id])
            if res.rows:
                return dict(zip(res.columns, res.rows[0]))
            return None
        except Exception:
            return None
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (item_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def atualizar_item_lista_desejos(
    item_id: int,
    titulo: Optional[str] = None,
    edicao: Optional[str] = None,
    editora: Optional[str] = None,
    melhor_preco: Optional[float] = None,
    melhor_loja: Optional[str] = None,
    link_oferta: Optional[str] = None,
    observacoes: Optional[str] = None,
    db_path: str = DB_DEFAULT_PATH
) -> bool:
    """Atualiza os campos de um item da Lista de Desejos."""
    campos = []
    valores = []

    if titulo is not None:
        campos.append("titulo = ?")
        valores.append(str(titulo).strip())
    if edicao is not None:
        campos.append("edicao = ?")
        valores.append(str(edicao).strip())
    if editora is not None:
        campos.append("editora = ?")
        valores.append(str(editora).strip())
    if melhor_preco is not None:
        try:
            preco_num = float(melhor_preco)
        except (ValueError, TypeError):
            preco_num = 0.0
        campos.append("melhor_preco = ?")
        valores.append(preco_num)
    if melhor_loja is not None:
        campos.append("melhor_loja = ?")
        valores.append(str(melhor_loja).strip())
    if link_oferta is not None:
        campos.append("link_oferta = ?")
        valores.append(str(link_oferta).strip())
    if observacoes is not None:
        campos.append("observacoes = ?")
        valores.append(str(observacoes).strip())

    if not campos:
        return False

    valores.append(item_id)
    sql = f"UPDATE lista_desejos SET {', '.join(campos)} WHERE id = ?"

    if is_using_turso():
        try:
            res = executar_turso_query(sql, valores)
            return res.rows_affected > 0
        except Exception as e:
            print(f"Erro ao atualizar lista de desejos (Turso): {e}")
            return False
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(valores))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()



