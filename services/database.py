import json
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "saved_videos.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


def _use_postgres() -> bool:
    return bool(DATABASE_URL and HAS_PSYCOPG2)


def _get_conn():
    if _use_postgres():
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect(DB_PATH)


def _ph() -> str:
    return "%s" if _use_postgres() else "?"


def init_db():
    """Inicializa as tabelas (saved_videos e video_cache) em Postgres ou SQLite."""
    conn = _get_conn()
    cursor = conn.cursor()

    if _use_postgres():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_videos (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                title TEXT,
                category TEXT,
                platform TEXT,
                url TEXT,
                summary TEXT,
                transcription TEXT DEFAULT '',
                obsidian_content TEXT DEFAULT '',
                wikilinks TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_cache (
                cache_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("[Database] PostgreSQL conectado e inicializado.")
        return

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            category TEXT,
            platform TEXT,
            url TEXT,
            summary TEXT,
            transcription TEXT DEFAULT '',
            obsidian_content TEXT DEFAULT '',
            wikilinks TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS video_cache (
            cache_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Migração segura para bancos SQLite existentes
    cursor.execute("PRAGMA table_info(saved_videos)")
    columns = [row[1] for row in cursor.fetchall()]

    if "transcription" not in columns:
        cursor.execute("ALTER TABLE saved_videos ADD COLUMN transcription TEXT DEFAULT ''")
    if "obsidian_content" not in columns:
        cursor.execute("ALTER TABLE saved_videos ADD COLUMN obsidian_content TEXT DEFAULT ''")
    if "wikilinks" not in columns:
        cursor.execute("ALTER TABLE saved_videos ADD COLUMN wikilinks TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def save_cache_entry(cache_id: str, data: dict):
    """Persiste os dados do card no banco para sobreviver a reinícios do servidor."""
    if not cache_id or not isinstance(data, dict):
        return
    # Remove bytes pesados antes de serializar em JSON
    clean_data = {k: v for k, v in data.items() if k != "cover_bytes"}
    payload_json = json.dumps(clean_data, ensure_ascii=False)

    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    if _use_postgres():
        cursor.execute(f"""
            INSERT INTO video_cache (cache_id, payload_json, updated_at)
            VALUES ({p}, {p}, CURRENT_TIMESTAMP)
            ON CONFLICT (cache_id) DO UPDATE SET
                payload_json = EXCLUDED.payload_json,
                updated_at = CURRENT_TIMESTAMP
        """, (cache_id, payload_json))
    else:
        cursor.execute(f"""
            INSERT OR REPLACE INTO video_cache (cache_id, payload_json, updated_at)
            VALUES ({p}, {p}, CURRENT_TIMESTAMP)
        """, (cache_id, payload_json))
    conn.commit()
    conn.close()


def get_cache_entry(cache_id: str) -> dict | None:
    """Recupera os dados do card do banco caso não estejam mais na RAM."""
    if not cache_id:
        return None
    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    cursor.execute(f"SELECT payload_json FROM video_cache WHERE cache_id = {p}", (cache_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def save_video(
    user_id: int,
    title: str,
    category: str,
    platform: str,
    url: str,
    summary: str,
    transcription: str = "",
    obsidian_content: str = "",
    wikilinks: str = ""
) -> int:
    """Salva um vídeo processado na base de dados pessoal."""
    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    if _use_postgres():
        cursor.execute(f"""
            INSERT INTO saved_videos (user_id, title, category, platform, url, summary, transcription, obsidian_content, wikilinks)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            RETURNING id
        """, (user_id, title, category, platform, url, summary, transcription, obsidian_content, wikilinks))
        row_id = cursor.fetchone()[0]
    else:
        cursor.execute(f"""
            INSERT INTO saved_videos (user_id, title, category, platform, url, summary, transcription, obsidian_content, wikilinks)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
        """, (user_id, title, category, platform, url, summary, transcription, obsidian_content, wikilinks))
        row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def update_obsidian_data(user_id: int, url: str, obsidian_content: str, wikilinks: str):
    """Atualiza o conteúdo Markdown formatado e wikilinks da nota salva."""
    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    cursor.execute(f"""
        UPDATE saved_videos
        SET obsidian_content = {p}, wikilinks = {p}
        WHERE user_id = {p} AND url = {p}
    """, (obsidian_content, wikilinks, user_id, url))
    conn.commit()
    conn.close()


def get_user_videos(user_id: int, limit: int = 10) -> list[dict]:
    """Retorna os últimos vídeos salvos pelo usuário."""
    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    cursor.execute(f"""
        SELECT id, title, category, platform, url, summary, wikilinks, created_at
        FROM saved_videos
        WHERE user_id = {p}
        ORDER BY id DESC
        LIMIT {p}
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "title": r[1],
            "category": r[2],
            "platform": r[3],
            "url": r[4],
            "summary": r[5],
            "wikilinks": r[6],
            "created_at": str(r[7]),
        }
        for r in rows
    ]


def get_obsidian_notes(user_id: int, limit: int = 10) -> list[dict]:
    """Retorna as notas formatadas para o Obsidian ou salvas no cofre."""
    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    cursor.execute(f"""
        SELECT id, title, category, platform, url, wikilinks, obsidian_content, created_at
        FROM saved_videos
        WHERE user_id = {p}
        ORDER BY id DESC
        LIMIT {p}
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "title": r[1],
            "category": r[2],
            "platform": r[3],
            "url": r[4],
            "wikilinks": r[5],
            "obsidian_content": r[6],
            "created_at": str(r[7]),
        }
        for r in rows
    ]


def search_saved_videos(user_id: int, query: str, limit: int = 8) -> list[dict]:
    """
    Busca inteligente por termos no título, categoria, resumo, transcrição e wikilinks.
    """
    terms = [t.strip() for t in query.split() if len(t.strip()) >= 2]
    if not terms:
        terms = [query.strip()]

    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    op = "ILIKE" if _use_postgres() else "LIKE"

    conditions = []
    params = [user_id]
    for term in terms:
        wildcard = f"%{term}%"
        conditions.append(f"""
            (title {op} {p} OR category {op} {p} OR summary {op} {p} OR transcription {op} {p} OR wikilinks {op} {p})
        """)
        params.extend([wildcard, wildcard, wildcard, wildcard, wildcard])

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    params.append(limit)

    cursor.execute(f"""
        SELECT id, title, category, platform, url, summary, wikilinks, created_at
        FROM saved_videos
        WHERE user_id = {p} AND ({where_clause})
        ORDER BY id DESC
        LIMIT {p}
    """, params)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "title": r[1],
            "category": r[2],
            "platform": r[3],
            "url": r[4],
            "summary": r[5],
            "wikilinks": r[6],
            "created_at": str(r[7]),
        }
        for r in rows
    ]


def get_all_notes_for_synthesis(user_id: int, limit: int = 25) -> list[dict]:
    """Retorna um lote de notas para a IA sintetizar conhecimento cruzado."""
    conn = _get_conn()
    cursor = conn.cursor()
    p = _ph()
    cursor.execute(f"""
        SELECT title, category, platform, summary, wikilinks, created_at
        FROM saved_videos
        WHERE user_id = {p}
        ORDER BY id DESC
        LIMIT {p}
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "title": r[0],
            "category": r[1],
            "platform": r[2],
            "summary": r[3],
            "wikilinks": r[4],
            "created_at": str(r[5]),
        }
        for r in rows
    ]
