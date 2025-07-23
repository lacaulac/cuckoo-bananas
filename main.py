import discord
from discord.ext import commands
import asyncio
import datetime
import json
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import shutil
import json
import uvicorn

app = FastAPI()

# Your sound and voice channels
SOUND_FILE = "ank.wav"
VOICE_CHANNEL_IDS = [
    577482669915373582,  # Channel 1
    1044193650994843728,  # Channel 2
]
CONFIG_FILE_NAME = "config.json"
SHARED_DIRECTORY = "shared"
SHARED_DIR = Path("./" + SHARED_DIRECTORY)
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".aac"}

config = None
channel_configs = []

# Check if the shared directory exists
import os
if os.path.exists(SHARED_DIRECTORY):
    # Check if the config file exists in the shared directory
    if os.path.exists(os.path.join(SHARED_DIRECTORY, CONFIG_FILE_NAME)):
        print(f"Using config file from shared directory: {SHARED_DIRECTORY}/{CONFIG_FILE_NAME}")
        CONFIG_FILE_NAME = os.path.join(SHARED_DIRECTORY, CONFIG_FILE_NAME)

# Load configuration from config.json
def load_config():
    global config, channel_configs, SOUND_FILE
    try:
        with open(CONFIG_FILE_NAME, 'r') as f:
            config = json.load(f)
            channel_configs = config["channels"]
            # Convert to integer IDs if they are strings
            for channel in channel_configs:
                if "id" in channel:
                    channel["id"] = int(channel["id"])
            # Same for member actions
            for member_action in config.get("member_actions", []):
                if "id" in member_action:
                    member_action["id"] = int(member_action["id"])
            SOUND_FILE = config["default_sound"] if "default_sound" in config else SOUND_FILE
            print(f"Loaded configuration: {channel_configs}")
    except FileNotFoundError:
        print("config.json not found, using default settings.")

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(command_prefix='%', intents=intents)

audio_file_cache = {}
audio_file_cache: dict[str, discord.FFmpegPCMAudio] = {}

def get_audio_file(file_path: str) -> discord.FFmpegPCMAudio:
    global audio_file_cache
    if file_path not in audio_file_cache:
        print(f"Cache miss for {file_path}, loading audio file.")
        audio_file_cache[file_path] = discord.FFmpegPCMAudio(file_path)
    else:
        print(f"Cache hit for {file_path}, using cached audio file.")
    # Return the cached audio file
    return audio_file_cache[file_path]

async def refresh_cached_file(file_path: str) -> discord.FFmpegPCMAudio:
    """Refresh the cached audio file."""
    global audio_file_cache
    if file_path in audio_file_cache:
        print(f"Refreshing cache for {file_path}.")
        audio_file_cache[file_path] = discord.FFmpegPCMAudio(file_path)
    else:
        print(f"File {file_path} not in cache, loading new audio file.")
        audio_file_cache[file_path] = get_audio_file(file_path)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    bot.loop.create_task(hourly_sound_loop())
    bot.loop.create_task(start_web_server())
    # print("Syncing commands...")
    # await bot.tree.sync(guild=discord.Object(id=577482669915373578))  # Sync commands to a specific guild
    # print("Commands synced successfully!")
    
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    # print(f"Voice state update for {member.name}: {before} -> {after}")
    # print(f"\tChannel: {before.channel} -> {after.channel}")
    if before.channel != after.channel and after.channel is not None:
        # A user has joined a voice channel
        for member_action in config["member_actions"]:
            if member.id == member_action["id"]:
                sound_file = member_action["sound"]
                delay = member_action["delay"] if "delay" in member_action else 0.0
                async def that_function(channel_id, sound_file, delay):
                    print(f"Playing sound for {member.name} in {after.channel.name} after {delay} seconds.")
                    await asyncio.sleep(delay)
                    try:
                        await play_if_channel_has_people(channel_id, sound_file)
                    except Exception as e:
                        print(f"[ERROR] Failed to play sound in channel {channel_id}: {e}")
                bot.loop.create_task(that_function(after.channel.id, sound_file, delay))
        # if member.id == 216809338537377792:
        #     print(f"Special user {member.name} joined {after.channel.name}, playing sound.")
        #     try:
        #         await play_if_channel_has_people(after.channel.id, "shared/hello.wav")
        #     except Exception as e:
        #         print(f"[ERROR] Failed to play sound in channel {after.channel.id}: {e}")

@bot.command(name="play_sound", description="Play a sound in the voice channel")
async def play_sound(ctx, channel_id: int, file_path: str):
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        await ctx.send(f"Channel ID {channel_id} is not a valid voice channel.")
        return
    voice_client = await channel.connect()

    the_sound_file = get_audio_file(file_path)
    voice_client.play(the_sound_file)
    bot.loop.create_task(refresh_cached_file(file_path)) # Refresh the cached file after playing
    while voice_client.is_playing():
        await asyncio.sleep(1)
    voice_client.stop()
    await voice_client.disconnect()


