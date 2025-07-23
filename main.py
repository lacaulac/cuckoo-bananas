import discord
from discord.ext import commands
import asyncio
import datetime
import json

# Your sound and voice channels
SOUND_FILE = "ank.wav"
VOICE_CHANNEL_IDS = [
    577482669915373582,  # Channel 1
    1044193650994843728,  # Channel 2
]
CONFIG_FILE_NAME = "config.json"
SHARED_DIRECTORY = "shared"

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
try:
    with open(CONFIG_FILE_NAME, 'r') as f:
        config = json.load(f)
        channel_configs = config["channels"]
        SOUND_FILE = config["default_sound"] if "default_sound" in config else SOUND_FILE
        print(f"Loaded configuration: {channel_configs}")
except FileNotFoundError:
    print("config.json not found, using default settings.")

intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(command_prefix='%', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    bot.loop.create_task(hourly_sound_loop())
    # print("Syncing commands...")
    # await bot.tree.sync(guild=discord.Object(id=577482669915373578))  # Sync commands to a specific guild
    # print("Commands synced successfully!")

@bot.command(name="play_sound", description="Play a sound in the voice channel")
async def play_sound(ctx, channel_id: int, file_path: str):
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        await ctx.send(f"Channel ID {channel_id} is not a valid voice channel.")
        return
    voice_client = await channel.connect()

    the_sound_file = discord.FFmpegPCMAudio(file_path)
    voice_client.play(the_sound_file)
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
            vc.play(discord.FFmpegPCMAudio(sound), after=lambda e: print(f'Done in {channel.name}: {e}'))

            while vc.is_playing():
                await asyncio.sleep(1)

            print(f"[LEAVE] Done playing in {channel.name}, disconnecting")
            await vc.disconnect()

        except discord.ClientException as e:
            print(f"[ERROR] ClientException in {channel.name}: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error in {channel.name}: {e}")


if __name__ == "__main__":
    if not config or "token" not in config:
        print("No valid configuration found. Please check your config.json file.")
        exit(1)
    discord.opus.load_opus()
    if not discord.opus.is_loaded():
        print('Opus failed to load')
        exit(1)
    bot.run(token=config["token"])