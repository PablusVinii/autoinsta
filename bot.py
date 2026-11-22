import asyncio
import logging
import os
import threading
import uuid
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import (
    Update,
    constants,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
    analyze_youtube_url_direct,
    analyze_and_summarize_video,
    generate_content_ideas,
    answer_video_question,
)
from services.notion import save_to_notion, categorize_content
from services.database import save_video, get_user_videos

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Cache de dados de vídeos recentes para os botões e conversação
# {cache_id: {"summary": str, "transcription": str, "url": str, "platform": str, "time": float, "category": str, "title": str}}
VIDEO_CACHE = {}

# Mapeia o ID da mensagem do resumo enviada pelo bot para o respectivo cache_id
# {message_id: cache_id}
MESSAGE_CACHE_MAP = {}

def clean_expired_cache():
    """Remove entradas com mais de 24 horas para economizar memória."""
    now = time.time()
    expired = [k for k, v in VIDEO_CACHE.items() if now - v.get("time", 0) > 86400]
    for k in expired:
        VIDEO_CACHE.pop(k, None)

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
        "🤖 *Olá! Eu sou o seu Assistente de Vídeos & Segundo Cérebro.*\n\n"
        "Suporto as principais redes de vídeo:\n"
        "• 📸 *Instagram:* Reels e vídeos do feed\n"
        "• ▶️ *YouTube:* Shorts e vídeos completos\n"
        "• 🎵 *TikTok:* Vídeos e links compartilhados\n"
        "• 🐦 *Twitter / X:* Posts com vídeo\n\n"
        "✨ *Super Poderes Ativos:*\n"
        "1. *Resumo Inteligente:* Envie qualquer link de vídeo para receber o resumo e takeaways.\n"
        "2. *Converse com o Vídeo:* Responda (dê 'Reply') a qualquer resumo fazendo uma pergunta sobre o vídeo!\n"
        "3. *Segundo Cérebro:* Salve no Notion com 1 clique ou consulte sua biblioteca digitando /salvos."
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

    lines.append("💡 *Dica:* Clique em *Salvar no Notion* em qualquer resumo para sincronizar com seu espaço de trabalho!")
    await update.message.reply_text("\n".join(lines), parse_mode=constants.ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens recebidas (links de vídeos ou perguntas de Q&A sobre um resumo)."""
    if not update.message or not update.message.text:
        return

    if not await check_user_allowed(update):
        await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
        return

    user_text = update.message.text.strip()

    # 1. VERIFICAÇÃO DE "CONVERSE COM O VÍDEO" (Q&A):
    # Se o usuário respondeu (reply) a uma mensagem de resumo anterior
    if update.message.reply_to_message:
        replied_msg_id = update.message.reply_to_message.message_id
        cache_id = MESSAGE_CACHE_MAP.get(replied_msg_id)

        if cache_id and cache_id in VIDEO_CACHE:
            video_data = VIDEO_CACHE[cache_id]
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
    if not extracted:
        await update.message.reply_text(
            "💡 Envie um link válido de vídeo (*Instagram, TikTok, YouTube, X*)\n"
            "Ou responda (dê 'Reply') a um resumo anterior para fazer perguntas sobre ele!",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    video_url, platform = extracted
    clean_expired_cache()

    status_msg = await update.message.reply_text(
        f"⏳ *Vídeo do {platform} detectado!*\nProcessando conteúdo e gerando inteligência com IA...",
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

        # Para YouTube, usa integração nativa do Gemini (imune a bloqueios de data center)
        if platform == "YouTube":
            yt_id = get_youtube_video_id(video_url)
            clean_yt_url = f"https://www.youtube.com/watch?v={yt_id}" if yt_id else video_url
            logger.info(f"Processando YouTube via Gemini: {clean_yt_url}")
            summary, transcription = await asyncio.to_thread(analyze_youtube_url_direct, clean_yt_url)

        # Para Instagram, TikTok e Twitter/X, baixa o arquivo de mídia
        if not summary:
            local_path = await asyncio.to_thread(download_video, video_url)
            summary, transcription = await asyncio.to_thread(analyze_and_summarize_video, local_path)

        # Categoriza o conteúdo com IA
        category = await asyncio.to_thread(categorize_content, summary)

        # Extrai título inicial do resumo
        title_line = "Vídeo"
        for line in summary.split("\n"):
            if "TÍTULO" in line or "TEMA" in line:
                continue
            if line.strip():
                title_line = line.replace("*", "").strip()[:80]
                break

        # Salva na base interna permanente
        user_id = update.effective_user.id
        save_video(user_id, title_line, category, platform, video_url, summary)

        # Guarda no cache em memória
        cache_id = str(uuid.uuid4())[:8]
        VIDEO_CACHE[cache_id] = {
            "summary": summary,
            "transcription": transcription,
            "url": video_url,
            "platform": platform,
            "category": category,
            "title": title_line,
            "time": time.time(),
        }

        # Cria botões interativos
        keyboard = [
            [
                InlineKeyboardButton("📝 Ver Transcrição", callback_data=f"tx_{cache_id}"),
                InlineKeyboardButton("💡 Ideias de Post", callback_data=f"idea_{cache_id}"),
            ],
            [
                InlineKeyboardButton("💬 Tirar Dúvida", callback_data=f"qa_{cache_id}"),
                InlineKeyboardButton("💾 Salvar no Notion", callback_data=f"notion_{cache_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        response_text = f"🏷️ *Categoria:* `#{category}`\n\n{summary}\n\n🔗 [{platform} Original]({video_url})"

        sent_msg = None
        try:
            sent_msg = await status_msg.edit_text(
                response_text,
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        except Exception:
            sent_msg = await status_msg.edit_text(response_text, reply_markup=reply_markup)

        # Registra o message_id para suportar Q&A com "Reply"
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

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com os cliques nos botões interativos abaixo do resumo."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()
    data = query.data

    if data.startswith("tx_"):
        cache_id = data[3:]
        cached = VIDEO_CACHE.get(cache_id)
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

    elif data.startswith("idea_"):
        cache_id = data[5:]
        cached = VIDEO_CACHE.get(cache_id)
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

    elif data.startswith("qa_"):
        cache_id = data[3:]
        await query.message.reply_text(
            "💬 *Como tirar dúvidas sobre este vídeo:*\n\n"
            "Basta clicar em **Responder (Reply)** na mensagem do resumo acima e digitar sua pergunta!\n\n"
            "Exemplos:\n"
            "• _Qual ferramenta ele mencionou?_\n"
            "• _Explique o passo 2 em mais detalhes._\n"
            "• _Como aplico isso no meu trabalho?_",
            parse_mode=constants.ParseMode.MARKDOWN,
        )

    elif data.startswith("notion_"):
        cache_id = data[7:]
        cached = VIDEO_CACHE.get(cache_id)
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

def main():
    try:
        config.validate_config()
    except ValueError as e:
        print(f"\n[ERRO DE CONFIGURAÇÃO]\n{e}\n")
        return

    print("Iniciando o Bot Universal de Resumos...")
    threading.Thread(target=start_health_server, daemon=True).start()
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("salvos", salvos_command))
    app.add_handler(CommandHandler("biblioteca", salvos_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print("Bot em execução!")
    app.run_polling()

if __name__ == "__main__":
    main()
