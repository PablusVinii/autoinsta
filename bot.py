import asyncio
import logging
from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import config
from services.downloader import extract_instagram_url, download_reel, cleanup_media
from services.summarizer import summarize_reel_video

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Servidor HTTP simples para atender aos health checks de plataformas de nuvem (Render, Koyeb, etc.)."""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot Telegram Reels Online")

    def log_message(self, format, *args):
        # Silencia logs de requisições de ping para manter o console limpo
        return

def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Health check HTTP ativo na porta {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Nao foi possivel iniciar servidor de health check: {e}")

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
        "🤖 *Olá! Eu sou o seu assistente de Reels com IA.*\n\n"
        "Sempre que você estiver no Instagram e quiser resumir um Reel:\n"
        "1. Toque no ícone de *Compartilhar* (o aviãozinho de papel ✈️) no Reel.\n"
        "2. Escolha o *Telegram* e selecione este bot.\n"
        "3. Ou simplesmente cole o link do Reel aqui!\n\n"
        "Vou analisar tanto o que é falado quanto o texto na tela e gerar um resumo estruturado para você em instantes."
    )
    await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa mensagens recebidas procurando links do Instagram."""
    if not update.message or not update.message.text:
        return

    if not await check_user_allowed(update):
        await update.message.reply_text("⛔ Acesso não autorizado a este bot.")
        return

    user_text = update.message.text.strip()
    reel_url = extract_instagram_url(user_text)

    if not reel_url:
        await update.message.reply_text(
            "💡 Por favor, envie ou compartilhe um link válido de um Reel do Instagram (ex: https://www.instagram.com/reel/XYZ/)."
        )
        return

    status_msg = await update.message.reply_text(
        "⏳ *Reel recebido!* Baixando vídeo e analisando conteúdo com IA... Aguarde alguns instantes.",
        parse_mode=constants.ParseMode.MARKDOWN,
    )

    local_path = None
    try:
        # Envia ação de "digitando"
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        # 1. Download do vídeo (em thread assíncrona para não travar o bot)
        local_path = await asyncio.to_thread(download_reel, reel_url)

        # 2. Resumo com Gemini (áudio + visual)
        summary = await asyncio.to_thread(summarize_reel_video, local_path)

        # 3. Monta a resposta final
        response_text = f"{summary}\n\n🔗 [Ver Reel Original]({reel_url})"

        try:
            await status_msg.edit_text(response_text, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            # Fallback caso haja conflito de caracteres Markdown do Gemini
            await status_msg.edit_text(response_text)

    except Exception as e:
        logger.error(f"Erro ao processar Reel {reel_url}: {e}", exc_info=True)
        error_msg = (
            "❌ *Não foi possível gerar o resumo deste Reel.*\n\n"
            "Possíveis motivos:\n"
            "• O perfil do autor é privado.\n"
            "• O Instagram bloqueou temporariamente o download deste vídeo.\n"
            f"• Detalhes do erro: `{str(e)[:150]}`"
        )
        await status_msg.edit_text(error_msg, parse_mode=constants.ParseMode.MARKDOWN)

    finally:
        # 4. Limpa o arquivo temporário local
        if local_path:
            await asyncio.to_thread(cleanup_media, local_path)

def main():
    try:
        config.validate_config()
    except ValueError as e:
        print(f"\n[ERRO DE CONFIGURAÇÃO]\n{e}\n")
        print("Preencha o arquivo .env conforme o .env.example e reinicie o bot.\n")
        return

    print("Iniciando o Bot do Telegram para Resumo de Reels...")
    threading.Thread(target=start_health_server, daemon=True).start()
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot em execução! Pressione Ctrl+C para encerrar.")
    app.run_polling()

if __name__ == "__main__":
    main()
