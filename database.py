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


def get_turso_client():
    """Retorna um cliente síncrono do Turso."""
    url, token = get_turso_credentials()
    if not url or not token:
        raise ValueError("Credenciais do Turso não configuradas.")
    # Converte libsql:// para https:// se necessário para compatibilidade HTTP
    clean_url = url.replace("libsql://", "https://")
    return libsql_client.create_client_sync(url=clean_url, auth_token=token)


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
        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    if is_using_turso():
        client = get_turso_client()
        try:
            client.execute(create_table_sql)
            # Migrações seguras no Turso
            try:
                res = client.execute("PRAGMA table_info(hqs)")
                cols = [r[1] for r in res.rows]
                if "lido" not in cols:
                    client.execute("ALTER TABLE hqs ADD COLUMN lido TEXT DEFAULT 'Não Lido'")
                if "genero" not in cols:
                    client.execute("ALTER TABLE hqs ADD COLUMN genero TEXT DEFAULT 'Outro'")
                if "escritor" not in cols:
                    client.execute("ALTER TABLE hqs ADD COLUMN escritor TEXT DEFAULT 'Não informado'")
                if "ilustrador" not in cols:
                    client.execute("ALTER TABLE hqs ADD COLUMN ilustrador TEXT DEFAULT 'Não informado'")
            except Exception:
                pass
        finally:
            client.close()
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(create_table_sql)
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

            conn.commit()
        finally:
            conn.close()


