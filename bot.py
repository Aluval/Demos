import os
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from db import get_settings, update_settings, set_thumbnail, get_thumbnail, clear_thumbnail
from utils import progress_bar, take_screenshots, cleanup, caption_styles

# 🔐 Config
BOT_TOKEN = "7097361755:AAHUd9LI4_JoAj57WfGbYVhG0msao8d04ck"
API_ID = 10811400
API_HASH = "191bf5ae7a6c39771e7b13cf4ffd1279"


app = Client("RenameBot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

# ⚙️ /start - Settings UI
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    s = get_settings(user_id)

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Screenshot: {'✅' if s.get('screenshot') else '❌'}", callback_data="toggle_ss"),
            InlineKeyboardButton(f"Count: {s.get('count', 3)}", callback_data="noop")
        ],
        [
            InlineKeyboardButton("➕", callback_data="inc_count"),
            InlineKeyboardButton("➖", callback_data="dec_count")
        ],
        [
            InlineKeyboardButton(f"Prefix: {'✅' if s.get('prefix') else '❌'}", callback_data="toggle_prefix"),
            InlineKeyboardButton(f"Type: {s.get('rename_type', 'doc')}", callback_data="toggle_type")
        ],
        [
            InlineKeyboardButton("Style", callback_data="style_menu"),
            InlineKeyboardButton("Thumbnail", callback_data="thumb_menu")
        ]
    ])
    await message.reply("⚙️ Customize your bot settings:", reply_markup=markup)

# ✅ Prefix customization command
@app.on_message(filters.command("prefix"))
async def set_custom_prefix(client, message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("❗ Usage: `/prefix MyPrefix -`", quote=True)
    new_prefix = message.text.split(None, 1)[1]
    update_settings(user_id, "custom_prefix", new_prefix)
    await message.reply(f"✅ Prefix updated to:\n`{new_prefix}`", quote=True)

# ⚙️ Callback Query Handler
@app.on_callback_query()
async def cb_settings(client, cb):
    user_id = cb.from_user.id
    data = get_settings(user_id)

    if cb.data == "toggle_ss":
        update_settings(user_id, "screenshot", not data.get("screenshot", False))
    elif cb.data == "inc_count":
        update_settings(user_id, "count", min(10, data.get("count", 3) + 1))
    elif cb.data == "dec_count":
        update_settings(user_id, "count", max(1, data.get("count", 3) - 1))
    elif cb.data == "toggle_prefix":
        update_settings(user_id, "prefix", not data.get("prefix", True))
    elif cb.data == "toggle_type":
        new_type = "video" if data.get("rename_type") == "doc" else "doc"
        update_settings(user_id, "rename_type", new_type)
    elif cb.data == "style_menu":
        styles = ["bold", "italic", "code", "mono", "plain"]
        style_buttons = [InlineKeyboardButton(st, callback_data=f"set_style:{st}") for st in styles]
        style_markup = InlineKeyboardMarkup([style_buttons[i:i+2] for i in range(0, len(style_buttons), 2)])
        await cb.message.edit("🎨 Choose Caption Style:", reply_markup=style_markup)
        await cb.answer()
        return
    elif cb.data.startswith("set_style:"):
        _, style = cb.data.split(":")
        update_settings(user_id, "caption_style", style)
        await cb.message.delete()
        return
    elif cb.data == "thumb_menu":
        thumb_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📌 Set Thumb (send photo)", callback_data="noop")],
            [InlineKeyboardButton("🗑️ Remove Thumbnail", callback_data="remove_thumb")]
        ])
        await cb.message.edit("🖼️ Thumbnail Options:", reply_markup=thumb_markup)
        await cb.answer()
        return
    elif cb.data == "remove_thumb":
        clear_thumbnail(user_id)
        await cb.answer("✅ Thumbnail removed.")
        return await start(client, cb.message)

    # 🔁 Refresh UI
    await cb.answer("✅ Updated")
    return await start(client, cb.message)

# 📸 Set Thumbnail
@app.on_message(filters.photo & filters.private)
async def save_thumb(client, message):
    user_id = message.from_user.id
    file_id = message.photo.file_id
    set_thumbnail(user_id, file_id)
    await message.reply("✅ Thumbnail saved.")

# ✏️ /rename Handler
@app.on_message(filters.command("rename"))
async def rename_file(client, message: Message):
    user_id = message.from_user.id
    settings = get_settings(user_id)
    rename_type = settings.get("rename_type", "doc")
    prefix = settings.get("prefix", True)
    caption_style = settings.get("caption_style", "bold")
    custom_prefix = settings.get("custom_prefix", "@sunriseseditsoffical6 -")
    thumb_id = get_thumbnail(user_id)

    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("❗ Reply to a file to rename it.")
    if len(message.command) < 2:
        return await message.reply("❗ Provide a new filename after /rename")

    new_name = message.text.split(None, 1)[1]
    if prefix:
        new_name = f"{custom_prefix} {new_name}"

    task = {
        "message": await message.reply("📥 Starting download..."),
        "start_time": time.time(),
        "action": "📥 Downloading"
    }

    file_path = await message.reply_to_message.download(
        file_name=new_name,
        progress=progress_bar,
        progress_args=(task,)
    )

    cap = caption_styles(caption_style, f"✅ File: `{new_name}`")

    task = {
        "message": await message.reply("📤 Uploading file..."),
        "start_time": time.time(),
        "action": "📤 Uploading"
    }

    if rename_type == "video":
        await message.reply_video(file_path, caption=cap, thumb=thumb_id, progress=progress_bar, progress_args=(task,))
    else:
        await message.reply_document(file_path, caption=cap, thumb=thumb_id, progress=progress_bar, progress_args=(task,))

    # 📸 Screenshots (after upload)
    if settings.get("screenshot") and new_name.lower().endswith((".mp4", ".mkv", ".mov", ".webm")):
        ss_dir = f"ss_{user_id}"
        os.makedirs(ss_dir, exist_ok=True)
        ss_list = take_screenshots(file_path, ss_dir, settings.get("count", 3))
        for ss in ss_list:
            if os.path.exists(ss):
                try:
                    await message.reply_photo(ss)
                except Exception as e:
                    await message.reply(f"❗ Failed screenshot: {e}")
        cleanup(ss_dir)

    cleanup(file_path)

app.run()
