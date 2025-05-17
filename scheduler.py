"""
Improved Scheduler Module for Replit environment

This module handles scheduling and timed delivery of podcast content,
optimized for Replit's environment constraints.
"""
import os
import logging
import json
import time
from datetime import datetime, timedelta
import threading
import pytz
import requests
import io
from requests_toolbelt import MultipartEncoder

# Map of user-friendly timezone names to IANA timezone database names
FRIENDLY_TIMEZONES = {
    # Americas
    "us/eastern": "US/Eastern",
    "us/central": "US/Central", 
    "us/mountain": "US/Mountain",
    "us/pacific": "US/Pacific",
    "new york": "America/New_York",
    "chicago": "America/Chicago",
    "los angeles": "America/Los_Angeles",
    "toronto": "America/Toronto",
    "mexico city": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    
    # Europe
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "rome": "Europe/Rome",
    "madrid": "Europe/Madrid",
    "moscow": "Europe/Moscow",
    "istanbul": "Europe/Istanbul",
    "athens": "Europe/Athens",
    
    # Asia
    "dubai": "Asia/Dubai",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "tokyo": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong",
    
    # Oceania
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "perth": "Australia/Perth",
    "auckland": "Pacific/Auckland",
    
    # Africa
    "cairo": "Africa/Cairo",
    "johannesburg": "Africa/Johannesburg",
    "lagos": "Africa/Lagos",
    
    # Standard timezones
    "utc": "UTC",
    "gmt": "GMT",
}

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_friendly_timezone(timezone_input):
    """
    Get the IANA timezone from a user-friendly input.
    
    Args:
        timezone_input (str): User input for timezone
        
    Returns:
        str: IANA timezone string or None if not found
    """
    # Normalize input
    cleaned_input = timezone_input.lower().strip()
    
    # Direct match in our friendly mappings
    if cleaned_input in FRIENDLY_TIMEZONES:
        return FRIENDLY_TIMEZONES[cleaned_input]
        
    # Check if it's already a valid IANA timezone
    try:
        pytz.timezone(timezone_input)
        return timezone_input
    except pytz.exceptions.UnknownTimeZoneError:
        pass
        
    # Try partial matching for major cities
    for friendly_name, iana_name in FRIENDLY_TIMEZONES.items():
        if cleaned_input in friendly_name:
            return iana_name
            
    # No match found
    return None

