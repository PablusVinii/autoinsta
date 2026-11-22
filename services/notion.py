import os
import requests
from google import genai
import config

NOTION_API_URL = "https://api.notion.com/v1/pages"

def categorize_content(summary_text: str) -> str:
    """Classifica o conteúdo do vídeo em uma categoria concisa com Gemini."""
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        prompt = f"""
Com base no resumo abaixo, escolha a categoria que melhor define o conteúdo:
Categorias possíveis: IA & Tecnologia, Marketing & Negócios, Finanças & Investimentos, Produtividade, Carreira & Vendas, Desenvolvimento Pessoal, Saúde & Fitness, Culinária, Entretenimento, Outros.

Responda APENAS com o nome da categoria exata (uma palavra ou frase curta):
\"\"\"
{summary_text[:1000]}
\"\"\"
"""
        interaction = client.interactions.create(
            model=config.GEMINI_MODEL,
            input=prompt
        )
        cat = interaction.output_text.strip().replace('"', '').replace("'", "")
        return cat if cat else "Geral"
    except Exception:
        return "Geral"

def save_to_notion(title: str, category: str, platform: str, url: str, summary_text: str) -> tuple[bool, str]:
    """
    Salva uma página no banco de dados do Notion do usuário.
    Retorna (sucesso: bool, mensagem_ou_url: str).
    """
    notion_key = os.getenv("NOTION_API_KEY", "").strip()
    database_id = os.getenv("NOTION_DATABASE_ID", "").strip()

    if not notion_key or not database_id:
        return False, (
            "⚠️ *Notion ainda não configurado!*\n\n"
            "Para ativar o salvamento direto no Notion, você só precisa adicionar duas variáveis no Render:\n"
            "• `NOTION_API_KEY` (sua chave de integração do Notion)\n"
            "• `NOTION_DATABASE_ID` (o ID da sua tabela/banco no Notion)\n\n"
            "*(O vídeo já foi guardado na sua biblioteca interna do bot! Digite /salvos para ver)*"
        )

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    # Limita o texto do resumo para blocos do Notion
    clean_title = (title or "Resumo de Vídeo")[:100]
    clean_summary = summary_text[:2000]

    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Nome": {
                "title": [
                    {"text": {"content": clean_title}}
                ]
            },
            "Categoria": {
                "select": {"name": category[:50]}
            },
            "Plataforma": {
                "select": {"name": platform[:50]}
            },
            "URL": {
                "url": url
            }
        },
        "children": [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": f"Resumo ({platform})"}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": clean_summary}}]
                }
            }
        ]
    }

    try:
        response = requests.post(NOTION_API_URL, json=payload, headers=headers, timeout=15)
        if response.status_code in (200, 201):
            page_data = response.json()
            page_url = page_data.get("url", "https://notion.so")
            return True, f"✅ *Salvo no Notion com sucesso!*\n🏷️ *Categoria:* #{category}\n🔗 [Abrir no Notion]({page_url})"
        else:
            err_msg = response.text[:150]
            return False, f"❌ Erro na API do Notion (Status {response.status_code}): `{err_msg}`"
    except Exception as e:
        return False, f"❌ Falha de conexão com o Notion: `{str(e)[:150]}`"
