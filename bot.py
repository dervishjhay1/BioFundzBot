import os
import io
import logging
import requests

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.environ.get("HUGGINGFACE_API_KEY")

STYLE_PROMPTS = {
    "cinematic": "cinematic hollywood movie poster style",
    "anime": "anime manga style artwork",
    "enhance": "ultra realistic hd enhancement",
    "removebg": "white clean background"
}


# =========================
# START COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🚀 Welcome to Biodun Fundz Bot\n\n"
        "Available Commands:\n"
        "/cinematic\n"
        "/anime\n"
        "/enhance\n"
        "/removebg\n\n"
        "Send a photo after choosing a style."
    )

    await update.message.reply_text(text)


# =========================
# STYLE COMMANDS
# =========================
async def cinematic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["style"] = "cinematic"
    await update.message.reply_text(
        "🎬 Cinematic mode activated.\nNow send your photo."
    )


async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["style"] = "anime"
    await update.message.reply_text(
        "🌸 Anime mode activated.\nNow send your photo."
    )


async def enhance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["style"] = "enhance"
    await update.message.reply_text(
        "✨ Enhance mode activated.\nNow send your photo."
    )


async def removebg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["style"] = "removebg"
    await update.message.reply_text(
        "🪄 Remove background mode activated.\nNow send your photo."
    )


# =========================
# IMAGE GENERATION
# =========================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    style = context.user_data.get("style")

    if not style:
        await update.message.reply_text(
            "Please choose a style first.\nExample: /anime"
        )
        return

    await update.message.reply_text("🎨 Processing image...")

    photo = update.message.photo[-1]

    file = await context.bot.get_file(photo.file_id)

    image_bytes = await file.download_as_bytearray()

    prompt = STYLE_PROMPTS.get(style)

    try:

        response = requests.post(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
            headers={
                "Authorization": f"Bearer {HF_TOKEN}"
            },
            json={
                "inputs": prompt
            },
            timeout=120
        )

        if response.status_code != 200:
            await update.message.reply_text(
                f"❌ Error from HuggingFace:\n{response.text}"
            )
            return

        image = response.content

        await update.message.reply_photo(
            photo=io.BytesIO(image),
            caption=f"✅ {style.capitalize()} image generated!"
        )

    except Exception as e:
        logger.error(str(e))

        await update.message.reply_text(
            f"❌ Error:\n{str(e)}"
        )


# =========================
# MAIN
# =========================
def main():

    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN missing")

    if not HF_TOKEN:
        raise ValueError("HUGGINGFACE_API_KEY missing")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cinematic", cinematic))
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("enhance", enhance))
    app.add_handler(CommandHandler("removebg", removebg))

    app.add_handler(
        MessageHandler(filters.PHOTO, handle_photo)
    )

    logger.info("Bot started...")

    app.run_polling()


if __name__ == "__main__":
    main()