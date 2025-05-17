"""
Database Module

This module handles all data persistence for the Onager bot.
For simplicity in the MVP, we'll use a JSON-based file storage system.
"""
import os
import json
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    """Simple file-based database for content storage."""
    
    def __init__(self):
        """Initialize the database."""
        self.db_dir = "data"
        self.content_file = os.path.join(self.db_dir, "content.json")
        self.user_prefs_file = os.path.join(self.db_dir, "user_preferences.json")
    
    def initialize(self):
        """Create database files if they don't exist."""
        # Create data directory if it doesn't exist
        os.makedirs(self.db_dir, exist_ok=True)
        
        # Create content file if it doesn't exist
        if not os.path.exists(self.content_file):
            with open(self.content_file, 'w') as f:
                json.dump([], f)
        
        # Create user preferences file if it doesn't exist
        if not os.path.exists(self.user_prefs_file):
            with open(self.user_prefs_file, 'w') as f:
                json.dump({}, f)
        
        logger.info("Database initialized successfully")

    def is_duplicate(self, content_item, existing_content):
        """
        Check if content item is a duplicate based on content type.
        
        Args:
            content_item (dict): New content item to check
            existing_content (list): List of existing content items
        
        Returns:
            bool: True if content is duplicate, False otherwise
        """
        user_id = content_item.get('user_id')
        content_type = content_item.get('content_type')
        
        # Filter for user's content only
        user_content = [item for item in existing_content if item.get('user_id') == user_id]
        
        if not user_content:
            return False
            
        if content_type == 'web_article':
            # Check source URL for web articles
            source_url = content_item.get('source_url')
            return any(
                item.get('source_url') == source_url
                for item in user_content
                if item.get('content_type') == 'web_article' and not item.get('processed', False)
            )
            
        elif content_type == 'youtube_video':
            # Check source URL for YouTube videos
            source_url = content_item.get('source_url')
            return any(
                item.get('source_url') == source_url
                for item in user_content
                if item.get('content_type') == 'youtube_video' and not item.get('processed', False)
            )
            
        elif content_type == 'twitter_post':
            # Check source URL and post type for Twitter posts
            source_url = content_item.get('source_url')
            post_type = content_item.get('post_type')
            
            for item in user_content:
                if (item.get('content_type') == 'twitter_post' and 
                    not item.get('processed', False) and
                    item.get('source_url') == source_url and 
                    item.get('post_type') == post_type):
                    return True
            return False
            
        elif content_type == 'plain_text':
            # Check content text for plain text
            content = content_item.get('content', '').strip()
            return any(
                item.get('content', '').strip() == content
                for item in user_content
                if item.get('content_type') == 'plain_text' and not item.get('processed', False)
            )
            
        elif content_type == 'document':
            # Check title and content length for documents
            title = content_item.get('title')
            content = content_item.get('content', '').strip()
            return any(
                item.get('title') == title and len(item.get('content', '').strip()) == len(content)
                for item in user_content
                if item.get('content_type') == 'document' and not item.get('processed', False)
            )
            
        return False

    def add_content(self, content_item):
        """
        Add a new content item to the database if it's not a duplicate.
        
        Args:
            content_item (dict): Content item to add
        
        Returns:
            bool: True if content was added, False if it was a duplicate
        """
        try:
            # Load existing content
            content = self._load_content()
            
            # Check for duplicates
            if self.is_duplicate(content_item, content):
                logger.info(f"Duplicate content detected, skipping: {content_item.get('title')}")
                return False
                
            # Add new content item
            content.append(content_item)
            
            # Save updated content
            self._save_content(content)
            
            logger.info(f"Added content item with ID: {content_item.get('id')}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding content item: {str(e)}")
            return False

    def get_unprocessed_content(self, user_id):
        """
        Get all unprocessed content for a user.
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            list: List of unprocessed content items
        """
        try:
            # Load all content
            content = self._load_content()
            
            # Filter for user's unprocessed content
            unprocessed = [
                item for item in content 
                if item.get('user_id') == user_id and not item.get('processed', False)
            ]
            
            return unprocessed
            
        except Exception as e:
            logger.error(f"Error getting unprocessed content: {str(e)}")
            return []
    
    def mark_content_as_processed(self, user_id, content_ids):
        """
        Mark content items as processed.
        
        Args:
            user_id (int): Telegram user ID
            content_ids (list): List of content IDs to mark as processed
        """
        try:
            # Load all content
            content = self._load_content()
            
            # Mark specified content as processed
            for item in content:
                if (item.get('user_id') == user_id and 
                    item.get('id') in content_ids and 
                    not item.get('processed', False)):
                    item['processed'] = True
                    item['date_processed'] = datetime.now().isoformat()
            
            # Save updated content
            self._save_content(content)
            
            logger.info(f"Marked {len(content_ids)} items as processed for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error marking content as processed: {str(e)}")
    
    def clear_unprocessed_content(self, user_id):
        """
        Clear all unprocessed content for a user.
        
        Args:
            user_id (int): Telegram user ID
        """
        try:
            # Load all content
            content = self._load_content()
            
            # Filter out user's unprocessed content
            updated_content = [
                item for item in content 
                if not (item.get('user_id') == user_id and not item.get('processed', False))
            ]
            
            # Save updated content
            self._save_content(updated_content)
            
            logger.info(f"Cleared unprocessed content for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error clearing unprocessed content: {str(e)}")
    
    def is_new_user(self, user_id):
        """
        Check if the user is new (has never interacted with the bot before).
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            bool: True if the user is new, False otherwise
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Check if user exists in preferences
            if user_id_str in user_prefs:
                return False
            
            # Also check if user has any content in the database
            content = self._load_content()
            user_content = [item for item in content if item.get('user_id') == user_id]
            
            if user_content:
                # User has content but no preferences - create an entry
                self.set_user_flag(user_id, 'onboarded', True)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if user is new: {str(e)}")
            return False  # Default to not showing intro to avoid potential spam

    def set_user_flag(self, user_id, flag_name, flag_value):
        """
        Set a flag for a user in preferences.
        
        Args:
            user_id (int): Telegram user ID
            flag_name (str): Name of the flag
            flag_value: Value of the flag
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Initialize user preferences if not exists
            if user_id_str not in user_prefs:
                user_prefs[user_id_str] = {}
            
            # Set flag
            user_prefs[user_id_str][flag_name] = flag_value
            
            # Save updated preferences
            self._save_user_preferences(user_prefs)
            
            logger.info(f"Set flag {flag_name}={flag_value} for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error setting user flag: {str(e)}")
    
    def get_user_flag(self, user_id, flag_name, default=None):
        """
        Get a flag value for a user from preferences.
        
        Args:
            user_id (int): Telegram user ID
            flag_name (str): Name of the flag
            default: Default value if flag not found
            
        Returns:
            Value of the flag or default if not found
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Check if user and flag exist
            if user_id_str in user_prefs and flag_name in user_prefs[user_id_str]:
                return user_prefs[user_id_str][flag_name]
            
            return default
            
        except Exception as e:
            logger.error(f"Error getting user flag: {str(e)}")
            return default
            
    def get_user_language(self, user_id):
        """
        Get a user's preferred language.
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            str: Language code (english, chinese, russian) or None if not set
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Get language preference
            if user_id_str in user_prefs and 'language' in user_prefs[user_id_str]:
                return user_prefs[user_id_str]['language']
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user language: {str(e)}")
            return None
    
    def set_user_language(self, user_id, language):
        """
        Set a user's preferred language.
        
        Args:
            user_id (int): Telegram user ID
            language (str): Language code (english, chinese, russian)
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Initialize user preferences if not exists
            if user_id_str not in user_prefs:
                user_prefs[user_id_str] = {}
            
            # Set language preference
            user_prefs[user_id_str]['language'] = language
            
            # Save updated preferences
            self._save_user_preferences(user_prefs)
            
            logger.info(f"Set language preference for user {user_id} to {language}")
            
        except Exception as e:
            logger.error(f"Error setting user language: {str(e)}")
    
    def _load_content(self):
        """
        Load content from the database file.
        
        Returns:
            list: List of content items
        """
        try:
            with open(self.content_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading content: {str(e)}")
            return []
    
    def _save_content(self, content):
        """
        Save content to the database file.
        
        Args:
            content (list): List of content items to save
        """
        try:
            with open(self.content_file, 'w') as f:
                json.dump(content, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving content: {str(e)}")
    
    def _load_user_preferences(self):
        """
        Load user preferences from the database file.
        
        Returns:
            dict: User preferences
        """
        try:
            with open(self.user_prefs_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading user preferences: {str(e)}")
            return {}
    
    def _save_user_preferences(self, user_prefs):
        """
        Save user preferences to the database file.
        
        Args:
            user_prefs (dict): User preferences to save
        """
        try:
            with open(self.user_prefs_file, 'w') as f:
                json.dump(user_prefs, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving user preferences: {str(e)}")

    def get_user_schedule(self, user_id):
        """
        Get a user's podcast delivery schedule.
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            dict: Schedule information or None if not set
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Get schedule preference
            if user_id_str in user_prefs and 'schedule' in user_prefs[user_id_str]:
                return user_prefs[user_id_str]['schedule']
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user schedule: {str(e)}")
            return None

    def set_user_schedule(self, user_id, schedule):
        """
        Set a user's podcast delivery schedule.
        
        Args:
            user_id (int): Telegram user ID
            schedule (dict): Schedule information
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Initialize user preferences if not exists
            if user_id_str not in user_prefs:
                user_prefs[user_id_str] = {}
            
            # Set schedule preference
            user_prefs[user_id_str]['schedule'] = schedule
            
            # Save updated preferences
            self._save_user_preferences(user_prefs)
            
            logger.info(f"Set schedule preference for user {user_id} to {schedule}")
            
        except Exception as e:
            logger.error(f"Error setting user schedule: {str(e)}")

    def remove_user_schedule(self, user_id):
        """
        Remove a user's podcast delivery schedule.
        
        Args:
            user_id (int): Telegram user ID
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Remove schedule if it exists
            if user_id_str in user_prefs and 'schedule' in user_prefs[user_id_str]:
                del user_prefs[user_id_str]['schedule']
                
                # Save updated preferences
                self._save_user_preferences(user_prefs)
                
                logger.info(f"Removed schedule for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error removing user schedule: {str(e)}")

    def set_prepared_podcast(self, user_id, audio_path):
        """
        Store the path to a prepared podcast.
        
        Args:
            user_id (int): Telegram user ID
            audio_path (str): Path to the audio file
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Initialize user preferences if not exists
            if user_id_str not in user_prefs:
                user_prefs[user_id_str] = {}
            
            # Set prepared podcast path
            user_prefs[user_id_str]['prepared_podcast'] = audio_path
            
            # Save updated preferences
            self._save_user_preferences(user_prefs)
            
            logger.info(f"Set prepared podcast path for user {user_id} to {audio_path}")
            
        except Exception as e:
            logger.error(f"Error setting prepared podcast path: {str(e)}")

    def get_prepared_podcast(self, user_id):
        """
        Get the path to a prepared podcast.
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            str or None: Path to the audio file or None if not found
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Get prepared podcast path
            if user_id_str in user_prefs and 'prepared_podcast' in user_prefs[user_id_str]:
                return user_prefs[user_id_str]['prepared_podcast']
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting prepared podcast path: {str(e)}")
            return None

    def clear_prepared_podcast(self, user_id):
        """
        Clear the path to a prepared podcast.
        
        Args:
            user_id (int): Telegram user ID
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Remove prepared podcast path if it exists
            if user_id_str in user_prefs and 'prepared_podcast' in user_prefs[user_id_str]:
                del user_prefs[user_id_str]['prepared_podcast']
                
                # Save updated preferences
                self._save_user_preferences(user_prefs)
                
                logger.info(f"Cleared prepared podcast path for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error clearing prepared podcast path: {str(e)}")

    def set_podcast_summaries(self, user_id, summaries):
        """
        Store summaries for a podcast.
        
        Args:
            user_id (int): Telegram user ID
            summaries (list): List of summary dictionaries
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Initialize user preferences if not exists
            if user_id_str not in user_prefs:
                user_prefs[user_id_str] = {}
            
            # Set summaries
            user_prefs[user_id_str]['podcast_summaries'] = summaries
            
            # Save updated preferences
            self._save_user_preferences(user_prefs)
            
            logger.info(f"Set podcast summaries for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error setting podcast summaries: {str(e)}")

    def get_podcast_summaries(self, user_id):
        """
        Get summaries for a podcast.
        
        Args:
            user_id (int): Telegram user ID
            
        Returns:
            list or None: List of summary dictionaries or None if not found
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Get summaries
            if user_id_str in user_prefs and 'podcast_summaries' in user_prefs[user_id_str]:
                return user_prefs[user_id_str]['podcast_summaries']
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting podcast summaries: {str(e)}")

    def get_user_timezone(self, user_id):
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Get timezone preference
            if user_id_str in user_prefs and 'timezone' in user_prefs[user_id_str]:
                return user_prefs[user_id_str]['timezone']
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user timezone: {str(e)}")
            return None
    
    def set_user_timezone(self, user_id, timezone):
        """
        Set a user's preferred timezone.
        
        Args:
            user_id (int): Telegram user ID
            timezone (str): Timezone string (e.g., 'Europe/Moscow')
        """
        try:
            # Load user preferences
            user_prefs = self._load_user_preferences()
            
            # Convert user_id to str for JSON dictionary keys
            user_id_str = str(user_id)
            
            # Initialize user preferences if not exists
            if user_id_str not in user_prefs:
                user_prefs[user_id_str] = {}
            
            # Set timezone preference
            user_prefs[user_id_str]['timezone'] = timezone
            
            # Save updated preferences
            self._save_user_preferences(user_prefs)
            
            logger.info(f"Set timezone preference for user {user_id} to {timezone}")
            
        except Exception as e:
            logger.error(f"Error setting user timezone: {str(e)}")
    
    def set_user_verida_token(self, user_id, token):
        """Save the Verida token for a user."""
        user_prefs = self._load_user_preferences()
        user_id_str = str(user_id)
        if user_id_str not in user_prefs:
            user_prefs[user_id_str] = {}
        user_prefs[user_id_str]['verida_token'] = token
        self._save_user_preferences(user_prefs)
        logger.info(f"Set Verida token for user {user_id}")

    def get_user_verida_token(self, user_id):
        """Retrieve the Verida token for a user, or None if not set."""
        user_prefs = self._load_user_preferences()
        user_id_str = str(user_id)
        return user_prefs.get(user_id_str, {}).get('verida_token')
    