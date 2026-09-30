"""Generate the narration, one clip per line.

    python3.12 demo/video/tts.py                 # OpenRouter gpt-audio (default)
    TTS_PROVIDER=gemini python3.12 demo/video/tts.py

Keys come from the environment or fleet/.env (OPENROUTER_API_KEY / GEMINI_API_KEY)
and are never printed.

Writes demo/video/audio/NN.wav (24 kHz mono) and audio/durations.json.
The key is read from the environment and never printed.
"""

import base64
import json
import os
import sys
import urllib.request
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDER = os.environ.get("TTS_PROVIDER", "openrouter")
MODEL = os.environ.get("TTS_MODEL", "openai/gpt-audio" if PROVIDER == "openrouter" else "gemini-3.8-flash-tts")
VOICE = os.environ.get("TTS_VOICE", "sage" if PROVIDER == "openrouter" else "Sulafat")
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "fleet", ".env")


def key(name: str) -> str:
    value = os.environ.get(name, "")
    if not value and os.path.exists(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            if line.startswith(name + "="):
                value = line.split("=", 1)[1].strip().strip('"')
    return value


def write_wav(path: str, pcm: bytes, rate: int) -> float:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return len(pcm) / 2 / rate


OR_SYSTEM = ("You are the narrator of a short, calm product film. Read the user's text aloud exactly as written, "
             "word for word, warm, clear and at a natural conversational pace, with short pauses at periods. Pronounce Wagent as 'WAY-jent'. "
             "Do not add, skip or change any words, and say nothing else.")


def speak_openrouter(text: str, path: str) -> float:
    body = {"model": MODEL, "modalities": ["text", "audio"], "audio": {"voice": VOICE, "format": "pcm16"},
            "stream": True, "messages": [{"role": "system", "content": OR_SYSTEM}, {"role": "user", "content": text}]}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key("OPENROUTER_API_KEY")})
    pcm = bytearray()
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                chunk = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices", []):
                audio = (choice.get("delta") or {}).get("audio") or {}
                if audio.get("data"):
                    pcm += base64.b64decode(audio["data"])
    if not pcm:
        raise RuntimeError("no audio returned")
    return write_wav(path, bytes(pcm), 24000)
STYLE = ("Read this like the calm, warm narrator of a short product film. "
         "Unhurried, confident, with small natural pauses at commas and periods. "
         "Pronounce the name Wagent as 'WAY-jent'. Text: ")

LINES = [
    "Agents are everywhere now. Writing our code. Running our systems.",
    "They hold our keys, and work while we sleep.",
    "Sometimes, one reaches for something it shouldn't.",
    "Wagent stops it. Before it happens.",
    "Then the lesson travels. Every agent learns it. Only the lesson moves. Never the data.",
    "One catch. Every agent protected.",
    "Wagent. A warden for your AI agents.",
]


def speak(text: str, path: str) -> float:
    if PROVIDER == "openrouter":
        return speak_openrouter(text, path)
    body = {
        "contents": [{"parts": [{"text": STYLE + text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json", "x-goog-api-key": key("GEMINI_API_KEY")})
    data = json.load(urllib.request.urlopen(req, timeout=120))
    part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    rate = 24000
    for piece in part.get("mimeType", "").split(";"):
        if piece.strip().startswith("rate="):
            rate = int(piece.split("=")[1])
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return len(pcm) / 2 / rate


def main() -> None:
    need = "OPENROUTER_API_KEY" if PROVIDER == "openrouter" else "GEMINI_API_KEY"
    if not key(need):
        sys.exit(f"{need} is not set (environment or fleet/.env)")
    out = os.path.join(HERE, "audio")
    os.makedirs(out, exist_ok=True)
    durations = []
    for i, line in enumerate(LINES):
        d = speak(line, os.path.join(out, f"{i:02d}.wav"))
        durations.append(round(d, 3))
        print(f"{i:02d}  {d:5.2f}s  {line}")
    json.dump({"voice": VOICE, "model": MODEL, "lines": LINES, "durations": durations},
              open(os.path.join(out, "durations.json"), "w"), indent=2)
    print(f"total speech {sum(durations):.1f}s")


if __name__ == "__main__":
    main()