# @bot.command()
# async def play(ctx, file_path: str):
#     channel = ctx.author.voice.channel
#     voice_client = await channel.connect()
#     voice_client.play(discord.FFmpegPCMAudio(file_path))

# @bot.command()
# async def stop(ctx):
#     voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
#     if voice_client.is_playing():
#         voice_client.stop()
#     await voice_client.disconnect()

async def wait_until_next_hour():
    now = datetime.datetime.utcnow()
    next_hour = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    wait_seconds = (next_hour - now).total_seconds()
    print(f"Waiting {wait_seconds:.2f} seconds until the top of the hour...")
    await asyncio.sleep(wait_seconds)
    
async def wait_until_next_minute():
    now = datetime.datetime.utcnow()
    next_minute = (now + datetime.timedelta(minutes=1)).replace(second=0, microsecond=0)
    wait_seconds = (next_minute - now).total_seconds()
    print(f"Waiting {wait_seconds:.2f} seconds until the next minute...")
    await asyncio.sleep(wait_seconds)

async def hourly_sound_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await wait_until_next_hour()
        for channel_config in channel_configs:
            channel_id = channel_config["id"]
            sound_file = channel_config["sound"] if "sound" in channel_config else SOUND_FILE

            if not channel_id:
                print("[ERROR] Channel ID is missing in config")
                continue

            try:
                await play_if_channel_has_people(channel_id, sound_file)
            except Exception as e:
                print(f"[ERROR] Failed to play sound in channel {channel_id}: {e}")

async def play_if_channel_has_people(channel_id, sound=SOUND_FILE):
    for guild in bot.guilds:
        channel = guild.get_channel(channel_id)
        if channel is None or not isinstance(channel, discord.VoiceChannel):
            print(f"[WARN] Channel ID {channel_id} not found or not a voice channel")
            continue

        humans = [m for m in channel.members if not m.bot]
        print(f"[INFO] Checking {channel.name}: {len(humans)} human(s) inside")

        if not humans:
            print(f"[SKIP] {channel.name} is empty or only has bots")
            continue

        try:
            # Check if already connected in this guild
            existing_vc = discord.utils.get(bot.voice_clients, guild=guild)
            if existing_vc:
                print(f"[CLEANUP] Already connected in {guild.name}, disconnecting...")
                await existing_vc.disconnect(force=True)

            print(f"[JOIN] Connecting to {channel.name}")
            vc = await channel.connect()
            print(f"[PLAY] Playing sound in {channel.name}")
            vc.play(get_audio_file(sound), after=lambda e: print(f'Done in {channel.name}: {e}'))
            # Refresh the cached file after playing
            bot.loop.create_task(refresh_cached_file(sound))

            while vc.is_playing():
                await asyncio.sleep(1)

            print(f"[LEAVE] Done playing in {channel.name}, disconnecting")
            await vc.disconnect()
            

        except discord.ClientException as e:
            print(f"[ERROR] ClientException in {channel.name}: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error in {channel.name}: {e}")

@app.get("/config")
async def get_config():
    with open(CONFIG_FILE_NAME, "r", encoding="utf-8") as l_f:
        l_config = json.load(l_f)
    l_config.pop("token", None)  # Remove the token from the response
    return l_config

@app.post("/config")
async def update_config(request: Request):
    data = await request.json()
    with open(CONFIG_FILE_NAME, "r", encoding="utf-8") as l_f:
        existing = json.load(l_f)
    data["token"] = existing.get("token", "")  # Preserve the token
    with open(CONFIG_FILE_NAME, "w", encoding="utf-8") as l_f:
        json.dump(data, l_f, indent=4)
    load_config()
    return {"status": "success"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")
    
    save_path = SHARED_DIR / file.filename

    # Avoid overwriting by adding a numeric suffix if needed
    counter = 1
    original_stem = save_path.stem
    while save_path.exists():
        save_path = SHARED_DIR / f"{original_stem}_{counter}{ext}"
        counter += 1

    with save_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": save_path.name}


@app.get("/files")
async def list_files():
    files = [f.name for f in SHARED_DIR.iterdir() if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS]
    return JSONResponse(files)

@app.delete("/files/{filename}")
async def delete_file(filename: str):
    # sanitize filename to avoid directory traversal
    safe_name = Path(filename).name
    file_path = SHARED_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        file_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
    return {"detail": "File deleted"}

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("./static/index.html", "r", encoding="utf-8") as l_f:
        return l_f.read()

app.mount("/static", StaticFiles(directory="./static"), name="static")

async def start_web_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
    
if __name__ == "__main__":
    load_config()
    if not config or "token" not in config:
        print("No valid configuration found. Please check your config.json file.")
        exit(1)
    # If not on Windows
    if os.name != 'nt':
        # Load Opus library
        if not discord.opus.is_loaded():
            discord.opus.load_opus("/usr/lib/libopus.so")
        if not discord.opus.is_loaded():
            print('Opus failed to load')
            exit(1)
    bot.run(token=config["token"])