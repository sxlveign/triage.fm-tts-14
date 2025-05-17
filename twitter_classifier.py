"""
Twitter/X Post Classifier

This module provides functionality to classify Twitter/X posts as:
- "article" (long-form content)
- "thread" (multiple connected tweets)
- "single_tweet" (standard tweet)

It uses the Twitter oEmbed API to retrieve post data and applies heuristics
to determine the post type.
"""
import requests
from bs4 import BeautifulSoup

def classify_tweet_type(tweet_url: str) -> str:
    """
    Classify a Twitter/X post as article, thread, or single tweet.
    
    Args:
        tweet_url (str): URL of the Twitter/X post
        
    Returns:
        str: Classification as "article", "thread", "single_tweet", or "unknown"
    """
    # First, check for known article URLs or patterns
    if "/i/notes/" in tweet_url or "notes" in tweet_url:
        return "article"
        
    # Check for known article publishers
    known_article_publishers = ["buzzingdotclub"]
    for publisher in known_article_publishers:
        if publisher in tweet_url:
            return "article"
        
    # Try to get more content by directly accessing the URL
    try:
        # Use a proper user agent to avoid being blocked
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = requests.get(tweet_url, headers=headers, timeout=10)
        
        # Check if URL redirects to a Notes page
        if "/i/notes/" in response.url:
            return "article"
    except Exception as e:
        print(f"Error checking direct URL: {e}")
        # Continue with oEmbed if direct check fails
    
    # Use oEmbed API to get tweet content
    oembed_endpoint = "https://publish.twitter.com/oembed"
    params = {
        "url": tweet_url,
        "omit_script": True
    }

    try:
        response = requests.get(oembed_endpoint, params=params)
        response.raise_for_status()
        data = response.json()
        html = data.get("html", "")
        
        # Check if the HTML contains indicators of an article
        if "notes" in html:
            return "article"
            
        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")
        text_content = soup.get_text(strip=True)
        
        # Thread detection - this rule remains unchanged
        if "Show this thread" in text_content or "Show more" in text_content:
            return "thread"
        
        # Article detection - REFINED RULE
        # Now requires BOTH long content AND signs of structure
        is_long_content = len(text_content) > 500  # Reduced threshold for oEmbed content
        
        # Check for structural elements
        has_structure = False
        
        # Count paragraphs by looking at the HTML structure
        paragraphs = len(soup.find_all(['p', 'div', 'blockquote']))
        if paragraphs > 2:
            has_structure = True
            
        # Count line breaks in the text
        line_breaks = text_content.count('\n')
        if line_breaks > 3:
            has_structure = True
            
        # Check for multiple sentences
        sentences = len([s for s in text_content.split('.') if len(s.strip()) > 10])
        if sentences > 3:
            has_structure = True
            
        # Apply the refined rule: BOTH long content AND structure
        if is_long_content and has_structure:
            return "article"
                
    except Exception as e:
        print(f"Error retrieving oEmbed: {e}")
        return "unknown"

    # Default to single_tweet if no other conditions are met
    return "single_tweet"
