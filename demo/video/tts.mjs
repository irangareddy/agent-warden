// Narration for the Wagent film, one clip per line, via OpenRouter (openai/gpt-audio).
//   OPENROUTER_API_KEY=... node tts.mjs
// Writes audio/raw/NN.wav, then audio/NN.wav (silence trimmed) and audio/timing.json.
// The key is read from the environment and never printed.
import { mkdirSync, writeFileSync } from "node:fs";
import { execFileSync, spawnSync } from "node:child_process";
import ffmpeg from "ffmpeg-static";
import { LINES } from "./script.mjs";

const KEY = process.env.OPENROUTER_API_KEY;
if (!KEY) { console.error("OPENROUTER_API_KEY is not set"); process.exit(1); }
const MODEL = process.env.TTS_MODEL || "openai/gpt-audio";
const VOICE = process.env.TTS_VOICE || "marin";
const SYSTEM = "You are the narrator of a short, modern product film. Read the user's text aloud exactly as written, " +
  "word for word, in a warm, clear, confident voice at a natural conversational pace, with brief pauses at periods. " +
  "Pronounce Wagent as 'WAY-jent'. Do not add, skip or change any words, and say nothing else.";

function wav(pcm, rate = 24000) {
  const h = Buffer.alloc(44);
  h.write("RIFF", 0); h.writeUInt32LE(36 + pcm.length, 4); h.write("WAVE", 8); h.write("fmt ", 12);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(rate, 24);
  h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write("data", 36); h.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([h, pcm]);
}

async function speak(text) {
  const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${KEY}` },
    body: JSON.stringify({ model: MODEL, stream: true, modalities: ["text", "audio"],
      audio: { voice: VOICE, format: "pcm16" },
      messages: [{ role: "system", content: SYSTEM }, { role: "user", content: text }] }),
  });
  if (!res.ok) throw new Error(`OpenRouter ${res.status}`);
  const chunks = []; let buf = ""; let said = "";
  for await (const part of res.body) {
    buf += Buffer.from(part).toString("utf8");
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line.startsWith("data: ") || line === "data: [DONE]") continue;
      try {
        for (const c of JSON.parse(line.slice(6)).choices || []) {
          const a = c.delta?.audio?.data; if (a) chunks.push(Buffer.from(a, "base64"));
          const tr = c.delta?.audio?.transcript; if (tr) said += tr;
        }
      } catch { /* keep-alive or partial */ }
    }
  }
  if (!chunks.length) throw new Error("no audio returned");
  return { pcm: Buffer.concat(chunks), said };
}

const norm = s => s.toLowerCase().replace(/[^a-z ]/g, " ").replace(/\s+/g, " ").trim();

const dur = f => {
  const err = spawnSync(ffmpeg, ["-hide_banner", "-i", f, "-f", "null", "-"], { encoding: "utf8" }).stderr;
  const m = [...err.matchAll(/time=(\d+):(\d+):([\d.]+)/g)].pop();
  return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
};

mkdirSync("audio/raw", { recursive: true });
const clips = [];
for (const [i, line] of LINES.entries()) {
  const n = String(i).padStart(2, "0");
  let got;
  for (let attempt = 1; attempt <= 4; attempt++) {
    got = await speak(line.say);
    if (norm(got.said) === norm(line.say)) break;
    console.log(`   retry ${n}: heard "${got.said.trim()}"`);
  }
  writeFileSync(`audio/raw/${n}.wav`, wav(got.pcm));
  execFileSync(ffmpeg, ["-hide_banner", "-loglevel", "error", "-y", "-i", `audio/raw/${n}.wav`, "-af",
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,areverse",
    `audio/${n}.wav`]);
  const d = dur(`audio/${n}.wav`);
  clips.push({ file: `audio/${n}.wav`, duration: d, said: got.said.trim(), exact: norm(got.said) === norm(line.say) });
  console.log(`${n}  ${d.toFixed(2)}s  ${norm(got.said) === norm(line.say) ? "exact" : "MISMATCH"}  ${got.said.trim()}`);
}
writeFileSync("audio/timing.json", JSON.stringify({ model: MODEL, voice: VOICE, clips }, null, 2));
console.log(`speech ${clips.reduce((a, c) => a + c.duration, 0).toFixed(1)}s`);
