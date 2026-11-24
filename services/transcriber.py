import os
import requests
import logging

logger = logging.getLogger(__name__)

# Chaves fornecidas pelo usuário com rotação automática
DEFAULT_DEEPGRAM_KEYS = [
    "0d20de59426d3fae985a44d7d5d0d872801e5160",
    "b370aafd13202a734cdd9b4b4f7280717f07b397",
    "82002c93b06141d9aaa0a16b62ab71629cac4c39"
]

def get_keys() -> list[str]:
    env_keys = os.getenv("DEEPGRAM_KEYS", "").strip()
    if env_keys:
        return [k.strip() for k in env_keys.split(",") if k.strip()]
    single_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if single_key:
        return [single_key] + DEFAULT_DEEPGRAM_KEYS
    return DEFAULT_DEEPGRAM_KEYS

CURRENT_KEY_INDEX = 0

def get_active_key() -> str:
    global CURRENT_KEY_INDEX
    keys = get_keys()
    if not keys:
        return ""
    return keys[CURRENT_KEY_INDEX % len(keys)]

def rotate_key():
    global CURRENT_KEY_INDEX
    keys = get_keys()
    if keys:
        CURRENT_KEY_INDEX = (CURRENT_KEY_INDEX + 1) % len(keys)
        logger.warning(f"[Deepgram] Chave rotacionada para o índice {CURRENT_KEY_INDEX}")

def format_diarized_transcript(data: dict) -> tuple[str, str]:
    """
    Processa a resposta do Deepgram e extrai:
    1. Transcrição contínua limpa
    2. Transcrição com diarização de locutores (🗣️ Locutor 1, 🗣️ Locutor 2)
    """
    channels = data.get("results", {}).get("channels", [])
    if not channels:
        return "", ""

    alt = channels[0].get("alternatives", [])[0]
    plain_transcript = alt.get("transcript", "").strip()

    paragraphs_data = alt.get("paragraphs", {}).get("paragraphs", [])
    if not paragraphs_data:
        return plain_transcript, plain_transcript

    # Identifica quantos locutores diferentes falaram
    speakers = set(p.get("speaker", 0) for p in paragraphs_data)
    has_multiple_speakers = len(speakers) > 1

    formatted_lines = []
    for p in paragraphs_data:
        spk_num = p.get("speaker", 0) + 1
        sentences = [s.get("text", "").strip() for s in p.get("sentences", []) if s.get("text")]
        para_text = " ".join(sentences).strip()
        if not para_text:
            continue

        if has_multiple_speakers:
            formatted_lines.append(f"🗣️ **Locutor {spk_num}:** {para_text}")
        else:
            formatted_lines.append(para_text)

    diarized_text = "\n\n".join(formatted_lines)
    return plain_transcript, diarized_text if diarized_text else plain_transcript

def transcribe_with_deepgram(file_path: str) -> tuple[str, str]:
    """
    Transcreve um arquivo de áudio ou vídeo usando Deepgram Nova-3 com Diarização.
    Retorna (plain_text, diarized_text).
    """
    if not os.path.exists(file_path):
        logger.error(f"[Deepgram] Arquivo não encontrado: {file_path}")
        return "", ""

    keys = get_keys()
    if not keys:
        logger.warning("[Deepgram] Nenhuma chave do Deepgram configurada.")
        return "", ""

    # Lê os bytes do arquivo de mídia
    try:
        with open(file_path, "rb") as f:
            audio_bytes = f.read()
    except Exception as e:
        logger.error(f"[Deepgram] Erro ao ler arquivo de mídia: {e}")
        return "", ""

    ext = os.path.splitext(file_path)[1].lower()
    content_type_map = {
        ".mp3": "audio/mp3",
        ".m4a": "audio/m4a",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    # Tenta com rotação entre as chaves disponíveis
    max_retries = len(keys)
    for attempt in range(max_retries):
        current_key = get_active_key()
        headers = {
            "Authorization": f"Token {current_key}",
            "Content-Type": content_type,
        }

        # Modelo Nova-3 com diarização e pontuação inteligente
        params = {
            "model": "nova-3",
            "smart_format": "true",
            "diarize": "true",
            "punctuate": "true",
            "paragraphs": "true",
            "detect_language": "true",
        }

        url = "https://api.deepgram.com/v1/listen"

        try:
            res = requests.post(url, headers=headers, params=params, data=audio_bytes, timeout=30)

            # Se Nova-3 falhar por versão, tenta com Nova-2
            if res.status_code == 400 and "nova-3" in res.text.lower():
                params["model"] = "nova-2"
                res = requests.post(url, headers=headers, params=params, data=audio_bytes, timeout=30)

            if res.status_code == 200:
                data = res.json()
                plain, diarized = format_diarized_transcript(data)
                logger.info(f"[Deepgram Nova-3] Transcrição concluída com sucesso ({len(plain)} caracteres).")
                return plain, diarized

            # Caso ocorra erro de quota ou autorização, rotaciona a chave
            if res.status_code in (401, 402, 429):
                logger.warning(f"[Deepgram] Status {res.status_code} na chave {current_key[:8]}... Rotacionando.")
                rotate_key()
                continue
            else:
                logger.warning(f"[Deepgram] Resposta {res.status_code}: {res.text[:150]}")
                break

        except Exception as e:
            logger.error(f"[Deepgram] Erro na requisição: {e}")
            rotate_key()

    return "", ""
