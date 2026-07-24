import aiohttp
import asyncio
import logging
import os
import shutil
import tempfile
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)


import re

def detect_language(text: str) -> str:
    """Automatically detect the language code of the input text based on script & stopword scoring."""
    t = text.strip()
    if not t:
        return "en"

    # 1. Non-Latin Script Detection via Unicode ranges
    if re.search(r"[\u0400-\u04FF]", t):
        return "ru"
    if re.search(r"[\u0900-\u097F]", t):
        return "hi"
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", t):
        return "ja"
    if re.search(r"[\uAC00-\uD7AF\u1100-\u11FF]", t):
        return "ko"
    if re.search(r"[\u4E00-\u9FFF]", t):
        return "zh-CN"
    if re.search(r"[\u0600-\u06FF]", t):
        return "ar"
    if re.search(r"[\u0370-\u03FF]", t):
        return "el"
    if re.search(r"[\u0590-\u05FF]", t):
        return "he"

    # 2. Latin Script Analysis (Diacritics & Common Word Patterns)
    t_lower = t.lower()
    words = set(re.findall(r"\b[a-zà-ÿñç]+\b", t_lower))

    scores = {
        "es": 0, "fr": 0, "de": 0, "it": 0, "pt": 0,
        "tr": 0, "pl": 0, "nl": 0, "sv": 0, "hi": 0, "en": 0,
    }

    # Hinglish (Hindi in Roman Script)
    hinglish_words = {
        "kya", "kaisa", "kaise", "kaisi", "kab", "kaha", "kidhar", "kon", "kaun", "kyun", "kyu",
        "mai", "main", "mujhe", "mera", "meri", "mere", "tum", "tumhara", "tumhari", "aap", "aapka",
        "aapki", "hum", "humara", "woh", "voh", "yeh", "ye", "hai", "hain", "ho", "hu", "hoon",
        "karo", "karna", "kar", "raha", "rahi", "rahe", "gaya", "gayi", "gaye", "bhai", "dost",
        "accha", "achha", "achi", "acche", "bura", "bohot", "bahut", "thik", "theek", "sahi",
        "galat", "sab", "badhiya", "hoga", "hogi", "hoge", "chahiye", "bolo", "batao", "sun",
        "suno", "dekh", "dekho", "chalo", "aao", "jao", "mat", "nhi", "nahin", "nahi", "yaar",
        "yr", "aaj", "kal", "parso", "bhi", "toh", "pe", "par", "khana", "khaya", "paani", "kuch"
    }
    scores["hi"] += len(words & hinglish_words) * 3

    # Spanish
    if any(c in t_lower for c in "ñ¿¡"): scores["es"] += 3
    es_words = {"hola", "como", "esta", "está", "que", "para", "con", "por", "amigos", "gracias", "buenos", "dias", "porfavor", "si"}
    scores["es"] += len(words & es_words) * 2

    # French
    if any(c in t_lower for c in "œæç"): scores["fr"] += 2
    if any(c in t_lower for c in "éèêëàâùûîï"): scores["fr"] += 1
    fr_words = {"bonjour", "merci", "salut", "comment", "allez", "vous", "est", "les", "des", "une", "pour", "avec", "oui"}
    scores["fr"] += len(words & fr_words) * 2

    # German
    if any(c in t_lower for c in "äöüß"): scores["de"] += 3
    de_words = {"hallo", "danke", "guten", "tag", "und", "das", "ist", "nicht", "mit", "fuer", "für", "auf", "ja", "nein"}
    scores["de"] += len(words & de_words) * 2

    # Italian
    it_words = {"ciao", "grazie", "buongiorno", "sono", "che", "per", "con", "molto", "bene", "si", "no"}
    scores["it"] += len(words & it_words) * 2

    # Portuguese
    if any(c in t_lower for c in "ãõ"): scores["pt"] += 3
    pt_words = {"olá", "ola", "obrigado", "obrigada", "como", "esta", "está", "tudo", "bem", "muito", "sim", "nao", "não"}
    scores["pt"] += len(words & pt_words) * 2

    # Turkish
    if any(c in t_lower for c in "ğşıi̇"): scores["tr"] += 3
    tr_words = {"merhaba", "teşekkürler", "tesekkurler", "evet", "hayır", "hayir", "bir", "ve", "bu", "nasılsın", "nasilsin"}
    scores["tr"] += len(words & tr_words) * 2

    # Polish
    if any(c in t_lower for c in "ąćęłńóśźż"): scores["pl"] += 3
    pl_words = {"cześć", "czesc", "dziękuję", "dziekuje", "jest", "tak", "nie", "dobre"}
    scores["pl"] += len(words & pl_words) * 2

    # English
    en_words = {"hello", "hi", "hey", "the", "be", "to", "of", "and", "a", "in", "that", "have", "it", "for", "not", "on", "with", "he", "as", "you", "do", "at", "this", "but", "his", "by", "from", "they", "we", "say", "her", "she", "or", "an", "will", "my", "one", "all", "would", "there", "their", "what", "so", "up", "out", "if", "about", "who", "get", "which", "go", "me", "world", "friend", "friends", "thanks", "thank"}
    scores["en"] += len(words & en_words) * 2

    best_lang, highest_score = max(scores.items(), key=lambda item: item[1])
    return best_lang if highest_score > 0 else "en"



async def generate_tts_audio(text: str, lang: str = "auto") -> bytes:
    """Fetch TTS MP3 audio bytes using Google Translate TTS API."""
    text_clean = text.strip()[:300]
    if not text_clean:
        raise ValueError("Text cannot be empty.")
    if not lang or lang.lower().strip() == "auto":
        lang_code = detect_language(text_clean)
    else:
        lang_code = lang.lower().strip()
    encoded = urllib.parse.quote(text_clean)
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl={lang_code}&client=tw-ob"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.read()
            else:
                raise ValueError(f"TTS API returned HTTP {resp.status}")



async def play_tts_on_voice(voice_client, text: str, lang: str = "en", volume: float = 1.0) -> bool:
    """Play TTS audio for the given text on a connected discord.VoiceClient."""
    if not voice_client or not voice_client.is_connected():
        raise ValueError("VoiceClient is not connected.")

    audio_bytes = await generate_tts_audio(text, lang)

    os.makedirs("data", exist_ok=True)
    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3", dir="data")
    try:
        os.write(temp_fd, audio_bytes)
        os.close(temp_fd)
    except Exception:
        os.close(temp_fd)
        raise

    import discord
    ffmpeg_exe = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    ffmpeg_kwargs = {}
    if ffmpeg_exe:
        ffmpeg_kwargs["executable"] = ffmpeg_exe

    loop = asyncio.get_running_loop()
    play_finished = asyncio.Event()

    def after_play(err):
        if err:
            logger.warning("Error during TTS playback: %s", err)
        loop.call_soon_threadsafe(play_finished.set)

    try:
        source = discord.FFmpegPCMAudio(temp_path, options="-vn", **ffmpeg_kwargs)
        volume_source = discord.PCMVolumeTransformer(source, volume=volume)

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

        voice_client.play(volume_source, after=after_play)
        await play_finished.wait()
        return True
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
