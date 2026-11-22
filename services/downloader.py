import os
import re
import tempfile
import yt_dlp

INSTAGRAM_URL_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p|share/reel)/([a-zA-Z0-9_\-]+)",
    re.IGNORECASE
)

def extract_instagram_url(text: str) -> str | None:
    """Extrai a URL do Instagram Reels ou Post do texto da mensagem."""
    if not text:
        return None
    match = INSTAGRAM_URL_REGEX.search(text)
    if match:
        # Retorna a URL base limpa
        code = match.group(1)
        return f"https://www.instagram.com/reel/{code}/"
    return None

def download_reel(url: str) -> str:
    """
    Baixa o vídeo do Reels usando yt-dlp e retorna o caminho do arquivo temporário.
    """
    temp_dir = tempfile.mkdtemp(prefix="reel_")
    out_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "mp4/best[ext=mp4]/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        # Headers genéricos para evitar restrições simples
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        # Se yt-dlp salvou com outra extensão comum
        if not os.path.exists(filename):
            base, _ = os.path.splitext(filename)
            for ext in [".mp4", ".mkv", ".webm", ".mov"]:
                candidate = base + ext
                if os.path.exists(candidate):
                    return candidate
            # Busca qualquer arquivo criado no diretório
            files = os.listdir(temp_dir)
            if files:
                return os.path.join(temp_dir, files[0])
            raise FileNotFoundError("Não foi possível localizar o arquivo baixado.")

        return filename

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
