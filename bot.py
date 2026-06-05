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
        "cinematic Hollywood-style movie poster, dramatic professional lighting, "
        "epic wide-angle composition, photorealistic, blockbuster film aesthetic, "
        "rich color grading, lens flare, depth of field, 8K quality"
    ),
    "anime": (
        "anime and manga-inspired artwork, vibrant saturated colors, "
        "Studio Ghibli or Makoto Shinkai aesthetic, expressive hand-drawn illustration style, "
        "clean linework, beautiful detailed cel-shading, dynamic composition"
    ),
    "enhance": (
        "ultra high-resolution HD upscaled version, enhanced facial features and skin detail, "
        "professional studio lighting correction, noise reduction, sharper crisp details, "
        "color vibrancy boost, photorealistic remaster quality"
    ),
    "removebg": (
        "subject isolated cleanly with a pure white background, all original background completely removed, "
        "sharp precise edges around subject, professional product photography cutout style, "
        "no shadows or artifacts from original background"
    ),
}

STYLE_LABELS = {
    "cinematic": "🎬 Cinematic Hollywood Poster",
    "anime":     "🌸 Anime / Manga Art",
    "enhance":   "✨ HD Enhanced",
    "removebg":  "🪄 Background Removed",
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
                            f"for use as a reference in generating a styled image. "
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

    full_prompt = (
        f"{style_prompt}. "
        f"Scene reference: {scene}. "
        "Professional composition, visually stunning, masterpiece quality."
    )

    image_resp = openai_client.images.generate(
        model="dall-e-3",
        prompt=full_prompt,
        size="1024x1792",
        quality="standard",
        n=1,
        response_format="b64_json",
    )

    return base64.standard_b64decode(image_resp.data[0].b64_json)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(STYLE_KEY, None)
    await update.message.reply_text(
        "🚀 *Welcome to Bio Fundz Bot!*\n\n"
        "I transform your photos into stunning AI-generated artwork using "
        "GPT-4o vision and DALL-E 3.\n\n"
        "*What I can do:*\n"
        "🎬 /cinematic — Hollywood-style movie posters\n"
        "🌸 /anime — Anime & manga-inspired artwork\n"
        "✨ /enhance — HD upscale & quality enhancement\n"
        "🪄 /removebg — Remove image backgrounds\n\n"
        "Pick a style, send me a photo, and I'll create your masterpiece!\n"
        "You can also send a photo with a custom caption for a personalized style.",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Bio Fundz Bot — Commands*\n\n"
        "/start — Welcome message & reset selected style\n"
        "/help — Show all commands with explanations\n"
        "/about — About Bio Fundz Bot\n\n"
        "*AI Editing Styles:*\n"
        "/cinematic — 🎬 Transform photos into cinematic Hollywood-style movie posters\n"
        "/anime — 🌸 Convert photos into anime or manga-inspired artwork\n"
        "/enhance — ✨ HD upscaling, face enhancement & lighting correction\n"
        "/removebg — 🪄 Remove image background, return clean white version\n\n"
        "*How to use:*\n"
        "1️⃣ Choose a style with one of the commands above\n"
        "2️⃣ Send any photo\n"
        "3️⃣ Receive your AI-generated result 🎨\n\n"
        "_Tip: Send a photo with a caption to use your own custom style!_",
        parse_mode="Markdown",
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌍 *About Bio Fundz Bot*\n\n"
        "Bio Fundz Bot is an AI-powered image transformation tool built to help "
        "creators, brands, and individuals turn everyday photos into professional-grade artwork.\n\n"
        "*Mission:*\n"
        "Make advanced AI image generation accessible to everyone — no design skills required.\n\n"
        "*Powered by:*\n"
        "• GPT-4o Vision — understands your photos\n"
        "• DALL-E 3 — generates stunning AI artwork\n\n"
        "Created with ❤️ by Bio Fundz.",
        parse_mode="Markdown",
    )


async def set_style_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, style_name: str
) -> None:
    context.user_data[STYLE_KEY] = style_name
    messages = {
        "cinematic": (
            "🎬 *Cinematic Mode activated!*\n\n"
            "I'll transform your photo into a Hollywood-style movie poster.\n"
            "You can add a caption with your custom prompt, or just send the photo!"
        ),
        "anime": (
            "🌸 *Anime Mode activated!*\n\n"
            "I'll convert your photo into anime or manga-inspired artwork.\n"
            "Send me any photo to get started!"
        ),
        "enhance": (
            "✨ *Enhance Mode activated!*\n\n"
            "I'll apply HD upscaling, face enhancement, lighting correction, "
            "and sharper details to your photo.\n"
            "Send me any photo to enhance it!"
        ),
        "removebg": (
            "🪄 *Remove Background Mode activated!*\n\n"
            "I'll automatically remove the background from your image "
            "and return a clean white background version.\n"
            "Send me any photo to process it!"
        ),
    }
    await update.message.reply_text(messages[style_name], parse_mode="Markdown")


async def cinematic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style_handler(update, context, "cinematic")


async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style_handler(update, context, "anime")


async def enhance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style_handler(update, context, "enhance")


async def removebg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await set_style_handler(update, context, "removebg")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    style_name = context.user_data.get(STYLE_KEY)

    if style_name and style_name in STYLES:
        style_prompt = STYLES[style_name]
        style_label = STYLE_LABELS[style_name]
    elif update.message.caption:
        style_prompt = (
            f"{update.message.caption}, cinematic composition, "
            "professional quality, visually stunning, high detail"
        )
        style_label = f'Custom: "{update.message.caption}"'
    else:
        style_prompt = STYLES["cinematic"]
        style_label = STYLE_LABELS["cinematic"]

    await update.message.reply_text(
        "🎨 Generating your AI image… this takes ~15 seconds. Please wait!"
    )

    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = await download_telegram_image(tg_file)

    try:
        poster_bytes = await generate_poster(image_bytes, style_prompt)
    except Exception as e:
        logger.error("Image generation failed: %s", e)
        await update.message.reply_text(
            "❌ Something went wrong generating your image. Please try again.\n"
            "If the problem persists, try a different style or photo."
        )
        return

    context.user_data.pop(STYLE_KEY, None)

    await update.message.reply_photo(
        photo=io.BytesIO(poster_bytes),
        caption=(
            f"✅ *Done!* Style: {style_label}\n\n"
            "Send another photo or pick a new style with /cinematic, /anime, /enhance, or /removebg"
        ),
        parse_mode="Markdown",
    )


async def post_init(app) -> None:
    await app.bot.set_my_commands([
        BotCommand("start",     "🚀 Welcome to Bio Fundz Bot & reset style"),
        BotCommand("help",      "📖 Show all commands & how to use the bot"),
        BotCommand("about",     "🌍 About Bio Fundz Bot, mission & creator"),
        BotCommand("cinematic", "🎬 Hollywood movie poster from your photo"),
        BotCommand("anime",     "🌸 Anime & manga artwork from your photo"),
        BotCommand("enhance",   "✨ HD upscale, face & lighting enhancement"),
        BotCommand("removebg",  "🪄 Remove background, clean white version"),
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
