import os
import re
import requests
from google import genai
import config

NOTION_API_URL = "https://api.notion.com/v1/pages"

def clean_database_id(raw_id: str) -> str:
    """Extrai e limpa o ID do banco de dados do Notion de uma URL ou string."""
    if not raw_id:
        return ""
    # Remove parâmetros de URL (?v=...)
    clean = raw_id.split("?")[0].strip()
    # Se for uma URL completa, pega a última parte
    clean = clean.rstrip("/").split("/")[-1]
    # Remove traços se houver (formato UUID para 32 hex)
    clean = clean.replace("-", "")
    return clean

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

def get_database_schema(database_id: str, headers: dict) -> dict:
    """Consulta o esquema do banco de dados do Notion para mapear as colunas existentes."""
    try:
        url = f"https://api.notion.com/v1/databases/{database_id}"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("properties", {})
    except Exception:
        pass
    return {}

def save_to_notion(title: str, category: str, platform: str, url: str, summary_text: str) -> tuple[bool, str]:
    """
    Salva uma página no banco de dados do Notion do usuário com mapeamento adaptativo.
    Retorna (sucesso: bool, mensagem_ou_url: str).
    """
    notion_key = os.getenv("NOTION_API_KEY", "").strip()
    raw_database_id = os.getenv("NOTION_DATABASE_ID", "").strip()
    database_id = clean_database_id(raw_database_id)

    if not notion_key or not database_id:
        return False, (
            "⚠️ *Notion ainda não configurado!*\n\n"
            "Para salvar diretamente no Notion com 1 clique:\n"
            "1. Crie uma integração no Notion e copie o `Internal Integration Secret`.\n"
            "2. Crie uma tabela no Notion e conecte a integração nela.\n"
            "3. Adicione `NOTION_API_KEY` e `NOTION_DATABASE_ID` no seu painel do Render!"
        )

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    clean_title = (title or "Resumo de Vídeo").replace("*", "")[:100]

    # Detecta as propriedades existentes na tabela do usuário para não quebrar
    schema = get_database_schema(database_id, headers)
    properties = {}

    title_prop_name = None
    for name, prop in schema.items():
        if prop.get("type") == "title":
            title_prop_name = name
            break

    # Se não identificou pelo esquema, tenta nomes comuns
    title_key = title_prop_name or "Nome"
    properties[title_key] = {
        "title": [{"text": {"content": clean_title}}]
    }

    # Mapeia colunas opcionais se existirem na tabela do Notion do usuário
    for name, prop in schema.items():
        p_type = prop.get("type")
        lower_name = name.lower()

        if p_type == "url" or "link" in lower_name or "url" in lower_name:
            properties[name] = {"url": url}
        elif p_type == "select" and ("cat" in lower_name or "tema" in lower_name):
            properties[name] = {"select": {"name": category[:50]}}
        elif p_type == "multi_select" and ("cat" in lower_name or "tag" in lower_name):
            properties[name] = {"multi_select": [{"name": category[:50]}]}
        elif p_type == "select" and ("plat" in lower_name or "origem" in lower_name or "rede" in lower_name):
            properties[name] = {"select": {"name": platform[:50]}}

    # Monta os blocos de conteúdo da página do Notion
    page_blocks = [
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"type": "emoji", "emoji": "🔗"},
                "rich_text": [
                    {"type": "text", "text": {"content": f"Vídeo Original ({platform}): "}},
                    {"type": "text", "text": {"content": url, "link": {"url": url}}}
                ]
            }
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Resumo & Takeaways"}}]
            }
        }
    ]

    # Quebra o resumo em parágrafos limpos para o Notion
    for paragraph in summary_text.split("\n\n"):
        p_clean = paragraph.strip()
        if p_clean:
            page_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": p_clean[:2000]}}]
                }
            })

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
        "children": page_blocks[:90] # limite de blocos por requisição
    }

    try:
        response = requests.post(NOTION_API_URL, json=payload, headers=headers, timeout=15)
        if response.status_code in (200, 201):
            page_data = response.json()
            page_url = page_data.get("url", "https://notion.so")
            return True, f"✅ *Salvo no seu Notion com sucesso!*\n🏷️ *Categoria:* `#{category}`\n🔗 [Abrir Página no Notion]({page_url})"
        else:
            err_msg = response.text[:200]
            # Caso comum: a integração não foi convidada para a página
            if "could not find database" in err_msg.lower():
                return False, (
                    "❌ *O Notion não encontrou o banco de dados!*\n\n"
                    "Lembre-se de ir na sua página/tabela do Notion, clicar nos **3 pontinhos `...`** no canto superior direito $\rightarrow$ **Conexões (Connections)** $\rightarrow$ e selecionar a sua integração criada!"
                )
            return False, f"❌ Erro na API do Notion (Status {response.status_code}): `{err_msg}`"
    except Exception as e:
        return False, f"❌ Falha de conexão com o Notion: `{str(e)[:150]}`"
