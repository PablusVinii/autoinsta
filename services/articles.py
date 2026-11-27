import logging
import re
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from services.nvidia import generate_text_smart

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+", re.IGNORECASE)


def extract_article_url(text: str) -> str | None:
    """Extrai a primeira URL web válida de uma mensagem."""
    if not text:
        return None
    m = URL_REGEX.search(text.strip())
    return m.group(0).rstrip(".,);") if m else None


def fetch_article_content(url: str) -> tuple[str, str, str]:
    """
    Baixa e extrai (titulo, texto_limpo, dominio) de um artigo web.
    Usa BeautifulSoup diretamente e faz fallback para r.jina.ai caso haja bloqueio.
    """
    domain = urlparse(url).netloc.replace("www.", "") or "Web"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    title = ""
    clean_text = ""

    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200 and res.text:
            if not res.encoding or res.encoding.lower() == "iso-8859-1":
                res.encoding = res.apparent_encoding or "utf-8"
            soup = BeautifulSoup(res.text, "html.parser")

            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                title = h1.get_text(" ", strip=True)
            elif soup.title and soup.title.string:
                title = soup.title.string.strip()

            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"]):
                tag.decompose()

            root = soup.find("article") or soup.find("main") or soup.body or soup
            blocks = []
            for el in root.find_all(["h2", "h3", "p", "li"]):
                txt = el.get_text(" ", strip=True)
                if len(txt) >= 25:
                    blocks.append(txt)
            clean_text = "\n\n".join(blocks)
    except Exception as e:
        logger.warning(f"[Articles] Falha direta em {url}: {e}")

    # Fallback anti-bloqueio / JS-rendered via Jina Reader
    if len(clean_text) < 350:
        try:
            jina_res = requests.get(
                f"https://r.jina.ai/{url}",
                headers={"User-Agent": headers["User-Agent"]},
                timeout=20,
            )
            if jina_res.status_code == 200 and len(jina_res.text) > len(clean_text):
                md_raw = jina_res.text
                if not title:
                    m_title = re.search(r"^Title:\s*(.+)$", md_raw, re.MULTILINE)
                    if m_title:
                        title = m_title.group(1).strip()
                clean_text = md_raw
        except Exception as e:
            logger.warning(f"[Articles] Fallback Jina falhou para {url}: {e}")

    if not clean_text or len(clean_text) < 120:
        raise RuntimeError("Não foi possível extrair o conteúdo do artigo (site bloqueado ou sem texto).")

    return title[:120] or f"Artigo ({domain})", clean_text[:18000], domain


def analyze_web_article(url: str) -> tuple[str, str, str, str]:
    """
    Lê um artigo da internet e cria uma síntese analítica original (não-cópia),
    com ângulos de engajamento alinhados ao perfil Sênior N3 / Infra / Hardware.
    Retorna (title, summary, raw_article_text, domain).
    """
    raw_title, article_text, domain = fetch_article_content(url)

    prompt = f"""
Você é um estrategista editorial de tecnologia analisando uma matéria da web para transformá-la em inteligência prática e ganchos de alto engajamento.

DOMÍNIO: {domain}
TÍTULO ORIGINAL: {raw_title}

CONTEÚDO EXTRAÍDO:
\"\"\"
{article_text[:10000]}
\"\"\"

REGRAS:
1. Idioma: Português do Brasil natural, direto e envolvente.
2. NÃO COPIE o artigo nem faça um resumo burocrático. Extraia os fatos mais curiosos, o porquê de isso importar hoje e qual lição prática de tecnologia/infraestrutura/engenharia/cultura humana dá para tirar daí.
3. Responda estritamente usando estas tags:

[TITULO]
(Um título atrativo e original em PT-BR para essa pauta, sem aspas)
[FIM_TITULO]

[CATEGORIA]
(Uma categoria curta, ex: Hardware & Engenharia, Infraestrutura & TI, Tecnologia & Cultura)
[FIM_CATEGORIA]

[RESUMO]
🎬 *GANCHO / TESE CENTRAL*
(1 frase forte explicando o coração da história ou descoberta)

🔎 *FATOS & CURIOSIDADES-CHAVE*
• [Fato técnico ou humano marcante 1]
• [Fato técnico ou humano marcante 2]
• [Detalhe que surpreende o leitor 3]

⚡ *POR QUE ISSO GERA ENGAJAMENTO (ÂNGULO EDITORIAL)*
(Como conectar esse tema à realidade de infraestrutura, reparo, engenharia ou aprendizado contínuo — pronto para virar post no LinkedIn ou Blog)
[FIM_RESUMO]
"""
    output = generate_text_smart(prompt, max_tokens=1800)

    t_match = re.search(r"\[TITULO\](.*?)\[FIM_TITULO\]", output, re.DOTALL)
    c_match = re.search(r"\[CATEGORIA\](.*?)\[FIM_CATEGORIA\]", output, re.DOTALL)
    r_match = re.search(r"\[RESUMO\](.*?)\[FIM_RESUMO\]", output, re.DOTALL)

    title = t_match.group(1).strip() if t_match else raw_title
    category = c_match.group(1).strip() if c_match else "Artigo Web"
    summary = r_match.group(1).strip() if r_match else output.strip()

    return title, summary, article_text, category
