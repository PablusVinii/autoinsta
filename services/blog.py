import base64
import json
import logging
import re
import unicodedata
from datetime import datetime
import requests
import config
from services.nvidia import generate_text_smart

logger = logging.getLogger(__name__)

AUTHOR_PERSONA = (
    "Você escreve na voz de Pablus Vinicius: Especialista Sênior em Infraestrutura de TI, "
    "Suporte N3 e Engenharia de Hardware com mais de 15 anos de experiência prática "
    "(do silício à rede: eletrônica SMD/BGA, Windows/Linux, deploy automatizado de imagens, "
    "Wireshark, PowerShell, Bash, Python, Docker, Kubernetes e AWS). "
    "Mentalidade pragmática orientada a causa raiz (RCA), alta disponibilidade, "
    "recuperação de ativos críticos, redução de custos e automação operacional."
)

BLOG_ANGLES = {
    "executivo": "Tom sênior estratégico e consultivo, focado em continuidade de negócios, redução de custos e decisões de arquitetura.",
    "tecnico": "Tom profundo de engenharia N3 e infraestrutura, detalhando causa raiz, ferramentas, scripts (PowerShell/Bash/Python), redes e hardware.",
    "didatico": "Tom claro, estruturado e prático de quem ensina pela experiência real de campo, conectando teoria à operação.",
}

BLOG_ANGLE_ORDER = ["executivo", "tecnico", "didatico"]


def next_blog_angle(current: str) -> str:
    try:
        idx = BLOG_ANGLE_ORDER.index(current)
        return BLOG_ANGLE_ORDER[(idx + 1) % len(BLOG_ANGLE_ORDER)]
    except ValueError:
        return BLOG_ANGLE_ORDER[0]


def slugify(text: str) -> str:
    """Converte um título em slug URL-safe."""
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", norm.lower()).strip("-")
    return slug[:64] or "artigo"


def generate_blog_article(
    title: str,
    summary: str,
    transcription: str = "",
    category: str = "Geral",
    angle: str = "executivo",
) -> tuple[str, str, str]:
    """
    Gera um artigo completo em Markdown para o blog no GitHub Pages.
    Retorna (article_title, excerpt, markdown_body).
    """
    tone_desc = BLOG_ANGLES.get(angle, BLOG_ANGLES["executivo"])

    prompt = f"""
Você é o autor do blog técnico abaixo, escrevendo em primeira pessoa para profissionais de TI, gestores e engenheiros.

PERFIL DO AUTOR:
{AUTHOR_PERSONA}

Sua tarefa é escrever um artigo autoral em Markdown mantendo coerência com esse posicionamento sênior em Infraestrutura, N3, Automação e Engenharia (mesmo quando o tema envolver software ou IA, conecte com visão prática de operação, escala e confiabilidade).

TEMA BASE: {title}
CATEGORIA: {category}
ESTILO DESEJADO: {tone_desc}

[NOTAS DE REFERÊNCIA INTERNA]
{summary}

[DETALHES COMPLEMENTARES]
{transcription[:5000]}

REGRAS CRÍTICAS:
1. AUTORIA ORIGINAL: Escreva 100% como um artigo autoral seu. É PROIBIDO mencionar vídeo, resumo, transcrição, autor original ou qualquer fonte externa (nunca diga "no vídeo", "nesse conteúdo", "o autor explicou", etc.).
2. Idioma: Português do Brasil elegante, claro e direto.
3. Estrutura obrigatória com estas tags exatas:
[TITULO]
(Um título forte e atrativo de artigo, sem aspas)
[FIM_TITULO]

[RESUMO_CURTO]
(1 frase de até 160 caracteres para o card do blog)
[FIM_RESUMO_CURTO]

[ARTIGO]
(Artigo em Markdown limpo: introdução direta, 2 a 3 subtítulos ##, listas com -, um destaque em blockquote > e conclusão prática. Entre 400 e 900 palavras. NÃO repita o título principal no topo do corpo.)
[FIM_ARTIGO]
"""
    raw = generate_text_smart(prompt)

    t_match = re.search(r"\[TITULO\](.*?)\[FIM_TITULO\]", raw, re.DOTALL)
    e_match = re.search(r"\[RESUMO_CURTO\](.*?)\[FIM_RESUMO_CURTO\]", raw, re.DOTALL)
    b_match = re.search(r"\[ARTIGO\](.*?)\[FIM_ARTIGO\]", raw, re.DOTALL)

    article_title = t_match.group(1).strip() if t_match else title[:80]
    excerpt = e_match.group(1).strip() if e_match else article_title
    body = b_match.group(1).strip() if b_match else raw

    return article_title, excerpt, body


