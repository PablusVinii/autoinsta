import time
import re
import logging
from google import genai
import config
from services.nvidia import generate_text_smart, is_gemini_blocked, mark_gemini_blocked

logger = logging.getLogger(__name__)

LENS_METADATA = {
    "biz": {
        "name": "Negócios & Vendas",
        "emoji": "💼",
    },
    "tech": {
        "name": "Tecnologia & IA",
        "emoji": "💻",
    },
    "wis": {
        "name": "Sabedoria & Filosofia",
        "emoji": "🧠",
    },
    "fth": {
        "name": "Fé & Espiritualidade",
        "emoji": "🙏",
    },
    "gen": {
        "name": "Síntese Geral",
        "emoji": "⚡",
    },
}

LANGUAGE_DIRECTIVE = """
INSTRUÇÃO CRÍTICA DE IDIOMA E TRADUÇÃO:
Independentemente do idioma original do vídeo (inglês, espanhol, etc.), você DEVE gerar todo o resumo e a transcrição estritamente em PORTUGUÊS DO BRASIL.
Traduza termos e expressões idiomáticas de forma natural, fluida e elegante.
"""

PROMPTS = {
    "biz": f"""
Você é um consultor executivo sênior e estrategista de negócios de elite.
Analise o vídeo fornecido com atenção total a falas, métricas, diagramas e dados apresentados.
{LANGUAGE_DIRECTIVE}

Seu objetivo é extrair inteligência pura de mercado, vendas, estratégia e monetização.
Sua resposta DEVE conter estritamente as seções delimitadas pelas tags:

[INICIO_RESUMO]
🎬 *TESE / TEMA DE NEGÓCIO*
(Uma frase clara explicando a grande ideia comercial, modelo de negócio ou oportunidade discutida)

📊 *FRAMEWORKS, ESTRATÉGIAS & INSIGHTS*
• [Insight ou framework estratégico 1]
• [Insight ou framework estratégico 2]
• [Métrica, funil ou tática citada 3]

🛠 *PLANO DE EXECUÇÃO / O QUE APLICAR*
1. [Ação prática imediata de implementação 1]
2. [Ação prática imediata de implementação 2]

⚠️ *ALERTA / ERRO A EVITAR*
(A armadilha ou erro mais comum citado pelo autor para quem empreende nessa área)

📌 *TAKEAWAY DE NEGÓCIOS*
(A lição comercial definitiva que gera retorno)
[FIM_RESUMO]

[INICIO_TRANSCRICAO]
(Escreva uma transcrição organizada em português do que foi falado no vídeo)
[FIM_TRANSCRICAO]
""",

    "tech": f"""
Você é um engenheiro de software sênior, arquiteto de soluções e especialista em Inteligência Artificial.
Analise o vídeo fornecido com atenção total a falas, telas, códigos, comandos e ferramentas mostradas.
{LANGUAGE_DIRECTIVE}

Seu objetivo é extrair detalhes técnicos práticos, nomes exatos de ferramentas, modelos e tutoriais.
Sua resposta DEVE conter estritamente as seções delimitadas pelas tags:

[INICIO_RESUMO]
🎬 *FERRAMENTA / TÓPICO TECNOLÓGICO*
(Nome da ferramenta/tecnologia e qual problema ela resolve)

🛠 *STACK & FERRAMENTAS CITADAS*
• [Nome exato do software, modelo de IA ou biblioteca 1]
• [Nome exato do software, modelo de IA ou biblioteca 2]

⚙️ *O QUE FOI CONSTRUÍDO / DEMONSTRADO*
(Explicação precisa do projeto, fluxo de automação ou funcionalidade apresentada)

📋 *PASSO A PASSO TÉCNICO & PROMPTS*
1. [Passo de instalação/configuração ou comando/prompt essencial 1]
2. [Passo de instalação/configuração ou comando/prompt essencial 2]

📌 *INSIGHT TÉCNICO / TAKEAWAY*
(A grande sacada de produtividade ou arquitetura que vale guardar)
[FIM_RESUMO]

[INICIO_TRANSCRICAO]
(Escreva uma transcrição organizada em português das explicações técnicas do vídeo)
[FIM_TRANSCRICAO]
""",

    "wis": f"""
Você é um mentor de vida, filósofo e especialista em desenvolvimento pessoal e psicologia comportamental.
Analise o vídeo fornecido com atenção total às reflexões, quebras de crenças e ensinamentos de vida.
{LANGUAGE_DIRECTIVE}

Seu objetivo é extrair sabedoria atemporal, clareza mental e princípios de maturidade.
Sua resposta DEVE conter estritamente as seções delimitadas pelas tags:

[INICIO_RESUMO]
🎬 *PRINCÍPIO / INSIGHT DE SABEDORIA*
(A verdade fundamental ou modelo mental discutido no vídeo)

🏛 *PONTOS-CHAVE & REFLEXÕES PROFUNDAS*
• [Princípio ou reflexão profunda 1]
• [Princípio ou reflexão profunda 2]
• [Princípio ou reflexão profunda 3]

🔄 *QUEBRA DE PARADIGMA (Antes vs. Depois)*
(Como a maioria das pessoas enxerga a situação vs. a postura madura/sábia revelada)

🧘 *APLICAÇÃO PRÁTICA NA VIDA*
1. [Mudança de atitude, rotina ou postura mental 1]
2. [Mudança de atitude, rotina ou postura mental 2]

💬 *FRASE / CITAÇÃO DE IMPACTO*
(A frase mais marcante ou marcadora dita no vídeo)
[FIM_RESUMO]

[INICIO_TRANSCRICAO]
(Escreva uma transcrição organizada em português das falas e reflexões do vídeo)
[FIM_TRANSCRICAO]
""",

    "fth": f"""
Você é um conselheiro espiritual e estudioso teológico dedicado a extrair edificação e valores de fé.
Analise o vídeo fornecido com sensibilidade espiritual, reverência e atenção à mensagem moral e bíblica.
{LANGUAGE_DIRECTIVE}

Seu objetivo é extrair a mensagem de fé, princípios devocionais e edificação espiritual.
Sua resposta DEVE conter estritamente as seções delimitadas pelas tags:

[INICIO_RESUMO]
🎬 *MENSAGEM CENTRAL DE FÉ*
(O tema espiritual central abordado pelo autor)

📖 *PRINCÍPIOS & REFERÊNCIAS BÍBLICAS*
• [Passagem, história bíblica ou mandamento abordado 1]
• [Princípio espiritual ou valor cristão demonstrado 2]

🕊️ *REFLEXÃO DEVOCIONAL*
(O que essa mensagem ensina ao coração, trazendo paz, alinhamento ou renovação)

🤲 *APLICAÇÃO PRÁTICA & ORAÇÃO*
1. [Atitude ou postura de fé para praticar hoje]
2. [Motivo de oração, gratidão ou meditação inspirada pelo vídeo]

📌 *ENSINAMENTO-CHAVE PARA GUARDAR*
(A verdade espiritual definitiva para carregar na caminhada)
[FIM_RESUMO]

[INICIO_TRANSCRICAO]
(Escreva uma transcrição organizada em português da mensagem e oração do vídeo)
[FIM_TRANSCRICAO]
""",

    "gen": f"""
Você é um assistente especialista em analisar, resumir e transcrever vídeos curtos e conteúdos digitais.
Analise o material fornecido com atenção total ao áudio, falas e textos na tela.
{LANGUAGE_DIRECTIVE}

Sua resposta DEVE conter estritamente as seções delimitadas pelas tags:

[INICIO_RESUMO]
🎬 *TÍTULO / TEMA PRINCIPAL*
(Uma frase clara resumindo o que é ensinado ou discutido)

💡 *PONTOS-CHAVE & INSIGHTS*
• [Ponto 1]
• [Ponto 2]
• [Ponto 3]

🛠 *PASSO A PASSO / DICAS PRÁTICAS*
1. [Passo ou argumento 1]
2. [Passo ou argumento 2]

📌 *TAKEAWAY CENTRAL*
(A lição ou ação mais importante para quem assistiu)
[FIM_RESUMO]

[INICIO_TRANSCRICAO]
(Escreva a transcrição em português do que foi falado no vídeo)
[FIM_TRANSCRICAO]
"""
}

