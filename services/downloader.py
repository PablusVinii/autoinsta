import os
import re
import tempfile
import yt_dlp

# Expressões regulares para plataformas suportadas
PATTERNS = {
    "Instagram": re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|share/reel)/([a-zA-Z0-9_\-]+)", re.IGNORECASE),
    "YouTube Shorts": re.compile(r"https?://(?:www\.)?(?:youtube\.com/shorts/|youtu\.be/)([a-zA-Z0-9_\-]+)", re.IGNORECASE),
    "TikTok": re.compile(r"https?://(?:(?:www|vm|vt)\.)?tiktok\.com/(?:@[a-zA-Z0-9_.]+/video/|v/|t/)?([a-zA-Z0-9_\-]+)", re.IGNORECASE),
    "Twitter/X": re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[a-zA-Z0-9_]+/status/([0-9]+)", re.IGNORECASE),
}

def extract_video_url(text: str) -> tuple[str, str] | None:
    """
    Identifica se a mensagem contém um link de vídeo suportado.
    Retorna tupla (url_original, plataforma) ou None.
    """
    if not text:
        return None

    for platform, pattern in PATTERNS.items():
        match = pattern.search(text)
        if match:
            raw_url = match.group(0)
            return raw_url, platform

    return None

# Compatibilidade retroativa
extract_instagram_url = lambda text: (extract_video_url(text) or (None, None))[0]

def download_video(url: str) -> str:
    """
    Baixa o vídeo de qualquer plataforma suportada (Instagram, TikTok, YouTube Shorts, X)
    usando yt-dlp e retorna o caminho do arquivo temporário.
    """
    temp_dir = tempfile.mkdtemp(prefix="video_")
    out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "mp4/best[ext=mp4]/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        if not os.path.exists(filename):
            base, _ = os.path.splitext(filename)
            for ext in [".mp4", ".mkv", ".webm", ".mov"]:
                candidate = base + ext
                if os.path.exists(candidate):
                    return candidate
            files = os.listdir(temp_dir)
            if files:
                return os.path.join(temp_dir, files[0])
            raise FileNotFoundError("Não foi possível localizar o arquivo baixado.")

        return filename

# Alias de compatibilidade
download_reel = download_video

def cleanup_media(file_path: str):
    """Remove o arquivo de mídia temporário e o diretório associado se vazio."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            parent_dir = os.path.dirname(file_path)
            if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
    except Exception as e:
        print(f"[Cleanup] Aviso ao excluir arquivo temporário {file_path}: {e}")