class PodcastScheduler:
    """Manages scheduling and delivery of triage.fm podcasts."""
    
    def __init__(self, db, content_processor, script_generator, tts_processor, bot):
        """
        Initialize the podcast scheduler.
        
        Args:
            db: Database instance for accessing user data
            content_processor: ContentProcessor instance
            script_generator: ScriptGenerator instance
            tts_processor: TTSProcessor instance
            bot: Telegram bot instance for sending messages
        """
        self.db = db
        self.content_processor = content_processor
        self.script_generator = script_generator
        self.tts_processor = tts_processor
        self.bot = bot
        
        # Jobs storage
        self.jobs_file = os.path.join("data", "scheduled_jobs.json")
        
        # Create jobs directory if it doesn't exist
        os.makedirs(os.path.dirname(self.jobs_file), exist_ok=True)
        
        # Thread control
        self.running = False
        self.scheduler_thread = None
        
        # Load existing jobs
        self.jobs = self.load_jobs()
        
        # Preparation time in minutes (generate podcast this many minutes before delivery)
        self.preparation_time_minutes = 5
        
        logger.info("Podcast scheduler initialized successfully")
    
    def load_jobs(self):
        """Load jobs from the jobs file."""
        try:
            if os.path.exists(self.jobs_file):
                with open(self.jobs_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading scheduled jobs: {str(e)}")
            return []
    
    def save_jobs(self):
        """Save jobs to the jobs file."""
        try:
            # Filter out any None values that might have crept in
            jobs_to_save = [job for job in self.jobs if job]
            
            with open(self.jobs_file, 'w') as f:
                json.dump(jobs_to_save, f, indent=2)
            
            logger.info(f"Saved {len(jobs_to_save)} scheduled jobs")
        except Exception as e:
            logger.error(f"Error saving scheduled jobs: {str(e)}")
    
    def schedule_podcast(self, user_id, hour, minute, days=None, timezone='UTC'):
        """
        Schedule a podcast for delivery at a specific time.
        
        Args:
            user_id (int): Telegram user ID
            hour (int): Hour of the day (0-23)
            minute (int): Minute of the hour (0-59)
            days (list): Days of the week to deliver (0-6, where 0 is Monday)
                If None, deliver every day.
            timezone (str): User's timezone
        
        Returns:
            bool: True if scheduled successfully, False otherwise
        """
        try:
            # Remove any existing job for this user
            self.unschedule_podcast(user_id)
            
            # Add the new job
            job = {
                'user_id': user_id,
                'time': f"{hour:02d}:{minute:02d}",
                'days': days if days else list(range(7)),  # Store all days if None
                'timezone': timezone,
                'next_check': datetime.now().timestamp(),  # Set initial check time
                'is_being_prepared': False,                # Add flag to track preparation status
                'prepared_audio_path': None               # Add field to store path to prepared audio
            }
            
            self.jobs.append(job)
            
            # Store the schedule in the database
            self.db.set_user_schedule(user_id, {
                'time': f"{hour:02d}:{minute:02d}",
                'days': days if days else list(range(7)),
                'timezone': timezone
            })
            
            # Save jobs to file
            self.save_jobs()
            
            logger.info(f"Scheduled podcast for user {user_id} at {hour:02d}:{minute:02d} {timezone} on days {days if days else 'every day'}")
            return True
            
        except Exception as e:
            logger.error(f"Error scheduling podcast: {str(e)}")
            return False
    
    def unschedule_podcast(self, user_id):
        """
        Remove a scheduled podcast.
        
        Args:
            user_id (int): Telegram user ID
        
        Returns:
            bool: True if unscheduled successfully, False otherwise
        """
        try:
            # Remove from jobs list
            self.jobs = [job for job in self.jobs if job.get('user_id') != user_id]
            
            # Remove from database
            self.db.remove_user_schedule(user_id)
            
            # Save jobs to file
            self.save_jobs()
            
            logger.info(f"Unscheduled podcast for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error unscheduling podcast: {str(e)}")
            return False
    
    def get_next_delivery_time(self, user_id):
        """
        Get the next scheduled delivery time for a user.
        
        Args:
            user_id (int): Telegram user ID
        
        Returns:
            datetime or None: Next delivery time or None if not scheduled
        """
        try:
            # Find the job for this user
            for job in self.jobs:
                if job.get('user_id') == user_id:
                    # Parse time
                    time_str = job.get('time', '00:00')
                    hour, minute = map(int, time_str.split(':'))
                    
                    # Parse timezone
                    timezone = job.get('timezone', 'UTC')
                    tz = pytz.timezone(timezone)
                    
                    # Get current time in user's timezone
                    now = datetime.now(tz)
                    
                    # Create a datetime for today at the scheduled time
                    scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # If the scheduled time is in the past, move to tomorrow
                    if scheduled_time < now:
                        scheduled_time = scheduled_time + timedelta(days=1)
                    
                    # Check if the day of the week is included
                    days = job.get('days', list(range(7)))
                    
                    # Find the next valid delivery day
                    while scheduled_time.weekday() not in days:
                        scheduled_time = scheduled_time + timedelta(days=1)
                    
                    return scheduled_time
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting next delivery time: {str(e)}")
            return None
    
    def start_scheduler(self):
        """Start the scheduler thread."""
        if self.running:
            return
        
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        logger.info("Podcast scheduler thread started")
    
    def stop_scheduler(self):
        """Stop the scheduler thread."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=1.0)
        logger.info("Podcast scheduler thread stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop."""
        try:
            logger.info("Scheduler loop started")
            while self.running:
                # Check for jobs that need to be prepared or delivered
                self._check_jobs()
                
                # Sleep for a bit to avoid excessive CPU usage
                time.sleep(30)  # Check every 30 seconds for more responsive scheduling
        except Exception as e:
            logger.error(f"Error in scheduler loop: {str(e)}")
    
    def _check_jobs(self):
        """
        Check for jobs that need to be prepared or delivered.
        Now includes logic to prepare podcasts in advance.
        """
        try:
            current_time = datetime.now().timestamp()
            
            for job in self.jobs:
                try:
                    user_id = job.get('user_id')
                    
                    # Parse time
                    time_str = job.get('time', '00:00')
                    hour, minute = map(int, time_str.split(':'))
                    
                    # Parse timezone
                    timezone = job.get('timezone', 'UTC')
                    tz = pytz.timezone(timezone)
                    
                    # Get current time in user's timezone
                    now = datetime.now(tz)
                    
                    # Create a datetime for today at the scheduled time
                    scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # Create preparation time (N minutes before scheduled time)
                    preparation_time = scheduled_time - timedelta(minutes=self.preparation_time_minutes)
                    
                    # Get the next check time for this job
                    next_check = job.get('next_check', current_time)
                    
                    # If it's time to check 
                    if current_time >= next_check:
                        # Check if the day of the week is included
                        days = job.get('days', list(range(7)))
                        
                        # Get preparation status
                        is_being_prepared = job.get('is_being_prepared', False)
                        prepared_audio_path = job.get('prepared_audio_path', None)
                        
                        # If today is a delivery day
                        if now.weekday() in days:
                            # If we're in the preparation window but haven't started preparing yet
                            if preparation_time <= now < scheduled_time and not is_being_prepared and not prepared_audio_path:
                                # Time to prepare!
                                logger.info(f"Time to prepare podcast for user {user_id}")
                                
                                # Set the flag to prevent duplicate preparation
                                job['is_being_prepared'] = True
                                self.save_jobs()
                                
                                # Generate in a separate thread to avoid blocking
                                preparation_thread = threading.Thread(
                                    target=self._prepare_podcast, 
                                    args=[user_id]
                                )
                                preparation_thread.daemon = True
                                preparation_thread.start()
                                
                                # Check again in 1 minute
                                job['next_check'] = current_time + 60
                                
                            # If we're at or past the delivery time and the audio is prepared
                            elif scheduled_time <= now < scheduled_time + timedelta(minutes=2) and prepared_audio_path:
                                # Time to deliver!
                                logger.info(f"Time to deliver prepared podcast for user {user_id}")
                                
                                # Send the podcast in a separate thread
                                delivery_thread = threading.Thread(
                                    target=self._send_prepared_podcast, 
                                    args=[user_id, prepared_audio_path]
                                )
                                delivery_thread.daemon = True
                                delivery_thread.start()
                                
                                # Reset flags and set next check time to tomorrow
                                job['is_being_prepared'] = False
                                job['prepared_audio_path'] = None
                                job['next_check'] = (now.replace(hour=0, minute=0, second=0) + timedelta(days=1)).timestamp()
                                self.save_jobs()
                                
                            # If we're at or past the delivery time but don't have prepared audio
                            elif scheduled_time <= now < scheduled_time + timedelta(minutes=2) and not prepared_audio_path:
                                # Attempt to generate and deliver immediately
                                logger.info(f"No prepared podcast available for user {user_id}, generating now")
                                
                                # Generate and send in a separate thread
                                delivery_thread = threading.Thread(
                                    target=self._generate_and_send_podcast, 
                                    args=[user_id]
                                )
                                delivery_thread.daemon = True
                                delivery_thread.start()
                                
                                # Reset flags and set next check time to tomorrow
                                job['is_being_prepared'] = False
                                job['next_check'] = (now.replace(hour=0, minute=0, second=0) + timedelta(days=1)).timestamp()
                                self.save_jobs()
                            else:
                                # Not preparation or delivery time yet, check again in 30 seconds
                                job['next_check'] = current_time + 30
                        else:
                            # Not a delivery day, check again tomorrow
                            job['next_check'] = (now.replace(hour=0, minute=0, second=0) + timedelta(days=1)).timestamp()
                            
                            # Reset preparation flags
                            job['is_being_prepared'] = False
                            if job.get('prepared_audio_path'):
                                try:
                                    # Clean up any prepared audio
                                    audio_path = job.get('prepared_audio_path')
                                    if audio_path and os.path.exists(audio_path):
                                        os.remove(audio_path)
                                except Exception as e:
                                    logger.error(f"Error removing audio file: {str(e)}")
                            job['prepared_audio_path'] = None
                    
                except Exception as e:
                    logger.error(f"Error checking job for user {job.get('user_id')}: {str(e)}")
            
            # Save updated jobs
            self.save_jobs()
            
        except Exception as e:
            logger.error(f"Error checking jobs: {str(e)}")
    
    def start_preparation_scheduler(self):
        """
        Start the scheduler. In this simplified version, we just start the main scheduler.
        """
        self.start_scheduler()
    
    def _prepare_podcast(self, user_id):
        """
        Prepare a podcast in advance of the scheduled delivery time.
        
        Args:
            user_id (int): Telegram user ID
        """
        logger.info(f"Preparing scheduled podcast for user {user_id}")
        try:
            # Generate the podcast
            audio_path = self._generate_podcast_now(user_id)
            
            if audio_path:
                logger.info(f"Successfully prepared podcast for user {user_id} at {audio_path}")
                
                # Find the job and update it
                for job in self.jobs:
                    if job.get('user_id') == user_id:
                        job['prepared_audio_path'] = audio_path
                        job['is_being_prepared'] = False
                        break
                        
                # Save the updated jobs
                self.save_jobs()
            else:
                logger.error(f"Failed to prepare podcast for user {user_id}")
                
                # Reset the preparation flag
                for job in self.jobs:
                    if job.get('user_id') == user_id:
                        job['is_being_prepared'] = False
                        break
                        
                self.save_jobs()
            
        except Exception as e:
            logger.error(f"Error preparing podcast: {str(e)}")
            
            # Reset the preparation flag
            for job in self.jobs:
                if job.get('user_id') == user_id:
                    job['is_being_prepared'] = False
                    break
                    
            self.save_jobs()
    
    def _generate_podcast_now(self, user_id):
        """
        Generate a podcast immediately.
        
        Args:
            user_id (int): Telegram user ID
        
        Returns:
            str or None: Path to the generated audio file or None if failed
        """
        try:
            # Get unprocessed content
            content_queue = self.db.get_unprocessed_content(user_id)
            if not content_queue:
                logger.warning(f"No content in queue for user {user_id}")
                return None
            
            # Generate script
            _, _, tts_script = self.script_generator.generate_script(user_id, content_queue)
            
            # Generate audio
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            audio_filename = f"scheduled_{user_id}_{timestamp}.mp3"
            audio_path = self.tts_processor.generate_audio(tts_script, filename=audio_filename)
            
            if audio_path and os.path.exists(audio_path):
                # Mark content as processed
                content_ids = [item['id'] for item in content_queue]
                self.db.mark_content_as_processed(user_id, content_ids)
                
                # Generate content summaries for later use
                summaries = []
                for item in content_queue:
                    try:
                        summary = self.script_generator.generate_content_summary(item)
                    except Exception:
                        content = item.get('content', '')
                        summary = content[:200] + '...' if len(content) > 200 else content
                    
                    summaries.append({
                        'title': item.get('title', 'Untitled'),
                        'author': item.get('author', 'Unknown Author'),
                        'summary': summary,
                        'source_url': item.get('source_url', ''),
                        'message_id': item.get('message_id', '')
                    })
                
                # Store summaries for later use when sending the podcast
                self.db.set_podcast_summaries(user_id, summaries)
                
                return audio_path
            else:
                logger.error(f"Failed to generate audio for user {user_id}")
                return None
        
        except Exception as e:
            logger.error(f"Error generating podcast: {str(e)}")
            return None
            
    def _generate_and_send_podcast(self, user_id):
        """
        Generate and send a podcast to a user.
        
        Args:
            user_id (int): Telegram user ID
        """
        logger.info(f"Generating scheduled podcast for user {user_id}")
        try:
            # Get unprocessed content first to check if there's anything to process
            content_queue = self.db.get_unprocessed_content(user_id)
            
            # If there's no content, just send a null message
            if not content_queue:
                self._send_null_content_message(user_id)
                return
                
            # Generate the podcast
            audio_path = self._generate_podcast_now(user_id)
            
            if not audio_path:
                logger.error(f"Failed to generate podcast for user {user_id}")
                self._send_error_message(user_id)
                return
            
            # Send the podcast to the user
            self._send_podcast(user_id, audio_path)
            
            # Clean up the file
            try:
                os.remove(audio_path)
            except Exception as e:
                logger.warning(f"Error removing temporary audio file: {str(e)}")
            
            logger.info(f"Successfully delivered scheduled podcast to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error delivering scheduled podcast: {str(e)}")
            self._send_error_message(user_id)
    
    def _send_prepared_podcast(self, user_id, audio_path):
        """Send a prepared podcast to a user.
        
        Args:
            user_id (int): Telegram user ID
            audio_path (str): Path to the audio file
        """
        # Check if the audio file exists
        if os.path.exists(audio_path):
            self._send_podcast(user_id, audio_path)
        else:
            logger.error(f"Prepared audio file doesn't exist: {audio_path}")
            # Try to generate and send a new podcast
            self._generate_and_send_podcast(user_id)
    
    def _send_podcast(self, user_id, audio_path):
        """
        Send a podcast to a user.
        
        Args:
            user_id (int): Telegram user ID
            audio_path (str): Path to the audio file
        """
        try:
            # Since we can't use await directly in this method (it's not an async function),
            # we need to use a different approach to send messages in a synchronous context
            
            # For send_audio
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
            
            # Use the synchronous post method to send the audio
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            audio_url = f"https://api.telegram.org/bot{bot_token}/sendAudio"
            
            # Get file name
            file_name = os.path.basename(audio_path)
            
            # Create the form data
            form_data = {
                'chat_id': str(user_id),
                'title': f"triage.fm podcast - {datetime.now().strftime('%Y-%m-%d')}",
                'caption': "Your scheduled podcast is ready! Enjoy listening.",
                'audio': (file_name, io.BytesIO(audio_data), 'audio/mpeg')
            }
            
            # Create multipart encoder
            m = MultipartEncoder(fields=form_data)
            
            # Send the request
            response = requests.post(
                audio_url,
                data=m,
                headers={'Content-Type': m.content_type}
            )
            
            if not response.ok:
                logger.error(f"Error sending audio: {response.status_code} {response.text}")
            
            # Send summary message
            summaries = self.db.get_podcast_summaries(user_id)
            if summaries:
                summary_message = "🎙️ PODCAST SUMMARY\n━━━━━━━━━━━━━━━\n\n"
                
                for i, item in enumerate(summaries, 1):
                    title = item.get('title', 'Untitled')
                    author = item.get('author', 'Unknown Author')
                    summary = item.get('summary', 'No summary available')
                    source_url = item.get('source_url', '')
                    message_id = item.get('message_id', '')
                    
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
                
                # Use the synchronous post method to send the message
                message_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                message_data = {
                    'chat_id': str(user_id),
                    'text': summary_message,
                    'disable_web_page_preview': 'true'
                }
                
                msg_response = requests.post(message_url, json=message_data)
                if not msg_response.ok:
                    logger.error(f"Error sending summary message: {msg_response.status_code} {msg_response.text}")
            
            # Clear the prepared podcast path
            self.db.clear_prepared_podcast(user_id)
            
        except Exception as e:
            logger.error(f"Error sending podcast: {str(e)}")
    
    def _send_error_message(self, user_id):
        """
        Send an error message to a user when podcast delivery fails.
        
        Args:
            user_id (int): Telegram user ID
        """
        try:
            error_message = (
                "I'm sorry, but I couldn't deliver your scheduled podcast. "
                "Please try using the /generate command manually, or check that you have content in your queue with /queue."
            )
            
            # Use the synchronous post method to send the message
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            message_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            message_data = {
                'chat_id': str(user_id),
                'text': error_message
            }
            
            response = requests.post(message_url, json=message_data)
            if not response.ok:
                logger.error(f"Error sending error message: {response.status_code} {response.text}")
            
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")
            
    def _send_null_content_message(self, user_id):
        """
        Send a message to a user when their content queue is empty.
        Instead of preventing scheduling, we'll just send a pre-made message.
        
        Args:
            user_id (int): Telegram user ID
        """
        try:
            null_message = (
                "Your scheduled podcast delivery time has arrived, but your content queue is empty. "
                "Please send me some links, documents, or text content to include in your next podcast."
            )
            
            # Use the synchronous post method to send the message
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            message_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            message_data = {
                'chat_id': str(user_id),
                'text': null_message
            }
            
            response = requests.post(message_url, json=message_data)
            if not response.ok:
                logger.error(f"Error sending null content message: {response.status_code} {response.text}")
            
        except Exception as e:
            logger.error(f"Error sending null content message: {str(e)}")