def get_prompt_for_lens(lens_code: str) -> str:
    """Retorna o prompt especializado para a lente escolhida."""
    return PROMPTS.get(lens_code, PROMPTS["gen"])

def _extract_yt_transcript_fallback(youtube_url: str) -> tuple[str, str]:
    """Extrai legendas do YouTube via youtube-transcript-api quando o Gemini estiver sem cota."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        m = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", youtube_url)
        if not m:
            return "", ""
        vid = m.group(1)
        api = YouTubeTranscriptApi()
        transcript_list = api.list(vid)
        chosen = None
        for lang_code in ("pt", "pt-BR", "en", "es"):
            try:
                chosen = transcript_list.find_transcript([lang_code])
                break
            except Exception:
                continue
        if not chosen:
            chosen = next(iter(transcript_list), None)
        if not chosen:
            return "", ""
        entries = chosen.fetch()
        text = " ".join(getattr(e, "text", e.get("text", "") if isinstance(e, dict) else "") for e in entries)
        return text.strip(), (getattr(chosen, "language_code", "") or "").lower()
    except Exception as e:
        logger.warning(f"[YouTube Fallback] Falha ao extrair legenda: {e}")
        return "", ""


def analyze_youtube_url_direct(youtube_url: str, lens: str = "gen", model_name: str = None, return_lang: bool = False):
    """
    Analisa um vídeo do YouTube via Gemini; se Gemini atingir cota/gasto, extrai legenda
    e analisa automaticamente com NVIDIA NIM.
    """
    model = model_name or config.GEMINI_MODEL
    prompt = get_prompt_for_lens(lens) + (
        "\n\nNo final absoluto da resposta, inclua a linha exata indicando o idioma falado no áudio original "
        "(código ISO, ex: en, pt, es): [IDIOMA_ORIGINAL: xx]"
    )

    output = ""
    yt_fallback_lang = ""

    if config.GEMINI_API_KEY and not is_gemini_blocked():
        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            interaction = client.interactions.create(
                model=model,
                input=[
                    {"type": "video", "uri": youtube_url},
                    {"type": "text", "text": prompt},
                ],
            )
            output = interaction.output_text or ""
        except Exception as e:
            err_lower = str(e).lower()
            if any(k in err_lower for k in ["429", "403", "quota", "limit", "spending", "billing", "exceeded"]):
                mark_gemini_blocked(900)
            logger.warning(f"[YouTube] Gemini falhou ({e}). Acionando fallback NVIDIA NIM...")

    if not output:
        yt_text, yt_fallback_lang = _extract_yt_transcript_fallback(youtube_url)
        if not yt_text:
            raise RuntimeError("Não foi possível analisar o YouTube: Gemini sem cota e vídeo sem legenda disponível.")
        nvidia_prompt = f"{prompt}\n\n[TRANSCRIÇÃO DO VÍDEO NO YOUTUBE]:\n{yt_text[:20000]}"
        output = generate_text_smart(nvidia_prompt, max_tokens=2048)

    orig_lang = yt_fallback_lang
    lang_match = re.search(r"\[IDIOMA_ORIGINAL:\s*([a-zA-Z\-]+)\]", output)
    if lang_match:
        orig_lang = lang_match.group(1).strip().lower()
        output = re.sub(r"\[IDIOMA_ORIGINAL:\s*[a-zA-Z\-]+\]", "", output).strip()

    summary = ""
    transcription = ""

    summary_match = re.search(r"\[INICIO_RESUMO\](.*?)\[FIM_RESUMO\]", output, re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()
    else:
        summary = output.strip()

    transcription_match = re.search(r"\[INICIO_TRANSCRICAO\](.*?)\[FIM_TRANSCRICAO\]", output, re.DOTALL)
    if transcription_match:
        transcription = transcription_match.group(1).strip()
    else:
        transcription = "Transcrição gerada a partir do YouTube."

    return (summary, transcription, orig_lang) if return_lang else (summary, transcription)

def analyze_and_summarize_video(file_path: str, lens: str = "gen", model_name: str = None, return_lang: bool = False, return_raw: bool = False):
    """
    Transcreve com Deepgram Nova-3 (com Diarização de locutores e isolamento de música)
    e analisa no Gemini — com fallback automático para NVIDIA NIM caso o Gemini atinja o limite.
    """
    from services.transcriber import transcribe_with_deepgram

    # 1. Transcrição ultrarrápida com Deepgram Nova-3 e Diarização de locutores
    dg_plain, dg_diarized, dg_lang, dg_raw = "", "", "", ""
    try:
        dg_plain, dg_diarized, dg_lang, dg_raw = transcribe_with_deepgram(file_path, return_lang=True, return_raw=True)
    except Exception as e:
        logger.warning(f"[Transcriber] Aviso ao transcrever com Deepgram: {e}")

    model = model_name or config.GEMINI_MODEL
    prompt = get_prompt_for_lens(lens)

    if dg_diarized:
        prompt += (
            f"\n\n[TRANSCRIÇÃO DE ALTA FIDELIDADE COM SEPARAÇÃO DE LOCUTORES (DEEPGRAM NOVA-3)]:\n"
            f"{dg_diarized}\n\n"
            f"Instrução Adicional: Use a transcrição acima para atribuir precisamente argumentos aos seus respectivos locutores."
        )

    output = ""
    if config.GEMINI_API_KEY and not is_gemini_blocked():
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        myfile = None
        try:
            myfile = client.files.upload(file=file_path)
            max_attempts = 30
            attempts = 0
            while attempts < max_attempts:
                if myfile.state and myfile.state.name == "ACTIVE":
                    break
                if myfile.state and myfile.state.name == "FAILED":
                    raise RuntimeError("Falha ao processar o arquivo na API do Gemini.")
                time.sleep(2)
                myfile = client.files.get(name=myfile.name)
                attempts += 1

            mime = myfile.mime_type or "video/mp4"
            media_type = "video"
            if mime.startswith("audio/") or file_path.lower().endswith((".m4a", ".mp3", ".wav", ".aac", ".ogg")):
                media_type = "audio"
                if not mime.startswith("audio/"):
                    mime = "audio/mp4"

            interaction = client.interactions.create(
                model=model,
                input=[
                    {"type": media_type, "uri": myfile.uri, "mime_type": mime},
                    {"type": "text", "text": prompt},
                ],
            )
            output = interaction.output_text or ""
        except Exception as e:
            err_lower = str(e).lower()
            if any(k in err_lower for k in ["429", "403", "quota", "limit", "spending", "billing", "exceeded"]):
                mark_gemini_blocked(900)
            logger.warning(f"[Summarizer] Gemini indisponível ({e}). Usando Deepgram + NVIDIA NIM...")
        finally:
            try:
                if myfile and myfile.name:
                    client.files.delete(name=myfile.name)
            except Exception as e:
                print(f"[Gemini Cleanup] Aviso ao deletar arquivo remoto: {e}")

    # Fallback imediato: Deepgram Nova-3 já transcreveu o áudio -> NVIDIA NIM analisa e resume!
    if not output:
        if not dg_diarized:
            raise RuntimeError("Gemini sem cota e o áudio não pôde ser transcrito pelo Deepgram.")
        output = generate_text_smart(prompt, max_tokens=2048)

    summary = ""
    transcription = ""

    summary_match = re.search(r"\[INICIO_RESUMO\](.*?)\[FIM_RESUMO\]", output, re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()
    else:
        summary = output.strip()

    # Prioriza a transcrição diarizada e cristalina do Deepgram Nova-3
    if dg_diarized:
        transcription = dg_diarized
    else:
        transcription_match = re.search(r"\[INICIO_TRANSCRICAO\](.*?)\[FIM_TRANSCRICAO\]", output, re.DOTALL)
        if transcription_match:
            transcription = transcription_match.group(1).strip()
        else:
            transcription = "Transcrição não disponível separadamente."

    if return_raw:
        return summary, transcription, dg_lang, dg_raw
    return (summary, transcription, dg_lang) if return_lang else (summary, transcription)

def generate_content_ideas(summary_text: str) -> str:
    """Gera ideias de posts e ganchos virais a partir do resumo."""
    prompt = f"""
