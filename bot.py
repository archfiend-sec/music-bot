import os
import threading
import requests
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
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


# --- Backup High-Quality Mirror Extractor ---
def get_mirror_stream(query):
    instances = [
        "https://vid.puffyan.us",
        "https://inv.tux.digital",
        "https://invidious.protobuf.it",
        "https://invidious.nerdvpn.de"
    ]
    for instance in instances:
        try:
            search_url = f"{instance}/api/v1/search?q={requests.utils.quote(query)}"
            search_res = requests.get(search_url, timeout=5).json()
            if not search_res:
                continue
            
            video_id = search_res[0]['videoId']
            title = search_res[0]['title']
            
            video_url = f"{instance}/api/v1/videos/{video_id}"
            video_data = requests.get(video_url, timeout=5).json()
            
            audio_url = None
            for fmt in video_data.get('adaptiveFormats', []):
                if fmt.get('type', '').startswith('audio/'):
                    audio_url = fmt.get('url')
                    break
                    
            if not audio_url and video_data.get('formatStreams'):
                audio_url = video_data['formatStreams'][0]['url']
                
            if audio_url:
                return audio_url, title
        except Exception:
            continue
    return None, None


@bot.on_message(filters.command("play") & filters.group)
async def play_song(client, message):
    query = " ".join(message.command[1:])
    if not query:
        return await message.reply("Give me a song name to play.")

    status_msg = await message.reply("🎧 Fetching audio stream...")

    # Corrected internal yt-dlp parameters
    ydl_opts = {
        'format': 'bestaudio/best',  
        'noplaylist': True,
        'quiet': True,
        'prefer_ffmpeg': True,       
        'geo_bypass': True,          
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'tv']
            }
        }
    }

    audio_url = None
    title = None

    try:
        # Strategy 1: Corrected Direct extraction
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                audio_url = info['url']
                title = info['title']
        except Exception:
            # Strategy 2: Instant mirror extraction fallback if Render's IP is blocked
            audio_url, title = get_mirror_stream(query)

        if not audio_url:
            return await status_msg.edit("Unable to locate a secure audio layout stream. Try again.")

        chat_id = message.chat.id
        await call_py.play(chat_id, audio_url)

        # Interactive Play Bar
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
            await call_py.pause(chat_id)
            await query.answer("⏸ Music Paused")
        elif query.data == "resume":
            await call_py.resume(chat_id)
            await query.answer("▶️ Music Resumed")
        elif query.data == "stop":
            await call_py.leave_call(chat_id)
            await query.answer("⏹ Music Stopped")
            await query.message.edit("⏹ **Playback Stopped.**")
    except Exception:
        await query.answer("Action failed. Is the music playing?", show_alert=True)

print("Launching systems...")
call_py.start()
bot.run()
