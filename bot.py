import os
import io
import json
import logging
import base64
import httpx
from datetime import date
from pathlib import Path
from openai import OpenAI
from telegram import (
    Update,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
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
ADMIN_ID = int(os.environ.get("ADMIN_USER_ID", "0"))

FREE_DAILY_LIMIT = 3
DATA_DIR   = Path("data")
USAGE_FILE = DATA_DIR / "usage.json"
VIP_FILE   = DATA_DIR / "vip.json"
USERS_FILE = DATA_DIR / "users.json"
DATA_DIR.mkdir(exist_ok=True)

# ── user_data keys ────────────────────────────────────────────────────────────
STYLE_KEY         = "style"
FLOW_KEY          = "flow"
WAITING_PROMPT    = "waiting_prompt"
WAITING_IMAGE     = "waiting_image"
STORED_PHOTO_ID   = "stored_photo_id"
CUSTOM_PROMPT_KEY = "custom_prompt"

# ── style definitions ─────────────────────────────────────────────────────────
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

GENERATING_MSGS = {
    "cinematic": "🎬 *Creating your cinematic masterpiece…*\nHollywood magic incoming — ~15 secs!",
    "anime":     "🌸 *Drawing your anime artwork…*\nBringing your scene to life — ~15 secs!",
    "enhance":   "✨ *Enhancing your image to HD…*\nSharpening every detail — ~15 secs!",
    "removebg":  "🪄 *Removing background…*\nCleaning up your image — ~15 secs!",
    "default":   "🎨 *Generating your AI image…*\nThis takes ~15 seconds. Please wait!",
}

PROMPT_HINTS = {
    "anime":    "anime style prompt _(e.g. 'Naruto cinematic style', 'Studio Ghibli forest scene')_",
    "enhance":  "enhancement direction _(e.g. 'sharp face detail, golden hour lighting')_",
    "removebg": "background description _(e.g. 'futuristic city skyline', 'white studio background')_",
}


# ── persistence helpers ───────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def is_vip(user_id: int) -> bool:
    vip = _load_json(VIP_FILE)
    return str(user_id) in vip


def add_vip(user_id: int) -> None:
    vip = _load_json(VIP_FILE)
    vip[str(user_id)] = True
    _save_json(VIP_FILE, vip)


def remove_vip(user_id: int) -> None:
    vip = _load_json(VIP_FILE)
    vip.pop(str(user_id), None)
    _save_json(VIP_FILE, vip)


def track_user(user_id: int, username: str | None, full_name: str) -> None:
    users = _load_json(USERS_FILE)
    users[str(user_id)] = {"username": username, "name": full_name}
    _save_json(USERS_FILE, users)


def get_usage(user_id: int) -> int:
    usage = _load_json(USAGE_FILE)
    today = str(date.today())
    return usage.get(str(user_id), {}).get(today, 0)


def increment_usage(user_id: int) -> int:
    usage = _load_json(USAGE_FILE)
    today = str(date.today())
    uid = str(user_id)
    if uid not in usage or list(usage[uid].keys()) != [today]:
        usage[uid] = {today: 0}
    usage[uid][today] += 1
    _save_json(USAGE_FILE, usage)
    return usage[uid][today]


def can_generate(user_id: int) -> bool:
    if user_id == ADMIN_ID or is_vip(user_id):
        return True
    return get_usage(user_id) < FREE_DAILY_LIMIT


def remaining(user_id: int) -> str:
    if user_id == ADMIN_ID or is_vip(user_id):
        return "∞ VIP"
    used = get_usage(user_id)
    left = max(0, FREE_DAILY_LIMIT - used)
    return f"{left}/{FREE_DAILY_LIMIT}"


# ── keyboards ─────────────────────────────────────────────────────────────────

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎬 Cinematic"), KeyboardButton("🌸 Anime")],
            [KeyboardButton("✨ Enhance"),   KeyboardButton("🪄 Remove BG")],
            [KeyboardButton("📖 Help"),      KeyboardButton("🌍 About")],
            [KeyboardButton("❌ Cancel"),    KeyboardButton("⭐ My Status")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Choose a style or send a photo…",
    )


def style_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Cinematic", callback_data="style_cinematic"),
            InlineKeyboardButton("🌸 Anime",     callback_data="style_anime"),
        ],
        [
            InlineKeyboardButton("✨ Enhance",   callback_data="style_enhance"),
            InlineKeyboardButton("🪄 Remove BG", callback_data="style_removebg"),
        ],
    ])


