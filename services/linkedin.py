import logging
import re
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
    "redução de custos e automação operacional — nunca superficial ou genérica."
)

ANGLES = {
    "executivo": (
        "Tom executivo e estratégico de especialista sênior em Infraestrutura e N3. "
        "Foque em continuidade operacional, redução de custos, arquitetura e impacto real."
    ),
    "tecnico": (
        "Tom de engenharia e troubleshooting N3 na prática. "
        "Destaque causa raiz, fluxo técnico, automação (PowerShell/Bash/Python), redes e hardware."
    ),
    "provocativo": (
        "Tom contraintuitivo e direto de quem está há 15+ anos na linha de frente. "
        "Desafie o senso comum operacional e mostre a visão de engenharia por trás do problema."
    ),
}

ANGLE_ORDER = ["executivo", "tecnico", "provocativo"]


def next_angle(current: str) -> str:
    """Retorna o próximo tom da lista de rotação."""
    try:
        idx = ANGLE_ORDER.index(current)
        return ANGLE_ORDER[(idx + 1) % len(ANGLE_ORDER)]
    except ValueError:
        return ANGLE_ORDER[0]


def generate_linkedin_post(
    title: str,
    summary: str,
    transcription: str = "",
    angle: str = "executivo",
) -> str:
    """
    Transforma o resumo/transcrição analisado em um post otimizado para o LinkedIn
    (sem Markdown cru, com gancho forte, escaneabilidade e hashtags).
    """
    tone_desc = ANGLES.get(angle, ANGLES["executivo"])

    prompt = f"""
Você é um ghostwriter escrevendo em primeira pessoa para o perfil de LinkedIn do autor abaixo.

PERFIL DO AUTOR:
{AUTHOR_PERSONA}

Sua tarefa é transformar o tema e os pontos abaixo em um post autoral pronto para publicar no LinkedIn, mantendo sempre o olhar prático de quem atua em Infraestrutura Sênior, N3, Automação e Engenharia.

TÍTULO / TEMA: {title}
ESTILO DESEJADO: {tone_desc}

[RESUMO ANALISADO]
{summary}

[TRECHO DA TRANSCRIÇÃO]
{transcription[:4000]}

REGRAS ESTRITAS DE FORMATAÇÃO E AUTORIA PARA O LINKEDIN:
1. AUTORIA ORIGINAL (REGRA CRÍTICA): Escreva como se o insight, a opinião e o domínio técnico fossem 100% seus (do autor do perfil). NUNCA mencione ou dê a entender que o texto veio de outro conteúdo — é PROIBIDO usar expressões como "no vídeo", "nesse conteúdo", "o autor disse", "segundo o resumo", "li/assisti recentemente", "na transcrição", "com base na análise" ou qualquer referência a vídeo/post/fonte externa.
2. Idioma: Português do Brasil natural, direto e sem clichês de IA ("No mundo dinâmico de hoje...", "Em conclusão...").
3. GANCHO (Hook): As 2 primeiras linhas devem ser curtas e magnéticas para gerar clique em "Ver mais".
4. SEM MARKDOWN: O LinkedIn NÃO renderiza `**negrito**`, `*itálico*` ou `# títulos`. NUNCA use asteriscos ou crases. Use texto puro, quebras de linha generosas e no máximo marcadores limpos como `→` ou `•`.
5. Escaneabilidade: Parágrafos curtos (1 a 2 frases por bloco).
6. Fechamento: Termine com uma pergunta aberta inteligente para estimular comentários + 3 a 5 hashtags relevantes no final.
7. Tamanho ideal: Entre 700 e 1.500 caracteres (máximo absoluto de 2.500 caracteres).
8. NÃO inclua links externos no corpo do post e NÃO coloque introduções como "Aqui está o post:". Entregue APENAS o texto final pronto para publicação.
"""
    post_text = generate_text_smart(prompt)
    # Garantia extra: remove eventuais asteriscos ou crases residuais de Markdown
    post_text = re.sub(r"\*\*(.*?)\*\*", r"\1", post_text)
    post_text = post_text.replace("`", "")
    return post_text


def _resolve_person_urn(token: str) -> str:
    """Obtém o Person URN via OpenID userinfo caso não esteja configurado."""
    if config.LINKEDIN_PERSON_URN:
        return config.LINKEDIN_PERSON_URN

    res = requests.get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if res.status_code == 200:
        sub = res.json().get("sub", "").strip()
        if sub:
            return f"urn:li:person:{sub}"
    return ""


def _upload_linkedin_image(token: str, person_urn: str, image_bytes: bytes) -> str:
    """Registra e envia uma imagem PNG para a API de Assets do LinkedIn, retornando o asset URN."""
    reg_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    reg_payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": person_urn,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
        }
    }
    reg_res = requests.post(reg_url, headers=headers, json=reg_payload, timeout=20)
    if reg_res.status_code not in (200, 201):
        raise RuntimeError(f"RegisterUpload ({reg_res.status_code}): {reg_res.text[:200]}")

    reg_data = reg_res.json().get("value", {})
    asset_urn = reg_data.get("asset", "")
    upload_mech = reg_data.get("uploadMechanism", {}).get(
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {}
    )
    upload_url = upload_mech.get("uploadUrl", "")
    if not asset_urn or not upload_url:
        raise RuntimeError("Resposta inválida do registerUpload do LinkedIn.")

    put_res = requests.put(
        upload_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/png",
        },
        data=image_bytes,
        timeout=30,
    )
    if put_res.status_code not in (200, 201):
        raise RuntimeError(f"Upload binário da imagem ({put_res.status_code}): {put_res.text[:200]}")

    return asset_urn


def publish_linkedin_post(text: str, image_bytes: bytes = None) -> tuple[bool, str]:
    """
    Publica um post (texto ou texto + imagem) no perfil pessoal do LinkedIn via API oficial.
    Retorna (sucesso, url_ou_mensagem_erro).
    """
    token = config.LINKEDIN_ACCESS_TOKEN
    if not token:
        return False, "LINKEDIN_ACCESS_TOKEN não configurado no ambiente."

    person_urn = _resolve_person_urn(token)
    if not person_urn:
        return False, "Não foi possível identificar o LinkedIn Person URN. Verifique o token e o escopo openid/profile."

    share_content = {
        "shareCommentary": {"text": text[:3000]},
        "shareMediaCategory": "NONE",
    }

    if image_bytes:
        try:
            asset_urn = _upload_linkedin_image(token, person_urn, image_bytes)
            share_content["shareMediaCategory"] = "IMAGE"
            share_content["media"] = [
                {
                    "status": "READY",
                    "media": asset_urn,
                }
            ]
        except Exception as e:
            logger.error(f"[LinkedIn] Erro ao subir imagem: {e}")
            return False, f"Erro ao enviar imagem para o LinkedIn: {e}"

    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": share_content
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    try:
        res = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=payload,
            timeout=20,
        )
        if res.status_code in (200, 201):
            post_id = res.headers.get("x-restli-id") or res.json().get("id", "")
            post_url = f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else "https://www.linkedin.com/feed/"
            return True, post_url
        elif res.status_code == 401:
            return False, "Token do LinkedIn expirado ou inválido (401). Gere um novo token no OAuth Tools e atualize o ambiente."
        else:
            logger.error(f"[LinkedIn] Erro {res.status_code}: {res.text[:300]}")
            return False, f"Erro da API do LinkedIn ({res.status_code}): {res.text[:200]}"
    except Exception as e:
        logger.error(f"[LinkedIn] Erro de conexão: {e}")
        return False, f"Erro de conexão ao publicar no LinkedIn: {e}"
