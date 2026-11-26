import base64
import logging
from google import genai
import config
from services.nvidia import generate_text_smart, is_gemini_blocked, mark_gemini_blocked

logger = logging.getLogger(__name__)

VISUAL_DIRECTOR_PROMPT = """
You are an avant-garde Creative Director for a top technology & engineering publication (like Wired or MIT Tech Review).
Your job is to create ONE disruptive, striking, high-contrast visual cover prompt (in English) for an AI image generator, based on the article/post topic below.

TOPIC / TITLE: {title}
KEY CONCEPTS: {summary}

STRICT VISUAL RULES:
1. MAKE IT DISRUPTIVE & MEMORABLE: Use bold visual metaphors (e.g., macro silicon circuitry colliding with organic light, brutalist obsidian monoliths, neon fiber-optic shockwaves, glowing server architecture emerging from shadow, dramatic isometric 3D or hyper-real editorial photography).
2. TOPIC RELEVANCE: The visual metaphor MUST clearly connect to the core theme of the topic above.
3. COLOR PALETTE: Deep obsidian/dark slate background (#0a0910) with electric violet, cyan, or molten amber rim lighting so it pops dramatically on LinkedIn feeds and dark-mode blogs.
4. ZERO TEXT IN IMAGE: Explicitly forbid any text, letters, numbers, logos, or watermarks inside the image (AI text gets garbled; pure visual impact works best).
5. FORMAT: Wide 16:9 editorial cover composition.

Return ONLY the final English image generation prompt (2 to 4 vivid sentences), nothing else.
"""


def generate_disruptive_cover(
    title: str,
    summary: str,
    variation_hint: str = "",
) -> bytes:
    """
    Gera uma imagem de capa disruptiva e chamativa em PNG (bytes) relacionada ao tema.
    Usa Gemini para criar o conceito visual metafórico + gemini-2.5-flash-image para sintetizar.
    """
    dir_prompt = VISUAL_DIRECTOR_PROMPT.format(
        title=title,
        summary=summary[:1200],
    )
    if variation_hint:
        dir_prompt += f"\nCreative twist: {variation_hint}"

    image_prompt = ""
    try:
        image_prompt = generate_text_smart(dir_prompt, max_tokens=512)
    except Exception:
        image_prompt = ""

    if not image_prompt:
        image_prompt = (
            f"Disruptive editorial 3D tech art representing {title}, "
            "deep obsidian dark background, electric violet and cyan rim lighting, "
            "hyper-detailed futuristic engineering metaphor, 16:9, no text, no letters."
        )
    else:
        image_prompt += " Wide 16:9 composition, ultra-sharp editorial lighting, no text, no words, no letters."

    if is_gemini_blocked():
        raise RuntimeError("Geração de imagem indisponível enquanto a API do Gemini estiver no limite de cota.")

    logger.info(f"[Visuals] Gerando capa com prompt: {image_prompt[:140]}...")

    client_img = genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options={"api_version": "v1beta"},
    )

    for img_model in ("gemini-2.5-flash-image", "gemini-3.1-flash-image"):
        try:
            res = client_img.interactions.create(
                model=img_model,
                input=image_prompt,
                response_modalities=["image"],
            )
            out_img = getattr(res, "output_image", None)
            if out_img and getattr(out_img, "data", None):
                raw_bytes = base64.b64decode(out_img.data)
                logger.info(f"[Visuals] Capa gerada com {img_model} ({len(raw_bytes)} bytes).")
                return raw_bytes
        except Exception as e:
            err_lower = str(e).lower()
            if any(k in err_lower for k in ["429", "403", "quota", "limit", "spending", "billing", "exceeded"]):
                mark_gemini_blocked(900)
                break
            logger.warning(f"[Visuals] Falha com {img_model}: {e}")

    raise RuntimeError("Não foi possível gerar a imagem de capa no momento.")
