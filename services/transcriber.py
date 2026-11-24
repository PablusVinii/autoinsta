import os
import re
import uuid
import tempfile
import requests
import logging
import edge_tts

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

def is_non_portuguese(text: str, detected_language: str = "") -> bool:
    """Verifica se o áudio transcrito está em inglês ou outro idioma não-português."""
    if detected_language:
        if not detected_language.lower().startswith("pt"):
            return True
        return False

    lower = text.lower()
    english_words = [" the ", " and ", " you ", " that ", " this ", " with ", " for ", " are ", " have ", " from ", " what ", " why ", " business ", " people "]
    matches = sum(1 for w in english_words if w in lower)
    return matches >= 2

def translate_to_portuguese(text: str) -> str:
    """
    Traduz a transcrição para o Português do Brasil mantendo as marcações de locutores intactas.
    """
    if not text or not text.strip():
        return ""

    prompt = (
        "Você é um tradutor executivo sênior especializado em Português do Brasil (pt-BR).\n"
        "Traduza o diálogo e a transcrição abaixo com vocabulário natural, fluído e idiomático para o Português do Brasil.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. MANTENHA RIGOROSAMENTE todas as marcações de locutores exatamente como estão (exemplo: '🗣️ **Locutor 1:**', '🗣️ **Locutor 2:**').\n"
        "2. NÃO resuma, NÃO pule nenhuma fala e NÃO adicione comentários próprios.\n"
        "3. Se o texto já estiver integralmente em português, retorne-o exatamente como está.\n\n"
        f"Texto original:\n{text}"
    )
    try:
        from google import genai
        import config
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        res = client.interactions.create(
            model=config.GEMINI_MODEL,
            input=prompt
        )
        translated = res.output_text.strip()
        return translated if translated else text
    except Exception as e:
        logger.error(f"[Transcriber Translator] Erro ao traduzir: {e}")
        return text

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
                detected_lang = data.get("results", {}).get("channels", [{}])[0].get("detected_language", "")
                plain, diarized = format_diarized_transcript(data)

                # Se o áudio original estiver em inglês ou outro idioma, traduz para pt-BR preservando os locutores
                if is_non_portuguese(diarized, detected_lang):
                    logger.info(f"[Deepgram] Áudio detectado em '{detected_lang or 'idioma estrangeiro'}'. Traduzindo transcrição para pt-BR...")
                    diarized = translate_to_portuguese(diarized)
                    plain = translate_to_portuguese(plain)

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

DEEPGRAM_AURA_VOICES = {
    1: "aura-2-orion-en",   # Masculino conversacional, dinâmico e enérgico (Aura-2)
    2: "aura-2-asteria-en", # Feminina expressiva, jovem e articulada (Aura-2)
    3: "aura-2-arcas-en",   # Masculino grave, autoridade e profundidade (Aura-2)
    4: "aura-2-luna-en",    # Feminina suave e natural (Aura-2)
}

def synthesize_turn_deepgram_aura(text: str, voice_model: str = "aura-2-orion-en") -> bytes:
    """Sintetiza um trecho de texto usando o modelo de voz Deepgram Aura com rotação de chaves."""
    clean_text = text.strip()
    if not clean_text:
        return b""

    keys = get_keys()
    for _ in range(len(keys)):
        key = get_active_key()
        headers = {
            "Authorization": f"Token {key}",
            "Content-Type": "application/json"
        }
        url = f"https://api.deepgram.com/v1/speak?model={voice_model}"
        payload = {"text": clean_text}

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                return res.content
            elif res.status_code in (401, 402, 429):
                logger.warning(f"[Deepgram Aura] Quota/Auth {res.status_code}. Rotacionando chave...")
                rotate_key()
                continue
            else:
                logger.warning(f"[Deepgram Aura] Status {res.status_code}: {res.text[:120]}")
                break
        except Exception as e:
            logger.error(f"[Deepgram Aura] Erro de rede: {e}")
            rotate_key()

    return b""

def clean_speech_line(text: str) -> str:
    """Limpa marcações e símbolos desnecessários para síntese de voz fluida."""
    text = re.sub(r'[*#_>`~]', '', text)
    text = re.sub(r'https?://\S+', '', text)
    return text.strip()

