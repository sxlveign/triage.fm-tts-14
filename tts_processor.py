"""
Text-to-Speech processor for converting podcast scripts to audio using Google TTS
With proper multi-voice support that properly distinguishes between speakers
"""
import os
import time
import logging
import threading
from typing import Optional
from gtts import gTTS
import re
from pydub import AudioSegment
from pydub.effects import speedup

logger = logging.getLogger(__name__)

class TTSProcessor:
    def __init__(self):
        """Initialize the TTS processor"""
        # Create a directory for audio files if it doesn't exist
        self.audio_dir = "temp/audio"
        os.makedirs(self.audio_dir, exist_ok=True)
        
        # Maximum size for each audio chunk (in characters)
        # gTTS has limitations on text length
        self.max_chunk_size = 4000
        
        # Ensure proper silence between segments
        self.segment_silence_ms = 500  # Slightly shorter pauses for better ADHD attention
        
        # Voice settings for different speakers
        # Use standard 'en' with 'com' tld for American accent (documented in gTTS)
        self.voice_settings = {
            "host": {"lang": "en", "tld": "us"},      # US English for host 
            "cohost": {"lang": "en", "tld": "us"}     # US English for co-host
        }
        
        # Speed factor for processing (1.0 = normal speed, higher = faster)
        # Slightly faster pace helps retain ADHD attention
        self.speed_factor = 1.15

    def generate_audio(self, script: str, language: str = "english", filename: Optional[str] = None) -> str:
        """Convert text to speech using Google TTS with proper multi-voice support."""
        # Retry logic
        max_retries = 3
        retry_delay = 5  # seconds
        
        for attempt in range(max_retries):
            try:
                # Generate a filename if not provided
                if filename is None:
                    timestamp = int(time.time())
                    filename = f"podcast_{timestamp}.mp3"
                
                filepath = os.path.join(self.audio_dir, filename)
                
                # Split script by speaker markers
                segments = self._split_by_speakers(script)
                logger.info(f"Split script into {len(segments)} speaker segments")
                
                # Process each segment with the appropriate voice and combine them
                combined_audio = None
                
                for segment in segments:
                    if not segment['text'].strip():
                        continue  # Skip empty segments
                    
                    # Clean the text for TTS
                    cleaned_text = self._clean_for_tts(segment['text'])
                    if not cleaned_text.strip():
                        continue  # Skip if cleaning removed all content
                    
                    # Process the segment with the appropriate voice
                    temp_path = os.path.join(self.audio_dir, f"temp_segment_{time.time()}.mp3")
                    
                    try:
                        # Select voice based on speaker
                        voice_settings = self.voice_settings["host"] if segment['speaker'] == 'HOST' else self.voice_settings["cohost"]
                        
                        # Define the number of TTS save retries
                        max_tts_retries = 3  # Number of retries for TTS saving
                        
                        # Use a thread-safe approach for TTS saving with timeout
                        for tts_attempt in range(max_tts_retries):
                            try:
                                # Generate TTS for this segment with tld='com' for American accent
                                # This forces the use of American English regardless of network location
                                tts = gTTS(
                                    text=cleaned_text, 
                                    lang=voice_settings["lang"], 
                                    tld=voice_settings["tld"],
                                    slow=False
                                )
                                
                                # Save with threading timeout instead of signal
                                success = self._save_tts_with_timeout(tts, temp_path, timeout=30)
                                
                                if success:
                                    break  # If successful, break the retry loop
                                else:
                                    logger.warning(f"TTS save attempt {tts_attempt + 1} timed out")
                                    if tts_attempt < max_tts_retries - 1:
                                        time.sleep(2)  # Wait before retrying
                                    else:
                                        raise Exception("Max retries reached for TTS saving")
                            except Exception as tts_e:
                                logger.warning(f"TTS save attempt {tts_attempt + 1} failed: {str(tts_e)}")
                                if tts_attempt < max_tts_retries - 1:
                                    time.sleep(2)  # Wait before retrying
                                else:
                                    raise  # Re-raise the exception if max retries reached
                        
                        # Load the audio segment
                        segment_audio = AudioSegment.from_mp3(temp_path)
                        
                        # Apply ADHD-friendly audio processing with different voice characteristics
                        segment_audio = self._process_audio_for_adhd(segment_audio, is_host=(segment['speaker'] == 'HOST'))
                        
                        # Add to combined audio
                        if combined_audio is None:
                            combined_audio = segment_audio
                        else:
                            # Add a small pause between segments for natural speech
                            silence = AudioSegment.silent(duration=self.segment_silence_ms)
                            combined_audio = combined_audio + silence + segment_audio
                        
                        # Clean up temp file
                        os.remove(temp_path)
                        
                    except Exception as e:
                        logger.error(f"Error processing segment: {str(e)}")
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        continue  # Try next segment even if one fails
                
                # Save the final combined audio
                if combined_audio:
                    # Add intro/outro effects
                    final_audio = self._add_bookend_effects(combined_audio)
                    
                    final_audio.export(filepath, format="mp3")
                    logger.info(f"Generated multi-voice audio file at {filepath}")
                    return filepath
                else:
                    logger.error("Failed to create combined audio - no segments were processed")
                    raise Exception("Failed to generate audio segments")
            
            except Exception as e:
                logger.error(f"Error generating audio (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)  # Wait before the next attempt
                else:
                    logger.error("Max retries reached. Audio generation failed.")
                    raise  # Re-raise the exception after the last attempt
    
    def _save_tts_with_timeout(self, tts, filepath, timeout=30):
        """
        Thread-safe function to save TTS with a timeout.
        
        Args:
            tts: The gTTS object
            filepath: Path to save the file
            timeout: Timeout in seconds
            
        Returns:
            bool: True if successful, False if timed out
        """
        result = {"success": False}
        
        def target():
            try:
                tts.save(filepath)
                result["success"] = True
            except Exception as e:
                logger.error(f"Error in TTS save thread: {str(e)}")
        
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            # Thread is still running, it timed out
            logger.warning(f"TTS save operation timed out after {timeout} seconds")
            return False
        
        return result["success"]
    
    def _split_by_speakers(self, text: str) -> list:
        """Split text into segments by speaker markers."""
        segments = []
        current_speaker = None
        current_text = []

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            if line.startswith('### HOST:'):
                if current_speaker and current_text:
                    segments.append({
                        'speaker': current_speaker,
                        'text': ' '.join(current_text)
                    })
                current_speaker = 'HOST'
                current_text = [line.replace('### HOST:', '').strip()]
            elif line.startswith('### COHOST:'):
                if current_speaker and current_text:
                    segments.append({
                        'speaker': current_speaker,
                        'text': ' '.join(current_text)
                    })
                current_speaker = 'COHOST'
                current_text = [line.replace('### COHOST:', '').strip()]
            else:
                if current_speaker:
                    current_text.append(line)

        # Add the last segment
        if current_speaker and current_text:
            segments.append({
                'speaker': current_speaker,
                'text': ' '.join(current_text)
            })

        return segments

    def _process_audio_for_adhd(self, segment, is_host=True):
        """
        Apply ADHD-friendly processing to an audio segment
        with enhanced voice differentiation
        
        Args:
            segment: The AudioSegment to process
            is_host: Whether this is the host's voice
            
        Returns:
            The processed AudioSegment
        """
        # Enhanced differentiation between voices
        if is_host:
            # Host voice - deeper and more masculine
            # Slightly faster pace
            segment = speedup(segment, self.speed_factor, 150)
            # Lower pitch for host (more bass)
            segment = segment.low_pass_filter(1700)
            # Slight volume increase
            segment = segment + 2
        else:
            # Co-host voice - slightly higher pitch and different pace
            # Slightly slower pace compared to host
            segment = speedup(segment, self.speed_factor * 0.9, 150)
            # Higher pitch for co-host (more treble)
            segment = segment.high_pass_filter(1300)
        
        # Normalize the volume for consistent listening experience
        segment = segment.normalize()
        
        return segment
    
    def _add_bookend_effects(self, audio):
        """
        Add subtle attention-focusing effects at beginning and end
        
        Args:
            audio: The main audio content
            
        Returns:
            AudioSegment with added effects
        """
        # For simplicity, we're just adding a short silence at the beginning and end
        # In a more advanced implementation, you could add gentle tones or transitions
        start_silence = AudioSegment.silent(duration=500)
        end_silence = AudioSegment.silent(duration=750)
        
        return start_silence + audio + end_silence
    
    def _chunk_text(self, text: str) -> list:
        """
        Split text into chunks suitable for TTS.
        
        Args:
            text (str): Text to split
            
        Returns:
            list: List of text chunks
        """
        # Split by sentences for more natural breaks
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= self.max_chunk_size:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = sentence
                else:
                    # If the sentence itself is too long, split it by commas
                    phrase_parts = sentence.split(', ')
                    if len(phrase_parts) > 1:
                        current_phrase = ""
                        for part in phrase_parts:
                            if len(current_phrase) + len(part) + 2 <= self.max_chunk_size:
                                if current_phrase:
                                    current_phrase += ", " + part
                                else:
                                    current_phrase = part
                            else:
                                chunks.append(current_phrase)
                                current_phrase = part
                        
                        if current_phrase:
                            current_chunk = current_phrase
                    else:
                        # Last resort: split by words
                        chunks.append(sentence[:self.max_chunk_size])
                        if len(sentence) > self.max_chunk_size:
                            current_chunk = sentence[self.max_chunk_size:]
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _clean_for_tts(self, text: str) -> str:
        """Clean text to make it more suitable for TTS."""
        # Remove any remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Replace quotes with spoken equivalents
        text = text.replace('"', ' ')
        text = text.replace("'", ' ')
        
        # Replace multiple spaces with a single space
        text = re.sub(r'\s+', ' ', text)
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Add proper pauses for punctuation
        text = text.replace('...', '. ')
        text = text.replace('--', ', ')
        
        # Clean up bullet points and list markers
        text = re.sub(r'^\s*[-•*]\s*', '', text)
        text = re.sub(r'\n\s*[-•*]\s*', ' ', text)
        
        # Ensure proper ending punctuation
        text = text.strip()
        if text and not text[-1] in '.!?:;,':
            text = text + '.'
        
        return text

    def cleanup_old_files(self, max_age_hours: int = 24):
        """
        Clean up old audio files to prevent disk space issues
        
        Args:
            max_age_hours (int): Maximum age of files to keep in hours
        """
        try:
            current_time = time.time()
            for filename in os.listdir(self.audio_dir):
                filepath = os.path.join(self.audio_dir, filename)
                if os.path.getmtime(filepath) < current_time - (max_age_hours * 3600):
                    os.remove(filepath)
                    logger.info(f"Removed old audio file: {filepath}")
        except Exception as e:
            logger.error(f"Error cleaning up old files: {str(e)}")