import os
import re
import tempfile
import time
import requests
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

extract_instagram_url = lambda text: (extract_video_url(text) or (None, None))[0]

def download_tiktok_api(url: str, temp_dir: str) -> str | None:
    """
    Faz download do TikTok via TikWM API (ignora bloqueios de IP de datacenter e erro 10231).
    """
    try:
        api_url = "https://www.tikwm.com/api/"
        params = {"url": url, "hd": 1}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        resp = requests.get(api_url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                video_data = data.get("data", {})
                video_url = video_data.get("play") or video_data.get("hdplay")
                if video_url:
                    out_path = os.path.join(temp_dir, f"tiktok_{int(time.time())}.mp4")
                    v_resp = requests.get(video_url, headers=headers, stream=True, timeout=30)
                    if v_resp.status_code == 200:
                        with open(out_path, "wb") as f:
                            for chunk in v_resp.iter_content(chunk_size=16384):
                                if chunk:
                                    f.write(chunk)
                        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                            return out_path
    except Exception as e:
        print(f"[TikWM] Erro ao baixar via TikWM API: {e}")
    return None

def download_video(url: str) -> str:
    """
    Baixa o vídeo de qualquer plataforma suportada (Instagram, TikTok, YouTube Shorts, X)
    usando yt-dlp e fallback dedicado para TikTok.
    """
    temp_dir = tempfile.mkdtemp(prefix="video_")

    # Se for TikTok, tenta a API direta primeiro (muito mais rápida e sem bloqueio de IP de datacenter)
    if "tiktok.com" in url:
        tiktok_path = download_tiktok_api(url, temp_dir)
        if tiktok_path:
            return tiktok_path

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

    try:
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
    except Exception as e:
        # Fallback de última chance para TikTok caso tenha falhado anteriormente
        if "tiktok.com" in url:
            fallback_path = download_tiktok_api(url, temp_dir)
            if fallback_path:
                return fallback_path
        raise e

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
