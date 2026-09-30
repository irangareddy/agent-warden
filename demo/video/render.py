"""Render the Wagent film: scene.html frames + narration -> wagent-film.mp4.

    uv run --no-project --with playwright --with imageio-ffmpeg python demo/video/render.py [--preview]

Uses the installed Google Chrome (no browser download). Narration clips come
from audio/trimmed/*.wav (see tts.py); timing is derived from their lengths.
"""

import argparse
import base64
import json
import os
import subprocess
import wave

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
LEAD, GAP, TAIL = 0.6, 0.45, 1.2
LOGOS = {
    "claudecode": "lobe-claudecode-color.svg", "codex": "lobe-codex-color.svg", "cursor": "lobe-cursor.svg",
    "copilot": "lobe-githubcopilot.svg", "gemini": "lobe-gemini-color.svg", "grok": "lobe-grok.svg",
    "openclaw": "lobe-openclaw.svg", "flower": "flower-official.svg", "flowerDark": "flower-official.svg",
}


def load_logo(name, file):
    svg = open(os.path.join(HERE, "logos", file), encoding="utf-8").read()
    svg = svg.replace('width="1em"', 'width="256"').replace('height="1em"', 'height="256"')
    color = "#3a3a40" if name == "flowerDark" else "#111111"
    return svg.replace("currentColor", color)


def timing():
    clips = sorted(f for f in os.listdir(os.path.join(HERE, "audio", "trimmed")) if f.endswith(".wav"))
    lines, t = [], LEAD
    for f in clips:
        w = wave.open(os.path.join(HERE, "audio", "trimmed", f))
        d = w.getnframes() / w.getframerate()
        lines.append([round(t, 3), round(t + d, 3), f])
        t += d + GAP
    return lines, round(lines[-1][1] + TAIL, 3)


def narration(lines, end, out):
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    inputs, filters = [], []
    for i, (start, _, f) in enumerate(lines):
        inputs += ["-i", os.path.join(HERE, "audio", "trimmed", f)]
        ms = int(start * 1000)
        filters.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(lines)))
    fc = ";".join(filters) + f";{mix}amix=inputs={len(lines)}:normalize=0,apad,atrim=0:{end},afade=t=out:st={end-0.6}:d=0.6,loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", fc,
                    "-map", "[out]", "-ac", "2", out], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="render stills only (one per shot)")
    opt = ap.parse_args()
    lines, end = timing()
    tjs = {"lines": [[a, b] for a, b, _ in lines], "end": end}
    logos = {k: load_logo(k, v) for k, v in LOGOS.items()}
    frames = os.path.join(HERE, "build", "frames")
    os.makedirs(frames, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.add_init_script(f"window.__TIMING__={json.dumps(tjs)};window.__LOGOS__={json.dumps(logos)};")
        page.goto("file://" + os.path.join(HERE, "scene.html"))
        page.evaluate("window.__ready__")
        page.wait_for_timeout(500)
        if opt.preview:
            stills = [2.5, 8.5, 14.0, lines[3][0] + 1.2, lines[4][0] + 3.0, lines[4][0] + 6.5, lines[5][0] + 1.5, lines[6][0] + 2.6]
            for i, t in enumerate(stills):
                data = page.evaluate(f"window.snap({t}, 0.9)")
                open(os.path.join(HERE, "build", f"still_{i}_{t:.1f}.jpg"), "wb").write(base64.b64decode(data.split(",")[1]))
            print("stills:", [round(s, 1) for s in stills], "end", end)
            browser.close()
            return
        n = int(end * FPS)
        for i in range(n):
            data = page.evaluate(f"window.snap({i / FPS}, 0.93)")
            open(os.path.join(frames, f"{i:05d}.jpg"), "wb").write(base64.b64decode(data.split(",")[1]))
        browser.close()
    audio = os.path.join(HERE, "build", "narration.wav")
    narration(lines, end, audio)
    out = os.path.join(HERE, "wagent-film.mp4")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS),
                    "-i", os.path.join(frames, "%05d.jpg"), "-i", audio, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-preset", "slow", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    print(f"wrote {out}  ({end:.1f}s, {n} frames)")


if __name__ == "__main__":
    main()
