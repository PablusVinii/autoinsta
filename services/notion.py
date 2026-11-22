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
    clean = raw_id.split("?")[0].strip()
    clean = clean.rstrip("/").split("/")[-1]
    clean = clean.replace("-", "")
    return clean

def parse_summary_sections(text: str) -> dict:
    """Extrai estruturadamente as 4 seções do resumo."""
    sections = {
        "title": "",
        "insights": [],
        "steps": [],
        "takeaway": ""
    }
    current_sec = None
    for line in text.split("\n"):
        l = line.strip()
        if not l:
            continue
        if "TÍTULO" in l or "TEMA PRINCIPAL" in l:
            current_sec = "title"
            continue
        elif "PONTOS-CHAVE" in l or "INSIGHTS" in l:
            current_sec = "insights"
            continue
        elif "PASSO A PASSO" in l or "DICAS PRÁTICAS" in l or "ARGUMENTOS" in l:
            current_sec = "steps"
            continue
        elif "TAKEAWAY" in l or "CONCLUSÃO" in l:
            current_sec = "takeaway"
            continue

        if current_sec == "title" and not sections["title"]:
            sections["title"] = l.replace("*", "").strip()
        elif current_sec == "insights":
            clean_item = l.lstrip("•-*0123456789. ").replace("*", "").strip()
            if clean_item:
                sections["insights"].append(clean_item)
        elif current_sec == "steps":
            clean_item = l.lstrip("•-*0123456789. ").replace("*", "").strip()
            if clean_item:
                sections["steps"].append(clean_item)
        elif current_sec == "takeaway" and not sections["takeaway"]:
            sections["takeaway"] = l.replace("*", "").strip()

    return sections

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

def save_to_notion(title: str, category: str, platform: str, url: str, summary_text: str, transcription_text: str = "") -> tuple[bool, str]:
    """
    Salva uma página ricamente estruturada no Notion contendo:
    - Título e metadados nas propriedades (colunas)
    - Título principal
    - Pontos-chave & Insights em bullet points
    - Passo a passo numerado
    - Takeaway em bloco de citação
    - Transcrição completa sanfonada (toggle)
    """
    notion_key = os.getenv("NOTION_API_KEY", "").strip()
    raw_database_id = os.getenv("NOTION_DATABASE_ID", "").strip()
    database_id = clean_database_id(raw_database_id)

    if not notion_key or not database_id:
        return False, (
            "⚠️ *Notion ainda não configurado!*\n\n"
            "Adicione `NOTION_API_KEY` e `NOTION_DATABASE_ID` no seu painel do Render para ativar."
        )

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    # Extrai cada seção do resumo
    parsed = parse_summary_sections(summary_text)
    final_title = (parsed["title"] or title or "Resumo de Vídeo")[:100]

    # Identifica colunas existentes na tabela do usuário
    schema = get_database_schema(database_id, headers)
    properties = {}

    title_prop_name = None
    for name, prop in schema.items():
        if prop.get("type") == "title":
            title_prop_name = name
            break

    title_key = title_prop_name or "Nome"
    properties[title_key] = {
        "title": [{"text": {"content": final_title}}]
    }

    # Preenche colunas opcionais adicionais se o usuário tiver criado na tabela
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
        elif p_type == "rich_text" and ("takeaway" in lower_name or "conclus" in lower_name):
            if parsed["takeaway"]:
                properties[name] = {"rich_text": [{"text": {"content": parsed["takeaway"][:2000]}}]}
        elif p_type == "rich_text" and ("resumo" in lower_name or "summary" in lower_name):
            short_res = parsed["takeaway"] or final_title
            properties[name] = {"rich_text": [{"text": {"content": short_res[:2000]}}]}

    # MONTA O CORPO DA PÁGINA (CHILDREN) ESTRUTURADO COM TODAS AS SEÇÕES
    page_blocks = []

    # 1. Card com link original
    page_blocks.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": "🎬"},
            "rich_text": [
                {"type": "text", "text": {"content": f"Vídeo no {platform}: "}},
                {"type": "text", "text": {"content": url, "link": {"url": url}}}
            ]
        }
    })

    # 2. Título / Tema Principal
    page_blocks.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {
            "rich_text": [{"type": "text", "text": {"content": final_title}}]
        }
    })
    page_blocks.append({"object": "block", "type": "divider", "divider": {}})

    # 3. Pontos-Chave & Insights
    if parsed["insights"]:
        page_blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "💡 Pontos-Chave & Insights"}}]
            }
        })
        for item in parsed["insights"]:
            page_blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": item[:2000]}}]
                }
            })

    # 4. Passo a Passo / Ações Práticas
    if parsed["steps"]:
        page_blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "🛠 Passo a Passo / Dicas Práticas"}}]
            }
        })
        for step in parsed["steps"]:
            page_blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": step[:2000]}}]
                }
            })

    # 5. Takeaway Central
    if parsed["takeaway"]:
        page_blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📌 Takeaway Central"}}]
            }
        })
        page_blocks.append({
            "object": "block",
            "type": "quote",
            "quote": {
                "rich_text": [{"type": "text", "text": {"content": parsed["takeaway"][:2000]}}]
            }
        })

    # 6. Fallback caso as tags não tenham sido encontradas (insere os parágrafos diretos)
    if not parsed["insights"] and not parsed["steps"]:
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

    # 7. Transcrição completa retrátil (se disponível)
    if transcription_text and len(transcription_text) > 30:
        page_blocks.append({
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "📝 Transcrição Completa (Clique para ver)"}}],
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": transcription_text[:1900]}}]
                        }
                    }
                ]
            }
        })

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
        "children": page_blocks[:95]
    }

    try:
        response = requests.post(NOTION_API_URL, json=payload, headers=headers, timeout=15)
        if response.status_code in (200, 201):
            page_data = response.json()
            page_url = page_data.get("url", "https://notion.so")
            return True, f"✅ *Página criada no seu Notion com sucesso!*\n\n🎬 *Título:* {final_title}\n🏷️ *Categoria:* `#{category}`\n🔗 [Abrir Página no Notion]({page_url})"
        else:
            err_msg = response.text[:200]
            if "could not find database" in err_msg.lower():
                return False, (
                    "❌ *O Notion não encontrou o banco de dados!*\n\n"
                    "Lembre-se de ir na sua página/tabela do Notion, clicar nos **3 pontinhos `...`** no canto superior direito $\rightarrow$ **Conexões (Connections)** $\rightarrow$ e selecionar a sua integração criada!"
                )
            return False, f"❌ Erro na API do Notion (Status {response.status_code}): `{err_msg}`"
    except Exception as e:
        return False, f"❌ Falha de conexão com o Notion: `{str(e)[:150]}`"