def salvar_hqs(
    itens: List[Dict[str, Any]],
    prateleira: str,
    db_path: str = DB_DEFAULT_PATH,
    lido_padrao: str = "Não Lido"
) -> int:
    """
    Insere uma lista de quadrinhos identificados no banco de dados associados à prateleira e autores.
    """
    if not itens:
        return 0

    registros = []
    for item in itens:
        titulo = (item.get("titulo") or "").strip()
        if not titulo:
            continue
        
        edicao = str(item.get("edicao") or "").strip()
        editora = (item.get("editora") or "").strip()
        genero = (item.get("genero") or "Outro").strip()
        escritor = (item.get("escritor") or "Não informado").strip()
        ilustrador = (item.get("ilustrador") or "Não informado").strip()
        prateleira_val = prateleira.strip() if prateleira else "Não especificada"
        lido_val = (item.get("lido") or lido_padrao).strip()

        registros.append((titulo, edicao, editora, genero, escritor, ilustrador, prateleira_val, lido_val))

    if not registros:
        return 0

    if is_using_turso():
        client = get_turso_client()
        try:
            for reg in registros:
                client.execute(
                    """
                    INSERT INTO hqs (titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    list(reg)
                )
        finally:
            client.close()
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO hqs (titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                registros,
            )
            conn.commit()
        finally:
            conn.close()

    return len(registros)


def listar_todas_hqs(
    busca: Optional[str] = None,
    prateleira_filtro: Optional[str] = None,
    genero_filtro: Optional[str] = None,
    status_leitura_filtro: Optional[str] = None,
    db_path: str = DB_DEFAULT_PATH
) -> Any:
    """
    Consulta o banco e retorna todas as HQs em formato pandas DataFrame ou lista de dicts.
    """
    query = "SELECT id, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, criado_em FROM hqs WHERE 1=1"
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

    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        query += " AND (titulo LIKE ? OR editora LIKE ? OR edicao LIKE ? OR genero LIKE ? OR escritor LIKE ? OR ilustrador LIKE ?)"
        params.extend([termo, termo, termo, termo, termo, termo])

    query += " ORDER BY id DESC"

    if is_using_turso():
        client = get_turso_client()
        try:
            res = client.execute(query, params)
            rows = [dict(zip(res.columns, r)) for r in res.rows]
            if pd is not None:
                return pd.DataFrame(rows)
            return rows
        finally:
            client.close()
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


def obter_prateleiras(db_path: str = DB_DEFAULT_PATH) -> List[str]:
    """Retorna uma lista única de prateleiras cadastradas."""
    sql = "SELECT DISTINCT prateleira FROM hqs WHERE prateleira IS NOT NULL AND prateleira != '' ORDER BY prateleira ASC"
    if is_using_turso():
        client = get_turso_client()
        try:
            res = client.execute(sql)
            return [r[0] for r in res.rows if r[0]]
        finally:
            client.close()
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [row["prateleira"] for row in rows]
        finally:
            conn.close()


def obter_generos(db_path: str = DB_DEFAULT_PATH) -> List[str]:
    """Retorna uma lista única de gêneros cadastrados."""
    sql = "SELECT DISTINCT genero FROM hqs WHERE genero IS NOT NULL AND genero != '' ORDER BY genero ASC"
    if is_using_turso():
        client = get_turso_client()
        try:
            res = client.execute(sql)
            return [r[0] for r in res.rows if r[0]]
        finally:
            client.close()
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
    """Retorna métricas gerais da coleção."""
    if is_using_turso():
        client = get_turso_client()
        try:
            total_hqs = client.execute("SELECT COUNT(*) FROM hqs").rows[0][0] or 0
            total_prat = client.execute("SELECT COUNT(DISTINCT prateleira) FROM hqs WHERE prateleira != ''").rows[0][0] or 0
            total_edit = client.execute("SELECT COUNT(DISTINCT editora) FROM hqs WHERE editora != ''").rows[0][0] or 0
            total_gen = client.execute("SELECT COUNT(DISTINCT genero) FROM hqs WHERE genero != ''").rows[0][0] or 0
            total_lidos = client.execute("SELECT COUNT(*) FROM hqs WHERE lido = 'Lido'").rows[0][0] or 0
            total_nao_lidos = total_hqs - total_lidos
            return {
                "total_hqs": total_hqs,
                "total_prateleiras": total_prat,
                "total_editoras": total_edit,
                "total_generos": total_gen,
                "total_lidos": total_lidos,
                "total_nao_lidos": total_nao_lidos,
            }
        finally:
            client.close()
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM hqs")
            total_hqs = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(DISTINCT prateleira) as total_prat FROM hqs")
            total_prateleiras = cursor.fetchone()["total_prat"]

            cursor.execute("SELECT COUNT(DISTINCT editora) as total_edit FROM hqs WHERE editora != '' AND editora IS NOT NULL")
            total_editoras = cursor.fetchone()["total_edit"]

            cursor.execute("SELECT COUNT(DISTINCT genero) as total_gen FROM hqs WHERE genero != '' AND genero IS NOT NULL")
            total_generos = cursor.fetchone()["total_gen"]

            cursor.execute("SELECT COUNT(*) as total_lidos FROM hqs WHERE lido = 'Lido'")
            total_lidos = cursor.fetchone()["total_lidos"]

            total_nao_lidos = total_hqs - total_lidos

            return {
                "total_hqs": total_hqs,
                "total_prateleiras": total_prateleiras,
                "total_editoras": total_editoras,
                "total_generos": total_generos,
                "total_lidos": total_lidos,
                "total_nao_lidos": total_nao_lidos,
            }
        finally:
            conn.close()


def deletar_hq(hq_id: int, db_path: str = DB_DEFAULT_PATH) -> bool:
    """Exclui um registro específico por ID."""
    if is_using_turso():
        client = get_turso_client()
        try:
            res = client.execute("DELETE FROM hqs WHERE id = ?", [hq_id])
            return res.rows_affected > 0
        finally:
            client.close()
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hqs WHERE id = ?", (hq_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


def obter_hq_por_id(hq_id: int, db_path: str = DB_DEFAULT_PATH) -> Optional[Dict[str, Any]]:
    """Busca os dados de uma HQ específica pelo seu ID."""
    sql = "SELECT id, titulo, edicao, editora, genero, escritor, ilustrador, prateleira, lido, criado_em FROM hqs WHERE id = ?"
    if is_using_turso():
        client = get_turso_client()
        try:
            res = client.execute(sql, [hq_id])
            if res.rows:
                return dict(zip(res.columns, res.rows[0]))
            return None
        finally:
            client.close()
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
    db_path: str = DB_DEFAULT_PATH
) -> bool:
    """Atualiza os campos de um registro de HQ existente."""
    sql = """
    UPDATE hqs
    SET titulo = ?, edicao = ?, editora = ?, genero = ?, escritor = ?, ilustrador = ?, prateleira = ?, lido = ?
    WHERE id = ?
    """
    params = [titulo.strip(), edicao.strip(), editora.strip(), genero.strip(), escritor.strip(), ilustrador.strip(), prateleira.strip(), lido.strip(), hq_id]

    if is_using_turso():
        client = get_turso_client()
        try:
            res = client.execute(sql, params)
            return res.rows_affected > 0
        finally:
            client.close()
    else:
        conn = get_sqlite_connection(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, tuple(params))
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
        db_path=db_path
    )
    return novo_status
