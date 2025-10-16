
import asyncio
import base64
import datetime
import json
import logging
import os
import random

# from plugins.pm_filter import ENABLE_SHORTLINK
import re
import sys

from pyrogram import Client, enums, filters
from pyrogram.errors import FloodWait

#########################################
from pyrogram.types import *
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.connections_mdb import *
from database.ia_filterdb import *
from database.users_chats_db import *
from info import *
from Script import script
from utils import *

from .join_req import *
from .pm_filter import auto_filter

# Auto delete function
async def auto_delete_file(client, chat_id, message_id, user_id, start_param):
    await asyncio.sleep(600)  # 10 minutes
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception as e:
        logging.warning(f"Failed to delete message {message_id}: {e}")
    # Send get again message
    btn = [[InlineKeyboardButton("Get File Again", url=f"https://t.me/{temp.U_NAME}?start={start_param}")]]
    try:
        await client.send_message(
            user_id,
            "⚠️ File deleted due to copyright issues.\n\nGet the file again:",
            reply_markup=InlineKeyboardMarkup(btn)
        )
    except Exception as e:
        logging.warning(f"Failed to send get again message to {user_id}: {e}")

###################################


logger = logging.getLogger(__name__)

# Add your handler here, for example, a file handler:
handler = logging.FileHandler('error_log.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


# Set up logging
logging.basicConfig(level=logging.ERROR)


BATCH_FILES = {}


@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    # ---------------- Group / Supergroup flow ----------------
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        
        await message.reply(
            script.START_TXT.format(message.from_user.mention),
           
            disable_web_page_preview=True
        )

        # Add group in DB
        await asyncio.sleep(2)
        if not await db.get_chat(message.chat.id):
            try:
                total = await client.get_chat_members_count(message.chat.id)
            except Exception:
                total = 0
            try:
                await client.send_message(
                    LOG_CHANNEL,
                    script.LOG_TEXT_G.format(
                        message.chat.title,
                        message.chat.id,
                        total,
                        "Unknown",
                        temp.U_NAME
                    )
                )
            except Exception:
                pass
            await db.add_chat(message.chat.id, message.chat.title)
        return

    # ---------------- Ensure user exists in DB ----------------
    if not await db.is_user_exist(message.from_user.id):
        try:
            await db.add_user(message.from_user.id, message.from_user.first_name)
            try:
                await client.send_message(
                    LOG_CHANNEL,
                    script.LOG_TEXT_P.format(
                        message.from_user.id,
                        message.from_user.mention,
                        temp.U_NAME
                    )
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"DB add_user failed for {message.from_user.id}: {e}")
            btn = InlineKeyboardMarkup([[InlineKeyboardButton(
                "𝐂𝐨𝐧𝐭𝐢𝐧𝐮𝐞 𝐓𝐨 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 ♂️",
                url=f"https://t.me/{temp.U_NAME}?start={message.command[1] if len(message.command) > 1 else ''}"
            )]])
            await message.reply(
                "⚠️ Unable to add you to database.\n\n👉 Click the below button to continue.",
                reply_markup=btn
            )
            return

    # ---------------- If no args -> normal start ----------------
    if len(message.command) != 2:
       
        await message.reply(
            text=script.START_TXT.format(message.from_user.mention),
            parse_mode=enums.ParseMode.HTML
        )
        return

    # ---------------- Check unjoined channels ----------------
    try:
        unjoined = await get_unjoined_channels(client, message.from_user.id)
    except Exception as e:
        logging.exception(f"get_unjoined_channels failed: {e}")
        unjoined = {"channels": [], "count": 0}

    btn = []
    private_count = 1

    # ---------------- Show join buttons if user is unjoined ----------------
    if unjoined["channels"]:
        for ch in unjoined["channels"]:
            ch_id = ch["channel_id"]
            url = ch["url"]
            is_store = ch["is_store"]

            if is_store:
                label = "Join Main Channel"
            else:
                label = f"Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ {private_count} ♂️"
                private_count += 1

            btn.append([InlineKeyboardButton(label, url=url)])

        # ---------------- Add Continue button together ----------------
        if message.text and message.text.startswith("/start") and len(message.command) > 1:
            try:
                kk, file_id = message.command[1].split("_", 1)
                btn.append([InlineKeyboardButton(
                    "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                    url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                )])
            except (IndexError, ValueError):
                btn.append([InlineKeyboardButton(
                    "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                    url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                )])

        await client.send_message(
                    chat_id=message.from_user.id,
                    text="⚠️ You must join the below channels to continue:",
                    reply_markup=InlineKeyboardMarkup(btn),
                    parse_mode=enums.ParseMode.HTML
                )
        return  # Stop here, do NOT give file yet

    # ---------------- Final fallback / special command handling ----------------
    if len(message.command) == 2 and message.command[1] in ["subscribe", "error", "okay", "help"]:
        
        await message.reply(
            text=script.START_TXT.format(message.from_user.mention),
            parse_mode=enums.ParseMode.HTML
        )
        return

    # getfile function for movies update log
    if len(message.command) == 2 and message.command[1].startswith('getfile'):
        movies = message.command[1].split("-", 1)[1]
        movie = movies.replace('-', ' ')
        message.text = movie
        await auto_filter(client, message)
        return

    # mid verify function
    if len(message.command) == 2 and message.command[1].startswith('midverify'):
        try:
            verify_url = message.command[1].split("midverify-", 1)[1]
            verify_url = verify_url.replace('9cln', ':')
            verify_url = verify_url.replace('9slsh', '/')
            verify_url = verify_url.replace('9dot', '.')
            verify_url = verify_url.replace('-', ' ')

            custom_message = "𝗪𝗲𝗹𝗰𝗼𝗺𝗲!\n𝗛𝗲𝗿𝗲 𝗶𝘀 𝗬𝗼𝘂𝗿 𝗩𝗲𝗿𝗶𝗳𝗶𝗰𝗮𝘁𝗶𝗼𝗻 𝗹𝗶𝗻𝗸. 👇\n\nआपका स्वागत है!\nयह रहा आपका वेरीफाई लिंक है। 👇"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("𝗩𝗲𝗿𝗶𝗳𝘆 ♂️", url=verify_url)]
            ])
            await message.reply_text(custom_message, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error in midverify processing: {e}")
            await message.reply_text("An error occurred while processing the verification. Please try again later.")

    # ---------------- Referral handling ----------------
    data = message.command[1]
    try:
        data = (base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")
    except:
        pass
    if data.split("-", 1)[0] == "VJ":
        user_id = int(data.split("-", 1)[1])
        vj = await referal_add_user(user_id, message.from_user.id)
        if vj:
            await message.reply(f"<b>You have joined using the referral link of user with ID {user_id}\n\nSend /start again to use the bot</b>")
            num_referrals = await get_referal_users_count(user_id)
            await client.send_message(chat_id=user_id, text=f"<b>{message.from_user.mention} start the bot with your referral link\n\nTotal Referals - {num_referrals}</b>")
            if num_referrals == REFERAL_COUNT:
                time_ = REFERAL_PREMEIUM_TIME
                seconds = await get_seconds(time_)
                if seconds > 0:
                    expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
                    user_data = {"id": user_id, "expiry_time": expiry_time}
                    await db.update_user(user_data)
                    await delete_all_referal_users(user_id)
                    await client.send_message(chat_id=user_id, text=f"<b>You Have Successfully Completed Total Referal.\n\nYou Added In Premium For {REFERAL_PREMEIUM_TIME}</b>")
                    return
        else:
            buttons = [[
                InlineKeyboardButton('➕ Aᴅᴅ Mᴇ Tᴏ Yᴏᴜʀ Gʀᴏᴜᴘ ➕', url='http://telegram.me/idontknowwhoim_bot?startgroup=true&admin=post_messages+delete_messages+edit_messages+invite_users+promote_members+pin_messages')
            ]]
            reply_markup = InlineKeyboardMarkup(buttons)
            await message.reply(
                text=script.START_TXT.format(message.from_user.mention),
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML
            )
            return

    # ---------------- Handle genlink "get-" links ----------------
    if data.startswith("get-"):
        parts = data.split("-")
        if len(parts) == 2:
            # single file
            encoded_msg_id = parts[1]
            msg_id = int(encoded_msg_id) // abs(FILE_STORE_CHANNEL[0])
            try:
                msg = await client.get_messages(FILE_STORE_CHANNEL[0], msg_id)
                sent_msg = await msg.copy(message.from_user.id)
                if AUTO_DELETE:
                    asyncio.create_task(auto_delete_file(client, message.from_user.id, sent_msg.id, message.from_user.id, data))
                    await client.send_message(message.from_user.id, "⚠️ **Auto Delete Alert:**\n\nThis file will be automatically deleted in **10 minutes** due to copyright issues. Save it quickly!")
            except Exception as e:
                await message.reply(f"Error: {e}")
        elif len(parts) == 3:
            # batch
            f_encoded = parts[1]
            s_encoded = parts[2]
            f_msg_id = int(f_encoded) // abs(FILE_STORE_CHANNEL[0])
            s_msg_id = int(s_encoded) // abs(FILE_STORE_CHANNEL[0])
            sts = await message.reply("<b>Please wait...</b>")
            sent_messages = []
            async for msg in client.iter_messages(FILE_STORE_CHANNEL[0], s_msg_id, f_msg_id):
                sent_msg = await msg.copy(message.from_user.id)
                sent_messages.append(sent_msg)
                await asyncio.sleep(1)
            await sts.delete()
            if AUTO_DELETE:
                for sent_msg in sent_messages:
                    asyncio.create_task(auto_delete_file(client, message.from_user.id, sent_msg.id, message.from_user.id, data))
                await client.send_message(message.from_user.id, "⚠️ **Auto Delete Alert:**\n\nThese files will be automatically deleted in **10 minutes** due to copyright issues. Save them quickly!")
        return

    # ---------------- File download / batch handling ----------------
    try:
        pre, file_id = data.split('_', 1)
    except Exception:
        file_id = data
        pre = ""

    if data.split("-", 1)[0] == "BATCH":
        sts = await message.reply("<b>Please wait...</b>")
        file_id = data.split("-", 1)[1]
        msgs = BATCH_FILES.get(file_id)
        if not msgs:
            file = await client.download_media(file_id)
            try:
                with open(file) as file_data:
                    msgs = json.loads(file_data.read())
            except:
                await sts.edit("FAILED")
                return await client.send_message(LOG_CHANNEL, "UNABLE TO OPEN FILE.")
            os.remove(file)
            BATCH_FILES[file_id] = msgs
        for msg in msgs:
            title = msg.get("title")
            size = get_size(int(msg.get("size", 0)))
            f_caption = msg.get("caption", "")
            if BATCH_FILE_CAPTION:
                try:
                    f_caption = BATCH_FILE_CAPTION.format(file_name='' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
                except Exception as e:
                    logger.exception(e)
                    f_caption = f_caption
            if f_caption is None:
                f_caption = f"{title}"
            try:
                sent_msg = await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton('Sᴜᴘᴘᴏʀᴛ Gʀᴏᴜᴘ', url=GRP_LNK),
                                InlineKeyboardButton('Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ', url=CHNL_LNK)
                            ]
                        ]
                    )
                )
            except FloodWait as e:
                await asyncio.sleep(e.x)
                logger.warning(f"Floodwait of {e.x} sec.")
                sent_msg = await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton('Sᴜᴘᴘᴏʀᴛ Gʀᴏᴜᴘ', url=GRP_LNK),
                                InlineKeyboardButton('Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ', url=CHNL_LNK)
                            ]
                        ]
                    )
                )
            except Exception as e:
                logger.warning(e, exc_info=True)
                continue
            if AUTO_DELETE:
                asyncio.create_task(auto_delete_file(client, message.from_user.id, sent_msg.id, message.from_user.id, data))
            await asyncio.sleep(1)
        if AUTO_DELETE:
            await client.send_message(message.from_user.id, "⚠️ **Auto Delete Alert:**\n\nThese files will be automatically deleted in **10 minutes** due to copyright issues. Save them quickly!")
        await sts.delete()
        return

    elif data.split("-", 1)[0] == "DSTORE":
        sts = await message.reply("<b>Please wait...</b>")
        b_string = data.split("-", 1)[1]
        decoded = (base64.urlsafe_b64decode(b_string + "=" * (-len(b_string) % 4))).decode("ascii")
        try:
            f_msg_id, l_msg_id, f_chat_id, protect = decoded.split("_", 3)
        except:
            f_msg_id, l_msg_id, f_chat_id = decoded.split("_", 2)
            protect = "/pbatch" if PROTECT_CONTENT else "batch"
        diff = int(l_msg_id) - int(f_msg_id)
        async for msg in client.iter_messages(int(f_chat_id), int(l_msg_id), int(f_msg_id)):
            if msg.media:
                media = getattr(msg, msg.media.value)
                if BATCH_FILE_CAPTION:
                    try:
                        f_caption=BATCH_FILE_CAPTION.format(file_name=getattr(media, 'file_name', ''), file_size=getattr(media, 'file_size', ''), file_caption=getattr(msg, 'caption', ''))
                    except Exception as e:
                        logger.exception(e)
                        f_caption = getattr(msg, 'caption', '')
                else:
                    media = getattr(msg, msg.media.value)
                    file_name = getattr(media, 'file_name', '')
                    f_caption = getattr(msg, 'caption', file_name)
                try:
                    await msg.copy(message.chat.id, caption=f_caption, protect_content=True if protect == "/pbatch" else False)
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await msg.copy(message.chat.id, caption=f_caption, protect_content=True if protect == "/pbatch" else False)
                except Exception as e:
                    logger.exception(e)
                    continue
            elif msg.empty:
                continue
            else:
                try:
                    await msg.copy(message.chat.id, protect_content=True if protect == "/pbatch" else False)
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await msg.copy(message.chat.id, protect_content=True if protect == "/pbatch" else False)
                except Exception as e:
                    logger.exception(e)
                    continue
            await asyncio.sleep(1) 
        return await sts.delete()

    elif data.split("-", 1)[0] == "verify":
        userid = data.split("-", 2)[1]
        token = data.split("-", 3)[2]
        fileid = data.split("-", 3)[3]
        if str(message.from_user.id) != str(userid):
            return await message.reply_text(
                text="<b>Invalid link or Expired link !</b>",
                protect_content=True
            )
        is_valid = await check_token(client, userid, token)
        if is_valid == True:
            if fileid == "send_all":
                btn = [[
                    InlineKeyboardButton("Gᴇᴛ Fɪʟᴇ", callback_data="checksub#send_all")
                ]]
                await verify_user(client, userid, token)
                await client.send_message(LOG_CHANNEL_V, script.LOG_TEXT_V.format(message.from_user.id, message.from_user.mention, temp.U_NAME))
                await message.reply_text(
                    text=f"=> Hᴇʏ {message.from_user.mention}, Yᴏᴜ ᴀʀᴇ sᴜᴄᴄᴇssғᴜʟʟʏ\n🥰 🇻 🇪 🇷 🇮 🇫 🇮 🇪 🇩 🥰\n\nNᴏᴡ Yᴏᴜ Hᴀᴠᴇ Uɴʟɪᴍɪᴛᴇᴅ Mᴏᴠɪᴇs Dᴏᴡɴʟᴏᴀᴅɪɴɢ Aᴄᴄᴇss Fᴏʀ 𝟼 Hᴏᴜʀs Fʀᴏᴍ Nᴏᴡ.\n\n=> आप सफलतापूर्वक verify हो गए हैं, अब आपके पास 6 घंटे तक के लिए असीमित मूवी डाउनलोडिंग की सुविधा है।\n\n<b>#Verification_Completed 👍</b>",
                    protect_content=True,
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                return
            btn = [[
                InlineKeyboardButton("♻️ Get your File ♻️", url=f"https://telegram.me/{temp.U_NAME}?start=files_{fileid}")
            ]]
            await verify_user(client, userid, token)
            await client.send_message(LOG_CHANNEL_V, script.LOG_TEXT_V.format(message.from_user.id, message.from_user.mention, temp.U_NAME))
            await message.reply_text(
                text=f"=> Hᴇʏ {message.from_user.mention}, Yᴏᴜ ᴀʀᴇ sᴜᴄᴄᴇssғᴜʟʟʏ\n🥰 🇻 🇪 🇷 🇮 🇫 🇮 🇪 🇩 🥰\n\nNᴏᴡ Yᴏᴜ Hᴀᴠᴇ Uɴʟɪᴍɪᴛᴇᴅ Mᴏᴠɪᴇs Dᴏᴡɴʟᴏᴀᴅɪɴɢ Aᴄᴄᴇss Fᴏʀ 𝟼 Hᴏᴜʀs Fʀᴏᴍ Nᴏᴡ.\n\n=> आप सफलतापूर्वक verify हो गए हैं, अब आपके पास 6 घंटे तक के लिए असीमित मूवी डाउनलोडिंग की सुविधा है।\n\n<b>#Verification_Completed 👍</b>",
                protect_content=True,
                reply_markup=InlineKeyboardMarkup(btn)
            )
            return
        else:
            return await message.reply_text(
                text="<b>Invalid link or Expired link !</b>",
                protect_content=True
            )
            
                                   
    if data.startswith("sendfiles"):
        chat_id = int("-" + file_id.split("-")[1])
        userid = message.from_user.id if message.from_user else None
        g = await get_shortlink(chat_id, f"https://telegram.me/{temp.U_NAME}?start=allfiles_{file_id}")
        k = await client.send_message(chat_id=message.from_user.id,text=f"<b>Get All Files in a Single Click!!!\n\n📂 ʟɪɴᴋ ➠ : {g}\n\n<i>Note: This message is deleted in 3 mins to avoid copyrights. Save the link to Somewhere else\n\n यह मैसेज 3 मिनट में ऑटोमैटिक डिलीट हो जायेगा। \n लिंक को कही और सेव कर लीजिए।</i></b>\n\nDᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴅɪʀᴇᴄᴛ ғɪʟᴇs? Wɪᴛʜᴏᴜᴛ sᴇᴇɪɴɢ ᴀᴅᴠᴇʀᴛɪsᴇᴍᴇɴᴛs?\nTʜᴇɴ ᴄʟɪᴄᴋ ʜᴇʀᴇ /plan .\n\nक्या आपको डायरेक्ट फाइल्स चाहिएं ? बिना एडवरटाइजमेंट देंखे?,\nतो यहा क्लिक करें /plan", reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton('📂 Dᴏᴡɴʟᴏᴀᴅ Nᴏᴡ 📂', url=g)
                    ], [
                        InlineKeyboardButton('⁉️ Hᴏᴡ Tᴏ Dᴏᴡɴʟᴏᴀᴅ ⁉️', url=await get_tutorial(chat_id))
                    ]
                ]
            )
        )
        await asyncio.sleep(180)
        await k.edit("<b>Your message is successfully deleted!!!</b>")
        return
        
    
    elif data.startswith("short"):
        user = message.from_user.id
        chat_id = temp.SHORT.get(user)
        files_ = await get_file_details(file_id)
        files = files_[0]
        g = await get_shortlink(chat_id, f"https://telegram.me/{temp.U_NAME}?start=file_{file_id}")
        k = await client.send_message(chat_id=user,text=f"<b>📕Nᴀᴍᴇ ➠ : <code>{files.file_name}</code> \n\n🔗Sɪᴢᴇ ➠ : {get_size(files.file_size)}\n\n📂Fɪʟᴇ ʟɪɴᴋ ➠ : {g}\n\n<i>Note: This message is deleted in 3 mins to avoid copyrights. Save the link to Somewhere else\n\n यह मैसेज 3 मिनट में ऑटोमैटिक डिलीट हो जायेगा। \n लिंक को कही और सेव कर लीजिए।</i></b>\n\nDᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴅɪʀᴇᴄᴛ ғɪʟᴇs? Wɪᴛʜᴏᴜᴛ sᴇᴇɪɴɢ ᴀᴅᴠᴇʀᴛɪsᴇᴍᴇɴᴛs?\nTʜᴇɴ ᴄʟɪᴄᴋ ʜᴇʀᴇ /plan .\n\nक्या आपको डायरेक्ट फाइल्स चाहिएं ? बिना एडवरटाइजमेंट देंखे?,\nतो यहा क्लिक करें /plan", reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton('📂 Dᴏᴡɴʟᴏᴀᴅ Nᴏᴡ 📂', url=g)
                    ], [
                        InlineKeyboardButton('⁉️ Hᴏᴡ Tᴏ Dᴏᴡɴʟᴏᴀᴅ ⁉️', url=await get_tutorial(chat_id))
                    ]
                ]
            )
        )
        await asyncio.sleep(180)
        await k.edit("<b>Your message is successfully deleted!!!</b>")
        return
        
                
    elif data.startswith("all"):
        files = temp.GETALL.get(file_id)
        if not files:
            return await message.reply('<b><i>No such file exist.</b></i>')
        try:
            unjoined = await get_unjoined_channels(client, message.from_user.id)
        except Exception as e:
            logging.exception(f"get_unjoined_channels failed: {e}")
            unjoined = {"channels": [], "count": 0}
        if unjoined["channels"]:
            btn = []
            private_count = 1
            for ch in unjoined["channels"]:
                ch_id = ch["channel_id"]
                url = ch["url"]
                is_store = ch["is_store"]
                if is_store:
                    label = "Join Main Channel"
                else:
                    label = f"Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ {private_count} ♂️"
                    private_count += 1
                btn.append([InlineKeyboardButton(label, url=url)])
            # Add Continue button
            if message.text and message.text.startswith("/start") and len(message.command) > 1:
                try:
                    kk, file_id_temp = message.command[1].split("_", 1)
                    btn.append([InlineKeyboardButton(
                        "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                        url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                    )])
                except (IndexError, ValueError):
                    btn.append([InlineKeyboardButton(
                        "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                        url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                    )])
            await client.send_message(
                chat_id=message.from_user.id,
                text="⚠️ You must join the below channels to continue:",
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML
            )
            return
        filesarr = []
        for file in files:
            file_id = file.file_id
            files_ = await get_file_details(file_id)
            files1 = files_[0]
            title = ' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@'), files1.file_name.split()))
            size=get_size(files1.file_size)
            f_caption=files1.caption
            if CUSTOM_FILE_CAPTION:
                try:
                    f_caption=CUSTOM_FILE_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
                except Exception as e:
                    logger.exception(e)
                    f_caption=f_caption
            if f_caption is None:
                f_caption = f"{' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@'), files1.file_name.split()))}"
                
            if not await check_verification(client, message.from_user.id) and VERIFY == True:
                vrmsg = await message.reply_text(
                    text="Please Wait A While, Im Generating A Token For You...",
                    protect_content=True)
                    
                verify_url, tutorial_link = await get_token(client, message.from_user.id, f"https://telegram.me/{temp.U_NAME}?start=", file_id)
                if MIDVERIFY == True:
                    verify_url = verify_url.replace(":", '9cln')
                    verify_url = verify_url.replace("/", '9slsh')
                    verify_url = verify_url.replace(".", '9dot')
                    verify_url = verify_url.replace(" ", '-')
               
                    btn = [[
                        InlineKeyboardButton("𝗩𝗲𝗿𝗶𝗳𝘆 ♂️", url=f"https://t.me/{MEDIATOR_BOT}?start=midverify-{verify_url}")
                    ],[
                        InlineKeyboardButton('Hᴏᴡ Tᴏ Vᴇʀɪғʏ Tᴜᴛᴏʀɪᴀʟ 🎦', url=tutorial_link)
                    ]]      
                else:
                    btn = [[
                        InlineKeyboardButton(" 𝗩𝗲𝗿𝗶𝗳𝘆 ♂️", url=verify_url)
                    ],[
                        InlineKeyboardButton('Hᴏᴡ Tᴏ Vᴇʀɪғʏ Tᴜᴛᴏʀɪᴀʟ 🎦', url=tutorial_link)
                    ]]
                             
                await message.reply_text(
                    text="‣ <b><u>📕Fɪʟᴇ Nᴀᴍᴇ ➠</u> : Multiple Files</b>\n\n‣ <b>English:-</b>\nYᴏᴜ Aʀᴇ Nᴏᴛ Vᴇʀɪғɪᴇᴅ Tᴏᴅᴀʏ. Pʟᴇᴀsᴇ Vᴇʀɪғʏ Tᴏ Gᴇᴛ Uɴʟɪᴍɪᴛᴇᴅ Dᴏᴡɴʟᴏᴀᴅɪɴɢ Aᴄᴄᴇss Fᴏʀ 𝟼 Hᴏᴜʀs.\nWᴀɴᴛs ᴀ Dɪʀᴇᴄᴛ Fɪʟᴇ's ᴀɴᴅ Sᴛʀᴇᴀᴍ ғᴇᴀᴛᴜʀᴇ, Wɪᴛʜᴏᴜᴛ Vᴇʀɪғɪᴄᴀᴛɪᴏɴ ? Sᴇᴇ Oᴜʀ Pʀᴇᴍɪᴜᴍ Pʟᴀɴs\n👉 /plan .\n‣ Sᴇᴇ Yᴏᴜʀ Cᴜʀʀᴇɴᴛ Sᴜʙsᴄʀɪᴘᴛɪᴏɴ \n👉 /myplan\n\n‣ <b>हिंदी:-</b>\nआज आपने वेरीफाई नहीं किया हैं। कृपया 𝟼 घंटे के लिए असीमित डाउनलोडिंग एक्सेस प्राप्त करने के लिए वेरीफाई करें।\nबिना वेरीफाई के डायरेक्ट फ़ाइल और स्ट्रीम सुविधा चाहते है? तो हमारी प्रीमियम योजनाएँ देखें। \n👉 /plan\n‣ अपनी वर्तमान सदस्यता देखें। \n👉 /myplan\n\n‣ <b><u>Tʀᴀɴsʟᴀᴛᴇ Tʜɪs Mᴇssᴀɢᴇ ɪɴ :-</u> <a href='https://telegra.ph/%E0%AE%9A%E0%AE%B0%E0%AE%AA%E0%AE%B0%E0%AE%AA%E0%AE%AA-%E0%AE%B5%E0%AE%B4%E0%AE%AE%E0%AE%B1%E0%AE%95%E0%AE%B3-09-13'>தமிழ்</a> ll <a href='https://telegra.ph/%E0%B0%A7%E0%B0%B5%E0%B0%95%E0%B0%B0%E0%B0%A3-%E0%B0%B5%E0%B0%A7%E0%B0%A8%E0%B0%B2-09-13'>తెలుగు</a> ll <a href='https://telegra.ph/%E0%B4%B8%E0%B4%A5%E0%B4%B0%E0%B4%95%E0%B4%B0%E0%B4%A3-%E0%B4%A8%E0%B4%9F%E0%B4%AA%E0%B4%9F%E0%B4%95%E0%B4%B0%E0%B4%AE%E0%B4%99%E0%B4%99%E0%B5%BE-09-13'>മലയാളം</a></b>",
                    protect_content=True,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                await asyncio.sleep(1)
                await vrmsg.delete()
                return
                
            msg = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_id,
                caption=f_caption,
                protect_content=True if pre == 'filep' else False,
                reply_markup=InlineKeyboardMarkup(
                    [
                    [
                      InlineKeyboardButton('Sᴜᴘᴘᴏʀᴛ Gʀᴏᴜᴘ', url=GRP_LNK),
                      InlineKeyboardButton('Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ', url=CHNL_LNK)
                    ]
                    ]
                )
            )
            filesarr.append(msg)
            if AUTO_DELETE:
                asyncio.create_task(auto_delete_file(client, message.from_user.id, msg.id, message.from_user.id, f"allfiles_{file_id}"))
        if AUTO_DELETE:
            await client.send_message(message.from_user.id, "⚠️ **Auto Delete Alert:**\n\nThese files will be automatically deleted in **10 minutes** due to copyright issues. Save them quickly!")
      #  k = await client.send_message(chat_id = message.from_user.id, text=f"<b><u>❗️❗️❗️IMPORTANT❗️️❗️❗️</u></b>\n\nThis Movie Files/Videos will be deleted in <b><u>1 minutes</u> 🫥 <i></b>(Due to Copyright Issues)</i>.\n<b><i>Please forward this ALL Files/Videos to your Saved Messages and Start Download there</i></b>\n\nयह मूवी फ़ाइलें या वीडियो <i>(कॉपीराइट मुद्दों के कारण)</i> <b><u>2 मिनट में Delete</u> 🫥 <i></b> कर दी जाएंगी।\n\n<i><b>कृपया इन सभी फ़ाइलों या वीडियो को अपने <u>Saved Message</u> में <u>Forward</u> करें और वहां डाउनलोड प्रारंभ करें।</b></i>")
      #  await asyncio.sleep(60)
      #  for x in filesarr:
      #     await x.delete()
      #  await k.edit_text("<b>Your All Files/Videos is successfully deleted!!!</b>")
        return
        
    elif data.startswith("files"):
        user = message.from_user.id
        try:
            unjoined = await get_unjoined_channels(client, message.from_user.id)
        except Exception as e:
            logging.exception(f"get_unjoined_channels failed: {e}")
            unjoined = {"channels": [], "count": 0}
        if unjoined["channels"]:
            btn = []
            private_count = 1
            for ch in unjoined["channels"]:
                ch_id = ch["channel_id"]
                url = ch["url"]
                is_store = ch["is_store"]
                if is_store:
                    label = "Join Main Channel"
                else:
                    label = f"Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ {private_count} ♂️"
                    private_count += 1
                btn.append([InlineKeyboardButton(label, url=url)])
            # Add Continue button
            if message.text and message.text.startswith("/start") and len(message.command) > 1:
                try:
                    kk, file_id_temp = message.command[1].split("_", 1)
                    btn.append([InlineKeyboardButton(
                        "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                        url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                    )])
                except (IndexError, ValueError):
                    btn.append([InlineKeyboardButton(
                        "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                        url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                    )])
            await client.send_message(
                chat_id=message.from_user.id,
                text="⚠️ You must join the below channels to continue:",
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML
            )
            return
        if temp.SHORT.get(user)==None:
            await message.reply_text(text="<b>This is not your requested movies\nPlease Request Your Owen Movies\n\nयह किसी और के द्वारा रिक्वेस्ट की गई मूवी है \nकृपया खुद से रिक्वेस्ट करें।</b>")
        else:
            chat_id = temp.SHORT.get(user)
        settings = await get_settings(chat_id)
        if not await db.has_premium_access(user) and settings['is_shortlink']: #added premium membership check 
            files_ = await get_file_details(file_id)
            files = files_[0]
            g = await get_shortlink(chat_id, f"https://telegram.me/{temp.U_NAME}?start=file_{file_id}")
            k = await client.send_message(chat_id=message.from_user.id,text=f"<b>📕Nᴀᴍᴇ ➠ : <code>{files.file_name}</code> \n\n🔗Sɪᴢᴇ ➠ : {get_size(files.file_size)}\n\n📂Fɪʟᴇ ʟɪɴᴋ ➠ : {g}\n\n<i>Note: This message is deleted in 3 mins to avoid copyrights. Save the link to Somewhere else\n\n यह मैसेज 3 मिनट में ऑटोमैटिक डिलीट हो जायेगा। \n लिंक को कही और सेव कर लीजिए।</i></b>\n\nDᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴅɪʀᴇᴄᴛ ғɪʟᴇs? Wɪᴛʜᴏᴜᴛ sᴇᴇɪɴɢ ᴀᴅᴠᴇʀᴛɪsᴇᴍᴇɴᴛs?\nTʜᴇɴ ᴄʟɪᴄᴋ ʜᴇʀᴇ /plan .\n\nक्या आपको डायरेक्ट फाइल्स चाहिएं ? बिना एडवरटाइजमेंट देंखे?,\nतो यहा क्लिक करें /plan", reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton('📂 Dᴏᴡɴʟᴏᴀᴅ Nᴏᴡ 📂', url=g)
                        ], [
                            InlineKeyboardButton('⁉️ Hᴏᴡ Tᴏ Dᴏᴡɴʟᴏᴀᴅ ⁉️', url=await get_tutorial(chat_id))
                        ]
                    ]
                )
            )
            await asyncio.sleep(180)
            await k.edit("<b>Your message is successfully deleted!!!</b>")
            return

        if AUTO_DELETE:
            asyncio.create_task(auto_delete_file(client, message.from_user.id, msg.id, message.from_user.id, f"file_{file_id}"))

    user = message.from_user.id
    files_ = await get_file_details(file_id)
    if not files_:
        pre, file_id = ((base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")).split("_", 1)
        try:
            try:
                unjoined = await get_unjoined_channels(client, message.from_user.id)
            except Exception as e:
                logging.exception(f"get_unjoined_channels failed: {e}")
                unjoined = {"channels": [], "count": 0}
            if unjoined["channels"]:
                btn = []
                private_count = 1
                for ch in unjoined["channels"]:
                    ch_id = ch["channel_id"]
                    url = ch["url"]
                    is_store = ch["is_store"]
                    if is_store:
                        label = "Join Main Channel"
                    else:
                        label = f"Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ {private_count} ♂️"
                        private_count += 1
                    btn.append([InlineKeyboardButton(label, url=url)])
                # Add Continue button
                if message.text and message.text.startswith("/start") and len(message.command) > 1:
                    try:
                        kk, file_id_temp = message.command[1].split("_", 1)
                        btn.append([InlineKeyboardButton(
                            "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                            url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                        )])
                    except (IndexError, ValueError):
                        btn.append([InlineKeyboardButton(
                            "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                            url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                        )])
                await client.send_message(
                    chat_id=message.from_user.id,
                    text="⚠️ You must join the below channels to continue:",
                    reply_markup=InlineKeyboardMarkup(btn),
                    parse_mode=enums.ParseMode.HTML
                )
                return
            if not await check_verification(client, message.from_user.id) and VERIFY == True:
                vrmsg = await message.reply_text(
                    text="Please Wait A While, Im Generating A Token For You...",
                    protect_content=True)
                    
                verify_url, tutorial_link = await get_token(client, message.from_user.id, f"https://telegram.me/{temp.U_NAME}?start=", file_id)
                if MIDVERIFY == True:
                    verify_url = verify_url.replace(":", '9cln')
                    verify_url = verify_url.replace("/", '9slsh')
                    verify_url = verify_url.replace(".", '9dot')
                    verify_url = verify_url.replace(" ", '-')
                
                    btn = [[
                        InlineKeyboardButton("𝗩𝗲𝗿𝗶𝗳𝘆 ♂️", url=f"https://t.me/{MEDIATOR_BOT}?start=midverify-{verify_url}")
                    ],[
                        InlineKeyboardButton('Hᴏᴡ Tᴏ Vᴇʀɪғʏ Tᴜᴛᴏʀɪᴀʟ 🎦', url=tutorial_link)
                    ]]         
                else:      
                    btn = [[
                        InlineKeyboardButton(" 𝗩𝗲𝗿𝗶𝗳𝘆 ♂️", url=verify_url)
                    ],[
                        InlineKeyboardButton('Hᴏᴡ Tᴏ Vᴇʀɪғʏ Tᴜᴛᴏʀɪᴀʟ 🎦', url=tutorial_link)
                    ]]
                #    Check if the file name exists
                file_name_text = f"‣ <b><u>📕Fɪʟᴇ Nᴀᴍᴇ ➠</u> : {files_.file_name}</b>\n\n" if files_ and hasattr(files_, 'file_name') else "<b><u>Yᴏᴜ Nᴇᴇᴅ Tᴏ Vᴇʀɪғʏ Fᴏʀ Tʜᴀᴛ Fɪʟᴇ</u></b>\n\n"
                await message.reply_text(
                    text=f"{file_name_text}‣ <b>English:-</b>\nYᴏᴜ Aʀᴇ Nᴏᴛ Vᴇʀɪғɪᴇᴅ Tᴏᴅᴀʏ. Pʟᴇᴀsᴇ Vᴇʀɪғʏ Tᴏ Gᴇᴛ Uɴʟɪᴍɪᴛᴇᴅ Dᴏᴡɴʟᴏᴀᴅɪɴɢ Aᴄᴄᴇss Fᴏʀ 𝟼 Hᴏᴜʀs.\nWᴀɴᴛs ᴀ Dɪʀᴇᴄᴛ Fɪʟᴇ's ᴀɴᴅ Sᴛʀᴇᴀᴍ ғᴇᴀᴛᴜʀᴇ, Wɪᴛʜᴏᴜᴛ Vᴇʀɪғɪᴄᴀᴛɪᴏɴ? Sᴇᴇ Oᴜʀ Pʀᴇᴍɪᴜᴍ Pʟᴀɴs\n👉 /plan .\n‣ Sᴇᴇ Yᴏᴜʀ Cᴜʀʀᴇɴᴛ Sᴜʙsᴄʀɪᴘᴛɪᴏɴ \n👉 /myplan\n\n‣ <b>हिंदी:-</b>\nआज आपने वेरीफाई नहीं किया हैं। कृपया 𝟼 घंटे के लिए असीमित डाउनलोडिंग एक्सेस प्राप्त करने के लिए वेरीफाई करें।\nबिना वेरीफाई के डायरेक्ट फ़ाइल और स्ट्रीम सुविधा चाहते है? तो हमारी प्रीमियम योजनाएँ देखें। \n👉 /plan\n‣ अपनी वर्तमान सदस्यता देखें। \n👉 /myplan\n\n‣ <b><u>Tʀᴀɴsʟᴀᴛᴇ Tʜɪs Mᴇssᴀɢᴇ ɪɴ :-</u>  <a href='https://telegra.ph/%E0%AE%9A%E0%AE%B0%E0%AE%AA%E0%AE%B0%E0%AE%AA%E0%AE%AA-%E0%AE%B5%E0%AE%B4%E0%AE%AE%E0%AE%B1%E0%AE%95%E0%AE%B3-09-13'>தமிழ்</a> ll <a href='https://telegra.ph/%E0%B0%A7%E0%B0%B5%E0%B0%95%E0%B0%B0%E0%B0%A3-%E0%B0%B5%E0%B0%A7%E0%B0%A8%E0%B0%B2-09-13'>తెలుగు</a> ll <a href='https://telegra.ph/%E0%B4%B8%E0%B4%A5%E0%B4%B0%E0%B4%95%E0%B4%B0%E0%B4%A3-%E0%B4%A8%E0%B4%9F%E0%B4%AA%E0%B4%9F%E0%B4%95%E0%B4%B0%E0%B4%AE%E0%B4%99%E0%B4%99%E0%B5%BE-09-13'>മലയാളം</a></b>",
                    protect_content=True,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                await asyncio.sleep(1)
                await vrmsg.delete()
                return
                
            msg = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_id,
                protect_content=True if pre == 'filep' else False,
            )
            filetype = msg.media
            file = getattr(msg, filetype.value)
            title = '@epiccinemanearme  ' + ' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@'), file.file_name.split()))
            size = get_size(file.file_size)
            f_caption = f"<code>{title}</code>"
            if CUSTOM_FILE_CAPTION:
                try:
                    f_caption = CUSTOM_FILE_CAPTION.format(file_name='' if title is None else title, file_size='' if size is None else size, file_caption='')
                except:
                    return
            
            await msg.edit_caption(
                caption=f_caption
            )
            if AUTO_DELETE:
                asyncio.create_task(auto_delete_file(client, message.from_user.id, msg.id, message.from_user.id, f"file_{file_id}"))
                await client.send_message(message.from_user.id, "⚠️ **Auto Delete Alert:**\n\nThis file will be automatically deleted in **10 minutes** due to copyright issues. Save it quickly!")
            btn = [[
                InlineKeyboardButton("Get File Again", callback_data=f'delfile   {file_id}')
            ]]
        except Exception as e:
            print(f"An error occurred: {e}")        
         #   k = await msg.reply("<b><u>❗️❗️❗️IMPORTANT❗️️❗️❗️</u></b>\n\nThis Movie Files/Videos will be deleted in <b><u>1 minutes</u> 🫥 <i></b>(Due to Copyright Issues)</i>.\n<b><i>Please forward this ALL Files/Videos to your Saved Messages and Start Download there</i></b>\n\nयह मूवी फ़ाइलें या वीडियो <i>(कॉपीराइट मुद्दों के कारण)</i> <b><u>2 मिनट में Delete</u> 🫥 <i></b> कर दी जाएंगी।\n\n<i><b>कृपया इन सभी फ़ाइलों या वीडियो को अपने <u>Saved Message</u> में <u>Forward</u> करें और वहां डाउनलोड प्रारंभ करें।</b></i>",quote=True)
           # await asyncio.sleep(60)
         #   await msg.delete()
         #   await k.edit_text("<b>Your File/Video is successfully deleted!!!\n\nClick below button to get your deleted file 👇</b>\n\nआपकी फ़ाइल या वीडियो सफलता पूर्वक Delete कर दी गयी है।\n\nअपनी डिलीट की गई फ़ाइल पुनः प्राप्त करने के लिए नीचे दिए गए बटन पर क्लिक करें",reply_markup=InlineKeyboardMarkup(btn)) 
         #   return 
     #   except:
      #      pass
        return await message.reply('ThankYou❤️.')
    files = files_[0]
    title = '@epiccinemanearme  ' + ' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@'), files.file_name.split()))
    size=get_size(files.file_size)
    f_caption=files.caption
    if CUSTOM_FILE_CAPTION:
        try:
            f_caption=CUSTOM_FILE_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
        except Exception as e:
            logger.exception(e)
            f_caption=f_caption
    if f_caption is None:
        f_caption = f"@epiccinemanearme  {' '.join(filter(lambda x: not x.startswith('[') and not x.startswith('@'), files.file_name.split()))}"
    try:
        unjoined = await get_unjoined_channels(client, message.from_user.id)
    except Exception as e:
        logging.exception(f"get_unjoined_channels failed: {e}")
        unjoined = {"channels": [], "count": 0}
    if unjoined["channels"]:
        btn = []
        private_count = 1
        for ch in unjoined["channels"]:
            ch_id = ch["channel_id"]
            url = ch["url"]
            is_store = ch["is_store"]
            if is_store:
                label = "Join Main Channel"
            else:
                label = f"Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ {private_count} ♂️"
                private_count += 1
            btn.append([InlineKeyboardButton(label, url=url)])
        # Add Continue button
        if message.text and message.text.startswith("/start") and len(message.command) > 1:
            try:
                kk, file_id_temp = message.command[1].split("_", 1)
                btn.append([InlineKeyboardButton(
                    "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                    url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                )])
            except (IndexError, ValueError):
                btn.append([InlineKeyboardButton(
                    "𝐂𝐨𝐧𝐭𝐢ɴᴜᴇ 𝐓ᴏ 𝐃ᴏᴡɴʟᴏᴀᴅ ♂️",
                    url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}"
                )])
        await client.send_message(
            chat_id=message.from_user.id,
            text="⚠️ You must join the below channels to continue:",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode=enums.ParseMode.HTML
        )
        return
    if not await check_verification(client, message.from_user.id) and VERIFY == True:
        vrmsg = await message.reply_text(
            text="Please Wait A While, Im Generating A Token For You...",
            protect_content=True)
                                        
        verify_url, tutorial_link = await get_token(client, message.from_user.id, f"https://telegram.me/{temp.U_NAME}?start=", file_id)                
        if MIDVERIFY == True:
            verify_url = verify_url.replace(":", '9cln')
            verify_url = verify_url.replace("/", '9slsh')
            verify_url = verify_url.replace(".", '9dot')
            verify_url = verify_url.replace(" ", '-')
                
            btn = [[
                InlineKeyboardButton("𝗩𝗲𝗿𝗶𝗳𝘆 ♂️", url=f"https://t.me/{MEDIATOR_BOT}?start=midverify-{verify_url}")
            ],[
                InlineKeyboardButton('Hᴏᴡ Tᴏ Vᴇʀɪғʏ Tᴜᴛᴏʀɪᴀʟ 🎦', url=tutorial_link)
            ]]           
        else:    
            btn = [[
                InlineKeyboardButton(" 𝗩𝗲𝗿𝗶𝗳𝘆 ♂️", url=verify_url)
            ],[
                InlineKeyboardButton('Hᴏᴡ Tᴏ Vᴇʀɪғʏ Tᴜᴛᴏʀɪᴀʟ 🎦', url=tutorial_link)
            ]]
                
        await message.reply_text(
                    text=f"‣ <b><u>📕Fɪʟᴇ Nᴀᴍᴇ ➠</u> : {files.file_name}</b>\n\n‣ <b>English:-</b>\nYᴏᴜ Aʀᴇ Nᴏᴛ Vᴇʀɪғɪᴇᴅ Tᴏᴅᴀʏ. Pʟᴇᴀsᴇ Vᴇʀɪғʏ Tᴏ Gᴇᴛ Uɴʟɪᴍɪᴛᴇᴅ Dᴏᴡɴʟᴏᴀᴅɪɴɢ Aᴄᴄᴇss Fᴏʀ 𝟼 Hᴏᴜʀs.\nWᴀɴᴛs ᴀ Dɪʀᴇᴄᴛ Fɪʟᴇ's ᴀɴᴅ Sᴛʀᴇᴀᴍ ғᴇᴀᴛᴜʀᴇ, Wɪᴛʜᴏᴜᴛ Vᴇʀɪғɪᴄᴀᴛɪᴏɴ ? Sᴇᴇ Oᴜʀ Pʀᴇᴍɪᴜᴍ Pʟᴀɴs\n👉 /plan .\n‣ Sᴇᴇ Yᴏᴜʀ Cᴜʀʀᴇɴᴛ Sᴜʙsᴄʀɪᴘᴛɪᴏɴ \n👉 /myplan\n\n‣ <b>हिंदी:-</b>\nआज आपने वेरीफाई नहीं किया हैं। कृपया 𝟼 घंटे के लिए असीमित डाउनलोडिंग एक्सेस प्राप्त करने के लिए वेरीफाई करें।\nबिना वेरीफाई के डायरेक्ट फ़ाइल और स्ट्रीम सुविधा चाहते है? तो हमारी प्रीमियम योजनाएँ देखें। \n👉 /plan\n‣ अपनी वर्तमान सदस्यता देखें। \n👉 /myplan\n\n‣ <b><u>Tʀᴀɴsʟᴀᴛᴇ Tʜɪs Mᴇssᴀɢᴇ ɪɴ :-</u>  <a href='https://telegra.ph/%E0%AE%9A%E0%AE%B0%E0%AE%AA%E0%AE%B0%E0%AE%AA%E0%AE%AA-%E0%AE%B5%E0%AE%B4%E0%AE%AE%E0%AE%B1%E0%AE%95%E0%AE%B3-09-13'>தமிழ்</a> ll <a href='https://telegra.ph/%E0%B0%A7%E0%B0%B5%E0%B0%95%E0%B0%B0%E0%B0%A3-%E0%B0%B5%E0%B0%A7%E0%B0%A8%E0%B0%B2-09-13'>తెలుగు</a> ll <a href='https://telegra.ph/%E0%B4%B8%E0%B4%A5%E0%B4%B0%E0%B4%95%E0%B4%B0%E0%B4%A3-%E0%B4%A8%E0%B4%9F%E0%B4%AA%E0%B4%9F%E0%B4%95%E0%B4%B0%E0%B4%AE%E0%B4%99%E0%B4%99%E0%B5%BE-09-13'>മലയാളം</a></b>",
            protect_content=True,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(btn)
        )
        await asyncio.sleep(1)
        await vrmsg.delete()
        return
        
    msg = await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        protect_content=True if pre == 'filep' else False
        
    )
    btn = [[
        InlineKeyboardButton("Get File Again", callback_data=f'delfile#{file_id}')
    ]]
   # k = await msg.reply("<b><u>❗️❗️❗️IMPORTANT❗️️❗️❗️</u></b>\n\nThis Movie Files/Videos will be deleted in <b><u>1 minutes</u> 🫥 <i></b>(Due to Copyright Issues)</i>.\n<b><i>Please forward this ALL Files/Videos to your Saved Messages and Start Download there</i></b>\n\nयह मूवी फ़ाइलें या वीडियो <i>(कॉपीराइट मुद्दों के कारण)</i> <b><u>2 मिनट में Delete</u> 🫥 <i></b> कर दी जाएंगी।\n\n<i><b>कृपया इन सभी फ़ाइलों या वीडियो को अपने <u>Saved Message</u> में <u>Forward</u> करें और वहां डाउनलोड प्रारंभ करें।</b></i>",quote=True)
   # await asyncio.sleep(60)
   # await msg.delete()
   # await k.edit_text("<b>Your File/Video is successfully deleted!!!\n\nClick below button to get your deleted file 👇</b>\n\nआपकी फ़ाइल या वीडियो सफलता पूर्वक Delete कर दी गयी है।\n\nअपनी डिलीट की गई फ़ाइल पुनः प्राप्त करने के लिए नीचे दिए गए बटन पर क्लिक करें",reply_markup=InlineKeyboardMarkup(btn)) 
    return   



@Client.on_message(filters.command('channel') & filters.user(ADMINS))
async def channel_info(bot, message):
           
    """Send basic information of channel"""
    if isinstance(CHANNELS, (int, str)):
        channels = [CHANNELS]
    elif isinstance(CHANNELS, list):
        channels = CHANNELS
    else:
        raise ValueError("Unexpected type of CHANNELS")

    text = '📑 **Indexed channels/groups**\n'
    for channel in channels:
        chat = await bot.get_chat(channel)
        if chat.username:
            text += '\n@' + chat.username
        else:
            text += '\n' + chat.title or chat.first_name

    text += f'\n\n**Total:** {len(CHANNELS)}'

    if len(text) < 4096:
        await message.reply(text)
    else:
        file = 'Indexed channels.txt'
        with open(file, 'w') as f:
            f.write(text)
        await message.reply_document(file)
        os.remove(file)


@Client.on_message(filters.command('logs') & filters.user(ADMINS))
async def log_file(bot, message):
    """Send log file"""
    try:
        await message.reply_document('TELEGRAM BOT.LOG')
    except Exception as e:
        await message.reply(str(e))

@Client.on_message(filters.command('delete') & filters.user(ADMINS))
async def delete(bot, message):
    """Delete file from database"""
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("Processing...⏳", quote=True)
    else:
        await message.reply('Reply to file with /delete which you want to delete', quote=True)
        return

    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit('This is not supported file format')
        return
    
    file_id, file_ref = unpack_new_file_id(media.file_id)

    result = await Media.collection.delete_one({
        '_id': file_id,
    })
    if result.deleted_count:
        await msg.edit('File is successfully deleted from database')
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        result = await Media.collection.delete_many({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
            })
        if result.deleted_count:
            await msg.edit('File is successfully deleted from database')
        else:
            # files indexed before https://github.com/EvamariaTG/EvaMaria/commit/f3d2a1bcb155faf44178e5d7a685a1b533e714bf#diff-86b613edf1748372103e94cacff3b578b36b698ef9c16817bb98fe9ef22fb669R39 
            # have original file name.
            result = await Media.collection.delete_many({
                'file_name': media.file_name,
                'file_size': media.file_size,
                'mime_type': media.mime_type
            })
            if result.deleted_count:
                await msg.edit('File is successfully deleted from database')
            else:
                await msg.edit('File not found in database')


@Client.on_message(filters.command('deleteall') & filters.user(ADMINS))
async def delete_all_index(bot, message):
    await message.reply_text(
        'This will delete all indexed files.\nDo you want to continue??',
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="YES", callback_data="autofilter_delete"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="CANCEL", callback_data="close_data"
                    )
                ],
            ]
        ),
        quote=True,
    )


@Client.on_callback_query(filters.regex(r'^autofilter_delete'))
async def delete_all_index_confirm(bot, message):
    await Media.collection.drop()
    await message.answer('Piracy Is Crime')
    await message.message.edit('Succesfully Deleted All The Indexed Files.')


@Client.on_message(filters.command('settings'))
async def settings(client, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(f"You are anonymous admin. Use /connect {message.chat.id} in PM")
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        grpid = await active_connection(str(userid))
        if grpid is not None:
            grp_id = grpid
            try:
                chat = await client.get_chat(grpid)
                title = chat.title
            except:
                await message.reply_text("Make sure I'm present in your group!!", quote=True)
                return
        else:
            await message.reply_text("I'm not connected to any groups!", quote=True)
            return

    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grp_id = message.chat.id
        title = message.chat.title

    else:
        return

    st = await client.get_chat_member(grp_id, userid)
    if (
            st.status != enums.ChatMemberStatus.ADMINISTRATOR
            and st.status != enums.ChatMemberStatus.OWNER
            and str(userid) not in ADMINS
    ):
        return
    
    settings = await get_settings(grp_id)

    try:
        if settings['max_btn']:
            settings = await get_settings(grp_id)
    except KeyError:
        await save_group_settings(grp_id, 'max_btn', False)
        settings = await get_settings(grp_id)
    if 'is_shortlink' not in settings.keys():
        await save_group_settings(grp_id, 'is_shortlink', False)
    else:
        pass

    if settings is not None:
        buttons = [
            [
                InlineKeyboardButton(
                    'Rᴇsᴜʟᴛ Pᴀɢᴇ',
                    callback_data=f'setgs#button#{settings["button"]}#{grp_id}',
                ),
                InlineKeyboardButton(
                    'Bᴜᴛᴛᴏɴ' if settings["button"] else 'Tᴇxᴛ',
                    callback_data=f'setgs#button#{settings["button"]}#{grp_id}',
                ),
            ],
            [
                InlineKeyboardButton(
                    'Aᴜᴛᴏ-Fɪʟᴛᴇʀ',
                    callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}',
                ),
                InlineKeyboardButton(
                    '✔ Oɴ' if settings["auto_ffilter"] else '✘ Oғғ',
                    callback_data=f'setgs#auto_ffilter#{settings["auto_ffilter"]}#{grp_id}',
                ),
            ],
            [
                InlineKeyboardButton(
                    'Mᴀx Bᴜᴛᴛᴏɴs',
                    callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}',
                ),
                InlineKeyboardButton(
                    '10' if settings["max_btn"] else f'{MAX_B_TN}',
                    callback_data=f'setgs#max_btn#{settings["max_btn"]}#{grp_id}',
                ),
            ]
        ]

        btn = [[
                InlineKeyboardButton("Oᴘᴇɴ Hᴇʀᴇ ↓", callback_data=f"opnsetgrp#{grp_id}"),
                InlineKeyboardButton("Oᴘᴇɴ Iɴ PM ⇲", callback_data=f"opnsetpm#{grp_id}")
              ]]

        reply_markup = InlineKeyboardMarkup(buttons)
        if chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
            await message.reply_text(
                text="<b>Dᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴏᴘᴇɴ sᴇᴛᴛɪɴɢs ʜᴇʀᴇ ?</b>",
                reply_markup=InlineKeyboardMarkup(btn),
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML,
                reply_to_message_id=message.id
            )
        else:
            await message.reply_text(
                text=f"<b>Cʜᴀɴɢᴇ Yᴏᴜʀ Sᴇᴛᴛɪɴɢs Fᴏʀ {title} As Yᴏᴜʀ Wɪsʜ ⚙</b>",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                parse_mode=enums.ParseMode.HTML,
                reply_to_message_id=message.id
            )



@Client.on_message(filters.command('set_template'))
async def save_template(client, message):
    sts = await message.reply("Checking template")
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply(f"You are anonymous admin. Use /connect {message.chat.id} in PM")
    chat_type = message.chat.type

    if chat_type == enums.ChatType.PRIVATE:
        grpid = await active_connection(str(userid))
        if grpid is not None:
            grp_id = grpid
            try:
                chat = await client.get_chat(grpid)
                title = chat.title
            except:
                await message.reply_text("Make sure I'm present in your group!!", quote=True)
                return
        else:
            await message.reply_text("I'm not connected to any groups!", quote=True)
            return

    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grp_id = message.chat.id
        title = message.chat.title

    else:
        return

    st = await client.get_chat_member(grp_id, userid)
    if (
            st.status != enums.ChatMemberStatus.ADMINISTRATOR
            and st.status != enums.ChatMemberStatus.OWNER
            and str(userid) not in ADMINS
    ):
        return

    if len(message.command) < 2:
        return await sts.edit("No Input!!")
    template = message.text.split(" ", 1)[1]
    await save_group_settings(grp_id, 'template', template)
    await sts.edit(f"Successfully changed template for {title} to\n\n{template}")


@Client.on_message((filters.command(["request", "Request"]) | filters.regex("#request") | filters.regex("#Request")) & filters.group)
async def requests(bot, message):
    if REQST_CHANNEL is None or SUPPORT_CHAT_ID is None: return # Must add REQST_CHANNEL and SUPPORT_CHAT_ID to use this feature
    if message.reply_to_message and SUPPORT_CHAT_ID == message.chat.id:
        chat_id = message.chat.id
        reporter = str(message.from_user.id)
        mention = message.from_user.mention
        success = True
        content = message.reply_to_message.text
        try:
            if REQST_CHANNEL is not None:
                btn = [[
                        InlineKeyboardButton('View Request', url=f"{message.reply_to_message.link}"),
                        InlineKeyboardButton('Show Options', callback_data=f'show_option#{reporter}')
                      ]]
                reported_post = await bot.send_message(chat_id=REQST_CHANNEL, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                success = True
            elif len(content) >= 3:
                for admin in ADMINS:
                    btn = [[
                        InlineKeyboardButton('View Request', url=f"{message.reply_to_message.link}"),
                        InlineKeyboardButton('Show Options', callback_data=f'show_option#{reporter}')
                      ]]
                    reported_post = await bot.send_message(chat_id=admin, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                    success = True
            else:
                if len(content) < 3:
                    await message.reply_text("<b>You must type about your request [Minimum 3 Characters]. Requests can't be empty.</b>")
            if len(content) < 3:
                success = False
        except Exception as e:
            await message.reply_text(f"Error: {e}")
            pass
        
    elif SUPPORT_CHAT_ID == message.chat.id:
        chat_id = message.chat.id
        reporter = str(message.from_user.id)
        mention = message.from_user.mention
        success = True
        content = message.text
        keywords = ["#request", "/request", "#Request", "/Request"]
        for keyword in keywords:
            if keyword in content:
                content = content.replace(keyword, "")
        try:
            if REQST_CHANNEL is not None and len(content) >= 3:
                btn = [[
                        InlineKeyboardButton('View Request', url=f"{message.link}"),
                        InlineKeyboardButton('Show Options', callback_data=f'show_option#{reporter}')
                      ]]
                reported_post = await bot.send_message(chat_id=REQST_CHANNEL, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                success = True
            elif len(content) >= 3:
                for admin in ADMINS:
                    btn = [[
                        InlineKeyboardButton('View Request', url=f"{message.link}"),
                        InlineKeyboardButton('Show Options', callback_data=f'show_option#{reporter}')
                      ]]
                    reported_post = await bot.send_message(chat_id=admin, text=f"<b>𝖱𝖾𝗉𝗈𝗋𝗍𝖾𝗋 : {mention} ({reporter})\n\n𝖬𝖾𝗌𝗌𝖺𝗀𝖾 : {content}</b>", reply_markup=InlineKeyboardMarkup(btn))
                    success = True
            else:
                if len(content) < 3:
                    await message.reply_text("<b>You must type about your request [Minimum 3 Characters]. Requests can't be empty.</b>")
            if len(content) < 3:
                success = False
        except Exception as e:
            await message.reply_text(f"Error: {e}")
            pass

    else:
        success = False
    
    if success:
        '''if isinstance(REQST_CHANNEL, (int, str)):
            channels = [REQST_CHANNEL]
        elif isinstance(REQST_CHANNEL, list):
            channels = REQST_CHANNEL
        for channel in channels:
            chat = await bot.get_chat(channel)
        #chat = int(chat)'''
        link = await bot.create_chat_invite_link(int(REQST_CHANNEL))
        btn = [[
                InlineKeyboardButton('Join Channel', url=link.invite_link),
                InlineKeyboardButton('View Request', url=f"{reported_post.link}")
              ]]
        await message.reply_text("<b>Your request has been added! Please wait for some time.\n\nJoin Channel First & View Request</b>", reply_markup=InlineKeyboardMarkup(btn))
    
@Client.on_message(filters.command("send") & filters.user(ADMINS))
async def send_msg(bot, message):
    if message.reply_to_message:
        target_id = message.text.split(" ", 1)[1]
        out = "Users Saved In DB Are:\n\n"
        success = False
        try:
            user = await bot.get_users(target_id)
            users = await db.get_all_users()
            async for usr in users:
                out += f"{usr['id']}"
                out += '\n'
            if str(user.id) in str(out):
                await message.reply_to_message.copy(int(user.id))
                success = True
            else:
                success = False
            if success:
                await message.reply_text(f"<b>Your message has been successfully send to {user.mention}.</b>")
            else:
                await message.reply_text("<b>This user didn't started this bot yet !</b>")
        except Exception as e:
            await message.reply_text(f"<b>Error: {e}</b>")
    else:
        await message.reply_text("<b>Use this command as a reply to any message using the target chat id. For eg: /send userid</b>")

@Client.on_message(filters.command("deletefiles") & filters.user(ADMINS))
async def deletemultiplefiles(bot, message):
    chat_type = message.chat.type
    if chat_type != enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, This command won't work in groups. It only works on my PM !</b>")
    else:
        pass
    try:
        keyword = message.text.split(" ", 1)[1]
    except:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, Give me a keyword along with the command to delete files.</b>")
    k = await bot.send_message(chat_id=message.chat.id, text=f"<b>Fetching Files for your query {keyword} on DB... Please wait...</b>")
    files, total = await get_bad_files(keyword)
    await k.delete()
    #await k.edit_text(f"<b>Found {total} files for your query {keyword} !\n\nFile deletion process will start in 5 seconds !</b>")
    #await asyncio.sleep(5)
    btn = [[
       InlineKeyboardButton("Yes, Continue !", callback_data=f"killfilesdq#{keyword}")
       ],[
       InlineKeyboardButton("No, Abort operation !", callback_data="close_data")
    ]]
    await message.reply_text(
        text=f"<b>Found {total} files for your query {keyword} !\n\nDo you want to delete?</b>",
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_message(filters.command("shortlink"))
async def shortlink(bot, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply("You are anonymous admin. Turn off anonymous admin and try again this command")
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, This command only works on groups !\n\n<u>Follow These Steps to Connect Shortener:</u>\n\n1. Add Me in Your Group with Full Admin Rights\n\n2. After Adding in Grp, Set your Shortener\n\nSend this command in your group\n\n—> /shortlink ""{your_shortener_website_name} {your_shortener_api}\n\n#Sample:-\n/shortlink earnpro.in 67b0a56787476eef44423f101e753f3af7377a44\n\nThat's it!!! Enjoy Earning Money 💲\n\n[[[ Trusted Earning Site - https://earnpro.in]]]\n\nIf you have any Doubts, Feel Free to Ask me - @presood </b>")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    data = message.text
    userid = message.from_user.id
    user = await bot.get_chat_member(grpid, userid)
    if user.status != enums.ChatMemberStatus.ADMINISTRATOR and user.status != enums.ChatMemberStatus.OWNER and str(userid) not in ADMINS:
        return await message.reply_text("<b>You don't have access to use this command!\n\nAdd Me to Your Own Group as Admin and Try This Command\n\nFor More PM Me With This Command</b>")
    else:
        pass
    try:
        command, shortlink_url, api = data.split(" ")
    except:
        return await message.reply_text("<b>Command Incomplete :(\n\nGive me a shortener website link and api along with the command !\n\nFormat: <code>/shortlink earnpro.in 67b0a56787476eef44423f101e753f3af7377a44</code></b>")
    reply = await message.reply_text("<b>Please Wait...</b>")
    shortlink_url = re.sub(r"https?://?", "", shortlink_url)
    shortlink_url = re.sub(r"[:/]", "", shortlink_url)
    await save_group_settings(grpid, 'shortlink', shortlink_url)
    await save_group_settings(grpid, 'shortlink_api', api)
    await save_group_settings(grpid, 'is_shortlink', True)
    await reply.edit_text(f"<b>Successfully added shortlink API for {title}.\n\nCurrent Shortlink Website: <code>{shortlink_url}</code>\nCurrent API: <code>{api}</code></b>")
    
@Client.on_message(filters.command("setshortlinkoff"))
async def offshortlink(bot, message):
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text("I will Work Only in group")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    await save_group_settings(grpid, 'is_shortlink', False)
    # ENABLE_SHORTLINK = False
    return await message.reply_text("Successfully disabled shortlink")
    
@Client.on_message(filters.command("setshortlinkon"))
async def onshortlink(bot, message):
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text("I will Work Only in group")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    await save_group_settings(grpid, 'is_shortlink', True)
    # ENABLE_SHORTLINK = True
    return await message.reply_text("Successfully enabled shortlink")

@Client.on_message(filters.command("shortlink_info"))
async def showshortlink(bot, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply("You are anonymous admin. Turn off anonymous admin and try again this command")
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text(f"<b>Hey {message.from_user.mention}, This Command Only Works in Group\n\nTry this command in your own group, if you are using me in your group</b>")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    chat_id=message.chat.id
    userid = message.from_user.id
    user = await bot.get_chat_member(grpid, userid)
#     if 'shortlink' in settings.keys():
#         su = settings['shortlink']
#         sa = settings['shortlink_api']
#     else:
#         return await message.reply_text("<b>Shortener Url Not Connected\n\nYou can Connect Using /shortlink command</b>")
#     if 'tutorial' in settings.keys():
#         st = settings['tutorial']
#     else:
#         return await message.reply_text("<b>Tutorial Link Not Connected\n\nYou can Connect Using /set_tutorial command</b>")
    if user.status != enums.ChatMemberStatus.ADMINISTRATOR and user.status != enums.ChatMemberStatus.OWNER and str(userid) not in ADMINS:
        return await message.reply_text("<b>Tʜɪs ᴄᴏᴍᴍᴀɴᴅ Wᴏʀᴋs Oɴʟʏ Fᴏʀ ᴛʜɪs Gʀᴏᴜᴘ Oᴡɴᴇʀ/Aᴅᴍɪɴ\n\nTʀʏ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪɴ ʏᴏᴜʀ Oᴡɴ Gʀᴏᴜᴘ, Iғ Yᴏᴜ Aʀᴇ Usɪɴɢ Mᴇ Iɴ Yᴏᴜʀ Gʀᴏᴜᴘ</b>")
    else:
        settings = await get_settings(chat_id) #fetching settings for group
        if 'shortlink' in settings.keys() and 'tutorial' in settings.keys():
            su = settings['shortlink']
            sa = settings['shortlink_api']
            st = settings['tutorial']
            return await message.reply_text(f"<b>Shortlink Website: <code>{su}</code>\n\nApi: <code>{sa}</code>\n\nTutorial: <code>{st}</code></b>")
        elif 'shortlink' in settings.keys() and 'tutorial' not in settings.keys():
            su = settings['shortlink']
            sa = settings['shortlink_api']
            return await message.reply_text(f"<b>Shortener Website: <code>{su}</code>\n\nApi: <code>{sa}</code>\n\nTutorial Link Not Connected\n\nYou can Connect Using /set_tutorial command</b>")
        elif 'shortlink' not in settings.keys() and 'tutorial' in settings.keys():
            st = settings['tutorial']
            return await message.reply_text(f"<b>Tutorial: <code>{st}</code>\n\nShortener Url Not Connected\n\nYou can Connect Using /shortlink command</b>")
        else:
            return await message.reply_text("Shortener url and Tutorial Link Not Connected. Check this commands, /shortlink and /set_tutorial")


@Client.on_message(filters.command("set_tutorial"))
async def settutorial(bot, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply("You are anonymous admin. Turn off anonymous admin and try again this command")
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text("This Command Work Only in group\n\nTry it in your own group")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    userid = message.from_user.id
    user = await bot.get_chat_member(grpid, userid)
    if user.status != enums.ChatMemberStatus.ADMINISTRATOR and user.status != enums.ChatMemberStatus.OWNER and str(userid) not in ADMINS:
        return
    else:
        pass
    if len(message.command) == 1:
        return await message.reply("<b>Give me a tutorial link along with this command\n\nCommand Usage: /set_tutorial your tutorial link</b>")
    elif len(message.command) == 2:
        reply = await message.reply_text("<b>Please Wait...</b>")
        tutorial = message.command[1]
        await save_group_settings(grpid, 'tutorial', tutorial)
        await save_group_settings(grpid, 'is_tutorial', True)
        await reply.edit_text(f"<b>Successfully Added Tutorial\n\nHere is your tutorial link for your group {title} - <code>{tutorial}</code></b>")
    else:
        return await message.reply("<b>You entered Incorrect Format\n\nFormat: /set_tutorial your tutorial link</b>")

@Client.on_message(filters.command("remove_tutorial"))
async def removetutorial(bot, message):
    userid = message.from_user.id if message.from_user else None
    if not userid:
        return await message.reply("You are anonymous admin. Turn off anonymous admin and try again this command")
    chat_type = message.chat.type
    if chat_type == enums.ChatType.PRIVATE:
        return await message.reply_text("This Command Work Only in group\n\nTry it in your own group")
    elif chat_type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        grpid = message.chat.id
        title = message.chat.title
    else:
        return
    userid = message.from_user.id
    user = await bot.get_chat_member(grpid, userid)
    if user.status != enums.ChatMemberStatus.ADMINISTRATOR and user.status != enums.ChatMemberStatus.OWNER and str(userid) not in ADMINS:
        return
    else:
        pass
    reply = await message.reply_text("<b>Please Wait...</b>")
    await save_group_settings(grpid, 'is_tutorial', False)
    await reply.edit_text("<b>Successfully Removed Your Tutorial Link!!!</b>")
        
    
@Client.on_message(filters.command("restart") & filters.user(ADMINS))
async def stop_button(bot, message):
    msg = await bot.send_message(text="**🔄 𝙿𝚁𝙾𝙲𝙴𝚂𝚂𝙴𝚂 𝚂𝚃𝙾𝙿𝙴𝙳. 𝙱𝙾𝚃 𝙸𝚂 𝚁𝙴𝚂𝚃𝙰𝚁𝚃𝙸𝙽𝙶...**", chat_id=message.chat.id)       
    await asyncio.sleep(3)
    await msg.edit("**✅️ 𝙱𝙾𝚃 𝙸𝚂 𝚁𝙴𝚂𝚃𝙰𝚁𝚃𝙴𝙳. 𝙽𝙾𝚆 𝚈𝙾𝚄 𝙲𝙰𝙽 𝚄𝚂𝙴 𝙼𝙴**")
    os.execl(sys.executable, sys.executable, *sys.argv)



import logging

from pyrogram import Client, filters


# /sell command
@Client.on_message(filters.command("sell") & filters.user(ADMINS))
async def sell_command(client, message):
    try:
        text_lines = ["📊 **Channel User Report** 📊\n"]

        # saare channels fetch karo
        async for doc in db.channels.find({}, {"_id": 1, "user_ids": 1}):
            chat_id = doc["_id"]
            user_count = len(doc.get("user_ids", []))

            # optional: channel ka naam/username
            try:
                chat = await client.get_chat(chat_id)
                chat_name = chat.title or chat.username or str(chat_id)
            except Exception as e:
                logging.warning(f"[SELL] Failed to fetch chat info {chat_id}: {e}")
                chat_name = str(chat_id)

            text_lines.append(f"✅ {chat_name} (`{chat_id}`) → **{user_count}** users")

        if len(text_lines) == 1:
            await message.reply_text("⚠️ Database me koi channel saved nahi hai.")
            return

        await message.reply_text("\n".join(text_lines), disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"[SELL CMD] ERROR: {e}")
        await message.reply_text("❌ Error while fetching data.")
