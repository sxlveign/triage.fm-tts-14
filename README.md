# triage.fm – Telegram Content Triage & Podcast Bot

**triage.fm** is a Telegram bot that transforms your "read-it-later" content into concise, ADHD-friendly podcast episodes. Send links, documents, or text, and get back a podcast script and audio summary—perfect for catching up on your backlog while on the go.

---

## ✨ Features

- **Content Reception**: Send web links, YouTube videos, PDFs, Word docs, Twitter/X posts, or plain text.
- **AI Summarization**: Uses OpenRouter API (Llama 3) to generate short, podcast-ready scripts.
- **Podcast Generation**: Converts scripts to audio using Google TTS (multi-voice, ADHD-friendly pacing).
- **Queue Management**: Track processed and pending content per user.
- **Daily Scheduling**: Schedule automatic podcast delivery at your preferred time and timezone.
- **Lightweight Storage**: Uses local JSON files for persistence (no external DB required).
- **Replit/TimeWeb Ready**: Easy deployment on cloud platforms or locally.

---

## 🛠 Tech Stack

- Python 3.8+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [OpenRouter API](https://openrouter.ai/) (for AI summarization)
- [gTTS](https://pypi.org/project/gTTS/) + [pydub](https://pypi.org/project/pydub/) (for TTS audio)
- [PyPDF2](https://pypi.org/project/PyPDF2/), [python-docx](https://pypi.org/project/python-docx/), [youtube-transcript-api](https://pypi.org/project/youtube-transcript-api/), [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [requests](https://pypi.org/project/requests/), [beautifulsoup4](https://pypi.org/project/beautifulsoup4/), [python-dotenv](https://pypi.org/project/python-dotenv/)
- JSON file storage (no SQL/NoSQL DB required)

---

## 🚀 Setup & Deployment

### Prerequisites

- Python 3.8 or higher
- Telegram Bot Token ([@BotFather](https://t.me/BotFather))
- OpenRouter API key (optional, but recommended for best results)

### Installation

1. **Clone the Repository**
   ```bash
   git clone <your-repo-url>
   cd <repo-folder>
   ```
2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables**
   Create a `.env` file in the root directory:
   ```env
   TELEGRAM_BOT_TOKEN=your-telegram-token-here
   OPENROUTER_API_KEY=your-openrouter-key-here  # Optional, but recommended
   ```
4. **Run the Bot**
   ```bash
   python main.py
   ```

---

## 🧑‍💻 Usage

- **Send Content**: DM the bot with links, documents, or text. Supported: web articles, YouTube, PDFs, DOCX, Twitter/X, plain text.
- **Commands:**
  - `/start` – Welcome message
  - `/help` – Usage instructions
  - `/generate` – Create a podcast from your queue
  - `/queue` – View your current content queue
  - `/clear` – Clear your queue
  - `/schedule` – Set up daily podcast delivery (with timezone support)

- **Scheduling Example:**
  - `/schedule 08:30` – Daily at 8:30 AM (UTC)
  - `/schedule 17:45 mon,wed,fri Europe/Paris` – Mon/Wed/Fri at 5:45 PM (Paris time)
  - `/schedule cancel` – Cancel scheduled delivery

- **Output:**
  - Podcast script (HTML and plain text)
  - Audio file (MP3, multi-voice, ADHD-friendly pacing)

---

## 📁 File/Folder Structure

- `main.py` – Telegram bot entry point and command handlers
- `content_processor.py` – Handles all content extraction and validation
- `script_generator.py` – Summarizes content and generates podcast scripts (via OpenRouter API)
- `tts_processor.py` – Converts scripts to audio (Google TTS, multi-voice)
- `database.py` – JSON-based storage for user content, preferences, and schedules
- `scheduler.py` – Handles daily podcast scheduling and delivery
- `data/` – Stores user content, preferences, and scheduled jobs
- `temp/` – Temporary files (audio, scripts)

---

## ⚙️ Environment Variables

- `TELEGRAM_BOT_TOKEN` – Your Telegram bot token
- `OPENROUTER_API_KEY` – (Optional) Your OpenRouter API key for AI summarization

---

## 🤝 Contributing

Pull requests and issues are welcome! Please open an issue to discuss your ideas or report bugs.

---

## 📄 License

MIT License. See `LICENSE` file for details.