Com base no resumo deste conteúdo:
\"\"\"
{summary_text}
\"\"\"

Crie um kit prático de ideias de conteúdo para redes sociais no seguinte formato:

🎣 *3 GANCHOS VIRAIS (Hooks)*
1. "[Gancho magnético 1]"
2. "[Gancho magnético 2]"
3. "[Gancho magnético 3]"

📱 *IDEIA DE CARROSSEL / REEL*
• *Slide 1 (Capa):* [Título chamativo]
• *Slide 2 a 4 (Conteúdo):* [Passo a passo ou argumentos-chave]
• *Slide Final (CTA):* [Chamada para ação de engajamento]

🧵 *TWEET / THREAD (Ideia curta)*
"[Um tweet direto, provocativo ou educativo sintetizando o valor principal]"

Responda em Português do Brasil com formatação elegante para Telegram.
"""
    return generate_text_smart(prompt) or "Não foi possível gerar as ideias no momento."

def answer_video_question(summary_text: str, transcription_text: str, question: str) -> str:
    """Responde a perguntas específicas de Q&A do usuário com base no vídeo."""
    prompt = f"""
Você é o assistente que assistiu e analisou o vídeo a seguir.
O usuário está fazendo uma pergunta específica sobre o conteúdo do vídeo.

[RESUMO DO VÍDEO]
{summary_text}

