import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from db import (
    get_settings, update_settings, set_thumbnail, get_thumbnail, clear_thumbnail,
    update_caption, get_caption, get_admins, is_admin_user,
    increase_limit, decrease_limit, get_max_concurrent
)
from utils import progress_bar, take_screenshots, cleanup, caption_styles

API_ID = 10811400
API_HASH = "191bf5ae7a6c39771e7b13cf4ffd1279"
BOT_TOKEN = "7097361755:AAHUd9LI4_JoAj57WfGbYVhG0msao8d04ck"

app = Client("RenameBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
QUEUE = asyncio.Semaphore(get_max_concurrent())

# /start - Settings UI
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    s = get_settings(user_id)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📸 Screenshot: {'✅' if s.get('screenshot') else '❌'}", callback_data="toggle_ss"),
         InlineKeyboardButton(f"🧮 Count: {s.get('count')}", callback_data="noop")],
        [InlineKeyboardButton("➕", callback_data="inc_count"), InlineKeyboardButton("➖", callback_data="dec_count")],
        [InlineKeyboardButton(f"📎 Prefix: {'✅' if s.get('prefix_enabled') else '❌'}", callback_data="toggle_prefix"),
         InlineKeyboardButton(f"📄 Type: {s.get('rename_type')}", callback_data="toggle_type")],
        [InlineKeyboardButton("🎨 Style", callback_data="style_menu"),
         InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumb_menu")],
        [InlineKeyboardButton("🔤 Prefix Text", callback_data="show_prefix")]
    ])
    await message.reply("⚙️ Customize your bot settings:", reply_markup=markup)

# /setprefix
@app.on_message(filters.command("setprefix"))
async def set_prefix_command(client, message):
    uid = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("❗ Usage: /setprefix <text>")
    prefix = message.text.split(None, 1)[1].strip()
    update_settings(uid, "prefix_text", prefix)
    await message.reply(f"✅ Prefix updated to:\n{prefix}")

# /setcaption
@app.on_message(filters.command("setcaption"))
async def set_caption_command(client, message):
    uid = message.from_user.id
    if len(message.command) < 2:
        return await message.reply("❗ Usage: /setcaption <text>")
    cap = message.text.split(None, 1)[1].strip()
    update_caption(uid, cap)
    await message.reply("✅ Custom caption updated!")

# /broadcast (admin only)
@app.on_message(filters.command("broadcast") & filters.user(get_admins()))
async def broadcast_admin(client, message):
    if len(message.command) < 2:
        return await message.reply("❗ Usage: /broadcast <text>")
    msg = message.text.split(None, 1)[1]
    from db import settings_col
    users = settings_col.distinct("_id")
    sent = 0
    for uid in users:
        try:
            await client.send_message(uid, msg)
            sent += 1
        except:
            continue
    await message.reply(f"✅ Sent to {sent} users")

# /increase & /decrease concurrency (admin only)
@app.on_message(filters.command("increase") & filters.user(get_admins()))
async def increase_concurrent(client, message):
    new = increase_limit()
    await message.reply(f"✅ Increased limit to {new}")

@app.on_message(filters.command("decrease") & filters.user(get_admins()))
async def decrease_concurrent(client, message):
    new = decrease_limit()
    await message.reply(f"✅ Decreased limit to {new}")

# Thumbnail save
@app.on_message(filters.photo & filters.private)
async def save_thumb(client, message):
    user_id = message.from_user.id
    file_id = message.photo.file_id
    set_thumbnail(user_id, file_id)
    await message.reply("✅ Thumbnail saved.")

