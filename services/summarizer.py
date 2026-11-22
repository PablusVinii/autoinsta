import time
import re
from google import genai
import config

ANALYSIS_PROMPT = """
Você é um assistente especialista em analisar, resumir e transcrever vídeos e conteúdos para redes sociais (Instagram Reels, TikTok, YouTube, Twitter/X).
Analise o material fornecido com atenção total:
1. Áudio e falas: tudo o que foi dito ou explicado.
2. Se houver vídeo/imagem: textos na tela, códigos, receitas, gráficos ou passos demonstrados.

Sua resposta DEVE conter estritamente as duas seções delimitadas pelas tags abaixo:

[INICIO_RESUMO]
🎬 *TÍTULO / TEMA PRINCIPAL*
(Uma frase clara resumindo o que é ensinado ou discutido)

💡 *PONTOS-CHAVE & INSIGHTS*
• [Ponto 1]
• [Ponto 2]
• [Ponto 3]

🛠 *PASSO A PASSO / DICAS PRÁTICAS*
(Se for um tutorial, receita, dica técnica ou guia prático, liste as etapas numeradas. Se for apenas reflexão ou opinião, destaque os principais argumentos)
1. [Passo ou argumento 1]
2. [Passo ou argumento 2]

📌 *TAKEAWAY CENTRAL*
(A lição ou ação mais importante para quem assistiu)
[FIM_RESUMO]

[INICIO_TRANSCRICAO]
(Escreva a transcrição detalhada do que foi dito no conteúdo em parágrafos limpos)
[FIM_TRANSCRICAO]

Observação: Responda em Português do Brasil com formatação compatível com Telegram (use * para negrito e • para tópicos).
"""

def analyze_and_summarize_video(file_path: str, model_name: str = None) -> tuple[str, str]:
    """
    Faz upload do vídeo ou áudio para a Gemini API, aguarda processamento e extrai:
    - summary: Resumo estruturado
    - transcription: Transcrição das falas
    """
    model = model_name or config.GEMINI_MODEL
    client = genai.Client(api_key=config.GEMINI_API_KEY)

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

        # Detecta se é áudio ou vídeo
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
                    "text": ANALYSIS_PROMPT
                }
            ]
        )

        output = interaction.output_text or ""

        # Extrai o resumo e a transcrição via tags
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

# Compatibilidade retroativa
def summarize_reel_video(file_path: str, model_name: str = None) -> str:
    summary, _ = analyze_and_summarize_video(file_path, model_name)
    return summary

def generate_content_ideas(summary_text: str) -> str:
    """
    Gera ideias de posts e ganchos para redes sociais a partir do resumo do vídeo.
    Chamada de texto ultrarrápida.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    prompt = f"""
Com base no resumo deste conteúdo:
\"\"\"
{summary_text}
\"\"\"

Crie um kit prático de ideias de conteúdo para redes sociais no seguinte formato:

🎣 *3 GANCHOS VIRAL (Hooks)*
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