def _github_put_bytes(repo: str, token: str, path: str, raw_bytes: bytes, message: str) -> tuple[bool, str]:
    """Cria ou atualiza um arquivo binário/texto em um repositório GitHub via Contents API."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    sha = None
    get_res = requests.get(url, headers=headers, timeout=15)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")

    encoded = base64.b64encode(raw_bytes).decode("utf-8")
    payload = {"message": message, "content": encoded}
    if sha:
        payload["sha"] = sha

    put_res = requests.put(url, headers=headers, json=payload, timeout=30)
    if put_res.status_code in (200, 201):
        return True, "OK"
    return False, f"GitHub API ({put_res.status_code}): {put_res.text[:200]}"


def _github_put_file(repo: str, token: str, path: str, content_str: str, message: str) -> tuple[bool, str]:
    """Cria ou atualiza um arquivo de texto em um repositório GitHub via Contents API."""
    return _github_put_bytes(repo, token, path, content_str.encode("utf-8"), message)


def publish_to_github_blog(
    article_title: str,
    excerpt: str,
    markdown_body: str,
    category: str = "Geral",
    image_bytes: bytes = None,
) -> tuple[bool, str]:
    """
    Publica o artigo .md e atualiza posts/index.json no repositório GitHub Pages.
    Retorna (sucesso, url_publica_ou_erro).
    """
    token = config.BLOG_GITHUB_TOKEN
    repo = config.BLOG_GITHUB_REPO
    base_url = config.BLOG_BASE_URL

    if not token:
        return False, (
            "⚠️ Token do GitHub para o Blog não configurado!\n"
            "Adicione `BLOG_GITHUB_TOKEN` (ou `GITHUB_TOKEN`) no `.env` / Render com permissão `repo`."
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = f"{date_str}-{slugify(article_title)}"
    md_path = f"posts/{slug}.md"

    word_count = len(markdown_body.split())
    read_mins = max(1, round(word_count / 200))

    # 1. Envia a imagem de capa (se houver)
    cover_path = ""
    if image_bytes:
        img_path = f"posts/images/{slug}.png"
        ok_img, msg_img = _github_put_bytes(
            repo=repo,
            token=token,
            path=img_path,
            raw_bytes=image_bytes,
            message=f"blog: adiciona capa '{slug}'",
        )
        if ok_img:
            cover_path = img_path
        else:
            logger.warning(f"[Blog] Falha ao subir imagem de capa: {msg_img}")

    # 2. Envia o arquivo Markdown do artigo
    ok, msg = _github_put_file(
        repo=repo,
        token=token,
        path=md_path,
        content_str=markdown_body,
        message=f"blog: publica artigo '{article_title[:50]}'",
    )
    if not ok:
        return False, f"Erro ao salvar artigo no GitHub: {msg}"

    # 3. Lê e atualiza posts/index.json
    index_url = f"https://api.github.com/repos/{repo}/contents/posts/index.json"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    posts_list = []
    idx_res = requests.get(index_url, headers=headers, timeout=15)
    if idx_res.status_code == 200:
        try:
            raw_b64 = idx_res.json().get("content", "")
            posts_list = json.loads(base64.b64decode(raw_b64).decode("utf-8"))
        except Exception as e:
            logger.warning(f"[Blog] Falha ao decodificar posts/index.json existente: {e}")
            posts_list = []

    new_entry = {
        "slug": slug,
        "title": article_title,
        "excerpt": excerpt,
        "category": category or "Geral",
        "date": date_str,
        "readTime": f"{read_mins} min",
        "file": md_path,
    }
    if cover_path:
        new_entry["cover"] = cover_path
    # Evita duplicar slug se republicado
    posts_list = [new_entry] + [p for p in posts_list if p.get("slug") != slug]

    ok_idx, msg_idx = _github_put_file(
        repo=repo,
        token=token,
        path="posts/index.json",
        content_str=json.dumps(posts_list, ensure_ascii=False, indent=2),
        message=f"blog: atualiza index.json com '{slug}'",
    )
    if not ok_idx:
        return False, f"Artigo salvo, mas falhou ao atualizar index.json: {msg_idx}"

    return True, f"{base_url}/post.html?slug={slug}"
