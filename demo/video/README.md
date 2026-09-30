# Wagent film (64 s)

`wagent-film.mp4`: 1080p, 30 fps, narrated. Plays in about 42 seconds at 1.5×.
Pure JavaScript; every agent and icon is drawn in code (no images).

| File | What it does |
|---|---|
| `script.mjs` | The narration lines and the headline shown with each |
| `tts.mjs` | Narration via OpenRouter `openai/gpt-audio`; checks each clip's transcript against the script and retries mismatches |
| `scene.js` | Draws any frame from a timestamp (open `scene.html` in a browser to watch a live loop) |
| `render.mjs` | Renders frames in Chrome, mixes and normalises the narration, encodes the MP4 |

```bash
npm install
OPENROUTER_API_KEY=... npm run voice   # only when script.mjs changes
npm run stills                         # one still per shot in build/
npm run render                         # wagent-film.mp4
```
