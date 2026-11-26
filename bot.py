import asyncio
import logging
import os
import threading
import uuid
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import (
    Update,
    constants,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import config
from services.downloader import (
    extract_video_url,
    get_youtube_video_id,
    download_video,
    cleanup_media,
)
from services.summarizer import (
    LENS_METADATA,
    analyze_youtube_url_direct,
    analyze_and_summarize_video,
    generate_content_ideas,
    answer_video_question,
    generate_engaging_comments,
    generate_bilingual_study,
    get_english_practice_text,
    evaluate_user_translation,
)
from services.notion import save_to_notion
from services.obsidian import (
    generate_obsidian_content,
    save_note_to_github_vault,
    extract_wikilinks,
    list_github_vault_notes,
    synthesize_vault_knowledge,
)
from services.database import (
    save_video,
    get_user_videos,
    get_obsidian_notes,
    update_obsidian_data,
    search_saved_videos,
    get_all_notes_for_synthesis,
    save_cache_entry,
    get_cache_entry,
)
from services.nvidia import (
    generate_critical_analysis,
    generate_audio_summary,
    semantic_search,
)
from services.linkedin import (
    generate_linkedin_post,
    publish_linkedin_post,
    next_angle,
)
from services.blog import (
    generate_blog_article,
    publish_to_github_blog,
    next_blog_angle,
)
from services.visuals import generate_disruptive_cover

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Cache de vídeos analisados para botões e Q&A
VIDEO_CACHE = {}

# Mapeia o ID da mensagem do resumo para o cache_id
MESSAGE_CACHE_MAP = {}

# Guarda links aguardando escolha de lente pelo usuário
# {req_id: {"url": str, "platform": str, "user_id": int, "time": float}}
PENDING_REQUESTS = {}

def clean_expired_cache():
    """Remove entradas com mais de 24 horas da RAM para economizar memória."""
    now = time.time()
    expired = [k for k, v in VIDEO_CACHE.items() if now - v.get("time", 0) > 86400]
    for k in expired:
        VIDEO_CACHE.pop(k, None)


def set_cached_video(cache_id: str, data: dict):
    """Salva na RAM e persiste no banco para sobreviver a reinícios no Render."""
    VIDEO_CACHE[cache_id] = data
    try:
        save_cache_entry(cache_id, data)
    except Exception as e:
        logger.warning(f"[Cache] Erro ao persistir cache {cache_id}: {e}")


def get_cached_video(cache_id: str) -> dict | None:
    """Busca na RAM e faz fallback automático no banco caso o servidor tenha reiniciado."""
    if not cache_id:
        return None
    cached = VIDEO_CACHE.get(cache_id)
    if cached:
        return cached
    try:
        cached = get_cache_entry(cache_id)
        if cached:
            VIDEO_CACHE[cache_id] = cached
            return cached
    except Exception as e:
        logger.warning(f"[Cache] Erro ao recuperar cache {cache_id}: {e}")
    return None

    expired_pending = [k for k, v in PENDING_REQUESTS.items() if now - v.get("time", 0) > 3600]
    for k in expired_pending:
        PENDING_REQUESTS.pop(k, None)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Servidor HTTP simples para atender aos health checks do Render/Koyeb."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot Universal de Resumos Online")

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health check HTTP ativo na porta {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Aviso ao iniciar servidor de health check: {e}")

async def check_user_allowed(update: Update) -> bool:
    """Verifica se o usuário está na lista de permissões."""
    if not config.ALLOWED_USER_IDS:
        return True
    user_id = update.effective_user.id if update.effective_user else None
    return user_id in config.ALLOWED_USER_IDS

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao comando /start com instruções de uso."""
    if not await check_user_allowed(update):
        await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
        return

    text = (
        "🤖 *Olá! Eu sou o seu Assistente Especializado de Vídeos & Segundo Cérebro.*\n\n"
        "Suporto vídeos em **Português, Inglês e Espanhol** das principais redes:\n"
        "• 📸 *Instagram:* Reels e vídeos do feed\n"
        "• ▶️ *YouTube:* Shorts e vídeos completos\n"
        "• 🎵 *TikTok:* Vídeos e links compartilhados\n"
        "• 🐦 *Twitter / X:* Posts com vídeo\n"
        "• 🎙️ *Notas de Voz:* Envie áudios gravados no Telegram para transcrever instantaneamente com Deepgram Nova-3!\n\n"
        "🎯 *Como Funciona (Lentes Especializadas):*\n"
        "Basta colar ou compartilhar um link! Eu perguntarei qual tipo de extração você deseja:\n"
        "• 💼 *Negócios & Vendas:* Estratégias, frameworks e monetização\n"
        "• 💻 *Tecnologia & IA:* Softwares, códigos e prompts práticos\n"
        "• 🧠 *Sabedoria & Filosofia:* Modelos mentais e quebra de paradigmas\n"
        "• 🙏 *Fé & Espiritualidade:* Mensagens bíblicas, princípios e devocional\n"
        "• ⚡ *Síntese Geral:* Resumo rápido e universal\n\n"
        "🧠 *Segundo Cérebro & Obsidian (com NVIDIA NIM):*\n"
        "• `/obsidian` — Ver notas recentes e conexões `[[Wikilinks]]`\n"
        "• `/buscar <termo>` — Pesquisa semântica por significado (NVIDIA Embeddings)\n"
        "• `/consultar <pergunta>` — Síntese cruzada estratégica com RAG\n"
        "• `/salvos` — Histórico de vídeos salvos\n\n"
        "⚡ *Superpoderes por Vídeo:*\n"
        "• `[ 🎙️ Dublagem pt-BR ]` — Dublagem multi-voz realista de toda a conversa traduzida\n"
        "• `[ 🎧 Resumo Áudio ]` — Locução do resumo em mensagem de voz rápida\n"
        "• `[ ⚖️ Auditoria Crítica ]` — Análise cética de riscos e viabilidade (NVIDIA)\n"
        "• `[ 📓 Obsidian ]` — Sincronização automática com `[[Wikilinks]]`\n"
        "• `[ 💾 Notion ]` — Envio direto para o banco de dados do Notion\n\n"
        "💬 *Dica:* Você também pode dar 'Reply' em qualquer resumo para tirar dúvidas com a IA!"
    )
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def salvos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe os últimos vídeos salvos na biblioteca pessoal."""
    if not await check_user_allowed(update):
        return

    user_id = update.effective_user.id
    items = get_user_videos(user_id, limit=8)

    if not items:
        await update.message.reply_text(
            "📚 Sua biblioteca de vídeos ainda está vazia!\nEnvie links de Reels, TikTok ou YouTube para começar a salvar."
        )
        return

    lines = ["📚 *SUA BIBLIOTECA PESSOAL (Últimos salvos):*\n"]
    for i, it in enumerate(items, 1):
        cat = it["category"] or "Geral"
        title = it["title"] or "Vídeo"
        lines.append(f"{i}. *{title}*\n   🏷️ `#{cat}` | 🔗 [{it['platform']}]({it['url']})\n")

    lines.append("💡 *Dica:* Digite `/obsidian` para ver notas com `[[Wikilinks]]` ou `/buscar <termo>` para pesquisar!")
    await update.message.reply_text("\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN)

async def obsidian_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista as notas recentes salvas e formatadas para o cofre do Obsidian."""
    if not await check_user_allowed(update):
        return

    user_id = update.effective_user.id
    notes = get_obsidian_notes(user_id, limit=6)
    repo_name = os.getenv("OBSIDIAN_GITHUB_REPO", "PablusVinii/meu-obsidian")

    if not notes:
        await update.message.reply_text(
            "📓 *Seu Cofre do Obsidian ainda não possui notas salvas!*\n\n"
            "Como adicionar:\n"
            "1. Envie qualquer link de vídeo (Instagram, TikTok, YouTube, X)\n"
            "2. Escolha a lente de extração\n"
            "3. Clique no botão *[ 📓 Obsidian ]*\n\n"
            f"O bot irá gerar os `[[Wikilinks]]` e sincronizar direto com seu repositório `{repo_name}`!",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    lines = [
        "📓 *SEU SEGUNDO CÉREBRO NO OBSIDIAN*\n"
        f"📂 *Repositório:* [{repo_name}](https://github.com/{repo_name})\n"
        "Aqui estão suas notas e sínteses mais recentes:\n"
    ]

    for i, n in enumerate(notes, 1):
        title = n["title"] or "Nota"
        cat = n["category"] or "Geral"
        links = n["wikilinks"] or ""
        created = n.get("created_at", "")[:10]

        entry = f"{i}. *{title}*\n   🏷️ `#{cat}` | 📅 `{created}`"
        if links:
            short_links = ", ".join(links.split(",")[:4])
            entry += f"\n   🧠 *Conexões:* {short_links}"
        if n.get("url"):
            entry += f"\n   🔗 [{n['platform']}]({n['url']})"
        lines.append(entry + "\n")

    lines.append(
        "💡 *Comandos Úteis:*\n"
        "• `/buscar <termo>` — Pesquisa direta no cofre\n"
        "• `/consultar <pergunta>` — Síntese cruzada com Gemini"
    )

    await update.message.reply_text("\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN)

async def buscar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca termos, ferramentas ou conceitos nas notas via busca textual e RAG Semântico da NVIDIA."""
    if not await check_user_allowed(update):
        return

    if not context.args:
        await update.message.reply_text(
            "🔍 *Como usar a Busca no Segundo Cérebro:*\n\n"
            "Digite `/buscar <termo>` para localizar qualquer assunto em suas notas.\n\n"
            "*Exemplos:*\n"
            "• `/buscar inteligência artificial`\n"
            "• `/buscar vendas`\n"
            "• `/buscar automação`\n"
            "• `/buscar mindset`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    query = " ".join(context.args).strip()
    user_id = update.effective_user.id

    # 1. Busca textual no SQLite
    text_results = search_saved_videos(user_id, query, limit=6)

    # 2. RAG Semântico vetorial com NVIDIA NIM (se configurado)
    all_user_notes = get_all_notes_for_synthesis(user_id, limit=30)
    semantic_results = []
    if config.NVIDIA_API_KEY and all_user_notes:
        try:
            raw_semantic = await asyncio.to_thread(
                semantic_search,
                query,
                all_user_notes,
                top_k=5,
            )
            # Filtra notas com afinidade semântica significativa
            semantic_results = [r for r in raw_semantic if r.get("similarity_score", 0) >= 0.28]
        except Exception as e:
            logger.warning(f"Aviso no RAG semântico da NVIDIA: {e}")

    # Mescla resultados evitando duplicatas (privilegiando semânticos relevantes)
    results = []
    seen_titles = set()
    for r in semantic_results:
        t = r.get("title", "")
        if t and t not in seen_titles:
            seen_titles.add(t)
            results.append(r)

    for r in text_results:
        t = r.get("title", "")
        if t and t not in seen_titles:
            seen_titles.add(t)
            results.append(r)

    results = results[:6]

    if not results:
        await update.message.reply_text(
            f"🔍 *Nenhum resultado encontrado para:* \"{query}\"\n\n"
            "• Tente palavras mais curtas ou sinônimos (ex: `vendas`, `IA`, `marketing`)\n"
            "• Digite `/obsidian` para ver todas as notas disponíveis na sua biblioteca.",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    lines = [f"🔎 *RESULTADOS PARA:* \"{query}\" ({len(results)} encontrados)\n"]
    for i, r in enumerate(results, 1):
        title = r["title"] or "Nota"
        cat = r["category"] or "Geral"
        links = r.get("wikilinks", "")
        summary = r.get("summary", "")
        score = r.get("similarity_score")

        summary_preview = ""
        for s_line in summary.split("\n"):
            if s_line.strip() and not s_line.startswith("#") and not any(k in s_line.upper() for k in ["TÍTULO", "TEMA", "LENTE"]):
                summary_preview = s_line.strip()[:140]
                break

        entry = f"{i}. *{title}*\n   🏷️ `#{cat}` | 🔗 [{r['platform']}]({r['url']})"
        if score:
            pct = int(score * 100)
            entry += f"\n   🎯 *Afinidade Semântica (NVIDIA):* `{pct}%`"
        if summary_preview:
            entry += f"\n   📌 _{summary_preview}..._"
        if links:
            short_links = ", ".join(links.split(",")[:3])
            entry += f"\n   🧠 {short_links}"
        lines.append(entry + "\n")

    lines.append(f"💡 *Dica:* Para cruzar essas ideias com a IA, digite:\n`/consultar {query}`")
    await update.message.reply_text("\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN)

async def consultar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cruza o conhecimento acumulado no cofre do Obsidian com RAG Semântico NVIDIA e Gemini."""
    if not await check_user_allowed(update):
        return

    if not context.args:
        await update.message.reply_text(
            "🧠 *Modo \"Consultar Segundo Cérebro\":*\n\n"
            "Faça uma pergunta e a IA cruzará as lições, metodologias e conexões de todos os vídeos salvos usando o RAG Semântico da NVIDIA!\n\n"
            "*Exemplos:*\n"
            "• `/consultar quais as principais estratégias de vendas que aprendi?`\n"
            "• `/consultar como usar IA para produtividade com base nas notas?`\n"
            "• `/consultar sintetize os princípios de sabedoria e disciplina salvos.`",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    query = " ".join(context.args).strip()
    user_id = update.effective_user.id

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=constants.ChatAction.TYPING,
    )

    loading = await update.message.reply_text(
        "🧠 *Consultando seu Segundo Cérebro...*\n"
        "Buscando vetores semânticos com NVIDIA NIM e gerando síntese cruzada...",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    all_notes = get_all_notes_for_synthesis(user_id, limit=30)

    # 1. Recuperação Vetorial Semântica (NVIDIA RAG)
    combined_notes = []
    if config.NVIDIA_API_KEY and all_notes:
        try:
            combined_notes = await asyncio.to_thread(
                semantic_search,
                query,
                all_notes,
                top_k=8,
            )
        except Exception as e:
            logger.warning(f"Fallback de busca vetorial: {e}")

    # Fallback se a busca vetorial não encontrar ou não estiver ativa
    if not combined_notes:
        targeted_notes = search_saved_videos(user_id, query, limit=8)
        recent_notes = get_all_notes_for_synthesis(user_id, limit=15)
        seen_titles = set()
        for n in (targeted_notes + recent_notes):
            t = n.get("title", "")
            if t and t not in seen_titles:
                seen_titles.add(t)
                combined_notes.append(n)

    if not combined_notes:
        await loading.edit_text(
            "⚠️ *Você ainda não possui notas salvas no seu Segundo Cérebro!*\n\n"
            "Envie links de vídeos (Instagram, TikTok, YouTube) para o bot e clique em *Salvar no Obsidian* para que eu possa cruzar seus conhecimentos."
        )
        return

    try:
        answer = await asyncio.to_thread(
            synthesize_vault_knowledge,
            query,
            combined_notes,
        )

        if len(answer) <= 4000:
            try:
                await loading.edit_text(answer, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception:
                await loading.edit_text(answer)
        else:
            chunks = [answer[i:i + 3900] for i in range(0, len(answer), 3900)]
            await loading.edit_text(chunks[0], parse_mode=constants.ParseMode.MARKDOWN)
            for ch in chunks[1:]:
                await update.message.reply_text(ch, parse_mode=constants.ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Erro na síntese do cofre: {e}", exc_info=True)
        await loading.edit_text(f"❌ Erro ao consultar o Segundo Cérebro: `{str(e)[:150]}`")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens recebidas (links de vídeos ou perguntas de Q&A sobre um resumo)."""
    if not update.message or not update.message.text:
        return

    if not await check_user_allowed(update):
        await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
        return

    user_text = update.message.text.strip()

    # 1. VERIFICAÇÃO DE "CONVERSE COM O VÍDEO" (Q&A):
    if update.message.reply_to_message:
        replied_msg_id = update.message.reply_to_message.message_id
        cache_id = MESSAGE_CACHE_MAP.get(replied_msg_id)

        if cache_id:
            video_data = get_cached_video(cache_id)
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=constants.ChatAction.TYPING,
            )

            loading = await update.message.reply_text("💬 *Consultando o conteúdo do vídeo...*")
            try:
                answer = await asyncio.to_thread(
                    answer_video_question,
                    video_data["summary"],
                    video_data["transcription"],
                    user_text,
                )
                await loading.edit_text(answer, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Erro no Q&A: {e}")
                await loading.edit_text(f"❌ Não consegui responder no momento: {e}")
            return

    # 2. VERIFICAÇÃO DE LINK DE VÍDEO NOVO:
    extracted = extract_video_url(user_text)
    if extracted:
        context.user_data.pop("awaiting_translation", None)

    # 1.5 VERIFICAÇÃO DE MODO PRÁTICA DE TRADUÇÃO (INGLÊS -> PORTUGUÊS):
    practice_data = context.user_data.get("awaiting_translation")
    if practice_data and not extracted:
        context.user_data.pop("awaiting_translation", None)
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )
        loading = await update.message.reply_text("✍️ *Corrigindo sua tradução palavra por palavra...*", parse_mode=constants.ParseMode.MARKDOWN)
        try:
            feedback = await asyncio.to_thread(
                evaluate_user_translation,
                practice_data["english_text"],
                user_text,
            )
            retry_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Praticar Novamente", callback_data=f"practice_{practice_data['cache_id']}")]
            ])
            if len(feedback) <= 3900:
                try:
                    await loading.edit_text(feedback, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=retry_kb)
                except Exception:
                    await loading.edit_text(feedback, reply_markup=retry_kb)
            else:
                chunks = [feedback[i:i + 3800] for i in range(0, len(feedback), 3800)]
                await loading.edit_text(chunks[0])
                for ch in chunks[1:-1]:
                    await update.message.reply_text(ch)
                await update.message.reply_text(chunks[-1], reply_markup=retry_kb)
        except Exception as e:
            logger.error(f"Erro ao corrigir tradução: {e}", exc_info=True)
            await loading.edit_text(f"❌ Erro ao corrigir tradução: {e}")
        return

    if not extracted:
        await update.message.reply_text(
            "💡 Envie um link válido de vídeo (*Instagram, TikTok, YouTube, X*)\n"
            "Ou responda (dê 'Reply') a um resumo anterior para fazer perguntas sobre ele!",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    video_url, platform = extracted
    clean_expired_cache()

    # Armazena a solicitação pendente para a escolha de lente
    req_id = str(uuid.uuid4())[:8]
    PENDING_REQUESTS[req_id] = {
        "url": video_url,
        "platform": platform,
        "user_id": update.effective_user.id,
        "time": time.time(),
    }

    # Apresenta o menu de lentes temáticas para extração personalizada
    keyboard = [
        [
            InlineKeyboardButton("💼 Negócios & Vendas", callback_data=f"ln_biz_{req_id}"),
            InlineKeyboardButton("💻 Tecnologia & IA", callback_data=f"ln_tech_{req_id}"),
        ],
        [
            InlineKeyboardButton("🧠 Sabedoria & Filosofia", callback_data=f"ln_wis_{req_id}"),
            InlineKeyboardButton("🙏 Fé & Espiritualidade", callback_data=f"ln_fth_{req_id}"),
        ],
        [
            InlineKeyboardButton("⚡ Síntese Geral Rápida", callback_data=f"ln_gen_{req_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎯 *Vídeo do {platform} detectado!*\n\n"
        "Qual tipo de extração e ensinamento você deseja tirar desse conteúdo?",
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com cliques em botões (escolha de lente, transcrição, ideias, q&a, notion)."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data

    # A) PROCESSA ESCOLHA DE LENTE DE EXTRAÇÃO
    if data.startswith("ln_"):
        parts = data.split("_")
        if len(parts) < 3:
            return
        lens_code = parts[1]
        req_id = parts[2]

        req = PENDING_REQUESTS.pop(req_id, None)
        if not req:
            await query.message.edit_text("⚠️ A solicitação deste vídeo expirou. Por favor, envie o link novamente.")
            return

        video_url = req["url"]
        platform = req["platform"]
        user_id = req["user_id"]

        lens_meta = LENS_METADATA.get(lens_code, LENS_METADATA["gen"])
        lens_name = lens_meta["name"]
        lens_emoji = lens_meta["emoji"]

        status_msg = await query.message.edit_text(
            f"⏳ *Analisando sob a lente de {lens_emoji} {lens_name}...*\n"
            "Processando conteúdo e gerando inteligência com IA...",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        local_path = None
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
                action=constants.ChatAction.TYPING,
            )

            summary = None
            transcription = None
            orig_lang = ""
            orig_transcription = ""

            # Para YouTube, usa integração nativa do Gemini com a lente
            if platform == "YouTube":
                yt_id = get_youtube_video_id(video_url)
                clean_yt_url = f"https://www.youtube.com/watch?v={yt_id}" if yt_id else video_url
                logger.info(f"Processando YouTube via Gemini ({lens_name}): {clean_yt_url}")
                summary, transcription, orig_lang = await asyncio.to_thread(
                    analyze_youtube_url_direct, clean_yt_url, lens_code, None, True
                )

            # Para Instagram, TikTok e Twitter/X, baixa o arquivo de mídia
            if not summary:
                local_path = await asyncio.to_thread(download_video, video_url)
                summary, transcription, orig_lang, orig_transcription = await asyncio.to_thread(
                    analyze_and_summarize_video, local_path, lens_code, None, True, True
                )

            category = f"{lens_name}"

            # Extrai título inicial do resumo
            title_line = "Vídeo"
            for line in summary.split("\n"):
                if any(k in line.upper() for k in ["TÍTULO", "TEMA", "TESE", "FERRAMENTA", "MENSAGEM CENTRAL", "PRINCÍPIO"]):
                    continue
                if line.strip():
                    title_line = line.replace("*", "").strip()[:80]
                    break

            # Salva no banco SQLite interno
            save_video(
                user_id=user_id,
                title=title_line,
                category=category,
                platform=platform,
                url=video_url,
                summary=summary,
                transcription=transcription or "",
            )

            # Guarda no cache em memória e no banco persistente
            cache_id = str(uuid.uuid4())[:8]
            set_cached_video(cache_id, {
                "summary": summary,
                "transcription": transcription,
                "orig_transcription": orig_transcription,
                "url": video_url,
                "platform": platform,
                "category": category,
                "title": title_line,
                "orig_lang": orig_lang,
                "time": time.time(),
            })

            keyboard = [
                [
                    InlineKeyboardButton("📝 Transcrição", callback_data=f"tx_{cache_id}"),
                    InlineKeyboardButton("🇺🇸 Estudar Inglês", callback_data=f"study_{cache_id}"),
                    InlineKeyboardButton("✍️ Praticar Tradução", callback_data=f"practice_{cache_id}"),
                ],
                [
                    InlineKeyboardButton("🎙️ Dublagem pt-BR", callback_data=f"dub_{cache_id}"),
                    InlineKeyboardButton("🎧 Resumo Áudio", callback_data=f"audio_{cache_id}"),
                    InlineKeyboardButton("💡 Ideias de Post", callback_data=f"idea_{cache_id}"),
                ],
                [
                    InlineKeyboardButton("💭 Gerar Comentário", callback_data=f"comment_{cache_id}"),
                    InlineKeyboardButton("⚖️ Auditoria Crítica", callback_data=f"critique_{cache_id}"),
                    InlineKeyboardButton("💬 Tirar Dúvida", callback_data=f"qa_{cache_id}"),
                ],
                [
                    InlineKeyboardButton("💾 Notion", callback_data=f"notion_{cache_id}"),
                    InlineKeyboardButton("📓 Obsidian", callback_data=f"obsidian_{cache_id}"),
                ],
                [
                    InlineKeyboardButton("💼 Post LinkedIn", callback_data=f"li_prep_{cache_id}"),
                    InlineKeyboardButton("🌐 Post Blog", callback_data=f"blog_prep_{cache_id}"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            response_text = f"🏷️ *Lente:* {lens_emoji} `#{category}`\n\n{summary}\n\n🔗 [{platform} Original]({video_url})"

            sent_msg = None
            try:
                sent_msg = await status_msg.edit_text(
                    response_text,
                    parse_mode=constants.ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
            except Exception:
                sent_msg = await status_msg.edit_text(response_text, reply_markup=reply_markup)

            if sent_msg:
                MESSAGE_CACHE_MAP[sent_msg.message_id] = cache_id

        except Exception as e:
            logger.error(f"Erro ao processar {platform} ({video_url}): {e}", exc_info=True)
            error_msg = (
                f"❌ *Não foi possível processar este vídeo do {platform}.*\n\n"
                f"• Detalhes técnicos: `{str(e)[:150]}`"
            )
            await status_msg.edit_text(error_msg, parse_mode=constants.ParseMode.MARKDOWN)

        finally:
            if local_path:
                await asyncio.to_thread(cleanup_media, local_path)
        return

    # B) VER TRANSCRIÇÃO COMPLETA
    if data.startswith("tx_"):
        cache_id = data[3:]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        transcription = cached.get("transcription", "Transcrição não disponível.")
        text = f"📝 *TRANSCRIÇÃO COMPLETA:*\n\n{transcription}"

        if len(text) > 4000:
            text = text[:3950] + "\n\n... *(Transcrição truncada por limite do Telegram)*"

        try:
            await query.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            await query.message.reply_text(text)

    # C) GERAR IDEIAS DE POST
    elif data.startswith("idea_"):
        cache_id = data[5:]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        loading_msg = await query.message.reply_text("⏳ *Criando kit de ganchos e ideias de post com IA...*")
        try:
            summary = cached.get("summary", "")
            ideas = await asyncio.to_thread(generate_content_ideas, summary)
            try:
                await loading_msg.edit_text(ideas, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception:
                await loading_msg.edit_text(ideas)
        except Exception as e:
            await loading_msg.edit_text(f"❌ Erro ao gerar ideias: {e}")

    # D) COMO TIRAR DÚVIDA (Q&A)
    elif data.startswith("qa_"):
        await query.message.reply_text(
            "💬 *Como tirar dúvidas sobre este vídeo:*\n\n"
            "Basta clicar em **Responder (Reply)** na mensagem do resumo acima e digitar sua pergunta!\n\n"
            "Exemplos:\n"
            "• _Qual ferramenta ele mencionou?_\n"
            "• _Explique o passo 2 em mais detalhes._\n"
            "• _Como aplico isso no meu contexto?_",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    # E) SALVAR NO NOTION
    elif data.startswith("notion_"):
        cache_id = data[7:]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        feedback_msg = await query.message.reply_text("⏳ *Sincronizando com o Notion...*")
        success, msg = await asyncio.to_thread(
            save_to_notion,
            cached.get("title", "Vídeo"),
            cached.get("category", "Geral"),
            cached.get("platform", "Vídeo"),
            cached.get("url", ""),
            cached.get("summary", ""),
            cached.get("transcription", ""),
        )
        try:
            await feedback_msg.edit_text(msg, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            await feedback_msg.edit_text(msg)

    # F) SALVAR NO OBSIDIAN
    elif data.startswith("obsidian_"):
        cache_id = data[9:]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        feedback_msg = await query.message.reply_text("⏳ *Formatando nota com [[Wikilinks]] e sincronizando com o Obsidian...*")

        title = cached.get("title", "Vídeo")
        summary = cached.get("summary", "")
        transcription = cached.get("transcription", "")
        category = cached.get("category", "Geral")
        platform = cached.get("platform", "Vídeo")
        url = cached.get("url", "")

        # Gera o Markdown enriquecido com [[Wikilinks]] e frontmatter
        md_content = await asyncio.to_thread(
            generate_obsidian_content,
            summary,
            transcription,
            title,
            category,
            platform,
            url,
        )

        # Extrai os [[Wikilinks]] e registra no banco SQLite para buscas e conexões imediatas
        wikilinks = extract_wikilinks(md_content)
        wikilinks_str = ", ".join([f"[[{w}]]" for w in wikilinks])
        update_obsidian_data(
            user_id=update.effective_user.id,
            url=url,
            obsidian_content=md_content,
            wikilinks=wikilinks_str,
        )

        success, msg = await asyncio.to_thread(
            save_note_to_github_vault,
            title,
            md_content,
        )

        try:
            await feedback_msg.edit_text(msg, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            await feedback_msg.edit_text(msg)

        # Se ainda não configurou o token do GitHub, envia também o arquivo .md no chat como contingência
        if not success and "Token do GitHub" in msg:
            import io
            clean_t = title.replace("/", "_")[:35]
            file_stream = io.BytesIO(md_content.encode("utf-8"))
            file_stream.name = f"{clean_t}.md"
            await query.message.reply_document(
                document=file_stream,
                caption="📄 *Aqui está o seu arquivo .md pronto com [[Wikilinks]]!* Basta soltá-lo no seu cofre do Obsidian.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

    # G) OUVIR RESUMO EM ÁUDIO (NEURAL TTS TELEGRAM)
    elif data.startswith("audio_"):
        cache_id = data[6:]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.RECORD_VOICE,
        )

        status_msg = await query.message.reply_text("🎧 *Gerando locução neural do resumo em áudio...*")

        title = cached.get("title", "Vídeo")
        summary = cached.get("summary", "")

        audio_file = None
        try:
            audio_file = await generate_audio_summary(title, summary)
            with open(audio_file, "rb") as f:
                await context.bot.send_voice(
                    chat_id=update.effective_chat.id,
                    voice=f,
                    caption=f"🎙️ *Resumo em Áudio:* {title[:60]}\n🏷️ `#{cached.get('category', 'Geral')}`",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.error(f"Erro ao gerar áudio: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Não foi possível gerar a locução de áudio: {e}")
        finally:
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except Exception:
                    pass

    # H) AUDITORIA CRÍTICA & ADVOGADO DO DIABO (NVIDIA NEMOTRON REASONING)
    elif data.startswith("critique_"):
        cache_id = data[9:]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        loading_msg = await query.message.reply_text(
            "⚖️ *Executando Auditoria Crítica com IA da NVIDIA...*\n"
            "Analisando pontos cegos, riscos operacionais e viabilidade real...",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        title = cached.get("title", "Vídeo")
        category = cached.get("category", "Geral")
        summary = cached.get("summary", "")
        transcription = cached.get("transcription", "")

        try:
            critique = await asyncio.to_thread(
                generate_critical_analysis,
                title,
                category,
                summary,
                transcription,
            )
            resp = f"⚖️ *AUDITORIA CRÍTICA & VIABILIDADE (NVIDIA)*\n🎯 *Vídeo:* _{title}_\n\n{critique}"

            if len(resp) <= 4000:
                try:
                    await loading_msg.edit_text(resp, parse_mode=constants.ParseMode.MARKDOWN)
                except Exception:
                    await loading_msg.edit_text(resp)
            else:
                chunks = []
                current_chunk = ""
                for line in resp.split("\n"):
                    if len(current_chunk) + len(line) + 1 < 3800:
                        current_chunk += line + "\n"
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = line + "\n"
                if current_chunk:
                    chunks.append(current_chunk.strip())

                try:
                    await loading_msg.edit_text(chunks[0], parse_mode=constants.ParseMode.MARKDOWN)
                except Exception:
                    await loading_msg.edit_text(chunks[0])

                for ch in chunks[1:]:
                    try:
                        await query.message.reply_text(ch, parse_mode=constants.ParseMode.MARKDOWN)
                    except Exception:
                        await query.message.reply_text(ch)
        except Exception as e:
            logger.error(f"Erro na auditoria crítica: {e}", exc_info=True)
            await loading_msg.edit_text(f"❌ Erro ao gerar auditoria crítica: {e}")

    # I) DUBLAGEM MULTI-VOZ EM PORTUGUÊS (DEEPGRAM + VOZES NEURAIS)
    elif data.startswith("dub_"):
        cache_id = data[4:]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.RECORD_VOICE,
        )

        status_msg = await query.message.reply_text(
            "🎙️ *Gerando Dublagem Expressiva com Deepgram Aura...*\n"
            "Atribuindo vozes orgânicas (com respiração e entonação natural) a cada locutor...",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        title = cached.get("title", "Vídeo")
        transcription = cached.get("transcription", "")

        if not transcription or len(transcription) < 10:
            await status_msg.edit_text("❌ Transcrição não disponível para dublagem.")
            return

        audio_file = None
        try:
            from services.transcriber import generate_dubbed_audio
            audio_file = await generate_dubbed_audio(transcription)

            with open(audio_file, "rb") as f:
                await context.bot.send_voice(
                    chat_id=update.effective_chat.id,
                    voice=f,
                    caption=f"🎙️ *Dublagem Expressiva:* {title[:60]}\n👥 *Vozes:* Deepgram Aura (Expressão & Sotaque Conversacional)",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            await status_msg.delete()
        except Exception as e:
            logger.error(f"Erro na dublagem: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Não foi possível gerar a dublagem: {e}")
        finally:
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except Exception:
                    pass

    # J) LINKEDIN: GERAR RASCUNHO + CAPA VISUAL / TROCAR TOM / NOVA IMAGEM / PUBLICAR / CANCELAR
    elif data.startswith("li_prep_") or data.startswith("li_regen_"):
        is_regen = data.startswith("li_regen_")
        cache_id = data[len("li_regen_"):] if is_regen else data[len("li_prep_"):]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        angle = cached.get("linkedin_angle", "executivo")
        if is_regen:
            angle = next_angle(angle)
            status_msg = await query.message.edit_text(
                f"🔄 *Reescrevendo post para o LinkedIn (tom: {angle})...*",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            status_msg = await query.message.reply_text(
                "💼🎨 *Redigindo post e criando capa visual disruptiva para o LinkedIn...*",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

        try:
            draft = await asyncio.to_thread(
                generate_linkedin_post,
                cached.get("title", "Vídeo"),
                cached.get("summary", ""),
                cached.get("transcription", ""),
                angle,
            )
            cached["linkedin_draft"] = draft
            cached["linkedin_angle"] = angle

            if not cached.get("cover_bytes") and not is_regen:
                try:
                    cover_bytes = await asyncio.to_thread(
                        generate_disruptive_cover,
                        cached.get("title", "Infraestrutura & Tecnologia"),
                        cached.get("summary", ""),
                    )
                    cached["cover_bytes"] = cover_bytes
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=cover_bytes,
                        caption="🎨 *Capa visual disruptiva gerada* — será anexada ao publicar no LinkedIn.",
                        parse_mode=constants.ParseMode.MARKDOWN,
                    )
                except Exception as img_err:
                    logger.warning(f"[LinkedIn] Falha ao gerar imagem de capa: {img_err}")

            preview_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🚀 Publicar Agora", callback_data=f"li_pub_{cache_id}"),
                    InlineKeyboardButton("🔄 Outro Tom", callback_data=f"li_regen_{cache_id}"),
                ],
                [
                    InlineKeyboardButton("🎨 Nova Imagem", callback_data=f"li_img_{cache_id}"),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f"li_cancel_{cache_id}"),
                ],
            ])

            has_img = "✅ Capa anexada" if cached.get("cover_bytes") else "📝 Somente texto"
            preview_text = (
                f"💼 RASCUNHO LINKEDIN (tom: {angle} · {has_img})\n"
                f"────────────────────────\n\n"
                f"{draft[:3400]}\n\n"
                f"────────────────────────\n"
                f"Revise o texto acima antes de publicar:"
            )
            await status_msg.edit_text(preview_text, reply_markup=preview_keyboard)
        except Exception as e:
            logger.error(f"Erro ao gerar rascunho LinkedIn: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Erro ao gerar rascunho para o LinkedIn: {e}")

    elif data.startswith("li_img_"):
        cache_id = data[len("li_img_"):]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        wait_img = await query.message.reply_text("🎨 *Gerando uma nova capa visual disruptiva...*", parse_mode=constants.ParseMode.MARKDOWN)
        try:
            cover_bytes = await asyncio.to_thread(
                generate_disruptive_cover,
                cached.get("title", "Tecnologia"),
                cached.get("summary", ""),
                "use a completely different visual metaphor, dramatic lighting and angle",
            )
            cached["cover_bytes"] = cover_bytes
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=cover_bytes,
                caption="🎨 *Nova capa atualizada!* Clique em '🚀 Publicar Agora' acima para postar com esta imagem.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            await wait_img.delete()
        except Exception as e:
            await wait_img.edit_text(f"❌ Não foi possível gerar nova imagem: {e}")

    elif data.startswith("li_pub_"):
        cache_id = data[len("li_pub_"):]
        cached = get_cached_video(cache_id)
        if not cached or not cached.get("linkedin_draft"):
            await query.message.reply_text("⚠️ Rascunho expirado. Clique em '💼 Post LinkedIn' novamente.")
            return

        draft = cached["linkedin_draft"]
        cover_bytes = cached.get("cover_bytes")
        await query.message.edit_text("🚀 Publicando post + capa no seu perfil do LinkedIn...")
        ok, result = await asyncio.to_thread(publish_linkedin_post, draft, cover_bytes)
        if ok:
            await query.message.edit_text(
                f"✅ Post publicado no LinkedIn com sucesso!\n\n🔗 {result}"
            )
        else:
            await query.message.edit_text(f"❌ Falha ao publicar no LinkedIn:\n{result}")

    elif data.startswith("li_cancel_"):
        cache_id = data[len("li_cancel_"):]
        cached = get_cached_video(cache_id)
        if cached:
            cached.pop("linkedin_draft", None)
        await query.message.edit_text("❌ Publicação no LinkedIn cancelada.")

    # K) BLOG GITHUB.IO: GERAR ARTIGO + CAPA VISUAL / TROCAR TOM / NOVA IMAGEM / PUBLICAR / CANCELAR
    elif data.startswith("blog_prep_") or data.startswith("blog_regen_"):
        is_regen = data.startswith("blog_regen_")
        cache_id = data[len("blog_regen_"):] if is_regen else data[len("blog_prep_"):]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        angle = cached.get("blog_angle", "executivo")
        if is_regen:
            angle = next_blog_angle(angle)
            status_msg = await query.message.edit_text(
                f"🔄 *Reescrevendo artigo do Blog (tom: {angle})...*",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
        else:
            status_msg = await query.message.reply_text(
                "🌐🎨 *Redigindo artigo e criando capa visual disruptiva para o Blog...*",
                parse_mode=constants.ParseMode.MARKDOWN,
            )

        try:
            art_title, excerpt, body = await asyncio.to_thread(
                generate_blog_article,
                cached.get("title", "Artigo"),
                cached.get("summary", ""),
                cached.get("transcription", ""),
                cached.get("category", "Geral"),
                angle,
            )
            cached["blog_draft"] = {
                "title": art_title,
                "excerpt": excerpt,
                "body": body,
                "category": cached.get("category", "Geral"),
            }
            cached["blog_angle"] = angle

            if not cached.get("cover_bytes") and not is_regen:
                try:
                    cover_bytes = await asyncio.to_thread(
                        generate_disruptive_cover,
                        art_title,
                        cached.get("summary", ""),
                    )
                    cached["cover_bytes"] = cover_bytes
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=cover_bytes,
                        caption="🎨 *Capa visual disruptiva do artigo* — será publicada no topo do post no github.io.",
                        parse_mode=constants.ParseMode.MARKDOWN,
                    )
                except Exception as img_err:
                    logger.warning(f"[Blog] Falha ao gerar imagem de capa: {img_err}")

            preview_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🚀 Publicar no Blog", callback_data=f"blog_pub_{cache_id}"),
                    InlineKeyboardButton("🔄 Outro Tom", callback_data=f"blog_regen_{cache_id}"),
                ],
                [
                    InlineKeyboardButton("🎨 Nova Imagem", callback_data=f"blog_img_{cache_id}"),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f"blog_cancel_{cache_id}"),
                ],
            ])

            has_img = "✅ Capa anexada" if cached.get("cover_bytes") else "📝 Sem imagem"
            preview_text = (
                f"🌐 RASCUNHO DE ARTIGO ({angle} · {has_img})\n"
                f"────────────────────────\n"
                f"Título: {art_title}\n"
                f"Resumo: {excerpt}\n\n"
                f"{body[:2700]}\n"
                f"────────────────────────\n"
                f"Deseja publicar no seu GitHub Pages?"
            )
            await status_msg.edit_text(preview_text, reply_markup=preview_keyboard)
        except Exception as e:
            logger.error(f"Erro ao gerar artigo do blog: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Erro ao gerar artigo para o Blog: {e}")

    elif data.startswith("blog_img_"):
        cache_id = data[len("blog_img_"):]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        wait_img = await query.message.reply_text("🎨 *Gerando uma nova capa visual disruptiva para o Blog...*", parse_mode=constants.ParseMode.MARKDOWN)
        try:
            draft_title = cached.get("blog_draft", {}).get("title") or cached.get("title", "Tecnologia")
            cover_bytes = await asyncio.to_thread(
                generate_disruptive_cover,
                draft_title,
                cached.get("summary", ""),
                "use a completely different visual metaphor, dramatic lighting and angle",
            )
            cached["cover_bytes"] = cover_bytes
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=cover_bytes,
                caption="🎨 *Nova capa atualizada!* Clique em '🚀 Publicar no Blog' acima para postar com esta imagem.",
                parse_mode=constants.ParseMode.MARKDOWN,
            )
            await wait_img.delete()
        except Exception as e:
            await wait_img.edit_text(f"❌ Não foi possível gerar nova imagem: {e}")

    elif data.startswith("blog_pub_"):
        cache_id = data[len("blog_pub_"):]
        cached = get_cached_video(cache_id)
        draft = cached.get("blog_draft") if cached else None
        if not draft:
            await query.message.reply_text("⚠️ Rascunho expirado. Clique em '🌐 Post Blog' novamente.")
            return

        cover_bytes = cached.get("cover_bytes")
        await query.message.edit_text("🚀 Publicando artigo + capa no repositório GitHub Pages...")
        ok, result = await asyncio.to_thread(
            publish_to_github_blog,
            draft["title"],
            draft["excerpt"],
            draft["body"],
            draft["category"],
            cover_bytes,
        )
        if ok:
            await query.message.edit_text(
                f"✅ Artigo publicado no seu Blog!\n\n🔗 {result}\n\n"
                f"(O GitHub Pages leva cerca de 20-40 segundos para atualizar no ar.)"
            )
        else:
            await query.message.edit_text(f"❌ Falha ao publicar no Blog:\n{result}")

    elif data.startswith("blog_cancel_"):
        cache_id = data[len("blog_cancel_"):]
        cached = get_cached_video(cache_id)
        if cached:
            cached.pop("blog_draft", None)
        await query.message.edit_text("❌ Publicação no Blog cancelada.")

    # L) GERAR COMENTÁRIOS DE ENGAJAMENTO PARA A POSTAGEM ORIGINAL
    elif data.startswith("comment_"):
        cache_id = data[len("comment_"):]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        loading_msg = await query.message.reply_text(
            "💭 *Criando 3 opções de comentário para engajar no post original...*",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        try:
            comments_text = await asyncio.to_thread(
                generate_engaging_comments,
                cached.get("title", "Vídeo"),
                cached.get("summary", ""),
                cached.get("transcription", ""),
                cached.get("orig_lang", ""),
            )
            try:
                await loading_msg.edit_text(
                    f"💭 *Sugestões de Comentário (escolha 1 e cole lá):*\n\n{comments_text}",
                    parse_mode=constants.ParseMode.MARKDOWN,
                )
            except Exception:
                await loading_msg.edit_text(
                    f"💭 Sugestões de Comentário (escolha 1 e cole lá):\n\n{comments_text}"
                )
        except Exception as e:
            logger.error(f"Erro ao gerar comentários: {e}", exc_info=True)
            await loading_msg.edit_text(f"❌ Erro ao gerar comentários: {e}")

    # M) ESTUDAR INGLÊS (LINHA A LINHA: INGLÊS EM CIMA + PORTUGUÊS EMBAIXO)
    elif data.startswith("study_"):
        cache_id = data[len("study_"):]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        loading_msg = await query.message.reply_text(
            "🇺🇸 *Montando transcrição bilíngue (Inglês + Português) linha a linha...*",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        try:
            bilingual = await asyncio.to_thread(
                generate_bilingual_study,
                cached.get("transcription", ""),
                cached.get("orig_transcription", ""),
                cached.get("orig_lang", ""),
            )
            header = f"🇺🇸 *Estudo Bilíngue — {cached.get('title', 'Vídeo')[:50]}*\n\n"
            full_text = header + bilingual

            if len(full_text) <= 3800:
                await loading_msg.edit_text(full_text)
            else:
                chunks = []
                curr = ""
                for block in full_text.split("\n\n"):
                    if len(curr) + len(block) + 2 < 3800:
                        curr += block + "\n\n"
                    else:
                        if curr:
                            chunks.append(curr.strip())
                        curr = block + "\n\n"
                if curr:
                    chunks.append(curr.strip())
                await loading_msg.edit_text(chunks[0])
                for c in chunks[1:]:
                    await query.message.reply_text(c)
        except Exception as e:
            logger.error(f"Erro no modo Estudar Inglês: {e}", exc_info=True)
            await loading_msg.edit_text(f"❌ Erro ao gerar estudo bilíngue: {e}")

    # N) PRATICAR TRADUÇÃO (ENVIA TEXTO EM INGLÊS E CORRIGE A TRADUÇÃO DO USUÁRIO)
    elif data.startswith("practice_"):
        cache_id = data[len("practice_"):]
        cached = get_cached_video(cache_id)
        if not cached:
            await query.message.reply_text("⚠️ As informações desse vídeo expiraram do cache.")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        loading_msg = await query.message.reply_text(
            "✍️ *Preparando texto completo em inglês para você praticar...*",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

        try:
            en_text = await asyncio.to_thread(
                get_english_practice_text,
                cached.get("transcription", ""),
                cached.get("orig_transcription", ""),
                cached.get("orig_lang", ""),
            )
            if not en_text:
                await loading_msg.edit_text("❌ Transcrição não disponível para praticar.")
                return

            context.user_data["awaiting_translation"] = {
                "cache_id": cache_id,
                "english_text": en_text,
            }

            msg_text = (
                f"✍️ *MODO PRÁTICA DE TRADUÇÃO*\n\n"
                f"Leia o texto completo em inglês abaixo e *envie agora a sua tradução em português* aqui no chat (pode traduzir tudo ou um trecho):\n\n"
                f"────────────────────────\n"
                f"{en_text[:3200]}\n"
                f"────────────────────────\n"
                f"⏳ _Aguardando sua tradução para corrigir as palavras..._"
            )
            try:
                await loading_msg.edit_text(msg_text, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception:
                await loading_msg.edit_text(msg_text)
        except Exception as e:
            logger.error(f"Erro no modo Praticar Tradução: {e}", exc_info=True)
            await loading_msg.edit_text(f"❌ Erro ao iniciar prática de tradução: {e}")

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens de voz ou áudio gravadas diretamente no Telegram com Deepgram Nova-3."""
    if not update.message:
        return

    if not await check_user_allowed(update):
        await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=constants.ChatAction.TYPING,
    )

    status_msg = await update.message.reply_text("⚡ *Transcrevendo áudio com Deepgram Nova-3 e Diarização...*")

    tmp_path = None
    try:
        tg_file = await context.bot.get_file(voice.file_id)
        tmp_path = f"voice_{uuid.uuid4().hex[:8]}.ogg"
        await tg_file.download_to_drive(tmp_path)

        from services.transcriber import transcribe_with_deepgram
        plain, diarized, orig_lang = await asyncio.to_thread(transcribe_with_deepgram, tmp_path, True)

        if not plain:
            await status_msg.edit_text("❌ Não foi possível transcrever o áudio ou nenhuma fala foi detectada.")
            return

        user_id = update.effective_user.id
        title = f"Nota de Voz ({datetime.now().strftime('%d/%m %H:%M')})"
        category = "Nota de Voz"
        platform = "Telegram Áudio"

        # Salva no banco de dados
        save_video(
            user_id=user_id,
            title=title,
            category=category,
            platform=platform,
            url="",
            summary=diarized,
            transcription=diarized,
        )

        cache_id = str(uuid.uuid4())[:8]
        set_cached_video(cache_id, {
            "summary": diarized,
            "transcription": diarized,
            "url": "",
            "platform": platform,
            "category": category,
            "title": title,
            "orig_lang": orig_lang,
            "time": time.time(),
        })

        keyboard = [
            [
                InlineKeyboardButton("💡 Ideias de Post", callback_data=f"idea_{cache_id}"),
                InlineKeyboardButton("⚖️ Auditoria Crítica", callback_data=f"critique_{cache_id}"),
            ],
            [
                InlineKeyboardButton("💾 Notion", callback_data=f"notion_{cache_id}"),
                InlineKeyboardButton("📓 Obsidian", callback_data=f"obsidian_{cache_id}"),
            ],
            [
                InlineKeyboardButton("💼 Post LinkedIn", callback_data=f"li_prep_{cache_id}"),
                InlineKeyboardButton("🌐 Post Blog", callback_data=f"blog_prep_{cache_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        resp = f"🎙️ *TRANSCRIÇÃO DE VOZ (Deepgram Nova-3)*\n\n{diarized}"
        if len(resp) <= 4000:
            try:
                await status_msg.edit_text(resp, parse_mode=constants.ParseMode.MARKDOWN, reply_markup=reply_markup)
            except Exception:
                await status_msg.edit_text(resp, reply_markup=reply_markup)
        else:
            await status_msg.edit_text(resp[:3900], reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao processar voz no Telegram: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Erro ao transcrever mensagem de voz: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

async def setup_commands(application):
    """Configura o menu oficial de comandos e as sugestões automáticas ao digitar '/' no Telegram."""
    commands = [
        BotCommand("start", "Ver instruções e lentes de extração"),
        BotCommand("obsidian", "Notas recentes e conexões [[Wikilinks]]"),
        BotCommand("buscar", "Pesquisar assuntos e ferramentas no cofre"),
        BotCommand("consultar", "Perguntar à IA cruzando seu Segundo Cérebro"),
        BotCommand("salvos", "Biblioteca de vídeos processados"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Menu de comandos registrado com sucesso no Telegram!")
    except Exception as e:
        logger.warning(f"Aviso ao registrar comandos no Telegram: {e}")

def main():
    try:
        config.validate_config()
    except ValueError as e:
        print(f"\n[ERRO DE CONFIGURAÇÃO]\n{e}\n")
        return

    print("Iniciando o Bot Universal de Resumos...")
    threading.Thread(target=start_health_server, daemon=True).start()
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(setup_commands).build()

    # Comandos principais
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("salvos", salvos_command))
    app.add_handler(CommandHandler("biblioteca", salvos_command))

    # Segundo Cérebro & Obsidian
    app.add_handler(CommandHandler("obsidian", obsidian_command))
    app.add_handler(CommandHandler("notas", obsidian_command))
    app.add_handler(CommandHandler("buscar", buscar_command))
    app.add_handler(CommandHandler("pesquisar", buscar_command))
    app.add_handler(CommandHandler("consultar", consultar_command))
    app.add_handler(CommandHandler("cerebro", consultar_command))
    app.add_handler(CommandHandler("perguntar", consultar_command))

    # Mensagens de texto, áudios de voz e callbacks
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print("Bot em execução!")
    app.run_polling()

if __name__ == "__main__":
    main()
