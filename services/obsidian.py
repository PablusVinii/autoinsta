import os
import re
import base64
import requests
from datetime import datetime
from google import genai
import config

OBSIDIAN_PROMPT = """
Você é um especialista em Obsidian, Zettelkasten e Personal Knowledge Management (PKM).
Transforme o resumo abaixo em uma nota perfeita para o Obsidian.

Regras de Formatação Obsidian:
1. No topo, gere um Frontmatter YAML rigoroso:
---
tipo: video
plataforma: {platform}
lente: {category}
data: {date}
url: {url}
tags:
  - video
  - {tag1}
  - {tag2}
  - {tag3}
---

2. No corpo da nota:
- Identifique conceitos centrais, metodologias, ferramentas, nomes de pessoas relevantes, autores e termos técnicos e envolva-os em colchetes duplos [[Wikilink]] (exemplo: [[Marketing Digital]], [[MVP]], [[Inteligência Artificial]], [[Tráfego Pago]]).
- Use os blocos de destaque (callouts) nativos do Obsidian:
  > [!abstract] Resumo Executivo
  > [!tip] Ação Recomendada

3. No final da nota:
Adicione uma seção:
## 🔗 Conexões & Tópicos Relacionados
Liste de 3 a 5 [[Conceito]] para conectar o grafo de conhecimento do usuário.

Resumo a ser formatado:
\"\"\"
{summary}
\"\"\"
"""

def generate_obsidian_content(summary: str, transcription: str, title: str, category: str, platform: str, url: str) -> str:
    """Usa o Gemini para gerar o Markdown enriquecido com [[Wikilinks]] e frontmatter YAML."""
    try:
        from services.nvidia import generate_text_smart
        prompt = OBSIDIAN_PROMPT.format(
            platform=platform,
            category=category,
            date=datetime.now().strftime("%Y-%m-%d"),
            url=url,
            summary=summary,
            tag1=category.lower().replace("&", "").replace(" ", "-"),
            tag2=platform.lower(),
            tag3="segundo-cerebro"
        )
        md_text = generate_text_smart(prompt, max_tokens=2048)
        # Remove eventuais fences de markdown se a IA colocar
        if md_text.startswith("```markdown"):
            md_text = md_text[len("```markdown"):].strip()
        if md_text.startswith("```"):
            md_text = md_text[3:].strip()
        if md_text.endswith("```"):
            md_text = md_text[:-3].strip()

        # Anexa transcrição retrátil no rodapé
        if transcription and len(transcription) > 30:
            md_text += f"\n\n---\n## 📝 Transcrição Completa\n<details>\n<summary>Clique para expandir as falas na íntegra</summary>\n\n{transcription}\n</details>\n"

        return md_text
    except Exception as e:
        print(f"[Obsidian Formatter] Erro ao formatar com IA: {e}")
        # Fallback simples
        return f"""---
tipo: video
plataforma: {platform}
lente: {category}
data: {datetime.now().strftime("%Y-%m-%d")}
url: {url}
---

# {title}

{summary}

---
## 📝 Transcrição
{transcription}
"""

def clean_filename(title: str) -> str:
    """Gera um nome de arquivo seguro para o Windows e Obsidian."""
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    clean = clean.replace("*", "").strip()[:60]
    return clean if clean else "Nota_Video"

def save_note_to_github_vault(title: str, content: str) -> tuple[bool, str]:
    """
    Salva o arquivo .md diretamente no repositório do Obsidian no GitHub via REST API.
    Retorna (sucesso: bool, mensagem_ou_url: str).
    """
    token = os.getenv("OBSIDIAN_GITHUB_TOKEN", "").strip()
    repo = os.getenv("OBSIDIAN_GITHUB_REPO", "PablusVinii/meu-obsidian").strip()
    folder = os.getenv("OBSIDIAN_VAULT_FOLDER", "Inbox").strip().strip("/")

    if not token:
        return False, (
            "⚠️ *Token do GitHub para o Obsidian não configurado!*\n\n"
            "Para salvar diretamente no seu repositório do Obsidian, adicione a variável no Render:\n"
            "• `OBSIDIAN_GITHUB_TOKEN` : seu token do GitHub (`ghp_...` com permissão de `repo`)\n"
            "• `OBSIDIAN_GITHUB_REPO` : `PablusVinii/meu-obsidian`"
        )

    filename = f"{clean_filename(title)}.md"
    path = f"{folder}/{filename}" if folder else filename
    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AutoInsta-Obsidian-Sync"
    }

    # Verifica se o arquivo já existe para pegar o SHA caso precise atualizar
    sha = None
    get_res = requests.get(api_url, headers=headers, timeout=10)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")

    # Codifica conteúdo em Base64
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"Adicionar nota Obsidian: {title[:40]}",
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha

    try:
        put_res = requests.put(api_url, json=payload, headers=headers, timeout=15)
        if put_res.status_code in (200, 201):
            commit_data = put_res.json()
            html_url = commit_data.get("content", {}).get("html_url", f"https://github.com/{repo}")
            return True, f"✅ *Nota salva no seu Obsidian com sucesso!*\n\n📁 *Arquivo:* `{path}`\n🧠 *Conexões:* `[[Wikilinks]]` gerados automaticamente!\n🔗 [Ver no GitHub]({html_url})"
        else:
            return False, f"❌ Erro ao enviar para o GitHub (Status {put_res.status_code}): `{put_res.text[:150]}`"
    except Exception as e:
        return False, f"❌ Falha de conexão com o GitHub: `{str(e)[:150]}`"

