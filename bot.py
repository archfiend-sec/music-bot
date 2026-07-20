import os
import asyncio
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls, idle
from pytgcalls.types import MediaStream, Update
import yt_dlp

# --- RENDER HACK: Inject current directory to PATH so py-tgcalls finds FFmpeg ---
os.environ["PATH"] += os.pathsep + os.getcwd()

# --- ENV VARS ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
PORT = int(os.environ.get("PORT", 8080))

# --- RENDER HEALTH CHECK SERVER ---
app_flask = Flask(__name__)

@app_flask.route("/")
def health_check():
    return "Bot is alive!", 200

def run_flask():
    # Runs quietly in a daemon thread
    app_flask.run(host="0.0.0.0", port=PORT)

threading.Thread(target=run_flask, daemon=True).start()

# --- TELEGRAM CLIENTS ---
bot = Client(
    "bot_client",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

userbot = Client(
    "userbot_client",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

call_py = PyTgCalls(userbot)

# --- IN-MEMORY QUEUE ---
# Format: { chat_id: [{"title": "Song", "file_path": "downloads/..."}] }
queue = {}

# --- HELPER: DOWNLOAD AUDIO ---
def download_audio(query):
    os.makedirs("downloads", exist_ok=True)
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        if query.startswith("http"):
            info = ydl.extract_info(query, download=True)
        else:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)['entries'][0]
        
        file_path = ydl.prepare_filename(info)
        return file_path, info.get('title', 'Unknown Audio')

# --- BOT COMMANDS ---
@bot.on_message(filters.command("play") & filters.group)
async def play_command(c: Client, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("Usage: `/play <song name or url>`")
    
    query = m.text.split(" ", 1)[1]
    chat_id = m.chat.id
    status_msg = await m.reply_text("🔎 Searching and downloading...")

    try:
        # Run yt-dlp in a thread to prevent blocking the async event loop
        file_path, title = await asyncio.to_thread(download_audio, query)
    except Exception as e:
        return await status_msg.edit_text(f"❌ Download failed: {str(e)}")

    if chat_id not in queue:
        queue[chat_id] = []
        
    queue[chat_id].append({"file_path": file_path, "title": title})
    
    # If it's the only track in the queue, start playing immediately
    if len(queue[chat_id]) == 1:
        try:
            await call_py.play(chat_id, MediaStream(file_path))
            await status_msg.edit_text(f"▶️ Now playing: **{title}**")
        except Exception as e:
            await status_msg.edit_text(f"❌ Error joining VC: {str(e)}\nMake sure the Userbot is added to this group!")
            queue[chat_id].pop(0)
    else:
        await status_msg.edit_text(f"⏳ Added to queue (Position: {len(queue[chat_id]) - 1}): **{title}**")

@bot.on_message(filters.command("skip") & filters.group)
async def skip_command(c: Client, m: Message):
    chat_id = m.chat.id
    if chat_id not in queue or len(queue[chat_id]) == 0:
        return await m.reply_text("Nothing is playing right now.")
    
    # Remove current track and delete its file
    old_track = queue[chat_id].pop(0)
    try:
        os.remove(old_track['file_path'])
    except OSError:
        pass
    
    if len(queue[chat_id]) > 0:
        next_track = queue[chat_id][0]
        try:
            await call_py.play(chat_id, MediaStream(next_track['file_path']))
            await m.reply_text(f"⏭ Skipped. Now playing: **{next_track['title']}**")
        except Exception as e:
            await m.reply_text(f"❌ Error playing next: {e}")
            await call_py.leave_call(chat_id)
    else:
        await call_py.leave_call(chat_id)
        await m.reply_text("Queue finished. Left the voice chat.")

@bot.on_message(filters.command("stop") & filters.group)
async def stop_command(c: Client, m: Message):
    chat_id = m.chat.id
    if chat_id in queue:
        for track in queue[chat_id]:
            try:
                os.remove(track['file_path'])
            except OSError:
                pass
        queue[chat_id] = []
    
    try:
        await call_py.leave_call(chat_id)
        await m.reply_text("⏹ Stopped and cleared the queue.")
    except Exception as e:
        await m.reply_text(f"Error: {e}")

@bot.on_message(filters.command("pause") & filters.group)
async def pause_command(c: Client, m: Message):
    try:
        # Depending on minor version variations of py-tgcalls v2, 
        # pause_stream() is standard.
        await call_py.pause_stream(m.chat.id)
        await m.reply_text("⏸ Paused.")
    except Exception as e:
        await m.reply_text(f"Error: {e}")

@bot.on_message(filters.command("resume") & filters.group)
async def resume_command(c: Client, m: Message):
    try:
        await call_py.resume_stream(m.chat.id)
        await m.reply_text("▶️ Resumed.")
    except Exception as e:
        await m.reply_text(f"Error: {e}")

# --- AUTO-QUEUE PROGRESSION ---
@call_py.on_stream_end()
async def stream_ended_handler(client: PyTgCalls, update: Update):
    chat_id = update.chat_id
    if chat_id in queue and len(queue[chat_id]) > 0:
        
        # Track finished: remove it from queue and delete the file
        old_track = queue[chat_id].pop(0)
        try:
            os.remove(old_track['file_path'])
        except OSError:
            pass

        # Play next if exists
        if len(queue[chat_id]) > 0:
            next_track = queue[chat_id][0]
            try:
                await call_py.play(chat_id, MediaStream(next_track['file_path']))
            except Exception as e:
                await call_py.leave_call(chat_id)
        else:
            await call_py.leave_call(chat_id)

async def main():
    print("Starting MTProto clients...")
    await bot.start()
    # call_py.start() initializes the userbot attached to it
    await call_py.start()
    print("Bot is alive and listening for commands!")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
