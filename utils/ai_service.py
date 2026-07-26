import os
import logging
from typing import Optional, List, Dict
import aiohttp

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are Helix, an intelligent, helpful, and friendly AI assistant for a Discord server. "
    "Keep responses clear, concise, engaging, and well-formatted using markdown. Avoid unnecessary fluff."
)


async def call_openai(prompt: str, history: Optional[List[Dict[str, str]]] = None, system_prompt: Optional[str] = None) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY is not set in environment.")
        return None

    sys_p = system_prompt or DEFAULT_SYSTEM_PROMPT
    messages = [{"role": "system", "content": sys_p}]
    if history:
        for item in history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"]["content"].strip()
                else:
                    text = await resp.text()
                    logger.error("OpenAI API returned status %s: %s", resp.status, text)
    except Exception as e:
        logger.exception("Failed to call OpenAI API: %s", e)
    return None


async def call_gemini(prompt: str, history: Optional[List[Dict[str, str]]] = None, system_prompt: Optional[str] = None) -> Optional[str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set in environment.")
        return None

    sys_p = system_prompt or DEFAULT_SYSTEM_PROMPT
    contents = []
    
    # System instruction context
    full_prompt = f"System Instruction: {sys_p}\n\n"
    if history:
        for item in history:
            role_label = "User" if item.get("role") == "user" else "Assistant"
            full_prompt += f"{role_label}: {item.get('content', '')}\n"

    full_prompt += f"User: {prompt}\nAssistant:"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip()
                else:
                    text = await resp.text()
                    logger.error("Gemini API returned status %s: %s", resp.status, text)
    except Exception as e:
        logger.exception("Failed to call Gemini API: %s", e)
    return None


async def call_groq(prompt: str, history: Optional[List[Dict[str, str]]] = None, system_prompt: Optional[str] = None) -> Optional[str]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY is not set in environment.")
        return None

    sys_p = system_prompt or DEFAULT_SYSTEM_PROMPT
    messages = [{"role": "system", "content": sys_p}]
    if history:
        for item in history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"]["content"].strip()
                else:
                    text = await resp.text()
                    logger.error("Groq API returned status %s: %s", resp.status, text)
    except Exception as e:
        logger.exception("Failed to call Groq API: %s", e)
    return None


import base64

import urllib.parse

async def generate_image_gemini(prompt: str) -> Optional[bytes]:
    """Generate image bytes using Gemini Imagen API endpoint with Pollinations.ai free fallback."""
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1, "aspectRatio": "1:1"}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        preds = data.get("predictions", [])
                        if preds and "bytesBase64Encoded" in preds[0]:
                            b64_str = preds[0]["bytesBase64Encoded"]
                            return base64.b64decode(b64_str)
                    else:
                        text = await resp.text()
                        logger.warning("Gemini Imagen API returned status %s: %s. Falling back to free Pollinations AI.", resp.status, text[:100])
        except Exception as e:
            logger.warning("Failed to generate image via Gemini Imagen API: %s. Falling back to free Pollinations AI.", e)

    # 100% Free Fallback: Pollinations AI (Flux / SD model, no API key required)
    try:
        encoded_prompt = urllib.parse.quote(prompt.strip())
        pollinations_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed=42&model=flux&nologo=true"
        async with aiohttp.ClientSession() as session:
            async with session.get(pollinations_url, timeout=45) as resp:
                if resp.status == 200:
                    return await resp.read()
                else:
                    logger.error("Pollinations AI returned status %s", resp.status)
    except Exception as e:
        logger.exception("Failed to generate image via Pollinations AI: %s", e)

    return None



async def get_ai_response(
    prompt: str,
    history: Optional[List[Dict[str, str]]] = None,
    provider: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> str:
    """Fetch AI response using free providers (Gemini / Groq) or OpenAI with automatic fallback."""
    provider_clean = (provider or os.getenv("DEFAULT_AI_PROVIDER") or "gemini").lower().strip()

    providers_map = {
        "gemini": call_gemini,
        "groq": call_groq,
        "openai": call_openai,
        "gpt": call_openai
    }

    primary = providers_map.get(provider_clean, call_gemini)
    res = await primary(prompt, history=history, system_prompt=system_prompt)
    if res:
        return res

    # Fallback to other available free providers automatically
    fallback_funcs = [call_gemini, call_groq, call_openai]
    for fn in fallback_funcs:
        if fn != primary:
            res_fb = await fn(prompt, history=history, system_prompt=system_prompt)
            if res_fb:
                return res_fb

    return "❌ Sorry, I couldn't reach any AI provider right now. Please get a free `GEMINI_API_KEY` (from Google AI Studio) or `GROQ_API_KEY` and set it in your `.env` file!"