def extract_wikilinks(text: str) -> list[str]:
    """Extrai todos os [[Wikilinks]] de um texto em Markdown sem duplicatas."""
    if not text:
        return []
    links = re.findall(r'\[\[([^\]]+)\]\]', text)
    seen = set()
    unique_links = []
    for l in links:
        cleaned = l.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique_links.append(cleaned)
    return unique_links

def list_github_vault_notes(limit: int = 10) -> list[dict]:
    """
    Lista os arquivos .md presentes na pasta do cofre no repositório do GitHub.
    Retorna lista de dicionários com nome, url no GitHub e data.
    """
    token = os.getenv("OBSIDIAN_GITHUB_TOKEN", "").strip()
    repo = os.getenv("OBSIDIAN_GITHUB_REPO", "PablusVinii/meu-obsidian").strip()
    folder = os.getenv("OBSIDIAN_VAULT_FOLDER", "Inbox").strip().strip("/")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AutoInsta-Obsidian-Sync"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    api_url = f"https://api.github.com/repos/{repo}/contents/{folder}" if folder else f"https://api.github.com/repos/{repo}/contents"

    try:
        res = requests.get(api_url, headers=headers, timeout=10)
        if res.status_code == 200:
            items = res.json()
            if isinstance(items, list):
                md_files = [
                    {
                        "name": item.get("name", "").replace(".md", ""),
                        "filename": item.get("name", ""),
                        "path": item.get("path", ""),
                        "html_url": item.get("html_url", ""),
                        "download_url": item.get("download_url", ""),
                    }
                    for item in items
                    if item.get("name", "").endswith(".md")
                ]
                return md_files[:limit]
    except Exception as e:
        print(f"[Obsidian Vault] Aviso ao listar repositório GitHub: {e}")
    return []

VAULT_SYNTHESIS_PROMPT = """
Você é o assistente de inteligência e curador do Segundo Cérebro (PKM - Personal Knowledge Management) do usuário.
O usuário fez uma pergunta ou pediu uma síntese consultando o conhecimento que ele acumulou no seu cofre do Obsidian através de resumos de vídeos (Instagram, TikTok, YouTube, etc).

Pergunta do Usuário:
\"{query}\"

Base de Conhecimento Acumulada no Segundo Cérebro ({count} notas analisadas):
\"\"\"
{context}
\"\"\"

Diretrizes Obrigatórias:
1. Responda em Português do Brasil com clareza, rigor conceitual e tom de mentor estratégico.
2. CITE explicitamente quais notas/vídeos serviram de base para cada ensinamento (ex: "Na nota *{titulo}*...", "Conforme o vídeo sobre *{tema}*...").
3. Use rigorosamente a sintaxe de [[Wikilinks]] do Obsidian para destacar os conceitos centrais, métodos, ferramentas e referências (ex: [[Marketing Digital]], [[MVP]], [[Engenharia de Prompt]], [[Modelos Mentais]]).
4. Identifique e aponte conexões e padrões entre diferentes vídeos que o usuário salvou (síntese cruzada entre temas).
5. Conclua com um takeaway prático ou passos de aplicação imediata.
"""

def synthesize_vault_knowledge(query: str, notes: list[dict]) -> str:
    """
    Sintetiza uma resposta consultando a base de conhecimento das notas do usuário com o Gemini.
    """
    if not notes:
        return (
            "⚠️ *Nenhuma nota encontrada no seu Segundo Cérebro ainda!*\n\n"
            "Envie links de vídeos (Instagram, TikTok, YouTube) para o bot e clique em *Salvar no Obsidian* para começar a povoar seu cofre."
        )

    context_chunks = []
    for i, n in enumerate(notes, 1):
        title = n.get("title", "Nota")
        category = n.get("category", "Geral")
        platform = n.get("platform", "Vídeo")
        summary = n.get("summary", "")[:700]
        wikilinks = n.get("wikilinks", "")
        created_at = n.get("created_at", "")

        chunk = f"--- NOTA {i} ---\nTítulo: {title}\nCategoria/Lente: {category}\nPlataforma: {platform}\nData: {created_at}\n"
        if wikilinks:
            chunk += f"Wikilinks: {wikilinks}\n"
        chunk += f"Conteúdo do Resumo:\n{summary}\n"
        context_chunks.append(chunk)

    full_context = "\n".join(context_chunks)
    prompt = VAULT_SYNTHESIS_PROMPT.format(
        query=query,
        count=len(notes),
        context=full_context,
    )

    try:
        from services.nvidia import generate_text_smart
        return generate_text_smart(prompt, max_tokens=2500)
    except Exception as e:
        print(f"[Obsidian Synthesis] Erro na síntese: {e}")
        return f"❌ Erro ao consultar o Segundo Cérebro: {e}"