async def generate_dubbed_audio(transcription: str, output_file: str = None) -> str:
    """
    Gera um áudio de dublagem multi-voz com os modelos expressivos do Deepgram Aura (com sotaque conversacional autêntico).
    Cada locutor recebe uma voz do Deepgram Aura diferente. Se falhar, usa fallback neural.
    """
    if not output_file:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        output_file = tmp.name
        tmp.close()

    pattern = r'🗣️\s*\*\*Locutor\s*(\d+):\*\*\s*(.+)'
    turns = []
    current_spk = 1
    current_texts = []

    lines = transcription.strip().split('\n')
    has_speakers = False

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        m = re.match(pattern, line_clean)
        if m:
            has_speakers = True
            if current_texts:
                turns.append((current_spk, ' '.join(current_texts)))
                current_texts = []
            current_spk = int(m.group(1))
            current_texts.append(m.group(2))
        else:
            current_texts.append(line_clean)

    if current_texts:
        turns.append((current_spk, ' '.join(current_texts)))

    # Se for monólogo sem múltiplos locutores
    if not has_speakers:
        turns = [(1, transcription)]

    # Sintetiza com Deepgram Aura
    audio_chunks = []
    use_fallback = False

    for spk, text in turns:
        clean = clean_speech_line(text)
        if not clean:
            continue

        voice_aura = DEEPGRAM_AURA_VOICES.get(spk, "aura-2-orion-en")
        
        # Deepgram aceita blocos de texto; se for muito longo, divide em frases
        sub_chunks = []
        if len(clean) > 1500:
            sentences = re.split(r'(?<=[.!?])\s+', clean)
            curr = ""
            for s in sentences:
                if len(curr) + len(s) < 1200:
                    curr += s + " "
                else:
                    if curr: sub_chunks.append(curr.strip())
                    curr = s + " "
            if curr: sub_chunks.append(curr.strip())
        else:
            sub_chunks = [clean]

        for chunk_text in sub_chunks:
            chunk_bytes = synthesize_turn_deepgram_aura(chunk_text, voice_aura)
            if chunk_bytes:
                audio_chunks.append(chunk_bytes)
            else:
                use_fallback = True
                break
        if use_fallback:
            break

    # Se Deepgram Aura gerou os bytes com sucesso, salva no arquivo
    if audio_chunks and not use_fallback:
        with open(output_file, "wb") as fout:
            for b in audio_chunks:
                fout.write(b)
        logger.info(f"[Deepgram Aura] Dublagem gerada com sucesso via Aura ({os.path.getsize(output_file)} bytes).")
        return output_file

    # Fallback seguro para Edge TTS se o Aura estiver sem cota
    logger.warning("[Deepgram Aura] Usando fallback neural para dublagem...")
    VOICE_FALLBACK = {
        1: "pt-BR-AntonioNeural",
        2: "pt-BR-FranciscaNeural",
        3: "pt-BR-FabioNeural",
        4: "pt-BR-ThalitaNeural",
    }
    fb_chunks = []
    try:
        for i, (spk, text) in enumerate(turns):
            voice = VOICE_FALLBACK.get(spk, "pt-BR-AntonioNeural")
            clean = clean_speech_line(text)
            if not clean:
                continue
            tmp_name = os.path.join(tempfile.gettempdir(), f"fb_chunk_{uuid.uuid4().hex[:8]}_{i}.mp3")
            comm = edge_tts.Communicate(clean, voice=voice)
            await comm.save(tmp_name)
            fb_chunks.append(tmp_name)

        with open(output_file, "wb") as fout:
            for c in fb_chunks:
                if os.path.exists(c):
                    with open(c, "rb") as f_in:
                        fout.write(f_in.read())
                    try: os.remove(c)
                    except Exception: pass
        return output_file
    except Exception as e:
        logger.error(f"[Dubbing Fallback] Erro no fallback: {e}")
        for c in fb_chunks:
            if os.path.exists(c):
                try: os.remove(c)
                except Exception: pass
        raise
