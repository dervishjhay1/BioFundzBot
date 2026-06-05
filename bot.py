import os
import io
import logging
import base64
import httpx
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Bio Fundz Bot is online 🚀\n\n"
        "Send me an image with a caption describing the poster style you want "
        "and I'll generate a cinematic AI poster for you!"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prompt = update.message.caption or "cinematic movie poster, dramatic lighting, epic composition"

    await update.message.reply_text("🎬 Generating your cinematic poster… please wait.")

    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)

    async with httpx.AsyncClient() as client:
        resp = await client.get(tg_file.file_path)
        resp.raise_for_status()
        image_bytes = resp.content

    image_b64 = base64.standard_b64encode(image_bytes).decode()

    vision_response = openai.chat.completions.create(
        model="gpt-4o",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Describe the main subject and scene in this image in detail "
                            f"so it can be used as a reference for generating a cinematic poster. "
                            f"User style request: '{prompt}'"
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

    scene_description = vision_response.choices[0].message.content
    logger.info("Scene description: %s", scene_description)

    poster_prompt = (
        f"Cinematic movie poster. {prompt}. "
        f"Scene: {scene_description}. "
        "Epic dramatic lighting, professional film poster composition, "
        "high contrast, stunning visuals, photorealistic, 8K quality."
    )

    image_response = openai.images.generate(
        model="dall-e-3",
        prompt=poster_prompt,
        size="1024x1792",
        quality="standard",
        n=1,
        response_format="b64_json",
    )

    poster_b64 = image_response.data[0].b64_json
    poster_bytes = base64.standard_b64decode(poster_b64)

    await update.message.reply_photo(
        photo=io.BytesIO(poster_bytes),
        caption=f"🎬 Your cinematic poster\nStyle: {prompt}",
    )


async def handle_photo_no_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_photo(update, context)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("Bio Fundz Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
