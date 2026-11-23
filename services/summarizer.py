import time
import re
from google import genai
import config

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

def analyze_youtube_url_direct(youtube_url: str, lens: str = "gen", model_name: str = None) -> tuple[str, str]:
    """
    Analisa um vídeo do YouTube passando a URL diretamente para a API do Gemini
    com o prompt ajustado para a lente selecionada.
    """
    model = model_name or config.GEMINI_MODEL
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    prompt = get_prompt_for_lens(lens)

    interaction = client.interactions.create(
        model=model,
        input=[
            {
                "type": "video",
                "uri": youtube_url
            },
            {
                "type": "text",
                "text": prompt
            }
        ]
    )

    output = interaction.output_text or ""

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
        transcription = "Transcrição gerada pelo modelo Gemini a partir do YouTube."

    return summary, transcription

def analyze_and_summarize_video(file_path: str, lens: str = "gen", model_name: str = None) -> tuple[str, str]:
    """
    Faz upload do arquivo local (Instagram, TikTok, Twitter) para a Gemini API e analisa
    utilizando a lente temática selecionada.
    """
    model = model_name or config.GEMINI_MODEL
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    prompt = get_prompt_for_lens(lens)

    myfile = client.files.upload(file=file_path)

    try:
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
                {
                    "type": media_type,
                    "uri": myfile.uri,
                    "mime_type": mime
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        )

        output = interaction.output_text or ""

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
            transcription = "Transcrição não disponível separadamente."

        return summary, transcription

    finally:
        try:
            if myfile and myfile.name:
                client.files.delete(name=myfile.name)
        except Exception as e:
            print(f"[Gemini Cleanup] Aviso ao deletar arquivo remoto: {e}")

def generate_content_ideas(summary_text: str) -> str:
    """Gera ideias de posts e ganchos virais a partir do resumo."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
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
    interaction = client.interactions.create(
        model=config.GEMINI_MODEL,
        input=prompt
    )
    return interaction.output_text or "Não foi possível gerar as ideias no momento."

def answer_video_question(summary_text: str, transcription_text: str, question: str) -> str:
    """Responde a perguntas específicas de Q&A do usuário com base no vídeo."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
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
    interaction = client.interactions.create(
        model=config.GEMINI_MODEL,
        input=prompt
    )
    return interaction.output_text or "Não consegui formular uma resposta para essa pergunta."