[TRANSCRIÇÃO E FALAS DO VÍDEO]
{transcription_text[:40000]}

[PERGUNTA DO USUÁRIO]
{question}

Instruções:
- Responda de forma direta, clara e precisa com base estritamente no que foi falado ou demonstrado no vídeo.
- Se o vídeo mencionar ferramentas, nomes, passos, versículos, livros, valores ou detalhes técnicos, cite-os explicitamente.
- Se o vídeo não mencionar a resposta, diga com honestidade que o autor não abordou esse ponto no vídeo.
- Responda em Português do Brasil com formatação elegante para Telegram.
"""
    return generate_text_smart(prompt) or "Não consegui formular uma resposta para essa pergunta."


def generate_engaging_comments(
    title: str,
    summary_text: str,
    transcription_text: str = "",
    orig_lang: str = "",
) -> str:
    """
    Gera 3 comentários construtivos e naturais para engajar na postagem original.
    Se o conteúdo original for em inglês (ou outro idioma estrangeiro), gera em inglês + tradução pt-BR.
    Se for em português, gera apenas em pt-BR.
    """
    lang_clean = (orig_lang or "").strip().lower()
    is_foreign = bool(lang_clean) and not lang_clean.startswith("pt")

    if is_foreign:
        lang_instruction = f"""
