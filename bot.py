import os
import io
import logging
import base64
import httpx
from openai import OpenAI
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

STYLE_KEY = "poster_style"

STYLES = {
    "cinematic": (
        "cinematic movie poster, dramatic lighting, epic composition, "
        "photorealistic, Hollywood blockbuster style, 8K quality"
    ),
    "anime": (
        "anime movie poster style, vibrant colors, Studio Ghibli or Makoto Shinkai aesthetic, "
        "hand-drawn look, beautiful detailed illustration"
    ),
    "enhance": (
        "ultra high-resolution enhanced version, crystal clear details, "
        "professional photography, studio lighting, stunning realism"
    ),
    "removebg": (
        "subject isolated on a clean white background, no background, "
        "product photography style, sharp edges, professional cutout"
    ),
}


async def download_telegram_image(tg_file) -> bytes:
    async with httpx.AsyncClient() as client:
        resp = await client.get(tg_file.file_path)
        resp.raise_for_status()
        return resp.content


async def generate_poster(image_bytes: bytes, style_prompt: str) -> bytes:
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    vision_resp = openai_client.chat.completions.create(
        model="gpt-4o",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Describe the main subject and scene in this image in vivid detail "
                            f"for use as a reference in generating a styled poster. "
                            f"Target style: '{style_prompt}'"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
    )

    scene = vision_resp.choices[0].message.content
    logger.info("Scene description: %s", scene)

    poster_prompt = (
        f"{style_prompt}. Scene: {scene}. "
        "Professional composition, visually stunning, high contrast, masterpiece quality."
    )

    image_resp = openai_client.images.generate(
        model="dall-e-3",
        prompt=poster_prompt,
        size="1024x1792",
        quality="standard",
        n=1,
        response_format="b64_json",
    )

    return base64.standard_b64decode(image_resp.data[0].b64_json)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(STYLE_KEY, None)
    await update.message.reply_text(
        "Bio Fundz Bot is online 🚀\n\n"
        "Send me a photo (with an optional caption) and I'll generate a cinematic AI poster.\n\n"
        "Or pick a style first with /cinematic, /anime, /enhance, or /removebg — "
        "then send your photo!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📋 *Available Commands*\n\n"
        "/start — Welcome message & reset style\n"
        "/help — Show this help message\n"
        "/about — About Bio Fundz Bot\n"
        "/cinematic — Set style: Hollywood movie poster 🎬\n"
        "/anime — Set style: Anime illustration 🌸\n"
        "/enhance — Set style: Ultra-HD enhancement ✨\n"
        "/removebg — Set style: Clean white background 🪄\n\n"
        "After picking a style, send any photo to generate your poster!",
        parse_mode="Markdown",
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *Bio Fundz Bot*\n\n"
        "Transform your photos into stunning AI-generated posters using "
        "GPT-4o vision and DALL-E 3.\n\n"
        "Choose a style, send a photo, get your masterpiece. 🎨",
        parse_mode="Markdown",
    )


async def set_style(update: Update, context: ContextTypes.DEFAULT_TYPE, style_name: str) -> None:
    context.user_data[STYLE_KEY] = style_name
    labels = {
        "cinematic": "🎬 Cinematic movie poster",
        "anime": "🌸 Anime illustration",
        "enhance": "✨ Ultra-HD enhancement",
        "removebg": "🪄 White background cutout",
    }
    await update.message.reply_text(
        f"{labels[style_name]} style selected!\n\nNow send me a photo to generate your poster."
    )


async def cinematic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style(update, context, "cinematic")


async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style(update, context, "anime")


async def enhance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style(update, context, "enhance")


async def removebg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style(update, context, "removebg")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    style_name = context.user_data.get(STYLE_KEY)

    if style_name and style_name in STYLES:
        style_prompt = STYLES[style_name]
        style_label = style_name
    elif update.message.caption:
        style_prompt = update.message.caption
        style_label = update.message.caption
    else:
        style_prompt = STYLES["cinematic"]
        style_label = "cinematic"

    await update.message.reply_text("🎨 Generating your AI poster… this takes ~15 seconds.")

    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = await download_telegram_image(tg_file)

    try:
        poster_bytes = await generate_poster(image_bytes, style_prompt)
    except Exception as e:
        logger.error("Poster generation failed: %s", e)
        await update.message.reply_text(
            "❌ Something went wrong generating your poster. Please try again."
        )
        return

    context.user_data.pop(STYLE_KEY, None)

    await update.message.reply_photo(
        photo=io.BytesIO(poster_bytes),
        caption=f"🎨 Style: {style_label}\n\nSend another photo or pick a new style!",
    )


async def post_init(app) -> None:
    await app.bot.set_my_commands([
        BotCommand("start",    "Welcome & reset style"),
        BotCommand("help",     "Show all commands"),
        BotCommand("about",    "About this bot"),
        BotCommand("cinematic","🎬 Hollywood movie poster style"),
        BotCommand("anime",    "🌸 Anime illustration style"),
        BotCommand("enhance",  "✨ Ultra-HD enhancement style"),
        BotCommand("removebg", "🪄 White background cutout style"),
    ])
    logger.info("Bot commands registered with Telegram")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    app = ApplicationBuilder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("help",      help_command))
    app.add_handler(CommandHandler("about",     about))
    app.add_handler(CommandHandler("cinematic", cinematic))
    app.add_handler(CommandHandler("anime",     anime))
    app.add_handler(CommandHandler("enhance",   enhance))
    app.add_handler(CommandHandler("removebg",  removebg))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("Bio Fundz Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
