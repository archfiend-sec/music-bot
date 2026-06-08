import os
import threading
from flask import Flask
from pyrogram import Client, filters
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
call_py = PyTgCalls(assistant)

@bot.on_message(filters.command("play") & filters.group)
async def play_song(client, message):
    query = " ".join(message.command[1:])
    if not query:
        return await message.reply("Give me a song name or YouTube link to play.")

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
            info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            audio_url = info['url']
            title = info['title']

        await call_py.play(message.chat.id, MediaStream(audio_url))
        await status_msg.edit(f"▶️ **Now Playing:** {title}")
        
    except Exception as e:
        await status_msg.edit(f"Stream encountered an issue: `{e}`")

print("Launching systems...")
call_py.start()
bot.run()
