#(©)Codexbotz


import random

from pyrogram import Client, filters
from pyrogram import Client as Bot
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from helper_func import admin, encode, get_message_id
from info import BOT_USERNAMES, FILE_STORE_CHANNEL


@Bot.on_message(filters.private & admin & filters.command('batch'))
async def batch(client: Client, message: Message):
    while True:
        try:
            first_message = await client.ask(text = "Forward the First Message from DB Channel (with Quotes)..\n\nor Send the DB Channel Post Link", chat_id = message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        f_msg_id = await get_message_id(client, first_message)
        if f_msg_id:
            break
        else:
            await first_message.reply("❌ Error\n\nthis Forwarded Post is not from my DB Channel or this Link is taken from DB Channel", quote = True)
            continue

    while True:
        try:
            second_message = await client.ask(text = "Forward the Last Message from DB Channel (with Quotes)..\nor Send the DB Channel Post link", chat_id = message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        s_msg_id = await get_message_id(client, second_message)
        if s_msg_id:
            break
        else:
            await second_message.reply("❌ Error\n\nthis Forwarded Post is not from my DB Channel or this Link is taken from DB Channel", quote = True)
            continue


    string = f"get-{f_msg_id * abs(FILE_STORE_CHANNEL[0])}-{s_msg_id * abs(FILE_STORE_CHANNEL[0])}"
    base64_string = await encode(string)
    link = f"https://t.me/{random.choice(BOT_USERNAMES)}?start={base64_string}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f'https://t.me/share?url={link}')]])
    await second_message.reply_text(f"{link}", quote=True, reply_markup=reply_markup)


@Bot.on_message(filters.private & filters.command('link'))
async def link_generator(client: Client, message: Message):
    while True:
        try:
            channel_message = await client.ask(text = "Forward Message from the DB Channel (with Quotes)..\nor Send the DB Channel Post link", chat_id = message.from_user.id, filters=(filters.forwarded | (filters.text & ~filters.forwarded)), timeout=60)
        except:
            return
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            break
        else:
            await channel_message.reply("❌ Error\n\nthis Forwarded Post is not from my DB Channel or this Link is not taken from DB Channel", quote = True)
            continue

    base64_string = await encode(f"get-{msg_id * abs(FILE_STORE_CHANNEL[0])}")
    link = f"https://t.me/{random.choice(BOT_USERNAMES)}?start={base64_string}"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f'https://t.me/share?url={link}')]])
    await channel_message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=reply_markup)


@Bot.on_message(filters.private & admin & filters.command("custom_batch"))
async def custom_batch(client: Client, message: Message):
    collected = []
    STOP_KEYBOARD = ReplyKeyboardMarkup([["STOP"]], resize_keyboard=True)

    await message.reply("Send all messages you want to include in batch.\n\nPress STOP when you're done.", reply_markup=STOP_KEYBOARD)

    while True:
        try:
            user_msg = await client.ask(
                chat_id=message.chat.id,
                text="Waiting for files/messages...\nPress STOP to finish.",
                timeout=60
            )
        except TimeoutError:
            break

        if user_msg.text and user_msg.text.strip().upper() == "STOP":
            break

        try:
            sent = await user_msg.copy(FILE_STORE_CHANNEL[0], disable_notification=True)
            collected.append(sent.id)
        except Exception as e:
            await message.reply(f"❌ Failed to store a message:\n<code>{e}</code>")
            continue

    await message.reply("✅ Batch collection complete.", reply_markup=ReplyKeyboardRemove())

    if not collected:
        await message.reply("❌ No messages were added to batch.")
        return

    start_id = collected[0] * abs(FILE_STORE_CHANNEL[0])
    end_id = collected[-1] * abs(FILE_STORE_CHANNEL[0])
    string = f"get-{start_id}-{end_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{random.choice(BOT_USERNAMES)}?start={base64_string}"

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f'https://t.me/share?url={link}')]])
    await message.reply(f"<b>Here is your custom batch link:</b>\n\n{link}", reply_markup=reply_markup)