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
    get_youtube_transcript,
    download_video,
    cleanup_media,
)
from services.summarizer import (
    analyze_and_summarize_video,
    summarize_text_transcript,
    generate_content_ideas,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Cache em memória para guardar transcrição e resumo dos vídeos recentes (para os botões interativos)
# Estrutura: {cache_id: {"summary": str, "transcription": str, "url": str, "platform": str, "time": float}}
VIDEO_CACHE = {}

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
        "🤖 *Olá! Eu sou o seu Assistente Universal de Resumos.*\n\n"
        "Agora eu suporto as principais plataformas de vídeo curto:\n"
        "• 📸 *Instagram:* Reels e posts em vídeo\n"
        "• 🎵 *TikTok:* Vídeos e links compartilhados\n"
        "• ▶️ *YouTube:* Shorts e vídeos curtos\n"
        "• 🐦 *Twitter / X:* Vídeos de postagens\n\n"
        "Basta compartilhar o vídeo direto para este chat ou colar o link aqui!\n"
        "Você receberá o resumo completo com opções interativas para ver a transcrição ou transformar o vídeo em ideias de posts."
    )
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens procurando links de vídeos suportados."""
    if not update.message or not update.message.text:
        return

    if not await check_user_allowed(update):
        await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
        return

    user_text = update.message.text.strip()
    extracted = extract_video_url(user_text)

    if not extracted:
        await update.message.reply_text(
            "💡 Envie um link válido de vídeo do *Instagram*, *TikTok*, *YouTube Shorts* ou *Twitter/X* para eu resumir!",
            parse_mode=constants.ParseMode.MARKDOWN,
        )
        return

    video_url, platform = extracted
    clean_expired_cache()

    status_msg = await update.message.reply_text(
        f"⏳ *Vídeo do {platform} detectado!*\nBaixando mídia e gerando inteligência com IA...",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    local_path = None
    summary = None
    transcription = None

    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        # Se for YouTube, tenta obter a transcrição oficial primeiro (imune a checagens de bot e instantâneo)
        if platform == "YouTube":
            yt_id = get_youtube_video_id(video_url)
            if yt_id:
                transcript_text = await asyncio.to_thread(get_youtube_transcript, yt_id)
                if transcript_text:
                    logger.info(f"Transcrição do YouTube obtida para {yt_id} ({len(transcript_text)} caracteres)")
                    summary = await asyncio.to_thread(summarize_text_transcript, transcript_text)
                    transcription = transcript_text

        # Caso não seja YouTube ou o vídeo não tenha legendas/transcrição disponíveis
        if not summary:
            # 1. Download da mídia (áudio/vídeo)
            local_path = await asyncio.to_thread(download_video, video_url)

            # 2. Resumo e Transcrição com Gemini multimodal
            summary, transcription = await asyncio.to_thread(analyze_and_summarize_video, local_path)

        # 3. Guarda no cache para botões interativos
        cache_id = str(uuid.uuid4())[:8]
        VIDEO_CACHE[cache_id] = {
            "summary": summary,
            "transcription": transcription,
            "url": video_url,
            "platform": platform,
            "time": time.time(),
        }

        # 4. Cria teclado com botões interativos
        keyboard = [
            [
                InlineKeyboardButton("📝 Ver Transcrição", callback_data=f"tx_{cache_id}"),
                InlineKeyboardButton("💡 Criar Ideias de Post", callback_data=f"idea_{cache_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 5. Monta mensagem final
        response_text = f"{summary}\n\n🔗 [{platform} Original]({video_url})"

        try:
            await status_msg.edit_text(
                response_text,
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        except Exception:
            await status_msg.edit_text(response_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao processar {platform} ({video_url}): {e}", exc_info=True)
        error_msg = (
            f"❌ *Não foi possível processar este vídeo do {platform}.*\n\n"
            "Possíveis motivos:\n"
            "• O perfil ou vídeo é privado/restrito.\n"
            "• A plataforma bloqueou temporariamente o acesso do servidor.\n"
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

        # Se for muito longa, corta respeitando o limite do Telegram de 4096 caracteres
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
            logger.error(f"Erro ao gerar ideias de post: {e}")
            await loading_msg.edit_text(f"❌ Erro ao gerar ideias: {e}")

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
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print("Bot em execução!")
    app.run_polling()

if __name__ == "__main__":
    main()
