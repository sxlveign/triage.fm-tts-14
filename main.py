"""
triage.fm - A Telegram bot for generating podcast scripts and audio from read-it-later content
"""
import os
import logging
import textwrap
import threading
from datetime import datetime, time, timedelta
import re
import pytz
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
import json

# Import custom modules
from content_processor import ContentProcessor
from script_generator import ScriptGenerator
from database import Database
from tts_processor import TTSProcessor
from scheduler import PodcastScheduler
from scheduler import get_friendly_timezone
from replit_keep_alive import start_keep_alive

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logger.info("Starting triage.fm bot")

# Load environment variables
load_dotenv()

# Initialize global objects
db = Database()
content_processor = ContentProcessor()
script_generator = ScriptGenerator()
tts_processor = TTSProcessor()

# Initialize scheduler
scheduler = None

# Constants
MAX_MESSAGE_LENGTH = 4000  # Telegram's limit is 4096, but we'll use a smaller value to be safe

# Messages - Updated for the ADHD-focused triage app
WELCOME_MESSAGE = (
    "👋 Welcome to triage.fm!\n\n"
    "I'm your personal content triage assistant, designed specifically for ADHD minds.\n\n"
    "I'll help you decide which articles, videos, and docs actually deserve your full attention—and which ones you can confidently skip.\n\n"
    "Send me links, documents, or text, and I'll transform them into a podcast-style conversation that highlights only the MOST interesting and specific insights.\n\n"
    "Send me anything now to get started, or type /help to learn more."
)

# Second welcome message with value proposition
WELCOME_VALUE_PROPOSITION = (
    "⏱️ Stop wasting time on content that isn't worth it!\n\n"
    "With triage.fm, you'll:\n\n"
    "🧠 Cut through information overload\n"
    "💡 Discover if content contains truly valuable insights\n"
    "⚡ Make quick decisions about what deserves deeper reading\n"
    "🎧 Process your backlog while on the go\n"
    "🔍 Focus only on content with specific, surprising facts\n\n"
    "Instead of incomplete summaries, I'll give you the most interesting points so you can decide what's worth your full attention.\n\n"
    "Ready? Send me a link, document, or text you've been meaning to read!"
)

# Message after first content received
FIRST_CONTENT_RECEIVED = (
    "✅ Content received! I've added it to your queue.\n\n"
    "Here's how triage.fm works:\n\n"
    "1️⃣ Send me your \"read-it-later\" content - links, PDFs, YouTube videos, etc.\n"
    "2️⃣ Use /generate when you're ready for a decision helper\n"
    "3️⃣ I'll create a podcast-style conversation highlighting ONLY the most interesting and specific insights\n"
    "4️⃣ You'll quickly know which content deserves your full attention\n\n"
    "The podcast format is designed to be ADHD-friendly with distinct voices and focused insights, not generic summaries.\n\n"
    "Send more content anytime!"
)

# Content examples message
CONTENT_EXAMPLES = (
    "💡 triage.fm works best with:\n\n"
    "• Long articles you don't know if you should read fully\n"
    "• YouTube videos you're curious about but don't want to watch\n"
    "• PDFs and documents in your download folder\n"
    "• Twitter/X threads with potentially useful information\n"
    "• Backlog content you've been meaning to get to\n\n"
    "I'll extract the surprising facts and counterintuitive insights so you can make informed decisions about your content.\n\n"
    "Try sending something else you're unsure about reading!"
)

# Daily triage recommendation
DAILY_TRIAGE_RECOMMENDATION = (
    "🔍 Triage your content daily!\n\n"
    "Set up an automatic daily podcast delivery to help you decide what's worth reading:\n\n"
    "/schedule 07:30 mon,wed,fri - Content decisions on Monday, Wednesday, Friday at 7:30 AM\n"
    "/schedule 18:00 US/Eastern - Daily content triage at 6:00 PM Eastern time\n\n"
    "This creates a consistent decision-making system for your incoming content, helping you focus only on what truly matters.\n\n"
    "Type /help anytime for assistance!"
)