IDIOMA DETECTADO NO VÍDEO ORIGINAL: '{lang_clean}' (Estrangeiro).
Por isso, para CADA UMA das 3 opções, você DEVE entregar exatamente neste formato para o usuário poder copiar o inglês e entender em português:

💬 *Opção 1 — [Rótulo curto do ângulo]*
`[Comentário em INGLÊS natural, pronto para copiar e colar no Reels/post]`
🇧🇷 _Tradução:_ [Tradução fiel em Português do Brasil]
"""
    else:
        lang_instruction = """
IDIOMA DO VÍDEO ORIGINAL: Português.
Entregue cada uma das 3 opções diretamente em Português do Brasil neste formato:

💬 *Opção 1 — [Rótulo curto do ângulo]*
`[Comentário em Português natural, pronto para copiar e colar]`
"""

    prompt = f"""
Você vai escrever 3 sugestões de comentários para eu postar nos comentários de um Reels/vídeo e gerar engajamento genuíno.

SOBRE O MEU PERFIL (tom de fundo, sem parecer pedante):
Tenho mais de 15 anos de experiência prática resolvendo problemas reais de tecnologia, infraestrutura e operação. Tenho visão pragmática de quem vive o dia a dia na prática, valoriza o que realmente funciona e evita modismos vazios.

CONTEÚDO ANALISADO:
Título/Tema: {title}
Resumo:
\"\"\"
{summary_text}
\"\"\"
Trecho da fala:
\"\"\"
{transcription_text[:2500]}
\"\"\"

REGRAS CRÍTICAS PARA OS COMENTÁRIOS:
1. LEVANTE PONTOS INTERESSANTES (NÃO QUESTIONAMENTOS): Cada comentário deve agregar uma sacada complementar, reforçar uma verdade prática ou trazer um ângulo inteligente que faça o autor e outros leitores concordarem e curtirem. NUNCA faça perguntas críticas, dúvidas ou questionamentos.
2. LINGUAGEM ACESSÍVEL E HUMANA: Não seja muito técnico nem use jargão pesado demais. Escreva como uma pessoa real comentando no Instagram/YouTube/LinkedIn (1 a 3 frases curtas e naturais).
3. PROIBIDO CLICHÊS DE BOT: Nunca comece com "Ótimo vídeo!", "Concordo 100%!", "Great post!", "Amazing insights!" ou frases genéricas. Vá direto ao ponto interessante.
4. Gere exatamente **3 opções** com ângulos diferentes (ex: 1. Visão prática do dia a dia, 2. Complemento inteligente / detalhe esquecido, 3. Conexão com eficiência/resultado real).

