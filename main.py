
import os
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime, timedelta
import json
import asyncio

# Load environment variables (your Discord bot token)
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Initialize intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required for tracking members

# Initialize the bot with command prefix and intents
bot = commands.Bot(command_prefix='/', intents=intents)

# File paths for storing data
DATA_FILE = 'user_data.json'

# Helper function to convert datetime objects to string (for JSON serialization)
def datetime_to_str(dt):
    return dt.isoformat() if dt else None

# Helper function to convert strings back to datetime (for loading from JSON)
def str_to_datetime(dt_str):
    return datetime.fromisoformat(dt_str) if dt_str else None

# Load user data from a JSON file
def load_user_data():
    try:
        with open(DATA_FILE, 'r') as file:
            data = json.load(file)
            return defaultdict(lambda: [None] * 5, data.get('user_progress', {})), \
                   defaultdict(lambda: None, {k: str_to_datetime(v) for k, v in data.get('user_last_checklist', {}).items()}), \
                   defaultdict(lambda: [0] * 6, data.get('user_stats', {}))  # 6 slots, including one for 0%
    except (FileNotFoundError, json.JSONDecodeError):
        # If the file doesn't exist or is corrupted, initialize empty data
        return defaultdict(lambda: [None] * 5), defaultdict(lambda: None), defaultdict(lambda: [0] * 6)

# Save user data to a JSON file
def save_user_data():
    data = {
        'user_progress': dict(user_progress),
        'user_last_checklist': {k: datetime_to_str(v) for k, v in user_last_checklist.items()},
        'user_stats': dict(user_stats)
    }
    try:
        with open(DATA_FILE, 'w') as file:
            json.dump(data, file)
    except Exception as e:
        print(f"Error saving user data: {e}")

# Load the data when the bot starts
user_progress, user_last_checklist, user_stats = load_user_data()

questions = [
    "📌 **Have you defined your target audience?**",
    "📌 **Do you have a clear and compelling hook?**",
    "📌 **Is the title short and engaging?**",
    "📌 **Does the script fit within the 3-minute limit?**",
    "📌 **Does the pacing match the excitement level?**"
]

# Function to update user stats
def update_user_stats(user_id):
    filled = user_progress[user_id].count(True)
    if filled == 5:
        user_stats[user_id][4] += 1  # 100% completed
    elif filled == 4:
        user_stats[user_id][3] += 1  # 80% completed
    elif filled == 3:
        user_stats[user_id][2] += 1  # 60% completed
    elif filled == 2:
        user_stats[user_id][1] += 1  # 40% completed
    elif filled == 1:
        user_stats[user_id][0] += 1  # 20% completed
    elif filled == 0 and user_progress[user_id].count(False) == 5:
        user_stats[user_id][5] += 1  # Add to 0% count

    # Save data whenever stats are updated
    save_user_data()

# Event to notify when the bot is ready
@bot.event
async def on_ready():
    print(f'{bot.user} is now running!')
    reset_daily_checklist.start()  # Start the daily checklist reset task

# Command to start the checklist
@bot.command()
async def checklist(ctx):
    user_id = str(ctx.author.id)

    # Check if the user has already done the checklist within the cooldown period (1 minute)
    last_completed = user_last_checklist.get(user_id)
    if last_completed is not None and (datetime.utcnow() - last_completed) < timedelta(minutes=1):
        remaining_time = timedelta(minutes=1) - (datetime.utcnow() - last_completed)
        await ctx.send(f"⏳ **You've recently completed the checklist. Please wait {int(remaining_time.total_seconds())} more seconds!**")
        return

    # Start the checklist by asking the first question
    user_progress[user_id] = [None] * 5  # Reset progress for this user
    await ask_question(ctx, user_id)

# Ask a question and show progress
async def ask_question(ctx, user_id):
    next_question_index = next((i for i, answer in enumerate(user_progress[user_id]) if answer is None), None)

    if next_question_index is not None:
        # Show the progress
        progress_message = display_progress(user_progress[user_id])
        await ctx.send(f"📝 **Pre-Writing Checklist Progress:**\n{progress_message}")

        # Ask the next question
        await ctx.send(f"{questions[next_question_index]} (Type `/yes` or `/no` to answer)")
    else:
        # All questions answered, complete the checklist
        await handle_question_completion(ctx, user_id)

# Command to handle '/yes' response
@bot.command()
async def yes(ctx):
    await record_answer(ctx, True)

# Command to handle '/no' response
@bot.command()
async def no(ctx):
    await record_answer(ctx, False)

# Function to record the answer and move to the next question
async def record_answer(ctx, answer):
    user_id = str(ctx.author.id)
    next_question_index = next((i for i, ans in enumerate(user_progress[user_id]) if ans is None), None)

    if next_question_index is not None:
        user_progress[user_id][next_question_index] = answer
        await ask_question(ctx, user_id)
    else:
        await ctx.send("✅ **You have already completed the checklist.**")

# Handle checklist completion
async def handle_question_completion(ctx, user_id):
    if all(response is not None for response in user_progress[user_id]):
        await ctx.send("🎉 **You’ve completed the checklist!**")
        progress_message = display_progress(user_progress[user_id])
        await ctx.send(f"{progress_message}")
        update_user_stats(user_id)
        user_last_checklist[user_id] = datetime.utcnow()  # Record completion time
        save_user_data()  # Save the data immediately after completion
        await ctx.send(f"🗂 **Check your /stats to see your progress.**")

# Command to show stats for a user
@bot.command()
async def stats(ctx, username: str):
    user_id = get_user_id_from_username(username, ctx.guild)
    
    if user_id is None or user_id not in user_stats:
        await ctx.send(f"🔍 **No stats found for {username}.**")
    else:
        stats_message = (
            f"📊 **Stats for {username}:**\n"
            f"🌟 **0% Checklists:** {user_stats[user_id][5]}\n"
            f"🌟 **20% Checklists:** {user_stats[user_id][0]}\n"
            f"🌟 **40% Checklists:** {user_stats[user_id][1]}\n"
            f"🌟 **60% Checklists:** {user_stats[user_id][2]}\n"
            f"🌟 **80% Checklists:** {user_stats[user_id][3]}\n"
            f"🌟 **100% Checklists:** {user_stats[user_id][4]}"
        )
        await ctx.send(stats_message)

# Function to display progress bar and answers
def display_progress(progress):
    progress_bar = ""
    for answered in progress:
        if answered is True:
            progress_bar += "🟢"
        elif answered is False:
            progress_bar += "🔴"
        else:
            progress_bar += "🟠"

    percentage = (progress.count(True) / len(questions)) * 100
    return f"[{progress_bar}] **({int(percentage)}%)**"

# Function to get user ID from username
def get_user_id_from_username(username, guild):
    user = discord.utils.get(guild.members, name=username) or discord.utils.get(guild.members, display_name=username)
    return str(user.id) if user else None

# Task to reset the daily checklist
@tasks.loop(hours=24)
async def reset_daily_checklist():
    now = datetime.utcnow()
    for user_id in list(user_progress.keys()):
        if user_last_checklist[user_id] is None or (now - user_last_checklist[user_id]).days >= 1:
            user_progress[user_id] = [None] * 5  # Reset progress
            user_last_checklist[user_id] = None
    save_user_data()

# Run the bot
bot.run(TOKEN)
