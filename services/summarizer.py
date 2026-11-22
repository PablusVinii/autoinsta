import time
from google import genai
import config

SUMMARY_PROMPT = """
Você é um assistente especialista em analisar e resumir vídeos curtos (Instagram Reels).
Analise o vídeo fornecido com atenção total a dois elementos:
1. Áudio e fala: o que o autor diz ou ensina.
2. Elementos visuais e texto na tela: anotações, tópicos, códigos, legendas, nomes de ferramentas, receitas ou passos gráficos que aparecem no vídeo.

Gere um resumo direto ao ponto, elegante e estruturado no seguinte formato:

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

Observação: Responda em Português do Brasil com formatação compatível com Telegram (use * para negrito e • para tópicos).
"""

def summarize_reel_video(file_path: str, model_name: str = None) -> str:
    """
    Faz upload do vídeo para a Gemini API, aguarda processamento e gera um resumo detalhado.
    """
    model = model_name or config.GEMINI_MODEL
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    myfile = client.files.upload(file=file_path)

    try:
        # Aguarda o vídeo ficar no estado ACTIVE se necessário
        max_attempts = 30
        attempts = 0
        while attempts < max_attempts:
            if myfile.state and myfile.state.name == "ACTIVE":
                break
            if myfile.state and myfile.state.name == "FAILED":
                raise RuntimeError("Falha ao processar o vídeo na API do Gemini.")
            time.sleep(2)
            myfile = client.files.get(name=myfile.name)
            attempts += 1

        # Chamada com a Interactions API (padrão oficial atual)
        interaction = client.interactions.create(
            model=model,
            input=[
                {
                    "type": "video",
                    "uri": myfile.uri,
                    "mime_type": myfile.mime_type or "video/mp4"
                },
                {
                    "type": "text",
                    "text": SUMMARY_PROMPT
                }
            ]
        )

        output = interaction.output_text
        if not output:
            raise RuntimeError("O modelo Gemini não retornou nenhum texto.")

        return output

    finally:
        # Remove o arquivo temporário dos servidores do Google
        try:
            if myfile and myfile.name:
                client.files.delete(name=myfile.name)
        except Exception as e:
            print(f"[Gemini Cleanup] Aviso ao deletar arquivo remoto: {e}")
