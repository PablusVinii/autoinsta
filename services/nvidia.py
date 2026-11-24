import os
import re
import math
import asyncio
import tempfile
import requests
import logging
import edge_tts
import config

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
EMBEDDING_MODEL = "nvidia/nemotron-3.5-embed-1b"
REASONING_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
FAST_MODEL = "nvidia/nemotron-3.5-bolt-e4b"

def get_headers():
    key = config.NVIDIA_API_KEY or os.getenv("NVIDIA_API_KEY", "").strip()
    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

# ==========================================
# OPÇÃO A: RAG SEMÂNTICO (EMBEDDINGS & VETORES)
# ==========================================

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calcula a similaridade de cosseno pura entre dois vetores."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

def get_embedding(text: str, input_type: str = "query") -> list[float]:
    """
    Gera o vetor semântico (2048 dimensões) de um texto usando a NVIDIA NIM.
    """
    if not config.NVIDIA_API_KEY:
        return []

    clean_text = text.strip()[:1000]
    if not clean_text:
        return []

    url = f"{NVIDIA_BASE_URL}/embeddings"
    payload = {
        "model": EMBEDDING_MODEL,
        "input": [clean_text],
        "input_type": input_type,
    }

    try:
        res = requests.post(url, headers=get_headers(), json=payload, timeout=12)
        if res.status_code == 200:
            data = res.json().get("data", [])
            if data and "embedding" in data[0]:
                return data[0]["embedding"]
        else:
            logger.warning(f"[NVIDIA Embeddings] Status {res.status_code}: {res.text[:120]}")
    except Exception as e:
        logger.error(f"[NVIDIA Embeddings] Erro ao obter embedding: {e}")

    return []

def semantic_search(query: str, items: list[dict], top_k: int = 5) -> list[dict]:
    """
    Pesquisa semântica: compara o significado da pergunta com os resumos das notas.
    Retorna os itens ordenados pela maior similaridade semântica.
    """
    if not items:
        return []

    query_vec = get_embedding(query, input_type="query")
    if not query_vec:
        return items[:top_k]

    scored_items = []
    for item in items:
        # Monta representação rica do item para o vetor
        title = item.get("title", "")
        category = item.get("category", "")
        summary = item.get("summary", "")[:500]
        text_repr = f"{title}. Categoria: {category}. {summary}"

        item_vec = get_embedding(text_repr, input_type="passage")
        sim = cosine_similarity(query_vec, item_vec) if item_vec else 0.0

        item_copy = dict(item)
        item_copy["similarity_score"] = sim
        scored_items.append(item_copy)

    # Ordena por maior similaridade
    scored_items.sort(key=lambda x: x["similarity_score"], reverse=True)
    return scored_items[:top_k]

# ==========================================
# OPÇÃO B: AUDITOR CRÍTICO (ADVOGADO DO DIABO)
# ==========================================

CRITIQUE_PROMPT = """
Você é o Auditor Crítico Sênior do Segundo Cérebro.
Sua função NÃO é bajular, concordar ou elogiar o vídeo. Você deve agir como um "Advogado do Diabo" analítico, cético e experiente.

Avalie a ideia com rigor profissional:
Título do Vídeo: {title}
Categoria/Lente: {category}

Resumo do Vídeo:
\"\"\"
{summary}
\"\"\"

Estruture sua análise estritamente nos 4 tópicos abaixo:

1. 🔍 O Que o Autor Omitiu ou Simplificou Demais:
(Aponte o que faltou, etapas ignoradas ou meias-verdades).

2. ⚠️ Onde Isso Costuma Falhar na Prática:
(Riscos reais, custos ocultos, atrito operacional ou curva de aprendizado).

3. 🎯 Para Quem Realmente Funciona:
(Qual perfil se beneficia e quem vai apenas perder tempo ou dinheiro).

4. ⚖️ Veredito & Nota de Praticidade (1 a 10):
(Nota de 1 a 10 acompanhada do veredito: "Execução Recomendada", "Cautela / Depende", ou "Puro Hype de Internet").
"""

def generate_critical_analysis(title: str, category: str, summary: str, transcription: str = "") -> str:
    """
    Executa auditoria crítica usando o modelo de raciocínio profundo da NVIDIA.
    """
    if not config.NVIDIA_API_KEY:
        return "⚠️ Chave da NVIDIA NIM não configurada."

    prompt = CRITIQUE_PROMPT.format(
        title=title,
        category=category,
        summary=summary[:1500],
    )

    headers = get_headers()
    url = f"{NVIDIA_BASE_URL}/chat/completions"

    # 1. Tenta com o modelo de raciocínio da NVIDIA
    for model_name in [REASONING_MODEL, FAST_MODEL]:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Você é um auditor de negócios e tecnologias sênior, cético e focado em viabilidade real.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.5,
        }
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                data = res.json()
                choices = data.get("choices", [])
                if choices and "message" in choices[0]:
                    content = choices[0]["message"].get("content")
                    if content and content.strip():
                        return content.strip()
            else:
                logger.warning(f"[NVIDIA Critique] {model_name} retornou status {res.status_code}")
        except Exception as e:
            logger.error(f"[NVIDIA Critique] Erro com {model_name}: {e}")

    return "❌ Não foi possível gerar a auditoria crítica no momento. Tente novamente em instantes."

# ==========================================
# OPÇÃO C: SÍNTESE DE ÁUDIO (VOZ NEURAL TELEGRAM)
# ==========================================

def clean_text_for_speech(text: str) -> str:
    """Limpa marcações de markdown e URLs para uma locução agradável."""
    # Remove blocos de código
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove links markdown [texto](url)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove [[Wikilinks]] deixando só o nome do conceito
    text = re.sub(r'\[\[([^\]]+)\]\]', r'\1', text)
    # Remove URLs soltas
    text = re.sub(r'https?://\S+', '', text)
    # Remove caracteres especiais de markdown (#, *, _, >, `)
    text = re.sub(r'[*#_>`~]', '', text)
    # Remove múltiplos espaços e quebras
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

async def generate_audio_summary(title: str, summary: str, output_path: str = None) -> str:
    """
    Gera um arquivo de áudio narrando o resumo em português com voz neural de alta qualidade.
    Retorna o caminho do arquivo gerado (.mp3).
    """
    if not output_path:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        output_path = tmp.name
        tmp.close()

    clean_content = clean_text_for_speech(summary)

    # Cria script narrativo fluido
    script = f"Resumo inteligente sobre: {title}. {clean_content}"

    # Limita tamanho para áudio de cerca de 1 a 2 minutos no máximo
    if len(script) > 1800:
        script = script[:1750] + "... Esse foi o resumo essencial do vídeo."

    voice = "pt-BR-AntonioNeural"
    communicate = edge_tts.Communicate(script, voice=voice)
    await communicate.save(output_path)

    return output_path