def feedback_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👍 Great!",   callback_data="feedback_up"),
        InlineKeyboardButton("👎 Not good", callback_data="feedback_down"),
    ]])


def after_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👍 Great!",   callback_data="feedback_up"),
            InlineKeyboardButton("👎 Not good", callback_data="feedback_down"),
        ],
        [
            InlineKeyboardButton("🎬 Cinematic", callback_data="style_cinematic"),
            InlineKeyboardButton("🌸 Anime",     callback_data="style_anime"),
        ],
        [
            InlineKeyboardButton("✨ Enhance",   callback_data="style_enhance"),
            InlineKeyboardButton("🪄 Remove BG", callback_data="style_removebg"),
        ],
    ])


# ── core generation ───────────────────────────────────────────────────────────

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
    logger.info("Scene: %s", scene)

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


async def run_generation(
    message, context: ContextTypes.DEFAULT_TYPE,
    image_bytes: bytes, style_prompt: str, style_label: str,
    user_id: int,
) -> None:
    if not can_generate(user_id):
        await message.reply_text(
            "🚫 *Daily limit reached!*\n\n"
            f"Free users get *{FREE_DAILY_LIMIT} generations per day*.\n\n"
            "Upgrade to ⭐ VIP for *unlimited* generations!\n"
            "Contact the admin to get VIP access.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    style = context.user_data.get(STYLE_KEY, "default")
    gen_msg = GENERATING_MSGS.get(style, GENERATING_MSGS["default"])
    await message.reply_text(gen_msg, parse_mode="Markdown")

    try:
        poster_bytes = await generate_poster(image_bytes, style_prompt)
    except Exception as e:
        logger.error("Generation failed: %s", e)
        await message.reply_text(
            "❌ Generation failed. Please try again.",
            reply_markup=main_menu_keyboard(),
        )
        return

    used = increment_usage(user_id)
    left = remaining(user_id)

    await message.reply_photo(
        photo=io.BytesIO(poster_bytes),
        caption=(
            f"✅ *Done!* Style: {style_label}\n"
            f"📊 Usage today: {left}\n\n"
            "Rate your result and pick the next style:"
        ),
        parse_mode="Markdown",
        reply_markup=after_result_keyboard(),
    )

    context.user_data.clear()


# ── command handlers ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    user = update.effective_user
    track_user(user.id, user.username, user.full_name)
    vip_badge = " ⭐ VIP" if is_vip(user.id) or user.id == ADMIN_ID else ""
    left = remaining(user.id)
    await update.message.reply_text(
        f"🚀 *Welcome to Biodun Fundz Bot!*{vip_badge}\n\n"
        "Transform your photos into stunning AI artwork using GPT-4o & DALL-E 3.\n\n"
        "*Choose a style below or tap a button:*\n"
        "🎬 Cinematic — Hollywood movie poster\n"
        "🌸 Anime — Manga-inspired artwork\n"
        "✨ Enhance — HD upscale & clarity\n"
        "🪄 Remove BG — Clean white background\n\n"
        f"📊 Generations remaining today: *{left}*",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *Biodun Fundz Bot — How to Use*\n\n"
        "*Styles:*\n"
        "🎬 /cinematic — type prompt → send photo\n"
        "🌸 /anime — send photo → type style\n"
        "✨ /enhance — send photo → type direction\n"
        "🪄 /removebg — send photo → type new bg\n\n"
        "*Other:*\n"
        "/start — reset & show welcome\n"
        "/about — about this bot\n"
        "/status — check your usage & VIP status\n"
        "/cancel — abort current action\n\n"
        f"🆓 Free: *{FREE_DAILY_LIMIT} generations/day*\n"
        "⭐ VIP: *Unlimited generations*\n\n"
        "_Tip: use the menu buttons for quick access!_",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌍 *About Biodun Fundz Bot*\n\n"
        "An AI-powered image transformation tool that turns everyday photos "
        "into professional-grade artwork.\n\n"
        "*Mission:* Make AI image generation accessible to everyone.\n\n"
        "*Powered by:*\n"
        "• GPT-4o Vision — understands your photos\n"
        "• DALL-E 3 — generates stunning artwork\n\n"
        "Created with ❤️ by *Biodun Fundz*",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_vip(user.id) or user.id == ADMIN_ID:
        tier = "⭐ *VIP — Unlimited generations*"
    else:
        used = get_usage(user.id)
        left = max(0, FREE_DAILY_LIMIT - used)
        tier = f"🆓 *Free* — {left}/{FREE_DAILY_LIMIT} generations left today"
    await update.message.reply_text(
        f"👤 *Your Status*\n\n{tier}",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data:
        context.user_data.clear()
        await update.message.reply_text(
            "❌ *Cancelled!* Everything reset.\n\nPick a style to start fresh:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "Nothing to cancel. Pick a style:",
            reply_markup=main_menu_keyboard(),
        )


# ── admin commands ────────────────────────────────────────────────────────────

async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /addvip <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    add_vip(uid)
    await update.message.reply_text(f"✅ User {uid} is now VIP ⭐")


async def removevip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removevip <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return
    remove_vip(uid)
    await update.message.reply_text(f"✅ VIP removed for user {uid}")


async def listvip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    vip = _load_json(VIP_FILE)
    if not vip:
        await update.message.reply_text("No VIP users yet.")
        return
    ids = "\n".join(f"• {uid}" for uid in vip)
    await update.message.reply_text(f"⭐ *VIP Users:*\n{ids}", parse_mode="Markdown")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast <message>\n\nExample:\n/broadcast 🎉 New styles dropping soon!"
        )
        return

    msg_text = " ".join(context.args)
    users = _load_json(USERS_FILE)
    if not users:
        await update.message.reply_text("No users to broadcast to yet.")
        return

    sent = failed = 0
    status_msg = await update.message.reply_text(
        f"📡 Broadcasting to {len(users)} users…"
    )

    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *Message from Biodun Fundz Bot:*\n\n{msg_text}",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception as e:
            logger.warning("Broadcast failed for %s: %s", uid, e)
            failed += 1

    await status_msg.edit_text(
        f"✅ *Broadcast complete!*\n\n"
        f"📬 Sent: {sent}\n"
        f"❌ Failed: {failed}\n"
        f"👥 Total users: {len(users)}",
        parse_mode="Markdown",
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only.")
        return
    users = _load_json(USERS_FILE)
    vip   = _load_json(VIP_FILE)
    usage = _load_json(USAGE_FILE)
    today = str(date.today())
    active_today = sum(
        1 for u in usage.values()
        if today in u and u[today] > 0
    )
    await update.message.reply_text(
        f"📊 *Bot Statistics*\n\n"
        f"👥 Total users: {len(users)}\n"
        f"⭐ VIP users: {len(vip)}\n"
        f"🔥 Active today: {active_today}",
        parse_mode="Markdown",
    )


# ── style activation helpers ──────────────────────────────────────────────────

async def _activate_cinematic(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    context.user_data[STYLE_KEY] = "cinematic"
    context.user_data[FLOW_KEY] = "prompt_first"
    context.user_data[WAITING_PROMPT] = True
    await message.reply_text(
        "🎬 *Cinematic Mode!*\n\n"
        "Describe your cinematic vision:\n"
        "_(e.g. 'dark noir thriller', 'epic sci-fi', 'romantic golden sunset')_\n\n"
        "Type your prompt 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="action_cancel")
        ]]),
    )


async def _activate_image_first(
    message, context: ContextTypes.DEFAULT_TYPE, style: str
) -> None:
    context.user_data.clear()
    context.user_data[STYLE_KEY] = style
    context.user_data[FLOW_KEY] = "image_first"
    context.user_data[WAITING_IMAGE] = True
    labels = {
        "anime":    "🌸 *Anime Mode!*",
        "enhance":  "✨ *Enhance Mode!*",
        "removebg": "🪄 *Remove BG Mode!*",
    }
    await message.reply_text(
        f"{labels[style]}\n\nSend me your photo 📷",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ Cancel", callback_data="action_cancel")
        ]]),
    )


