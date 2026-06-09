import os
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
import yt_dlp

# --- Web Server for UptimeRobot ---
app_web = Flask(__name__)

@app_web.route('/')
def health_check():
    return "Bot Engine Active"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host="0.0.0.0", port=port)

threading.Thread(target=run_server, daemon=True).start()

# --- Telegram Infrastructure Setup ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SESSION_STRING = os.environ.get("SESSION_STRING")

bot = Client("music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
assistant = Client("assistant", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)

# Initialize PyTgCalls V3
call_py = PyTgCalls(assistant)

@bot.on_message(filters.command("play") & filters.group)
async def play_song(client, message):
    query = " ".join(message.command[1:])
    if not query:
        return await message.reply("Give me a song name to play.")

    status_msg = await message.reply("🎧 Fetching audio stream...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'extract_audio': True,
        'audio_format': 'mp3',
        'noplaylist': True,
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Using scsearch (SoundCloud) to bypass YouTube bot blocks
            info = ydl.extract_info(f"scsearch:{query}", download=False)['entries'][0]
            audio_url = info['url']
            title = info['title']

        # Playback Logic (V3 Native)
        chat_id = message.chat.id
        
        # In PyTgCalls V3, .play() automatically handles joining if not joined,
        # and seamlessly changes the stream if already playing. No change_stream needed!
        await call_py.play(chat_id, MediaStream(audio_url))

        # The Interactive Play Bar
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⏸ Pause", callback_data="pause"),
                InlineKeyboardButton("▶️ Resume", callback_data="resume"),
                InlineKeyboardButton("⏹ Stop", callback_data="stop")
            ]
        ])
        
        await status_msg.edit(f"▶️ **Now Playing:** {title}", reply_markup=buttons)
        
    except Exception as e:
        await status_msg.edit(f"Stream encountered an issue: `{e}`")


# --- Button Control Logic ---
@bot.on_callback_query()
async def cb_handler(client, query):
    chat_id = query.message.chat.id
    
    try:
        if query.data == "pause":
            try:
                await call_py.pause_stream(chat_id)
            except AttributeError:
                await call_py.pause(chat_id)
            await query.answer("⏸ Music Paused")
        
        elif query.data == "resume":
            try:
                await call_py.resume_stream(chat_id)
            except AttributeError:
                await call_py.resume(chat_id)
            await query.answer("▶️ Music Resumed")
        
        elif query.data == "stop":
            # V3 uses leave_call instead of leave_group_call
            await call_py.leave_call(chat_id)
            await query.answer("⏹ Music Stopped")
            await query.message.edit("⏹ **Playback Stopped.**")
            
    except Exception as e:
        await query.answer(f"Action failed. Is the music playing?", show_alert=True)

print("Launching systems...")
call_py.start()
bot.run()
