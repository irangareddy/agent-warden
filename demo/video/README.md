# Wagent film (38 s)

`wagent-film.mp4` is the 1080p concept film. Everything here is editable:

- `scene.html` draws every frame from a timestamp (open it in a browser to watch a live loop).
- `tts.py` writes the narration, one clip per line (OpenRouter `openai/gpt-audio`, key from the environment).
- `render.py` trims timing from the narration, renders frames with Chrome and muxes the audio:

```bash
OPENROUTER_API_KEY=... python3.12 demo/video/tts.py      # only if the script changes
uv run --no-project --with playwright --with imageio-ffmpeg python demo/video/render.py
```

Logos are trademarks of their owners and are shown to indicate compatibility.
