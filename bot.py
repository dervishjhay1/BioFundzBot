import os
import io
import logging
import base64
import httpx
from openai import OpenAI
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ── user_data keys ──────────────────────────────────────────────────────────
STYLE_KEY         = "style"
FLOW_KEY          = "flow"          # "prompt_first" | "image_first"
WAITING_PROMPT    = "waiting_prompt"
WAITING_IMAGE     = "waiting_image"
STORED_PHOTO_ID   = "stored_photo_id"
CUSTOM_PROMPT_KEY = "custom_prompt"

# ── style prompts ────────────────────────────────────────────────────────────
STYLE_BASE = {
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

PROMPT_HINTS = {
    "anime":    "anime style prompt _(e.g. 'Naruto cinematic style', 'Studio Ghibli forest scene')_",
    "enhance":  "enhancement direction _(e.g. 'sharp face detail, golden hour lighting')_",
    "removebg": "background replacement _(e.g. 'futuristic city', 'white studio background')_",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def feedback_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👍 Great!", callback_data="feedback_up"),
        InlineKeyboardButton("👎 Not good", callback_data="feedback_down"),
    ]])


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
        messages=[{
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
        }],
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


async def send_result(update_or_message, image_bytes: bytes, style_label: str) -> None:
    msg = update_or_message if hasattr(update_or_message, "reply_photo") else update_or_message.message
    await msg.reply_photo(
        photo=io.BytesIO(image_bytes),
        caption=(
            f"✅ *Done!* Style: {style_label}\n\n"
            "How did I do? Rate your result below!\n"
            "Try another: /cinematic | /anime | /enhance | /removebg"
        ),
        parse_mode="Markdown",
        reply_markup=feedback_keyboard(),
    )


# ── commands ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
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
        "/cinematic — 🎬 Describe your vision → send photo → get poster\n"
        "/anime — 🌸 Send photo → describe style → get anime art\n"
        "/enhance — ✨ Send photo → describe enhancement → get HD result\n"
        "/removebg — 🪄 Send photo → describe new bg → get clean cutout\n\n"
        "_Tip: Send a photo with a caption at any time for a quick custom style!_",
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


