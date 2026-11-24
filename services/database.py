import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "saved_videos.db")

def init_db():
    """Inicializa a tabela de vídeos salvos e migra novas colunas se necessário."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    conn.commit()

    # Migração segura para bancos existentes
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO saved_videos (user_id, title, category, platform, url, summary, transcription, obsidian_content, wikilinks)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, title, category, platform, url, summary, transcription, obsidian_content, wikilinks))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id

def update_obsidian_data(user_id: int, url: str, obsidian_content: str, wikilinks: str):
    """Atualiza o conteúdo Markdown formatado e wikilinks da nota salva."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE saved_videos
        SET obsidian_content = ?, wikilinks = ?
        WHERE user_id = ? AND url = ?
    """, (obsidian_content, wikilinks, user_id, url))
    conn.commit()
    conn.close()

def get_user_videos(user_id: int, limit: int = 10) -> list[dict]:
    """Retorna os últimos vídeos salvos pelo usuário."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, category, platform, url, summary, wikilinks, created_at
        FROM saved_videos
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
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
            "created_at": r[7],
        }
        for r in rows
    ]

def get_obsidian_notes(user_id: int, limit: int = 10) -> list[dict]:
    """Retorna as notas formatadas para o Obsidian ou salvas no cofre."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, category, platform, url, wikilinks, obsidian_content, created_at
        FROM saved_videos
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
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
            "created_at": r[7],
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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    conditions = []
    params = [user_id]
    for term in terms:
        wildcard = f"%{term}%"
        conditions.append("""
            (title LIKE ? OR category LIKE ? OR summary LIKE ? OR transcription LIKE ? OR wikilinks LIKE ?)
        """)
        params.extend([wildcard, wildcard, wildcard, wildcard, wildcard])

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    params.append(limit)

    cursor.execute(f"""
        SELECT id, title, category, platform, url, summary, wikilinks, created_at
        FROM saved_videos
        WHERE user_id = ? AND ({where_clause})
        ORDER BY id DESC
        LIMIT ?
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
            "created_at": r[7],
        }
        for r in rows
    ]

def get_all_notes_for_synthesis(user_id: int, limit: int = 25) -> list[dict]:
    """Retorna um lote de notas para a IA sintetizar conhecimento cruzado."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT title, category, platform, summary, wikilinks, created_at
        FROM saved_videos
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
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
            "created_at": r[5],
        }
        for r in rows
    ]

init_db()