HELP_MESSAGE = (
    "Here's how to use triage.fm:\n\n"
    "1. Send me any content you want to triage: links, documents, or text.\n"
    "2. I'll confirm when I've received and processed each item.\n"
    "3. When you're ready, use /generate to create a podcast that helps you decide which content deserves your full attention.\n"
    "4. You can also schedule daily content triage with /schedule.\n\n"
    "Available commands:\n"
    "/start - Start the bot\n"
    "/help - Show this help message\n"
    "/generate - Create a podcast from your content\n"
    "/queue - See what's in your content queue\n"
    "/clear - Clear your content queue\n"
    "/schedule - Set up scheduled podcast delivery"
)

GENERATING_MESSAGE = "I'm creating your audio podcast now. This may take a minute..."
EMPTY_QUEUE_MESSAGE = "You don't have any new content to process. Send me some links or documents first!"
ERROR_MESSAGE = "Sorry, I encountered an error while generating your podcast. Please try again later."
AUDIO_ERROR_MESSAGE = "Sorry, I couldn't generate the audio podcast at this time. Please try again later."
QUEUE_EMPTY_MESSAGE = "Your content queue is empty. Send me some links or documents to get started!"
QUEUE_HEADER_MESSAGE = "Your content queue:"
QUEUE_CLEARED_MESSAGE = "Your content queue has been cleared. You can start fresh now!"
CONTENT_RECEIVED_MESSAGE = "Content received and processed! It will be included in your next podcast."
UNSUPPORTED_CONTENT_MESSAGE = "Sorry, {message} Please send other content types."
PROCESSING_ERROR_MESSAGE = "Sorry, I couldn't process that content. Please try again or send a different format."
UNKNOWN_CONTENT_TYPE_MESSAGE = "Sorry, I can't process this type of content yet. Please send me text, links, or documents."
COMMAND_CORRECTION_MESSAGE = "It looks like you're trying to use a command. Please use /{command} instead."
PODCAST_SENT_MESSAGE = "Here's your podcast! Enjoy listening."
SCRIPT_PART_MESSAGE = "Script (Part {part_number}/{total_parts}):"

# Schedule command messages
SCHEDULE_HELP_MESSAGE = (
    "Set up a daily content triage schedule!\n\n"
    "Use the format: /schedule HH:MM [days] [timezone]\n"
    "Examples:\n"
    "/schedule 08:30 - Daily at 8:30 AM (UTC)\n"
    "/schedule 17:45 mon,wed,fri - Monday, Wednesday, Friday at 5:45 PM (UTC)\n"
    "/schedule 09:00 Europe/Paris - Daily at 9:00 AM (Paris time)\n"
    "/schedule 20:15 mon,fri US/Eastern - Monday and Friday at 8:15 PM (Eastern time)\n\n"
    "Common timezones: UTC, Europe/London, Europe/Paris, US/Eastern, US/Pacific, Asia/Tokyo, Australia/Sydney\n\n"
    "To cancel your schedule, use: /schedule cancel"
)
SCHEDULE_SET_MESSAGE = "I'll deliver your podcast at {time} {timezone} on {days}."
SCHEDULE_CANCELED_MESSAGE = "Your podcast delivery schedule has been canceled."
SCHEDULE_CURRENT_MESSAGE = "Your current schedule: Podcasts at {time} {timezone} on {days}."
SCHEDULE_INVALID_FORMAT_MESSAGE = "Invalid schedule format. Please use: /schedule HH:MM [days] [timezone]"
SCHEDULE_INVALID_TIME_MESSAGE = "Invalid time format. Please use HH:MM (24-hour format)."
NO_SCHEDULE_MESSAGE = "You don't have any scheduled podcast deliveries."
EMPTY_QUEUE_SCHEDULE_MESSAGE = "You need content in your queue before scheduling. Please send me some links or documents first!"
SCHEDULE_CONFIRMATION = "Your schedule has been set! I'll deliver your podcast at {time} {timezone} on {days}.\n\nThe next delivery will be on {next_delivery}."

# Add day name mapping
DAY_NAMES = {
    0: "Monday",
    1: "Tuesday", 
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday"
}

# Dictionary to track user states for onboarding
user_states = {}