async def cinematic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt-first flow: ask for prompt → then photo."""
    context.user_data.clear()
    context.user_data[STYLE_KEY] = "cinematic"
    context.user_data[FLOW_KEY] = "prompt_first"
    context.user_data[WAITING_PROMPT] = True
    await update.message.reply_text(
        "🎬 *Cinematic Mode activated!*\n\n"
        "What's your cinematic vision? Describe the style or mood you want:\n"
        "_(e.g. 'dark noir thriller', 'epic sci-fi adventure', 'romantic golden sunset')_\n\n"
        "Type your prompt 👇",
        parse_mode="Markdown",
    )


async def _image_first_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, style: str
) -> None:
    """Image-first flow: ask for photo → then prompt."""
    context.user_data.clear()
    context.user_data[STYLE_KEY] = style
    context.user_data[FLOW_KEY] = "image_first"
    context.user_data[WAITING_IMAGE] = True
    labels = {
        "anime":    "🌸 *Anime Mode activated!*",
        "enhance":  "✨ *Enhance Mode activated!*",
        "removebg": "🪄 *Remove Background Mode activated!*",
    }
    await update.message.reply_text(
        f"{labels[style]}\n\nSend me your image 📷",
        parse_mode="Markdown",
    )


async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _image_first_command(update, context, "anime")


async def enhance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _image_first_command(update, context, "enhance")


async def removebg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _image_first_command(update, context, "removebg")


# ── message handlers ──────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = context.user_data.get(FLOW_KEY)
    style = context.user_data.get(STYLE_KEY)

    # ── cinematic: collecting prompt before photo ──
    if flow == "prompt_first" and context.user_data.get(WAITING_PROMPT):
        prompt = update.message.text.strip()
        context.user_data[CUSTOM_PROMPT_KEY] = prompt
        context.user_data[WAITING_PROMPT] = False
        context.user_data[WAITING_IMAGE] = True
        await update.message.reply_text(
            f"✅ Got it — *\"{prompt}\"*\n\nNow send me your photo 📷",
            parse_mode="Markdown",
        )
        return

    # ── image-first styles: collecting prompt after photo ──
    if flow == "image_first" and context.user_data.get(WAITING_PROMPT):
        prompt = update.message.text.strip()
        context.user_data[CUSTOM_PROMPT_KEY] = prompt
        context.user_data[WAITING_PROMPT] = False

        photo_id = context.user_data.get(STORED_PHOTO_ID)
        if not photo_id:
            await update.message.reply_text("⚠️ Something went wrong. Please start over with /anime.")
            context.user_data.clear()
            return

        await update.message.reply_text("🎨 Generating… this takes ~15 seconds. Please wait!")

        tg_file = await context.bot.get_file(photo_id)
        image_bytes = await download_telegram_image(tg_file)

        base_style = STYLE_BASE.get(style, STYLE_BASE["anime"])
        style_prompt = f"{prompt}. Rendered as {base_style}"
        style_label = f"{STYLE_LABELS.get(style, style)} — \"{prompt}\""

        try:
            poster_bytes = await generate_poster(image_bytes, style_prompt)
        except Exception as e:
            logger.error("Generation failed: %s", e)
            await update.message.reply_text("❌ Generation failed. Please try again.")
            context.user_data.clear()
            return

        context.user_data.clear()
        await send_result(update.message, poster_bytes, style_label)
        return

    # ── no active flow ──
    await update.message.reply_text(
        "Pick a style to get started:\n"
        "/cinematic | /anime | /enhance | /removebg\n\n"
        "_Or just send a photo with a caption for a quick custom style!_",
        parse_mode="Markdown",
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow = context.user_data.get(FLOW_KEY)
    style = context.user_data.get(STYLE_KEY)

    # ── cinematic prompt-first: waiting for photo after prompt collected ──
    if flow == "prompt_first" and context.user_data.get(WAITING_IMAGE):
        custom_prompt = context.user_data.get(CUSTOM_PROMPT_KEY, "")
        style_prompt = f"{custom_prompt}. Rendered as {STYLE_BASE['cinematic']}"
        style_label = f"🎬 Cinematic — \"{custom_prompt}\""

        await update.message.reply_text("🎨 Generating… this takes ~15 seconds. Please wait!")

        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        image_bytes = await download_telegram_image(tg_file)

        try:
            poster_bytes = await generate_poster(image_bytes, style_prompt)
        except Exception as e:
            logger.error("Generation failed: %s", e)
            await update.message.reply_text("❌ Generation failed. Please try again.")
            context.user_data.clear()
            return

        context.user_data.clear()
        await send_result(update.message, poster_bytes, style_label)
        return

    # ── cinematic prompt-first: still waiting for prompt ──
    if flow == "prompt_first" and context.user_data.get(WAITING_PROMPT):
        await update.message.reply_text(
            "Please type your cinematic prompt first, then send the photo 🎬"
        )
        return

    # ── image-first: waiting for the initial image ──
    if flow == "image_first" and context.user_data.get(WAITING_IMAGE):
        photo = update.message.photo[-1]
        context.user_data[STORED_PHOTO_ID] = photo.file_id
        context.user_data[WAITING_IMAGE] = False
        context.user_data[WAITING_PROMPT] = True

        hint = PROMPT_HINTS.get(style, "your style prompt")
        await update.message.reply_text(
            f"📷 Image received!\n\nNow send your {hint} 👇",
            parse_mode="Markdown",
        )
        return

    # ── no active flow: use caption or default cinematic style ──
    if update.message.caption:
        style_prompt = (
            f"{update.message.caption}, cinematic composition, "
            "professional quality, visually stunning, high detail"
        )
        style_label = f'Custom: "{update.message.caption}"'
    else:
        style_prompt = STYLE_BASE["cinematic"]
        style_label = STYLE_LABELS["cinematic"]

    await update.message.reply_text("🎨 Generating… this takes ~15 seconds. Please wait!")

    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = await download_telegram_image(tg_file)

    try:
        poster_bytes = await generate_poster(image_bytes, style_prompt)
    except Exception as e:
        logger.error("Generation failed: %s", e)
        await update.message.reply_text("❌ Generation failed. Please try again.")
        return

    await send_result(update.message, poster_bytes, style_label)


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "feedback_up":
        logger.info("User %s rated 👍", query.from_user.id)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🙏 Thanks! Glad you loved it.\n"
            "Try another style: /cinematic | /anime | /enhance | /removebg"
        )
    elif query.data == "feedback_down":
        logger.info("User %s rated 👎", query.from_user.id)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "😔 Sorry it didn't hit the mark! Try a different style or a more detailed prompt.\n"
            "/cinematic | /anime | /enhance | /removebg"
        )


# ── startup ───────────────────────────────────────────────────────────────────

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_feedback, pattern="^feedback_"))

    logger.info("Bio Fundz Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
