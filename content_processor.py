"""
Content Processor Module

This module handles the processing of different types of content:
- Text messages
- Web links (articles, blog posts)
- YouTube video links
- PDF documents
- Word documents
- Twitter/X posts (excluding articles)
"""
import os
import re
import uuid
import logging
from datetime import datetime
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import PyPDF2
import docx
import youtube_transcript_api
import yt_dlp
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from twitter_classifier import classify_tweet_type

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContentProcessor:
    """Process different types of content and extract text."""

    def __init__(self):
        # URL pattern for detection
        self.url_pattern = re.compile(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
        )
        # YouTube URL pattern
        self.youtube_pattern = re.compile(
            r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
        )
        # Twitter URL pattern
        self.twitter_pattern = re.compile(
            r"(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/.*"
        )

        # Common bot commands that users might try without the slash
        self.common_commands = [
            "start",
            "help",
            "generate",
            "queue",
            "clear",
            "about",
            "settings",
            "status",
            "cancel",
            "delete",
        ]

        # Minimum content length (characters) for plain text
        self.min_content_length = 150

    def fetch_twitter_oembed(self, url):
        """Fetch oEmbed data from Twitter API."""
        try:
            oembed_url = f"https://publish.twitter.com/oembed?url={url}"
            response = requests.get(oembed_url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching Twitter oEmbed data: {str(e)}")
            return None
            
    def check_twitter_type(self, url):
        """
        Check the type of Twitter/X post.
        
        Args:
            url (str): Twitter/X post URL
            
        Returns:
            str: Classification as "article", "thread", "single_tweet", or "unknown"
        """
        try:
            logger.info(f"Classifying Twitter post: {url}")
            post_type = classify_tweet_type(url)
            logger.info(f"Twitter post classification result: {post_type}")
            return post_type
        except Exception as e:
            logger.error(f"Error classifying Twitter post: {str(e)}")
            return "unknown"

    def process_twitter_oembed(self, oembed_data):
        """Process Twitter oEmbed data and extract relevant information."""
        try:
            # Extract relevant information from the oEmbed data
            title = oembed_data.get("author_name", "Twitter Post")
            author = oembed_data.get("author_name", "Unknown Author")
            html_content = oembed_data.get("html", "")

            # Use BeautifulSoup to extract text content from the HTML
            soup = BeautifulSoup(html_content, "html.parser")
            text_content = soup.get_text(separator=" ", strip=True)

            # If the text content is too short, use the raw HTML content
            if len(text_content) < 100:
                content = html_content
            else:
                content = text_content

            return {
                "title": title,
                "author": author,
                "content": content,
            }
        except Exception as e:
            logger.error(f"Error processing Twitter oEmbed data: {str(e)}")
            return None

    def is_valid_content(self, text):
        """
        Check if text is valid content for podcast script generation.

        Args:
            text (str): The text to check

        Returns:
            tuple: (is_valid, message) where is_valid is a boolean and message explains why if invalid
        """
        # Check if text is None or empty
        if not text:
            return False, "Message is empty."

        # Trim whitespace
        text = text.strip()

        # Check if text is too short
        if len(text) < 15:
            return False, "Message is too short to be processed as content."

        # Check if text contains a URL - if it does, consider it valid regardless of other checks
        if self.url_pattern.search(text):
            return True, ""

        # If we get here, the text doesn't contain a URL, so continue with other checks

        # Check if it's a single word (potential command)
        words = text.split()
        if len(words) == 1:
            return False, "Single word messages are not processed as content."

        # Check if it's likely a mistyped command
        if len(words) <= 2 and words[0].lower() in self.common_commands:
            return False, f"This looks like a command. Did you mean '/{words[0].lower()}'?"

        # For plain text with no URL, check if it's long enough to summarize
        if len(text) < self.min_content_length:
            return False, f"Text is too short to summarize effectively. Please provide content with at least {self.min_content_length} characters."

        # If we passed all checks, it's probably valid content
        return True, ""

    def process_text(self, text, user_id, message_id=None, is_forwarded=False):
        """
        Process a text message that may contain a URL.

        Args:
            text (str): The text message to process
            user_id (int): Telegram user ID
            message_id (int, optional): Telegram message ID
            is_forwarded (bool, optional): Whether the message is forwarded

        Returns:
            dict: Processed content information
        """
        logger.info(f"Processing text: {text}")
        
        # First check if text is valid content
        is_valid, message = self.is_valid_content(text)
        if not is_valid:
            logger.warning(f"Invalid content: {message}")
            return {
                'success': False,
                'unsupported': True,
                'message': message
            }

        # Check if text contains a URL
        url_match = self.url_pattern.search(text)
        logger.info(f"URL match result: {url_match}")

        if url_match:
            url = url_match.group(0)
            logger.info(f"Found URL: {url}")

            # Check if it's a Twitter URL
            if self.twitter_pattern.search(url):
                logger.info("Twitter URL detected - checking post type")
                
                # Check if it's an article
                post_type = self.check_twitter_type(url)
                logger.info(f"Twitter post classified as: {post_type}")
                
                if post_type == "article":
                    logger.info(f"Rejecting Twitter article: {url}")
                    return {
                        'success': False,
                        'unsupported': True,
                        'message': 'Twitter/X articles are not supported. Please send single tweets or threads instead.'
                    }
                
                # Process non-article Twitter content
                logger.info("Processing Twitter post - attempting to fetch oEmbed data")
                oembed_data = self.fetch_twitter_oembed(url)
                if oembed_data:
                    processed_data = self.process_twitter_oembed(oembed_data)
                    if processed_data:
                        return {
                            'id': str(uuid.uuid4()),
                            'user_id': user_id,
                            'title': processed_data.get('title', 'Twitter Post'),
                            'author': processed_data.get('author', 'Unknown Author'),
                            'content': processed_data.get('content', ''),
                            'source_url': url,
                            'content_type': 'twitter_post',
                            'post_type': post_type,
                            'date_added': datetime.now().isoformat(),
                            'processed': False,
                            'success': True
                        }
                    else:
                        return {
                            'success': False,
                            'unsupported': True,
                            'message': 'Failed to process Twitter oEmbed data'
                        }
                else:
                    return {
                        'success': False,
                        'unsupported': True,
                        'message': 'Failed to fetch Twitter oEmbed data'
                    }

            # Check if it's a YouTube URL
            youtube_match = self.youtube_pattern.search(url)
            if youtube_match:
                logger.info(f"YouTube URL detected, video ID: {youtube_match.group(1)}")
                return self.process_youtube(youtube_match.group(1), user_id)

            # Process as regular web URL
            logger.info("Processing as regular web URL")
            return self.process_web_url(url, user_id)

        # Process as plain text or forwarded message
        logger.info("Processing as plain text or forwarded message")
        content_type = 'forwarded' if is_forwarded else 'plain_text'
        return self.process_plain_text(text, user_id, message_id=message_id, content_type=content_type)

    def process_web_url(self, url, user_id):
        """
        Process a web URL to extract article content.

        Args:
            url (str): The URL to process
            user_id (int): Telegram user ID

        Returns:
            dict: Processed content information
        """
        try:
            # Log the URL being processed 
            logger.info(f"Processing web URL: {url}")

            # Fetch the webpage
            response = requests.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }, timeout=10)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title
            title = soup.title.string if soup.title else "Article"

            # Extract author (attempt common patterns)
            author = "Unknown Author"
            # Try meta tags first
            author_meta = soup.find('meta', {'name': ['author', 'Author', 'AUTHOR']})
            if author_meta:
                author = author_meta.get('content', author)

            # Try common author classes/IDs if meta tag not found
            if author == "Unknown Author":
                author_elements = soup.select('.author, .byline, .article-author, [rel="author"]')
                if author_elements and author_elements[0].text.strip():
                    author = author_elements[0].text.strip()

            # Extract main content (improved approach)
            # Remove script, style, and nav elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                element.extract()

            # Try to find the main content
            main_content = None

            # Try common article containers
            article_containers = soup.select('article, .article, .post, .content, main, #content, #main')
            if article_containers:
                main_content = article_containers[0]

            # If no specific container found, use body
            if not main_content:
                main_content = soup.body

            # Get visible text
            if main_content:
                text = main_content.get_text(separator=' ', strip=True)
            else:
                text = soup.get_text(separator=' ', strip=True)

            # Basic cleaning
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            content = ' '.join(lines)

            # Check if content is substantial enough
            if len(content) < 200:  # Arbitrary threshold for article content
                return {
                    'success': False,
                    'unsupported': True,
                    'message': 'The URL does not contain enough text content to summarize.'
                }

            logger.info(f"Successfully processed URL: {url} with title: {title}")

            return {
                'id': str(uuid.uuid4()),
                'user_id': user_id,
                'title': title,
                'author': author,
                'content': content,
                'source_url': url,
                'content_type': 'web_article',
                'date_added': datetime.now().isoformat(),
                'processed': False,
                'success': True
            }

        except Exception as e:
            logger.error(f"Error processing web URL: {str(e)}")
            return {
                'success': False,
                'message': f"Failed to process the web URL: {str(e)}"
            }

    def process_youtube(self, video_id, user_id):
        """Process a YouTube video to extract metadata."""
        logger.info(f"Processing YouTube video: {video_id}")
        try:
            title = ""
            description = ""
            channel_name = "YouTube Creator"  # Default fallback
            
            # Try YouTube Data API first
            try:
                logger.info("Attempting to get content using YouTube Data API")
                api_key = os.getenv('YOUTUBE_API_KEY')
                if api_key:
                    youtube = build('youtube', 'v3', developerKey=api_key)
                    
                    # Get video details
                    video_response = youtube.videos().list(
                        part='snippet,contentDetails',
                        id=video_id
                    ).execute()
                    
                    if video_response['items']:
                        video = video_response['items'][0]
                        title = video['snippet']['title']
                        description = video['snippet']['description']
                        channel_name = video['snippet'].get('channelTitle', channel_name)
                        
            except Exception as e:
                logger.error(f"Error with YouTube Data API: {str(e)}")

            # If API fails, try direct request
            if not title or not description:
                try:
                    logger.info("Attempting direct request with headers")
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                    }
                    response = requests.get(url, headers=headers, timeout=10)
                    content = response.text
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Try to get title
                    if not title:
                        # Try meta tags first
                        meta_title = soup.find('meta', {'property': 'og:title'})
                        if meta_title:
                            title = meta_title.get('content', '')
                        else:
                            # Try title tag
                            title_tag = soup.find('title')
                            if title_tag:
                                title = title_tag.text.replace(' - YouTube', '')
                    
                    # Try to get description if not already set
                    if not description:
                        meta_desc = soup.find('meta', {'name': 'description'})
                        if meta_desc:
                            description = meta_desc.get('content', '')

                    # Try to get channel name if not already set
                    if channel_name == "YouTube Creator":
                        meta_channel = soup.find('meta', {'itemprop': 'channelId'})
                        if meta_channel:
                            channel_link = soup.find('link', {'itemprop': 'name'})
                            if channel_link:
                                channel_name = channel_link.get('content', channel_name)
                    
                except Exception as e:
                    logger.error(f"Error with direct request: {str(e)}")

            # Clean up title if needed
            title = title.strip()
            if title.startswith('"') and title.endswith('"'):
                title = title[1:-1]
            
            # If still no title, use video ID
            if not title or len(title) < 5:
                title = f"YouTube Video ({video_id})"
                
            # Extract timestamps from description if they exist
            timestamps = []
            if description:
                lines = description.split('\n')
                for line in lines:
                    # Match common timestamp patterns like "0:00" or "00:00" or "0:00:00"
                    if re.match(r'^\d{0,2}:?\d{1,2}:\d{2}\s*-?\s*', line):
                        timestamps.append(line.strip())
            
            # Create a structured content with essential info only
            content = {
                'title': title,
                'description': description[:500],  # Limit description length
                'timestamps': timestamps,
                'video_id': video_id,
                'url': f"https://www.youtube.com/watch?v={video_id}"
            }
            
            # Convert to string format
            formatted_content = f"{title}\n\n"
            if description:
                formatted_content += "Description:\n" + description[:500]
                if len(description) > 500:
                    formatted_content += "...\n\n"
                else:
                    formatted_content += "\n\n"
            if timestamps:
                formatted_content += "Timestamps:\n" + "\n".join(timestamps)

            logger.info(f"Got video title: {title}")

            return {
                'id': str(uuid.uuid4()),
                'user_id': user_id,
                'title': title,
                'author': channel_name,
                'content': formatted_content,
                'source_url': f"https://www.youtube.com/watch?v={video_id}",
                'content_type': 'youtube_video',
                'date_added': datetime.now().isoformat(),
                'processed': False,
                'success': True
            }

        except Exception as e:
            logger.error(f"Error processing YouTube video: {str(e)}")
            return {
                'success': False,
                'message': f"Failed to process the YouTube video. Please make sure the video is public and accessible."
            }

    def process_plain_text(self, text, user_id, message_id=None, content_type='plain_text'):
        """
        Process plain text content.

        Args:
            text (str): Text content
            user_id (int): Telegram user ID
            message_id (int, optional): Telegram message ID
            content_type (str): Type of content ('plain_text' or 'forwarded')

        Returns:
            dict: Processed content information
        """
        # For plain text, use first few words as title
        words = text.split()
        title = ' '.join(words[:5]) + ('...' if len(words) > 5 else '')

        return {
            'id': str(uuid.uuid4()),
            'user_id': user_id,
            'title': title,
            'author': 'You',
            'content': text,
            'content_type': content_type,
            'date_added': datetime.now().isoformat(),
            'processed': False,
            'success': True,
            'message_id': message_id
        }

    def process_document(self, file_path, file_name, user_id):
        """
        Process uploaded documents (PDF, Word).

        Args:
            file_path (str): Path to the downloaded file
            file_name (str): Original file name
            user_id (int): Telegram user ID

        Returns:
            dict: Processed content information
        """
        try:
            content = ""
            file_ext = os.path.splitext(file_name)[1].lower()

            # Process PDF
            if file_ext == '.pdf':
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num in range(len(pdf_reader.pages)):
                        page_text = pdf_reader.pages[page_num].extract_text()
                        if page_text:  # Only add non-empty pages
                            content += page_text + " "

            # Process Word document
            elif file_ext in ['.docx', '.doc']:
                doc = docx.Document(file_path)
                content = ' '.join([para.text for para in doc.paragraphs if para.text.strip()])

            # Unsupported document type
            else:
                return {
                    'success': False,
                    'unsupported': True,
                    'message': f"Document type {file_ext} is not supported yet"
                }

            # Check if document has enough content
            if not content or len(content.strip()) < self.min_content_length:
                return {
                    'success': False,
                    'unsupported': True,
                    'message': f'The document does not contain enough text to summarize effectively. Please provide content with at least {self.min_content_length} characters.'
                }

            return {
                'id': str(uuid.uuid4()),
                'user_id': user_id,
                'title': file_name,
                'author': 'Document Author',
                'content': content,
                'content_type': 'document',
                'date_added': datetime.now().isoformat(),
                'processed': False,
                'success': True
            }

        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            return {
                'success': False,
                'message': f"Failed to process document: {str(e)}"
            }