{lang_instruction}
"""
    return generate_text_smart(prompt) or "Não foi possível gerar os comentários no momento."


def generate_bilingual_study(
    transcription_text: str,
    orig_transcription: str = "",
    orig_lang: str = "",
) -> str:
    """
    Gera um roteiro bilíngue frase por frase para estudo de inglês:
    Linha 1: Frase original em inglês
    Linha 2: Tradução natural em português logo abaixo
    """
    source_text = (orig_transcription or transcription_text or "").strip()
    if not source_text or len(source_text) < 10:
        return "⚠️ Transcrição não disponível para gerar o estudo bilíngue."

    prompt = f"""
Você é um professor particular de inglês prático para brasileiros.
Abaixo está a transcrição de um vídeo ({orig_lang or 'inglês/português'}).

TAREFA:
Divida TODA a fala em frases ou blocos curtos de legenda (no máximo 1 frase por bloco) e entregue EXATAMENTE no formato bilíngue abaixo — **Inglês na linha de cima** e **Português do Brasil natural na linha de baixo**, separados por uma linha em branco entre cada bloco.

EXEMPLO EXATO DO FORMATO:
There is an idea in psychology
Tem uma ideia na psicologia

And it explains why most people hesitate
E isso explica por que a maioria das pessoas hesita

REGRAS OBRIGATÓRIAS:
1. Se o texto abaixo já estiver traduzido para português (sem o inglês original), reconstrua o inglês natural correspondente e coloque-o na linha de cima, com o português na linha de baixo.
2. Se o texto abaixo estiver em inglês, mantenha o inglês fiel do áudio na linha de cima e traduza de forma natural (como se fala no dia a dia) na linha de baixo.
3. NÃO coloque prefixos como "EN:", "PT:", "Inglês:", "Locutor 1:" ou numeração. Apenas as duas linhas limpas por bloco.
4. Cubra o conteúdo inteiro do texto sem pular partes.

TEXTO BASE:
\"\"\"
{source_text[:8000]}
\"\"\"
"""
    return generate_text_smart(prompt, max_tokens=3072) or "Não foi possível gerar o texto bilíngue no momento."


def get_english_practice_text(
    transcription_text: str,
    orig_transcription: str = "",
    orig_lang: str = "",
) -> str:
    """Retorna o texto completo em inglês do vídeo para o usuário praticar tradução."""
    lang_clean = (orig_lang or "").strip().lower()
    if orig_transcription and len(orig_transcription.strip()) > 10 and not lang_clean.startswith("pt"):
        return orig_transcription.strip()

    source = (orig_transcription or transcription_text or "").strip()
    if not source or len(source) < 10:
        return ""

    prompt = (
        "Traduza ou reescreva o texto falado abaixo integralmente para Inglês natural (mantendo todas as frases, sem resumir e sem rótulos de locutor).\n\n"
        f"Texto:\n{source[:6000]}"
    )
    return generate_text_smart(prompt, max_tokens=2500)


def evaluate_user_translation(english_text: str, user_pt_text: str) -> str:
    """Corrige a tradução digitada pelo usuário em português comparando com o original em inglês."""
    prompt = f"""
Você é um professor particular de inglês gentil, direto e preciso avaliando a tradução de um aluno brasileiro.

[TEXTO ORIGINAL EM INGLÊS]
\"\"\"
{english_text[:6000]}
\"\"\"

[TRADUÇÃO DIGITADA PELO ALUNO EM PORTUGUÊS]
\"\"\"
{user_pt_text[:6000]}
\"\"\"

Avalie a tradução do aluno e responda em Português do Brasil neste formato limpo para Telegram (sem tabelas):

📊 *Nota de Precisão:* [X]/10

✅ *O que você acertou bem:*
• [Elogie 1 ou 2 trechos/expressões que o aluno traduziu com precisão]

🔍 *Palavras e Expressões que Precisam de Ajuste:*
• *[trecho/palavra em inglês]* → Você colocou: *"[como o aluno traduziu ou 'não traduziu']"* → Sentido correto: *"[tradução correta]"* — [explicação curta e clara]
(Liste todas as palavras/expressões erradas, imprecisas ou puladas no trecho que o aluno tentou traduzir. Se o aluno traduziu tudo certo, diga que não houve erros!)

🎯 *Tradução de Referência Natural:*
[Tradução completa e natural em Português do Brasil para o aluno comparar]
"""
    return generate_text_smart(prompt, max_tokens=2500) or "Não foi possível corrigir a tradução no momento."
