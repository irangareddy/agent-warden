// Render the Wagent film: scene.js frames (Chrome) + narration -> wagent-film.mp4
//   node render.mjs            full film
//   node render.mjs --stills   one still per shot, for review
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { spawn, execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ffmpeg from "ffmpeg-static";
import { chromium } from "playwright-core";
import { LINES } from "./script.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FPS = 30, LEAD = 0.8, GAP = 0.55, TAIL = 2.6;
const timing = JSON.parse(readFileSync(path.join(HERE, "audio/timing.json"), "utf8"));
let t = LEAD; const lines = timing.clips.map(c => { const l = [+t.toFixed(3), +(t + c.duration).toFixed(3)]; t += c.duration + GAP; return l; });
const end = +(lines.at(-1)[1] + TAIL).toFixed(3);
const film = { lines, heads: LINES.map(l => l.head), end };
mkdirSync(path.join(HERE, "build"), { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.addInitScript(`window.__FILM__ = ${JSON.stringify(film)};`);
await page.goto("file://" + path.join(HERE, "scene.html"));
await page.evaluate("window.__ready__"); await page.waitForTimeout(400);
const snap = async (sec, q) => Buffer.from((await page.evaluate(([s, qq]) => window.snap(s, qq), [sec, q])).split(",")[1], "base64");

if (process.argv.includes("--stills")) {
  const picks = lines.map(([a, b]) => a + (b - a) * 0.7);
  for (const [i, s] of picks.entries()) writeFileSync(path.join(HERE, "build", `still_${String(i).padStart(2, "0")}.jpg`), await snap(s, 0.88));
  console.log("stills at", picks.map(s => s.toFixed(1)).join(", "), "· end", end);
  await browser.close(); process.exit(0);
}

// narration track: each clip placed at its line start, loudness normalised
const inputs = timing.clips.flatMap(c => ["-i", path.join(HERE, c.file)]);
const delays = timing.clips.map((c, i) => `[${i}:a]aresample=48000,adelay=${Math.round(lines[i][0] * 1000)}|${Math.round(lines[i][0] * 1000)}[a${i}]`).join(";");
const mix = timing.clips.map((_, i) => `[a${i}]`).join("");
const audio = path.join(HERE, "build", "narration.wav");
execFileSync(ffmpeg, ["-hide_banner", "-loglevel", "error", "-y", ...inputs, "-filter_complex",
  `${delays};${mix}amix=inputs=${timing.clips.length}:normalize=0,apad,atrim=0:${end},afade=t=out:st=${end - 0.8}:d=0.8,loudnorm=I=-16:TP=-1.5:LRA=11[out]`,
  "-map", "[out]", "-ac", "2", "-ar", "48000", audio]);

// frames piped straight into the encoder
const outFile = path.join(HERE, "wagent-film.mp4");
const enc = spawn(ffmpeg, ["-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
  "-i", audio, "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", outFile],
  { stdio: ["pipe", "inherit", "inherit"] });
const n = Math.round(end * FPS);
for (let i = 0; i < n; i++) {
  const buf = await snap(i / FPS, 0.94);
  if (!enc.stdin.write(buf)) await new Promise(r => enc.stdin.once("drain", r));
  if (i % 300 === 0) process.stdout.write(`frame ${i}/${n}\r`);
}
enc.stdin.end(); await new Promise(r => enc.on("close", r));
await browser.close();
console.log(`\nwrote ${outFile} (${end.toFixed(1)}s, ${n} frames)`);