def initialize_scheduler(application):
    """Initialize the podcast scheduler."""
    try:
        global scheduler
        scheduler = PodcastScheduler(db, content_processor, script_generator, tts_processor, application.bot)
        scheduler.start_scheduler()
        logger.info("Scheduler initialization successful")
    except Exception as e:
        logger.error(f"Error initializing scheduler: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    user_id = user.id
    
    # Check if this is a new user
    is_new_user = db.is_new_user(user_id)
    
    # Initialize user state if not exists
    if user_id not in user_states:
        user_states[user_id] = {
            'onboarding_step': 0,
            'first_content_received': False
        }
    
    if is_new_user:
        # Mark user as having seen the onboarding
        db.set_user_flag(user_id, 'onboarded', True)
        
        # Send the welcome message
        await update.message.reply_text(WELCOME_MESSAGE)
        
        # Send the value proposition message immediately after
        await update.message.reply_text(WELCOME_VALUE_PROPOSITION)
        
        # Update user's onboarding step
        user_states[user_id]['onboarding_step'] = 1
        
        logger.info(f"Started onboarding sequence for new user {user_id}")
    else:
        # For existing users, just send a simpler greeting
        await update.message.reply_text(
            f"Welcome back {user.first_name}! Send me links, documents, or text to add to your queue, "
            f"or use /generate to create a podcast from your existing content."
        )
        
        logger.info(f"Sent welcome back message to existing user {user_id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(HELP_MESSAGE)

async def send_long_message(update: Update, text: str) -> None:
    """
    Split and send a long message that exceeds Telegram's message length limit.
    """
    # Safely escape any potentially harmful HTML
    text = text.replace("<", "&lt;").replace(">", "&gt;")

    # Reapply our own safe formatting
    text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")

    # If the message is short enough, send it directly
    if len(text) <= MAX_MESSAGE_LENGTH:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    # Otherwise, split the message into parts
    parts = textwrap.wrap(text, MAX_MESSAGE_LENGTH, replace_whitespace=False, break_long_words=False)
    total_parts = len(parts)

    # Send each part with a header indicating which part it is
    for i, part in enumerate(parts, 1):
        part_header = SCRIPT_PART_MESSAGE.format(part_number=i, total_parts=total_parts)

        if i == 1:
            # For the first part, just send as is (to include the intro)
            message_text = f"{part}"
        else:
            # For subsequent parts, add a continuation header
            message_text = f"{part_header}\n\n{part}"

        await update.message.reply_text(message_text, parse_mode=ParseMode.HTML)

async def send_content_examples(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send content examples message after a delay."""
    job = context.job
    user_id = job.data  # Job data contains the user_id
    
    try:
        if user_id in user_states and user_states[user_id]['first_content_received']:
            await context.bot.send_message(chat_id=user_id, text=CONTENT_EXAMPLES)
            user_states[user_id]['onboarding_step'] = 3
            
            # Schedule the daily recommendation message to be sent after 1 day (86400 seconds)
            context.job_queue.run_once(
                send_daily_recommendation,
                86400,  # 1 day in seconds
                data=user_id,
                name=f"daily_recommendation_{user_id}"
            )
    except Exception as e:
        logger.error(f"Error sending content examples: {str(e)}")

async def send_daily_recommendation(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send daily recommendation message after a delay."""
    job = context.job
    user_id = job.data  # Job data contains the user_id
    
    try:
        if user_id in user_states and user_states[user_id]['onboarding_step'] >= 3:
            await context.bot.send_message(chat_id=user_id, text=DAILY_TRIAGE_RECOMMENDATION)
            user_states[user_id]['onboarding_step'] = 4
    except Exception as e:
        logger.error(f"Error sending daily recommendation: {str(e)}")

async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a podcast from the user's content queue."""
    user_id = update.effective_user.id

    # Check if there's content in the queue
    content_queue = db.get_unprocessed_content(user_id)
    if not content_queue:
        await update.message.reply_text(EMPTY_QUEUE_MESSAGE)
        return

    # Send generating message
    status_message = await update.message.reply_text(GENERATING_MESSAGE)

    try:
        # Generate script
        formatted_script, plain_script, tts_script = script_generator.generate_script(user_id, content_queue)

        # Save scripts to files
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        script_dir = f"data/scripts/{user_id}"
        os.makedirs(script_dir, exist_ok=True)

        # Save all versions of the script
        with open(f"{script_dir}/formatted_{timestamp}.html", 'w') as f:
            f.write(formatted_script)
        with open(f"{script_dir}/plain_{timestamp}.txt", 'w') as f:
            f.write(plain_script)
        with open(f"{script_dir}/tts_{timestamp}.txt", 'w') as f:
            f.write(tts_script)

        try:
            # Generate and send only the audio
            audio_path = tts_processor.generate_audio(tts_script)

            # Check if audio_path is valid
            if audio_path and os.path.exists(audio_path):
                with open(audio_path, 'rb') as audio_file:
                    await update.message.reply_audio(
                        audio=audio_file,
                        caption="Your podcast is ready! Enjoy listening.",
                        title=f"triage.fm podcast - {datetime.now().strftime('%Y-%m-%d')}"
                    )

                # Clean up the audio file after sending
                try:
                    os.remove(audio_path)
                    logger.info(f"Deleted temporary audio file: {audio_path}")
                except Exception as e:
                    logger.error(f"Error deleting audio file: {str(e)}")
            else:
                logger.error("Audio generation failed or audio file not found.")
                warning = ("Note: Due to high server load, the audio version couldn't be generated this time. "
                           "You can try generating it again in a few minutes using the /generate command.")
                await update.message.reply_text(warning)

        except Exception as e:
            logger.error(f"Error generating audio: {str(e)}")
            warning = ("Note: Due to high server load, the audio version couldn't be generated this time. "
                       "You can try generating it again in a few minutes using the /generate command.")
            await update.message.reply_text(warning)

        # Generate content summaries with ADHD-friendly formatting
        summary_message = "🎙️ PODCAST SUMMARY\n━━━━━━━━━━━━━━━\n\n"
        for i, item in enumerate(content_queue, 1):
            title = item.get('title', 'Untitled')
            author = item.get('author', 'Unknown Author')
            source_url = item.get('source_url', '')
            message_id = item.get('message_id', '')

            # Generate a focused 1-2 sentence summary for each item
            try:
                summary = script_generator.generate_content_summary(item)
            except Exception:
                content = item.get('content', '')
                summary = content[:200] + '...' if len(content) > 200 else content

            # Format the item link
            if source_url:
                link = source_url
            elif message_id:
                link = f"t.me/c/{abs(user_id)}/{message_id}"
            else:
                link = "No link available"

            # Create visually structured item summary with emojis and clear sections
            summary_message += f"📎 ITEM {i}\n"
            summary_message += f"━━━━━━━━━━━━━━━\n"
            summary_message += f"📗 Title: {title}\n"
            summary_message += f"✍️ Author: {author}\n"
            summary_message += f"💡 Insights: {summary}\n"
            summary_message += f"🔗 Link: {link}\n\n"

        # Send summary message
        await update.message.reply_text(summary_message, disable_web_page_preview=True)

        # Mark content as processed
        content_ids = [item['id'] for item in content_queue]
        db.mark_content_as_processed(user_id, content_ids)

        # Delete the status message
        await status_message.delete()

    except Exception as e:
        logger.error(f"Error generating podcast: {str(e)}")
        await update.message.reply_text(ERROR_MESSAGE)
        await status_message.delete()

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's content queue."""
    user_id = update.effective_user.id
    # Get unprocessed content
    unprocessed_content = db.get_unprocessed_content(user_id)
    if not unprocessed_content:
        await update.message.reply_text(QUEUE_EMPTY_MESSAGE)
        return

    # Create readable content type mapping
    content_type_display = {
        "youtube_video": "📺 YouTube Video",
        "web_article": "📄 Web Article",
        "document": "📝 Document",
        "plain_text": "✍️ Text Note",
        "forwarded": "↪️ Forwarded Message",
        "twitter_post": "🐦 Twitter Post",
        "unknown": "❓ Unknown Type",
    }

    # Format queue message
    queue_message = f"{QUEUE_HEADER_MESSAGE}\n\n"
    for i, item in enumerate(unprocessed_content, 1):
        content_type = item.get('content_type', 'unknown')
        readable_type = content_type_display.get(content_type, '❓ Unknown Type')
        
        if content_type == 'twitter_post':
            # For tweets, use the first sentence of content
            content = item.get('content', '')
            first_sentence = content.split('.')[0].strip()
            if len(first_sentence) > 100:
                first_sentence = first_sentence[:97] + "..."
            author = item.get('author', 'Unknown Author')
            display_title = f'"{first_sentence}" by {author}'
        else:
            display_title = f'"{item.get("title", "Untitled content")}"'
            
        queue_message += f"{i}. {display_title} [{readable_type}]\n"
    
    # Use send_long_message to handle potentially long messages
    await send_long_message(update, queue_message)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the user's content queue."""
    user_id = update.effective_user.id

    # Clear unprocessed content
    db.clear_unprocessed_content(user_id)

    await update.message.reply_text(QUEUE_CLEARED_MESSAGE)

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /schedule command to set up automated podcast delivery."""
    user_id = update.effective_user.id
    
    # Get command arguments
    args = context.args
    
    # If no arguments, show current schedule or help
    if not args:
        # Check if user has a schedule
        schedule = db.get_user_schedule(user_id)
        if schedule:
            time_str = schedule.get('time', '00:00')
            timezone = schedule.get('timezone', 'UTC')
            days = schedule.get('days', list(range(7)))
            
            # Format days as text
            if len(days) == 7:
                days_text = "every day"
            else:
                days_text = ", ".join(DAY_NAMES[day] for day in days)
            
            await update.message.reply_text(
                SCHEDULE_CURRENT_MESSAGE.format(
                    time=time_str,
                    timezone=timezone,
                    days=days_text
                )
            )
        else:
            # Check if user has saved timezone preference
            saved_timezone = db.get_user_timezone(user_id)
            timezone_msg = ""
            if saved_timezone:
                timezone_msg = f"\n\nYour current timezone is set to: {saved_timezone}"
                
            # Update help message to include timezone info
            updated_help = (
                SCHEDULE_HELP_MESSAGE + 
                "\n\nYou can also use city names for timezones:\n" +
                "/schedule 08:30 mon,wed,fri moscow\n" +
                "/schedule 14:00 new york\n\n" +
                "Common cities: new york, london, paris, berlin, moscow, tokyo, sydney" +
                timezone_msg
            )
            await update.message.reply_text(updated_help)
        return
    
    # Check for cancel command
    if args[0].lower() == 'cancel':
        # Cancel the schedule
        if scheduler.unschedule_podcast(user_id):
            await update.message.reply_text(SCHEDULE_CANCELED_MESSAGE)
        else:
            await update.message.reply_text(NO_SCHEDULE_MESSAGE)
        return
    
    # Parse time
    time_str = args[0]
    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        await update.message.reply_text(SCHEDULE_INVALID_FORMAT_MESSAGE)
        return
    
    try:
        hour, minute = map(int, time_str.split(':'))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            await update.message.reply_text(SCHEDULE_INVALID_TIME_MESSAGE)
            return
    except ValueError:
        await update.message.reply_text(SCHEDULE_INVALID_TIME_MESSAGE)
        return
    
    # Parse days and timezone
    days = None
    timezone = None  # Will be set to saved preference or UTC later
    timezone_specified = False  # Flag to track if user specified a timezone
    
    if len(args) > 1:
        # Check if the second argument is days or timezone
        if any(day in args[1].lower() for day in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']):
            # This is a day specification
            day_arg = args[1].lower()
            day_mapping = {
                'mon': 0, 'monday': 0,
                'tue': 1, 'tuesday': 1,
                'wed': 2, 'wednesday': 2,
                'thu': 3, 'thursday': 3,
                'fri': 4, 'friday': 4,
                'sat': 5, 'saturday': 5,
                'sun': 6, 'sunday': 6
            }
            
            days = []
            day_parts = day_arg.split(',')
            
            for part in day_parts:
                part = part.strip()
                if part in day_mapping:
                    days.append(day_mapping[part])
                else:
                    # Invalid day format
                    await update.message.reply_text(f"Invalid day format: {part}. Please use mon, tue, wed, thu, fri, sat, sun")
                    return
            
            # Check if there's a timezone specified as the third argument
            if len(args) > 2:
                # Get timezone from remaining arguments (for multi-word city names)
                timezone_input = ' '.join(args[2:])
                friendly_timezone = get_friendly_timezone(timezone_input)
                if friendly_timezone:
                    timezone = friendly_timezone
                    timezone_specified = True
                else:
                    await update.message.reply_text(
                        f"'{timezone_input}' is not a recognized timezone or city. Please use a standard timezone format (like 'Europe/Paris') " 
                        f"or a major city name (like 'paris', 'new york', 'tokyo')."
                    )
                    return
        else:
            # The second argument might be a timezone or part of a multi-word city name
            timezone_input = ' '.join(args[1:])
            friendly_timezone = get_friendly_timezone(timezone_input)
            if friendly_timezone:
                timezone = friendly_timezone
                timezone_specified = True
            else:
                await update.message.reply_text(
                    f"'{timezone_input}' is not a recognized timezone or city. Please use a standard timezone format (like 'Europe/Paris') " 
                    f"or a major city name (like 'paris', 'new york', 'tokyo')."
                )
                return
    
    # If no timezone specified, use saved preference or default to UTC
    if not timezone_specified:
        saved_timezone = db.get_user_timezone(user_id)
        if saved_timezone:
            timezone = saved_timezone
        else:
            timezone = "UTC"
    
    # Validate the timezone one more time
    try:
        tz = pytz.timezone(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        await update.message.reply_text(
            f"'{timezone}' is not a valid timezone. Please use a standard timezone format (like 'Europe/Paris') " 
            f"or a major city name (like 'paris', 'new york', 'tokyo')."
        )
        return
    
    # Save the timezone preference if specified
    if timezone_specified:
        db.set_user_timezone(user_id, timezone)
    
    # Schedule the podcast
    if scheduler.schedule_podcast(user_id, hour, minute, days, timezone):
        # Format days as text
        if days is None or len(days) == 7:
            days_text = "every day"
        else:
            days_text = ", ".join(DAY_NAMES[day] for day in days)
        
        # Format time in 12-hour format for display
        time_obj = time(hour=hour, minute=minute)
        formatted_time = time_obj.strftime("%I:%M %p")
        
        # Get next delivery time
        next_delivery = scheduler.get_next_delivery_time(user_id)
        next_delivery_text = next_delivery.strftime("%A, %B %d at %I:%M %p") if next_delivery else "unknown"
        
        # Add message about using saved timezone if not specified
        timezone_msg = ""
        if not timezone_specified and saved_timezone:
            timezone_msg = f"\n\nNote: Using your saved timezone preference ({timezone})."
        
        await update.message.reply_text(
            SCHEDULE_CONFIRMATION.format(
                time=formatted_time,
                timezone=timezone,
                days=days_text,
                next_delivery=next_delivery_text
            ) + timezone_msg
        )
    else:
        await update.message.reply_text(
            "I'm sorry, but I couldn't set your schedule. Please try again later."
        )

async def personalize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    # Set state to expect a Verida token
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]['awaiting_verida_token'] = True

    verida_connect_url = (
        "https://app.verida.ai/auth?appDID=did:vda:polpos:0x3F2810A6fa9a2e79B4c3A77Cf14D660D97e690e0"
        "&payer=app"
        "&scopes=api:ds-query"
        "&scopes=api:llm-agent-prompt"
        "&scopes=api:llm-profile-prompt"
        "&scopes=api:search-universal"
        "&scopes=ds:social-email"
        "&redirectUrl=https://admin.verida.ai/sandbox/token-generated"
    )
    keyboard = [
        [InlineKeyboardButton("Connect with Verida", url=verida_connect_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔗 <b>Let's personalize your podcast experience!</b>\n\n"
        "<b>1.</b> Click the button below to connect your Verida account and authorize access to your social data.\n"
        "<b>2.</b> After connecting, copy the token shown on the final page and paste it here in this chat.\n\n"
        "I'll save your token and use it to personalize your podcasts!",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = update.message

    # 1. Check for Verida token FIRST
    if user_id in user_states and user_states[user_id].get('awaiting_verida_token'):
        # Try to parse as JSON (for JSON tokens)
        try:
            token_data = json.loads(message.text)
            if 'token' in token_data and 'did' in token_data['token']:
                db.set_user_verida_token(user_id, token_data)
                user_states[user_id]['awaiting_verida_token'] = False
                await update.message.reply_text("✅ Your Verida token has been saved! Your podcast will now be personalized with your social data.")
                return
        except Exception:
            # If not JSON, try to treat as a raw token string
            token_str = message.text.strip()
            if len(token_str) > 30:  # crude check for token length
                db.set_user_verida_token(user_id, token_str)
                user_states[user_id]['awaiting_verida_token'] = False
                await update.message.reply_text("✅ Your Verida token has been saved! Your podcast will now be personalized with your social data.")
                return
        # If not valid, prompt user
        await update.message.reply_text("❌ That doesn't look like a valid Verida token. Please try again or restart /personalize.")
        return

    logger.info(f"Processing message from user {user_id}: {message.text}")

    # Initialize user state if not exists
    if user_id not in user_states:
        user_states[user_id] = {
            'onboarding_step': 0,
            'first_content_received': False
        }

    # Handle commands that might be missing the slash
    if message.text and not message.text.startswith('/'):
        lowercase_text = message.text.lower()
        if lowercase_text in ['start', 'help', 'generate', 'queue', 'clear', 'schedule', 'personalize']:
            await update.message.reply_text(COMMAND_CORRECTION_MESSAGE.format(command=lowercase_text))
            return

    # Check for message properties to determine content type
    content_item = None

    # Process text from the message, even if it has photos
    if message.text or message.caption:
        # Use caption if text is None (for messages with photos)
        text_content = message.text if message.text else message.caption
        if text_content:
            logger.info(f"Processing text content: {text_content}")
            # Check if it's a text-only message or contains a URL
            content_item = content_processor.process_text(
                text_content, 
                user_id,
                message_id=message.message_id,
                is_forwarded=bool(message.forward_from or message.forward_from_chat)
            )
            logger.info(f"Content processing result: {content_item}")

    # Process document
    elif message.document:
        logger.info(f"Processing document: {message.document.file_name}")
        # Get file from Telegram
        file = await message.document.get_file()
        file_path = f"temp/{message.document.file_id}"
        await file.download_to_drive(file_path)

        content_item = content_processor.process_document(
            file_path, 
            message.document.file_name, 
            user_id
        )

        # Clean up temp file
        os.remove(file_path)
	# Unknown content type
    else:
        logger.warning(f"Unknown content type for message: {message}")
        await message.reply_text(UNKNOWN_CONTENT_TYPE_MESSAGE)
        return

    # Handle content processing result
    if content_item and content_item.get('success'):
        logger.info(f"Successfully processed content: {content_item.get('title', 'No title')}")
        # Store content in database
        if db.add_content(content_item):
            # Check if this is the first content received during onboarding
            if not user_states[user_id]['first_content_received']:
                user_states[user_id]['first_content_received'] = True
                
                # Send the first content received message instead of the standard message
                await message.reply_text(FIRST_CONTENT_RECEIVED)
                
                # Schedule the content examples message to be sent after 5 minutes
                context.job_queue.run_once(
                    send_content_examples,
                    300,  # 300 seconds = 5 minutes
                    data=user_id,
                    name=f"content_examples_{user_id}"
                )
                
                logger.info(f"Scheduled content examples message for user {user_id} in 5 minutes")
            else:
                # Send standard confirmation for subsequent content
                await message.reply_text(CONTENT_RECEIVED_MESSAGE)
        else:
            await message.reply_text("This content is already in your queue. I'll skip adding it again.")
    elif content_item and content_item.get('unsupported'):
        logger.warning(f"Unsupported content: {content_item.get('message', 'No message')}")
        await message.reply_text(
            UNSUPPORTED_CONTENT_MESSAGE.format(message=content_item.get('message', 'this content type is not supported yet'))
        )
    else:
        logger.error(f"Failed to process content: {content_item}")
        await message.reply_text(PROCESSING_ERROR_MESSAGE)

def main() -> None:
    """Start the bot."""
    try:
        # Start the keep-alive server for Replit
        keep_alive_server = start_keep_alive()
        logger.info("Keep-alive server started")
        
        # Create application
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("No TELEGRAM_BOT_TOKEN found in environment variables")
            return

        # Initialize database
        db.initialize()
        
        # Clean up old audio files on startup
        tts_processor.cleanup_old_files()
        
        # Create temp directories if they don't exist
        os.makedirs("temp", exist_ok=True)
        os.makedirs("temp/audio", exist_ok=True)
        os.makedirs("data", exist_ok=True)

        application = Application.builder().token(token).http_version("1.1").get_updates_http_version("1.1").pool_timeout(60).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("generate", generate_command))
        application.add_handler(CommandHandler("queue", queue_command))
        application.add_handler(CommandHandler("clear", clear_command))
        application.add_handler(CommandHandler("schedule", schedule_command))
        application.add_handler(CommandHandler("personalize", personalize_command))
        
        # Add message handler for content - including photos and all types that might have captions
        application.add_handler(MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.FORWARDED, 
            process_message
        ))

        # Initialize scheduler
        initialize_scheduler(application)
        logger.info("Initialization complete, starting polling")

        # Start the Bot
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Error in main function: {str(e)}")

if __name__ == "__main__":
    main()