async def cinematic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _activate_cinematic(update.message, context)


async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _activate_image_first(update.message, context, "anime")


async def enhance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _activate_image_first(update.message, context, "enhance")


async def removebg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _activate_image_first(update.message, context, "removebg")


# ── text & photo handlers ─────────────────────────────────────────────────────

BUTTON_MAP = {
    "🎬 Cinematic": "cinematic",
    "🌸 Anime":     "anime",
    "✨ Enhance":   "enhance",
    "🪄 Remove BG": "removebg",
}


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    flow  = context.user_data.get(FLOW_KEY)
    style = context.user_data.get(STYLE_KEY)

    # ── reply keyboard shortcuts ──
    if text in BUTTON_MAP:
        s = BUTTON_MAP[text]
        if s == "cinematic":
            await _activate_cinematic(update.message, context)
        else:
            await _activate_image_first(update.message, context, s)
        return

    if text == "📖 Help":
        await help_command(update, context); return
    if text == "🌍 About":
        await about(update, context); return
    if text == "❌ Cancel":
        await cancel(update, context); return
    if text == "⭐ My Status":
        await status_command(update, context); return

    # ── cinematic: collecting prompt ──
    if flow == "prompt_first" and context.user_data.get(WAITING_PROMPT):
        context.user_data[CUSTOM_PROMPT_KEY] = text
        context.user_data[WAITING_PROMPT] = False
        context.user_data[WAITING_IMAGE] = True
        await update.message.reply_text(
            f"✅ *\"{text}\"* — got it!\n\nNow send your photo 📷",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="action_cancel")
            ]]),
        )
        return

    # ── image-first: collecting prompt after photo ──
    if flow == "image_first" and context.user_data.get(WAITING_PROMPT):
        photo_id = context.user_data.get(STORED_PHOTO_ID)
        if not photo_id:
            await update.message.reply_text("⚠️ Something went wrong. Please start over.")
            context.user_data.clear()
            return

        base_style   = STYLE_BASE.get(style, STYLE_BASE["anime"])
        style_prompt = f"{text}. Rendered as {base_style}"
        style_label  = f"{STYLE_LABELS.get(style, style)} — \"{text}\""

        tg_file     = await context.bot.get_file(photo_id)
        image_bytes = await download_telegram_image(tg_file)

        await run_generation(
            update.message, context, image_bytes,
            style_prompt, style_label, update.effective_user.id
        )
        return

    # ── no active flow ──
    await update.message.reply_text(
        "Pick a style to get started 👇",
        reply_markup=style_inline_keyboard(),
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    flow  = context.user_data.get(FLOW_KEY)
    style = context.user_data.get(STYLE_KEY)
    user_id = update.effective_user.id

    # ── cinematic: waiting for photo after prompt ──
    if flow == "prompt_first" and context.user_data.get(WAITING_IMAGE):
        custom_prompt = context.user_data.get(CUSTOM_PROMPT_KEY, "")
        style_prompt  = f"{custom_prompt}. Rendered as {STYLE_BASE['cinematic']}"
        style_label   = f"🎬 Cinematic — \"{custom_prompt}\""

        photo = update.message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        image_bytes = await download_telegram_image(tg_file)

        await run_generation(
            update.message, context, image_bytes,
            style_prompt, style_label, user_id
        )
        return

    # ── cinematic: prompt not yet given ──
    if flow == "prompt_first" and context.user_data.get(WAITING_PROMPT):
        await update.message.reply_text(
            "Please type your cinematic prompt first, then send the photo 🎬"
        )
        return

    # ── image-first: waiting for photo ──
    if flow == "image_first" and context.user_data.get(WAITING_IMAGE):
        photo = update.message.photo[-1]
        context.user_data[STORED_PHOTO_ID] = photo.file_id
        context.user_data[WAITING_IMAGE]   = False
        context.user_data[WAITING_PROMPT]  = True
        hint = PROMPT_HINTS.get(style, "your style prompt")
        await update.message.reply_text(
            f"📷 Image received!\n\nNow send your {hint} 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="action_cancel")
            ]]),
        )
        return

    # ── no active flow: use caption or default ──
    if update.message.caption:
        style_prompt = (
            f"{update.message.caption}, cinematic composition, "
            "professional quality, visually stunning, high detail"
        )
        style_label = f'Custom: "{update.message.caption}"'
    else:
        await update.message.reply_text(
            "Which style do you want? 👇",
            reply_markup=style_inline_keyboard(),
        )
        context.user_data[STORED_PHOTO_ID] = update.message.photo[-1].file_id
        context.user_data[FLOW_KEY]        = "image_first"
        context.user_data[WAITING_IMAGE]   = False
        context.user_data[WAITING_PROMPT]  = True
        return

    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    image_bytes = await download_telegram_image(tg_file)

    await run_generation(
        update.message, context, image_bytes,
        style_prompt, style_label, user_id
    )


