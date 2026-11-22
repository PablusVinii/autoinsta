import os
import re
import tempfile
import time
import requests
import yt_dlp

# Expressões regulares para plataformas suportadas
PATTERNS = {
    "Instagram": re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|share/reel)/([a-zA-Z0-9_\-]+)", re.IGNORECASE),
    "YouTube": re.compile(r"https?://(?:www\.)?(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)([a-zA-Z0-9_\-]+)", re.IGNORECASE),
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

def get_youtube_video_id(url: str) -> str | None:
    """Extrai o ID do vídeo do YouTube de qualquer formato de link."""
    match = PATTERNS["YouTube"].search(url)
    if match:
        return match.group(1)
    return None

def get_youtube_transcript(video_id: str) -> str | None:
    """
    Obtém a transcrição oficial/automática do YouTube sem baixar vídeo nem áudio.
    Totalmente imune a bloqueios de data center e checagem de bots do Google.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        yt = YouTubeTranscriptApi()
        try:
            transcript = yt.fetch(video_id, languages=["pt", "pt-BR", "en"])
        except Exception:
            transcript_list = yt.list(video_id)
            transcripts = list(transcript_list)
            if not transcripts:
                return None
            transcript = transcripts[0].fetch()

        full_text = " ".join([snippet.text for snippet in transcript if hasattr(snippet, "text")])
        if not full_text:
            full_text = " ".join([snippet.get("text", "") for snippet in transcript if isinstance(snippet, dict)])
        return full_text.strip() if full_text else None
    except Exception as e:
        print(f"[YouTube Transcript] Não foi possível obter legendas para {video_id}: {e}")
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
    Baixa a mídia de plataformas suportadas (Instagram, TikTok, YouTube, X)
    usando yt-dlp e estratégias anti-bloqueio.
    """
    temp_dir = tempfile.mkdtemp(prefix="media_")

    # Se for TikTok, tenta a API direta primeiro (sem bloqueio de data center)
    if "tiktok.com" in url:
        tiktok_path = download_tiktok_api(url, temp_dir)
        if tiktok_path:
            return tiktok_path

    is_youtube = ("youtube.com" in url) or ("youtu.be" in url)

    # Para YouTube, usa formato otimizado e os clients android/ios para burlar checagens de bot
    if is_youtube:
        fmt = "ba[ext=m4a]/ba/b[ext=mp4]/best"
        extractor_args = {
            "youtube": {
                "player_client": ["android", "ios"]
            }
        }
    else:
        fmt = "mp4/best[ext=mp4]/best"
        extractor_args = {}

    out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")
    ydl_opts = {
        "format": fmt,
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "extractor_args": extractor_args,
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
                for ext in [".mp4", ".m4a", ".webm", ".mkv", ".mov"]:
                    candidate = base + ext
                    if os.path.exists(candidate):
                        return candidate
                files = os.listdir(temp_dir)
                if files:
                    return os.path.join(temp_dir, files[0])
                raise FileNotFoundError("Não foi possível localizar o arquivo baixado.")

            return filename
    except Exception as e:
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
