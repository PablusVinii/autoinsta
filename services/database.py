import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "saved_videos.db")

def init_db():
    """Inicializa a tabela de vídeos salvos no SQLite."""
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_video(user_id: int, title: str, category: str, platform: str, url: str, summary: str):
    """Salva um vídeo processado na base de dados pessoal."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO saved_videos (user_id, title, category, platform, url, summary)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, title, category, platform, url, summary))
    conn.commit()
    conn.close()

def get_user_videos(user_id: int, limit: int = 10) -> list[dict]:
    """Retorna os últimos vídeos salvos pelo usuário."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT title, category, platform, url, created_at
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
            "url": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]

init_db()
