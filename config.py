import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-4-hydrogen").strip()
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "").strip()
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "").strip()

_allowed_raw = os.getenv("ALLOWED_USER_IDS", "").strip()
if _allowed_raw:
    ALLOWED_USER_IDS = [int(uid.strip()) for uid in _allowed_raw.split(",") if uid.strip().isdigit()]
else:
    ALLOWED_USER_IDS = []

def validate_config():
    errors = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "seu_token_aqui":
        errors.append("TELEGRAM_BOT_TOKEN não configurado no arquivo .env.")
    if not GEMINI_API_KEY or GEMINI_API_KEY == "sua_chave_gemini_aqui":
        errors.append("GEMINI_API_KEY não configurado no arquivo .env.")
    if errors:
        raise ValueError("\n".join(errors))