# ── callback query handler ────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # feedback
    if data == "feedback_up":
        logger.info("User %s rated 👍", query.from_user.id)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🙏 Glad you loved it!\nTry another style:",
            reply_markup=style_inline_keyboard(),
        )
        return

    if data == "feedback_down":
        logger.info("User %s rated 👎", query.from_user.id)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "😔 Sorry it missed the mark! Try a different style or more detailed prompt:",
            reply_markup=style_inline_keyboard(),
        )
        return

    # cancel button
    if data == "action_cancel":
        context.user_data.clear()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "❌ *Cancelled!* Pick a style to start fresh:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return

    # style selection via inline button
    if data.startswith("style_"):
        style = data[6:]
        if style == "cinematic":
            await _activate_cinematic(query.message, context)
        elif style in STYLE_BASE:
            await _activate_image_first(query.message, context, style)
        return


# ── startup ───────────────────────────────────────────────────────────────────

async def post_init(app) -> None:
    await app.bot.set_my_commands([
        BotCommand("start",     "🚀 Welcome & reset"),
        BotCommand("help",      "📖 How to use the bot"),
        BotCommand("about",     "🌍 About Biodun Fundz Bot"),
        BotCommand("status",    "📊 Check your usage & VIP status"),
        BotCommand("cinematic", "🎬 Hollywood movie poster"),
        BotCommand("anime",     "🌸 Anime & manga artwork"),
        BotCommand("enhance",   "✨ HD upscale & enhancement"),
        BotCommand("removebg",  "🪄 Remove image background"),
        BotCommand("cancel",    "❌ Cancel current action"),
        BotCommand("broadcast", "📡 Send message to all users (admin)"),
        BotCommand("stats",     "📊 Bot usage statistics (admin)"),
        BotCommand("addvip",    "⭐ Grant VIP to user (admin)"),
        BotCommand("removevip", "🚫 Revoke VIP from user (admin)"),
        BotCommand("listvip",   "📋 List all VIP users (admin)"),
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
    app.add_handler(CommandHandler("status",    status_command))
    app.add_handler(CommandHandler("cancel",    cancel))
    app.add_handler(CommandHandler("cinematic", cinematic))
    app.add_handler(CommandHandler("anime",     anime))
    app.add_handler(CommandHandler("enhance",   enhance))
    app.add_handler(CommandHandler("removebg",  removebg))
    app.add_handler(CommandHandler("addvip",    addvip))
    app.add_handler(CommandHandler("removevip", removevip))
    app.add_handler(CommandHandler("listvip",   listvip))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats",     stats))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Biodun Fundz Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
