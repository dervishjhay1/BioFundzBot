import os
import io
import json
import logging
from pathlib import Path
from datetime import date

import requests
from PIL import Image
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
ContextTypes,
filters,
)

=========================

LOGGING

=========================

logging.basicConfig(
format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
level=logging.INFO
)

logger = logging.getLogger(name)

=========================

ENV VARIABLES

=========================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HUGGINGFACE_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID", "0"))

if not BOT_TOKEN:
raise ValueError("TELEGRAM_BOT_TOKEN is missing")

if not HF_TOKEN:
raise ValueError("HUGGINGFACE_API_KEY is missing")

=========================

FILES

=========================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
USAGE_FILE = DATA_DIR / "usage.json"
VIP_FILE = DATA_DIR / "vip.json"

FREE_DAILY_LIMIT = 3

=========================

STYLES

=========================

STYLE_PROMPTS = {
"cinematic": "cinematic hollywood movie poster, dramatic lighting, ultra realistic",
"anime": "anime style artwork, studio ghibli, detailed anime illustration",
"enhance": "ultra detailed hd enhancement, sharp realistic photo",
"removebg": "clean white background portrait"
}

STYLE_NAMES = {
"cinematic": "🎬 Cinematic",
"anime": "🌸 Anime",
"enhance": "✨ Enhance",
"removebg": "🪄 Remove BG",
}

=========================

HELPERS

=========================

def load_json(path):
if path.exists():
try:
return json.loads(path.read_text())
except:
return {}
return {}

def save_json(path, data):
path.write_text(json.dumps(data, indent=2))

def is_vip(user_id):
vip = load_json(VIP_FILE)
return str(user_id) in vip

def get_usage(user_id):
usage = load_json(USAGE_FILE)
today = str(date.today())
return usage.get(str(user_id), {}).get(today, 0)

def increment_usage(user_id):
usage = load_json(USAGE_FILE)
today = str(date.today())

if str(user_id) not in usage:
    usage[str(user_id)] = {}

if today not in usage[str(user_id)]:
    usage[str(user_id)][today] = 0

usage[str(user_id)][today] += 1

save_json(USAGE_FILE, usage)

def can_generate(user_id):
if user_id == ADMIN_ID:
return True

if is_vip(user_id):
    return True

return get_usage(user_id) < FREE_DAILY_LIMIT

def remaining(user_id):
if user_id == ADMIN_ID or is_vip(user_id):
return "∞"

left = FREE_DAILY_LIMIT - get_usage(user_id)
return str(max(left, 0))

=========================

KEYBOARDS

=========================

def main_keyboard():
return ReplyKeyboardMarkup(
[
[KeyboardButton("🎬 Cinematic"), KeyboardButton("🌸 Anime")],
[KeyboardButton("✨ Enhance"), KeyboardButton("🪄 Remove BG")],
[KeyboardButton("📖 Help"), KeyboardButton("⭐ Status")]
],
resize_keyboard=True
)

def style_keyboard():
return InlineKeyboardMarkup([
[
InlineKeyboardButton("🎬 Cinematic", callback_data="cinematic"),
InlineKeyboardButton("🌸 Anime", callback_data="anime"),
],
[
InlineKeyboardButton("✨ Enhance", callback_data="enhance"),
InlineKeyboardButton("🪄 Remove BG", callback_data="removebg"),
]
])

=========================

IMAGE GENERATION

=========================

def generate_image(prompt):
API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

headers = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

response = requests.post(
    API_URL,
    headers=headers,
    json={"inputs": prompt},
    timeout=120
)

if response.status_code != 200:
    raise Exception(response.text)

return response.content

=========================

COMMANDS

=========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
context.user_data.clear()

await update.message.reply_text(
    "🚀 Welcome to Biodun Fundz Bot!\n\n"
    "Send a photo and choose a style.",
    reply_markup=main_keyboard()
)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"📖 Commands:\n\n"
"/start - Restart bot\n"
"/help - Help menu\n"
"/status - Check remaining generations",
reply_markup=main_keyboard()
)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
left = remaining(update.effective_user.id)

await update.message.reply_text(
    f"📊 Remaining generations today: {left}",
    reply_markup=main_keyboard()
)

=========================

TEXT HANDLER

=========================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

text = update.message.text

if text == "📖 Help":
    await help_command(update, context)
    return

if text == "⭐ Status":
    await status(update, context)
    return

button_map = {
    "🎬 Cinematic": "cinematic",
    "🌸 Anime": "anime",
    "✨ Enhance": "enhance",
    "🪄 Remove BG": "removebg",
}

if text in button_map:
    context.user_data["style"] = button_map[text]

    await update.message.reply_text(
        f"Send your image for {text}"
    )

=========================

PHOTO HANDLER

=========================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

user_id = update.effective_user.id

if not can_generate(user_id):
    await update.message.reply_text(
        "🚫 Daily limit reached."
    )
    return

style = context.user_data.get("style", "cinematic")

await update.message.reply_text(
    "🎨 Generating image..."
)

photo = update.message.photo[-1]

file = await context.bot.get_file(photo.file_id)

image_bytes = requests.get(file.file_path).content

prompt = STYLE_PROMPTS.get(style)

try:
    generated = generate_image(prompt)

    increment_usage(user_id)

    await update.message.reply_photo(
        photo=io.BytesIO(generated),
        caption=f"✅ Done! Style: {STYLE_NAMES[style]}"
    )

except Exception as e:
    logger.error(e)

    await update.message.reply_text(
        "❌ Generation failed."
    )

=========================

CALLBACKS

=========================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

query = update.callback_query
await query.answer()

style = query.data

context.user_data["style"] = style

await query.message.reply_text(
    f"✅ {STYLE_NAMES[style]} selected.\n\nNow send your image."
)

=========================

POST INIT

=========================

async def post_init(app):

await app.bot.set_my_commands([
    BotCommand("start", "Start bot"),
    BotCommand("help", "Help"),
    BotCommand("status", "Usage status"),
])

=========================

MAIN

=========================

def main():

app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .post_init(post_init)
    .build()
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("status", status))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

app.add_handler(CallbackQueryHandler(callback_handler))

logger.info("Bot started")

app.run_polling()

if name == "main":
main()