# Rename Handler
@app.on_message(filters.command("rename"))
async def rename_file(client, message: Message):
    user_id = message.from_user.id
    async with QUEUE:
        settings = get_settings(user_id)
        rename_type = settings.get("rename_type", "doc")
        prefix_on = settings.get("prefix_enabled", True)
        caption_style = settings.get("caption_style", "bold")
        thumb_id = get_thumbnail(user_id)
        prefix_text = settings.get("prefix_text", "")
        caption_custom = get_caption(user_id) or None

        if len(message.command) >= 2:
            new_name = message.text.split(None, 1)[1]
        elif message.reply_to_message and message.reply_to_message.document:
            return await message.reply("❗ Provide a new filename after /rename")
        else:
            return await message.reply("❗ Reply to a document or provide filename.")

        if prefix_on:
            new_name = f"{prefix_text} {new_name}"

        task = {"message": await message.reply("📥 Starting download..."), "start_time": time.time(), "action": "📥 Downloading"}
        file_path = await message.reply_to_message.download(
            file_name=new_name,
            progress=progress_bar,
            progress_args=(task,)
        )

        cap = caption_custom if caption_custom else caption_styles(caption_style, f"✅ File: `{new_name}`")
        task = {"message": await message.reply("📤 Uploading..."), "start_time": time.time(), "action": "📤 Uploading"}

        try:
            if rename_type == "video":
                await message.reply_video(file_path, caption=cap, thumb=thumb_id, progress=progress_bar, progress_args=(task,))
            else:
                await message.reply_document(file_path, caption=cap, thumb=thumb_id, progress=progress_bar, progress_args=(task,))
        except Exception as e:
            return await message.reply(f"❗ Upload failed: {e}")

        if settings.get("screenshot") and new_name.lower().endswith((".mp4", ".mkv", ".mov")):
            ss_dir = f"ss_{user_id}"
            os.makedirs(ss_dir, exist_ok=True)
            for ss in take_screenshots(file_path, ss_dir, settings.get("count", 3)):
                await message.reply_photo(ss)
            cleanup(ss_dir)

        cleanup(file_path)

# Callback Buttons Handler
@app.on_callback_query()
async def cb_settings(client, cb):
    uid = cb.from_user.id
    data = get_settings(uid)

    if cb.data == "toggle_ss":
        update_settings(uid, "screenshot", not data.get("screenshot", False))
    elif cb.data == "inc_count":
        update_settings(uid, "count", min(10, data.get("count", 3) + 1))
    elif cb.data == "dec_count":
        update_settings(uid, "count", max(1, data.get("count", 3) - 1))
    elif cb.data == "toggle_prefix":
        update_settings(uid, "prefix_enabled", not data.get("prefix_enabled", True))
    elif cb.data == "toggle_type":
        new_type = "video" if data.get("rename_type") == "doc" else "doc"
        update_settings(uid, "rename_type", new_type)
    elif cb.data == "show_prefix":
        await cb.answer()
        return await cb.message.reply(f"📎 Current Prefix:\n{data.get('prefix_text', '-')}")
    elif cb.data == "thumb_menu":
        await cb.message.edit("🖼️ Thumbnail Options:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📌 Send Photo to Set", callback_data="noop")],
            [InlineKeyboardButton("🗑️ Remove Thumbnail", callback_data="remove_thumb")]
        ]))
        return await cb.answer()
    elif cb.data == "remove_thumb":
        clear_thumbnail(uid)
        return await cb.answer("✅ Thumbnail removed")
    elif cb.data == "style_menu":
        styles = ["bold", "italic", "code", "mono", "plain"]
        style_buttons = [InlineKeyboardButton(st.title(), callback_data=f"set_style:{st}") for st in styles]
        await cb.message.edit("🎨 Choose Caption Style:", reply_markup=InlineKeyboardMarkup([
            style_buttons[i:i+2] for i in range(0, len(style_buttons), 2)
        ]))
        return await cb.answer()
    elif cb.data.startswith("set_style:"):
        style = cb.data.split(":")[1]
        update_settings(uid, "caption_style", style)
        await cb.message.delete()
        return

    # Reload updated settings
    new_data = get_settings(uid)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📸 Screenshot: {'✅' if new_data.get('screenshot') else '❌'}", callback_data="toggle_ss"),
         InlineKeyboardButton(f"🧮 Count: {new_data.get('count')}", callback_data="noop")],
        [InlineKeyboardButton("➕", callback_data="inc_count"), InlineKeyboardButton("➖", callback_data="dec_count")],
        [InlineKeyboardButton(f"📎 Prefix: {'✅' if new_data.get('prefix_enabled') else '❌'}", callback_data="toggle_prefix"),
         InlineKeyboardButton(f"📄 Type: {new_data.get('rename_type')}", callback_data="toggle_type")],
        [InlineKeyboardButton("🎨 Style", callback_data="style_menu"),
         InlineKeyboardButton("🖼️ Thumbnail", callback_data="thumb_menu")],
        [InlineKeyboardButton("🔤 Prefix Text", callback_data="show_prefix")]
    ])
    await cb.message.edit("⚙️ Customize your bot settings:", reply_markup=markup)
    await cb.answer()

app.run()
