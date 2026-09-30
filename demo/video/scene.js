// Wagent film — every frame is drawn from a timestamp, so rendering is exact and repeatable.
// window.__FILM__ = { lines: [[start, end], ...], heads: [...], end } is injected by render.mjs.
const FILM = window.__FILM__ || (() => {           // preview timing when opened directly
  const d = [2.3, 5.9, 4.4, 4.9, 6.2, 8.6, 6.4, 5.0, 4.2, 3.5, 3.2], lines = []; let t = 0.8;
  for (const x of d) { lines.push([t, t + x]); t += x + 0.55; }
  return { lines, heads: ["Your AI agents never sleep.", "They hold your keys.", "One reaches too far.", "Checked before it runs.",
    "No single agent can do this alone.", "One block becomes everyone's rule.", "Tested before it's trusted.", "Only the rule moves.",
    "A human knows right away.", "One catch. Every agent protected.", ""], end: t + 1.8 };
})();

const W = 1920, H = 1080;
const cv = document.getElementById("c"), g = cv.getContext("2d");
const L = FILM.lines, S = i => L[i][0], E = i => L[i][1];

/* ---------- palette & type ---------- */
const C = { bg0: "#0b1226", bg1: "#05080f", ink: "#f4f6fb", muted: "#8a93a8", faint: "rgba(255,255,255,0.08)",
  gold: "#f5c451", red: "#ff5a4e", green: "#4ade80", plate: "#0b1224" };
const AGENT = ["#8ab4ff", "#7ee2b8", "#f7a8c8", "#ffd479", "#b79cff", "#6fd6ea", "#ffa98a", "#9fe870", "#c4b5fd", "#f9a8d4", "#67e8f9", "#fcd34d"];
const SANS = "Inter, -apple-system, Helvetica, Arial, sans-serif", MONO = "'JetBrains Mono', ui-monospace, Menlo, monospace";

/* ---------- motion helpers ---------- */
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const seg = (t, a, b) => clamp((t - a) / (b - a));
const out = t => 1 - Math.pow(1 - clamp(t), 3);
const inOut = t => { t = clamp(t); return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
const pop = t => { t = clamp(t); return t === 0 ? 0 : 1 + Math.exp(-7 * t) * Math.sin(t * 11 - Math.PI / 2) * 0.9 + 0.0; };
const fadeIO = (t, a, b, f = .4) => seg(t, a, a + f) * (1 - seg(t, b - f, b));

/* ---------- scene layout ---------- */
// field layout (shots 1–4) and machine layout (shots 5–10)
const FIELD = [[1230, 560], [420, 300], [760, 200], [1120, 230], [1480, 300], [1720, 470], [900, 560], [560, 620], [300, 500], [1760, 180], [660, 420], [1000, 400]];
const PANELS = [{ x: 150, y: 110, name: "Machine 1", model: "GPT" }, { x: 1070, y: 110, name: "Machine 2", model: "Kimi" },
  { x: 150, y: 450, name: "Machine 3", model: "MiniMax" }, { x: 1070, y: 450, name: "Machine 4", model: "Gemini" }];
const PW = 700, PH = 290, HUB = { x: 960, y: 425 };
const PANEL_OF = [0, 0, 2, 1, 1, 3, 3, 2, 0, 1, 2, 3];      // which machine each agent lives on
const SLOT = [0, 1, 2, 0, 1, 2, 0, 0, 2, 2, 1, 1];
const TARGET = { x: 1540, y: 720 };                       // the thing it shouldn't touch
const TASKS = { 2: "writing code", 4: "shipping v2.4", 7: "syncing data", 11: "running tests" };
const panelSlot = (p, s) => ({ x: PANELS[p].x + 150 + s * 175, y: PANELS[p].y + 170 });

/* ---------- small drawings ---------- */
function glow(x, y, r, rgb, a) { if (a <= 0) return; const gr = g.createRadialGradient(x, y, 0, x, y, r); gr.addColorStop(0, `rgba(${rgb},${a})`); gr.addColorStop(1, `rgba(${rgb},0)`); g.fillStyle = gr; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); }
function text(s, x, y, size, weight, color, align = "left", font = SANS, ls = 0) { g.font = `${weight} ${size}px ${font}`; g.fillStyle = color; g.textAlign = align; g.textBaseline = "middle"; g.letterSpacing = ls + "px"; g.fillText(s, x, y); g.letterSpacing = "0px"; }
function rr(x, y, w, h, r) { g.beginPath(); g.roundRect(x, y, w, h, r); }

function agent(x, y, s, color, o = {}) {
  const a = o.alpha ?? 1; if (a <= 0) return;
  g.save(); g.globalAlpha = a; g.translate(x, y); const k = o.scale ?? 1; g.scale(k, k);
  glow(0, s * 0.1, s * 1.2, o.red ? "255,90,78" : "120,160,255", 0.22 * (o.dim ?? 1));
  // antenna
  g.strokeStyle = color; g.lineWidth = s * 0.06; g.lineCap = "round";
  g.beginPath(); g.moveTo(0, -s * 0.43); g.lineTo(0, -s * 0.62); g.stroke();
  g.fillStyle = color; g.beginPath(); g.arc(0, -s * 0.66, s * 0.08, 0, 7); g.fill();
  // body
  rr(-s / 2, -s * 0.43, s, s * 0.86, s * 0.28); g.fillStyle = color; g.fill();
  const sh = g.createLinearGradient(0, -s * 0.43, 0, s * 0.43); sh.addColorStop(0, "rgba(255,255,255,0.28)"); sh.addColorStop(1, "rgba(0,0,0,0.12)");
  rr(-s / 2, -s * 0.43, s, s * 0.86, s * 0.28); g.fillStyle = sh; g.fill();
  // face plate and eyes
  rr(-s * 0.36, -s * 0.24, s * 0.72, s * 0.42, s * 0.16); g.fillStyle = C.plate; g.fill();
  const bl = o.blink ?? 1, eh = s * 0.16 * bl + 1.5;
  g.fillStyle = o.red ? "#ff8a80" : "#e8f0ff";
  rr(-s * 0.18 - s * 0.05, -s * 0.03 - eh / 2, s * 0.1, eh, s * 0.05); g.fill();
  rr(s * 0.18 - s * 0.05, -s * 0.03 - eh / 2, s * 0.1, eh, s * 0.05); g.fill();
  if (o.dim !== undefined && o.dim < 1) { rr(-s / 2 - 2, -s * 0.7, s + 4, s * 1.2, s * 0.3); g.fillStyle = `rgba(5,8,15,${(1 - o.dim) * 0.75})`; g.fill(); }
  g.restore();
}
function key(x, y, k, a) { if (a <= 0) return; g.save(); g.globalAlpha = a; g.translate(x, y); g.scale(k, k); g.strokeStyle = C.gold; g.lineWidth = 3; g.lineCap = "round";
  g.beginPath(); g.arc(0, 0, 7, 0, 7); g.stroke(); g.beginPath(); g.moveTo(7, 0); g.lineTo(24, 0); g.moveTo(18, 0); g.lineTo(18, 6); g.moveTo(23, 0); g.lineTo(23, 5); g.stroke(); g.restore(); }
function padlock(x, y, k, a, color = C.red) { if (a <= 0) return; g.save(); g.globalAlpha = a; g.translate(x, y); g.scale(k, k);
  g.strokeStyle = color; g.lineWidth = 6; g.lineCap = "round"; g.beginPath(); g.arc(0, -18, 17, Math.PI, 0); g.lineTo(17, -4); g.moveTo(-17, -18); g.lineTo(-17, -4); g.stroke();
  g.fillStyle = color; rr(-27, -6, 54, 42, 9); g.fill(); g.fillStyle = C.plate; g.beginPath(); g.arc(0, 10, 6, 0, 7); g.fill(); g.fillRect(-2.5, 10, 5, 12); g.restore(); }
function check(x, y, k, a, color = C.green) { if (a <= 0) return; g.save(); g.globalAlpha = a; g.translate(x, y); g.scale(k, k); g.fillStyle = color; g.beginPath(); g.arc(0, 0, 14, 0, 7); g.fill();
  g.strokeStyle = C.plate; g.lineWidth = 3.5; g.lineCap = "round"; g.lineJoin = "round"; g.beginPath(); g.moveTo(-6, 0); g.lineTo(-1.5, 5); g.lineTo(7, -5); g.stroke(); g.restore(); }
function cross(x, y, k, a) { if (a <= 0) return; g.save(); g.globalAlpha = a; g.translate(x, y); g.scale(k, k); g.fillStyle = C.red; g.beginPath(); g.arc(0, 0, 14, 0, 7); g.fill();
  g.strokeStyle = C.plate; g.lineWidth = 3.5; g.lineCap = "round"; g.beginPath(); g.moveTo(-5, -5); g.lineTo(5, 5); g.moveTo(5, -5); g.lineTo(-5, 5); g.stroke(); g.restore(); }
function shieldGlyph(x, y, k, color) { g.save(); g.translate(x, y); g.scale(k, k); g.fillStyle = color; g.beginPath(); g.moveTo(0, -10); g.lineTo(8, -6); g.lineTo(8, 1); g.quadraticCurveTo(8, 8, 0, 11); g.quadraticCurveTo(-8, 8, -8, 1); g.lineTo(-8, -6); g.closePath(); g.fill(); g.restore(); }
function ruleCard(x, y, a, bad = false, k = 1) { if (a <= 0) return; g.save(); g.globalAlpha = a; g.translate(x, y); g.scale(k, k);
  const col = bad ? C.red : C.gold; glow(0, 0, 70, bad ? "255,90,78" : "245,196,81", 0.35);
  rr(-62, -22, 124, 44, 22); g.fillStyle = "#101a33"; g.fill(); g.lineWidth = 2.5; g.strokeStyle = col; g.stroke();
  shieldGlyph(-36, 0, 1.1, col); text(bad ? "bad rule" : "rule", 8, 1, 20, 600, col, "center"); g.restore(); }
function cylinder(x, y, a, lockA) { if (a <= 0) return; g.save(); g.globalAlpha = a; g.translate(x, y); g.strokeStyle = "rgba(180,200,255,0.8)"; g.lineWidth = 2.5; g.fillStyle = "rgba(120,150,220,0.14)";
  g.beginPath(); g.ellipse(0, -22, 26, 9, 0, 0, 7); g.fill(); g.stroke(); g.beginPath(); g.moveTo(-26, -22); g.lineTo(-26, 22); g.ellipse(0, 22, 26, 9, 0, Math.PI, 0, true); g.lineTo(26, -22); g.fill(); g.stroke();
  g.beginPath(); g.ellipse(0, 0, 26, 9, 0, 0, Math.PI); g.stroke(); text("data", 0, 48, 16, 500, C.muted, "center", MONO);
  if (lockA > 0) padlock(26, 26, 0.42, lockA, C.gold); g.restore(); }
// Flower mark (drawn from its SVG path, no image)
const FLOWER = [new Path2D("M34.87,22.13l-6.18,6.18v11.14s6.26,6.19,6.26,6.19l17.76-.21,6.09-6.01.28-10.93-6.19-6.35h-18.02ZM51.95,36.45l-2.11,2.09-12.08.15-2.15-2.12v-5.38s2.13-2.13,2.13-2.13h12.23s2.11,2.17,2.11,2.17l-.13,5.22h0Z"),
  new Path2D("M.3,39.91l1.73,12.1,7.47,2.47.07,7.76,11.56,6.66,5.42-1.69,3.92,4.84h14.65s4.51-4.38,4.51-4.38l5.01,2,12.53-4.52,1.22-7.37,7.56-.77,4.95-12.18-3.2-6.95,4.33-6.25h0s-3.85-13.47-3.85-13.47l-6.55-1.67-.37-6.61-10.85-6.81-6.18,1.63L50.1,0h-12.96s-3.7,4.7-3.7,4.7l-6.25-2.48-10.48,4.56-2.3,6.45-8.04.4L0,27.49l4.06,6.7-3.76,5.72ZM7.83,27.04l3.08-6.7,8.47-.42,2.85-7.98,5.09-2.21,8.38,3.33,4.81-6.12h6.46s4.88,5.56,4.88,5.56l7.42-1.96,5.27,3.31.46,8.1,7.61,1.94,1.85,6.5-4.71,6.81,3.6,7.82h0s-2.25,5.53-2.25,5.53l-8.68.88-1.42,8.59-6.23,2.25-6.74-2.69-5.75,5.58h-8.48s-4.82-5.96-4.82-5.96l-7.02,2.19-5.5-3.17-.08-8.76-8.1-2.68-.75-5.25,4.73-7.18-4.43-7.3Z")];
function flower(x, y, size, color) { g.save(); g.translate(x - size / 2, y - size * 0.44); g.scale(size / 82, size / 82); g.fillStyle = color; for (const p of FLOWER) g.fill(p, "evenodd"); g.restore(); }
function bell(x, y, k, color) { g.save(); g.translate(x, y); g.scale(k, k); g.fillStyle = color; g.beginPath(); g.moveTo(-11, 6); g.quadraticCurveTo(-11, -12, 0, -12); g.quadraticCurveTo(11, -12, 11, 6); g.lineTo(14, 9); g.lineTo(-14, 9); g.closePath(); g.fill(); g.beginPath(); g.arc(0, 12, 3.5, 0, 7); g.fill(); g.restore(); }

/* ---------- stars ---------- */
let seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const STARS = Array.from({ length: 140 }, () => ({ x: rnd() * W, y: rnd() * H, r: rnd() * 1.4 + 0.3, p: rnd() * 6 }));

/* ---------- headline: words rise in one by one ---------- */
function headline(t) {
  for (let i = 0; i < FILM.heads.length; i++) {
    const s = FILM.heads[i]; if (!s) continue;
    const a0 = S(i) - 0.1, a1 = (i + 1 < L.length ? S(i + 1) : FILM.end) - 0.25;
    const vis = fadeIO(t, a0, a1, 0.35); if (vis <= 0) continue;
    g.font = `700 64px ${SANS}`; g.letterSpacing = "-1.6px";
    let x = 150; const y = 948;
    s.split(" ").forEach((w, k) => {
      const p = out(seg(t, a0 + k * 0.07, a0 + k * 0.07 + 0.45));
      g.save(); g.globalAlpha = vis * p; text(w, x, y + (1 - p) * 26, 64, 700, C.ink, "left", SANS, -1.6); g.restore();
      g.font = `700 64px ${SANS}`; g.letterSpacing = "-1.6px"; x += g.measureText(w + " ").width;
    });
    g.letterSpacing = "0px";
  }
}

/* ---------- the film ---------- */
function frame(t) {
  // background
  const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, C.bg0); bg.addColorStop(1, C.bg1); g.fillStyle = bg; g.fillRect(0, 0, W, H);
  for (const s of STARS) { g.fillStyle = `rgba(200,215,255,${0.10 + 0.12 * Math.sin(t * 0.8 + s.p) ** 2})`; g.fillRect(s.x, (s.y + t * 3) % H, s.r, s.r); }

  const tStop = S(3) + (E(3) - S(3)) * 0.55;         // "This one, it stops."
  const morph = inOut(seg(t, S(4) + 0.2, S(4) + 2.2));
  // camera: close in on the rogue and the padlock during shots 3–4
  const tight = inOut(seg(t, S(2), S(2) + 1.8)) * (1 - inOut(seg(t, S(4), S(4) + 1.6)));
  const zoom = 1 + 0.03 * seg(t, 0, S(2)) + 0.26 * tight;
  const fx = lerp(W / 2, 1385, tight), fy = lerp(H / 2 - 40, 640, tight);
  g.save(); g.translate(W / 2, H / 2 - 40); g.scale(zoom, zoom); g.translate(-fx, -fy);

  // agent positions
  const drift = inOut(seg(t, S(2) + 0.2, tStop)) * 0.4;
  const pos = FIELD.map((p, i) => {
    let x = p[0], y = p[1] + Math.sin(t * 1.3 + i * 1.7) * 4 * (1 - morph);
    if (i === 0) { x = lerp(x, TARGET.x, drift); y = lerp(y, TARGET.y, drift); }
    const q = panelSlot(PANEL_OF[i], SLOT[i]);
    return { x: lerp(x, q.x, morph), y: lerp(y, q.y + Math.sin(t * 1.3 + i) * 2, morph) };
  });

  // machines (panels) appear with the morph
  const learnAt = [S(5) + 0.9, S(5) + 2.9, S(5) + 3.15, S(5) + 3.4];
  PANELS.forEach((P, k) => {
    const a = out(seg(t, S(4) + 0.9 + k * 0.12, S(4) + 1.9 + k * 0.12)) * (1 - seg(t, S(10) - 0.6, S(10))); if (a <= 0) return;
    const learned = seg(t, learnAt[k], learnAt[k] + 0.6);
    g.save(); g.globalAlpha = a;
    rr(P.x, P.y, PW, PH, 26); g.fillStyle = "rgba(255,255,255,0.035)"; g.fill();
    g.lineWidth = 2; g.strokeStyle = `rgba(${lerp(255, 245, learned)},${lerp(255, 196, learned)},${lerp(255, 81, learned)},${0.10 + 0.45 * learned})`; g.stroke();
    // "home" boundary pulse (shot 8)
    const home = fadeIO(t, S(7), S(8) + 0.4, 0.4);
    if (home > 0) { g.setLineDash([10, 10]); g.lineDashOffset = -t * 30; rr(P.x - 10, P.y - 10, PW + 20, PH + 20, 32); g.strokeStyle = `rgba(245,196,81,${0.5 * home})`; g.stroke(); g.setLineDash([]); }
    text(P.name, P.x + 32, P.y + 40, 24, 600, C.ink);
    g.font = `500 17px ${MONO}`; const mw = g.measureText(P.model).width + 26;
    rr(P.x + 170, P.y + 26, mw, 28, 14); g.fillStyle = "rgba(255,255,255,0.08)"; g.fill(); text(P.model, P.x + 170 + mw / 2, P.y + 41, 17, 500, "#c9d3ea", "center", MONO);
    // test bar (shot 7)
    const tb = S(6) + 0.3 + k * 0.25, prog = out(seg(t, tb, tb + 1.3)), bad = k === 3 ? seg(t, S(6) + 3.2, S(6) + 3.4) : 0;
    const tv = fadeIO(t, tb - 0.1, S(7) + 0.3, 0.3);
    if (tv > 0) {
      g.globalAlpha = a * tv; rr(P.x + 32, P.y + PH - 36, PW - 64, 6, 3); g.fillStyle = "rgba(255,255,255,0.08)"; g.fill();
      rr(P.x + 32, P.y + PH - 36, (PW - 64) * prog, 6, 3); g.fillStyle = C.green; g.fill();
      if (prog >= 1) { check(P.x + PW - 44, P.y + 40, 0.9, out(seg(t, tb + 1.3, tb + 1.6))); text("tested on its own work", P.x + PW - 70, P.y + 41, 17, 500, C.muted, "right"); }
      if (bad > 0) { rr(P.x - 4, P.y - 4, PW + 8, PH + 8, 30); g.strokeStyle = `rgba(255,90,78,${0.8 * bad * (1 - seg(t, S(6) + 4.4, S(6) + 5))})`; g.lineWidth = 3; g.stroke(); }
    }
    g.restore();
    cylinder(P.x + PW - 70, P.y + 165, a * (0.35 + 0.65 * fadeIO(t, S(7) - 0.2, S(9), 0.4)), fadeIO(t, S(7) + 0.4, S(9), 0.4));
  });

  // lines from Flower to each machine
  const hubA = out(seg(t, S(5), S(5) + 0.6)) * (1 - seg(t, S(10) - 0.6, S(10)));
  if (hubA > 0) {
    PANELS.forEach(P => { const ex = P.x < HUB.x ? P.x + PW : P.x, ey = P.y + PH / 2;
      g.strokeStyle = `rgba(245,196,81,${0.28 * hubA})`; g.lineWidth = 2; g.setLineDash([4, 8]); g.beginPath(); g.moveTo(HUB.x, HUB.y); g.lineTo(ex, ey); g.stroke(); g.setLineDash([]); });
  }

  // activity lines between nearby agents (shot 2)
  const busy = fadeIO(t, S(1) - 0.2, S(2) + 0.6, 0.6);
  if (busy > 0) for (let i = 1; i < pos.length; i++) for (let j = i + 1; j < pos.length; j++) {
    const a = pos[i], b = pos[j], d = Math.hypot(a.x - b.x, a.y - b.y); if (d > 420) continue;
    g.strokeStyle = `rgba(140,175,255,${0.12 * busy})`; g.lineWidth = 1.2; g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
    const p = (t * 0.4 + i * 0.13 + j * 0.07) % 1; glow(lerp(a.x, b.x, p), lerp(a.y, b.y, p), 7, "170,200,255", 0.6 * busy);
  }

  // the padlock it reaches for (shots 3–4)
  const lockA = fadeIO(t, S(2) + 0.1, S(4) + 1.2, 0.6);
  if (lockA > 0) { glow(TARGET.x, TARGET.y, 150, "255,90,78", 0.28 * lockA); padlock(TARGET.x, TARGET.y, 1.25, lockA);
    text("production keys", TARGET.x + 52, TARGET.y + 8, 20, 500, "rgba(255,138,128,0.9)", "left", MONO); }

  // agents
  const dimAll = 1 - 0.55 * inOut(seg(t, S(2) + 0.2, S(2) + 1.4)) * (1 - inOut(seg(t, S(4), S(4) + 1.2)));
  pos.forEach((p, i) => {
    const appear = pop(seg(t, 0.3 + i * 0.16, 0.3 + i * 0.16 + 0.9));
    const blink = ((t + i * 0.77) % 4.3) < 0.13 ? 0.1 : 1;
    const learned = i === 0 ? 0 : seg(t, learnAt[PANEL_OF[i]] + (i % 3) * 0.12, learnAt[PANEL_OF[i]] + (i % 3) * 0.12 + 0.5);
    const endFade = 1 - seg(t, S(10) - 0.6, S(10));
    const size = lerp(84, 72, morph);
    if (learned > 0) { g.save(); g.globalAlpha = endFade * out(learned); g.strokeStyle = C.gold; g.lineWidth = 3; g.beginPath(); g.arc(p.x, p.y, size * 0.8 + (1 - out(learned)) * 26, 0, 7); g.stroke(); glow(p.x, p.y, size * 1.3, "245,196,81", 0.16 * out(learned)); g.restore(); }
    agent(p.x, p.y, size, AGENT[i], { alpha: clamp(appear, 0, 1.2) * endFade, scale: appear > 0 ? Math.max(0.2, appear) : 0,
      blink, dim: i === 0 ? 1 : dimAll, red: i === 0 && t > tStop && t < S(5) + 1 });
  });

  // task chips and keys (shot 2)
  for (const [i, label] of Object.entries(TASKS)) {
    const k = Number(i), a = fadeIO(t, S(1) + 0.2 + k * 0.08, S(2) + 0.4, 0.4); if (a <= 0) continue;
    const p = pos[k]; g.save(); g.globalAlpha = a; g.font = `500 20px ${MONO}`; const w = g.measureText(label).width + 30;
    rr(p.x - w / 2, p.y - 132, w, 36, 18); g.fillStyle = "rgba(255,255,255,0.09)"; g.fill(); text(label, p.x, p.y - 114, 20, 500, "#c9d3ea", "center", MONO); g.restore();
  }
  pos.forEach((p, i) => key(p.x + 46, p.y - 58, 1.25, out(seg(t, S(1) + 2.6 + i * 0.07, S(1) + 3.2 + i * 0.07)) * (1 - seg(t, S(4), S(4) + 0.8)) * (i === 0 ? 1 : dimAll)));

  // checks pass over agents (shot 4, "checks every action")
  [3, 6, 8, 11, 5, 1].forEach((i, n) => { const a0 = S(3) + 0.15 + n * 0.22; check(pos[i].x, pos[i].y - 88, 1.05, out(seg(t, a0, a0 + 0.25)) * (1 - seg(t, a0 + 0.9, a0 + 1.2))); });
  // the stop
  const st = seg(t, tStop, tStop + 0.3);
  if (st > 0) { const fade = 1 - seg(t, S(4) + 0.4, S(4) + 1.2), p = pos[0]; g.save(); g.globalAlpha = fade;
    g.strokeStyle = C.red; g.lineWidth = 5; g.beginPath(); g.arc(p.x, p.y, lerp(140, 72, out(st)), 0, 7); g.stroke();
    const rip = seg(t, tStop + 0.3, tStop + 1.3); if (rip > 0 && rip < 1) { g.globalAlpha = fade * (1 - rip) * 0.6; g.lineWidth = 2; g.beginPath(); g.arc(p.x, p.y, 72 + rip * 90, 0, 7); g.stroke(); }
    g.globalAlpha = fade * out(seg(t, tStop + 0.25, tStop + 0.6)); text("Blocked", p.x, p.y + 108, 34, 700, "#ff7a6f", "center"); text("before it ran · 0.03 ms", p.x, p.y + 146, 17, 500, "rgba(255,138,128,0.85)", "center", MONO);
    g.restore(); }

  // Flower hub
  if (hubA > 0) { g.save(); g.globalAlpha = hubA; glow(HUB.x, HUB.y, 110, "245,196,81", 0.22); g.fillStyle = "#ffffff"; g.beginPath(); g.arc(HUB.x, HUB.y, 50, 0, 7); g.fill(); flower(HUB.x, HUB.y, 60, "#0b1224");
    text("Flower", HUB.x, HUB.y + 76, 20, 600, C.ink, "center"); g.restore(); }

  // the rule travels: Machine 1 -> Flower -> every machine (shot 6)
  const r0 = S(5) + 0.4, toHub = inOut(seg(t, r0, r0 + 1.1));
  if (toHub > 0 && toHub < 1) ruleCard(lerp(pos[0].x, HUB.x, toHub), lerp(pos[0].y, HUB.y, toHub), 1);
  [1, 2, 3].forEach((k, n) => { const s0 = r0 + 1.35 + n * 0.25, p = inOut(seg(t, s0, s0 + 1.0)); if (p <= 0 || p >= 1) return;
    const P = PANELS[k], ex = P.x + PW / 2, ey = P.y + PH / 2; ruleCard(lerp(HUB.x, ex, p), lerp(HUB.y, ey, p), 1, false, 0.9); });
  // only the rule moves: small cards keep circulating (shot 8)
  const flow = fadeIO(t, S(7), S(8) + 0.2, 0.4);
  if (flow > 0) PANELS.forEach((P, k) => { const p = (t * 0.45 + k * 0.25) % 1, ex = P.x < HUB.x ? P.x + PW : P.x, ey = P.y + PH / 2; ruleCard(lerp(HUB.x, ex, p), lerp(HUB.y, ey, p), flow * Math.sin(p * Math.PI), false, 0.6); });

  // a bad rule arrives and is rejected (shot 7)
  const b0 = S(6) + 2.4, bIn = out(seg(t, b0, b0 + 0.9)), bOut = seg(t, S(6) + 4.3, S(6) + 5.1);
  if (bIn > 0 && bOut < 1) { const x = lerp(2100, 1812, bIn) + bOut * 200 + (t > S(6) + 3.2 && t < S(6) + 3.7 ? Math.sin(t * 60) * 6 : 0), y = 595 + bOut * 160;
    ruleCard(x, y, 1 - bOut, true); if (t > S(6) + 3.2) { cross(x + 70, y - 28, 1, (1 - bOut) * out(seg(t, S(6) + 3.2, S(6) + 3.5))); text("rejected", x, y + 46, 18, 600, "#ff8a80", "center"); } }

  g.restore(); // camera

  // notification: a human knows (shot 9)
  const nIn = out(seg(t, S(8) + 0.1, S(8) + 0.7)), nOut = inOut(seg(t, S(9) + 0.2, S(9) + 0.8));
  if (nIn > 0 && nOut < 1) { const x = lerp(W + 40, 1300, nIn) + nOut * 700, y = 790; g.save();
    g.shadowColor = "rgba(0,0,0,0.5)"; g.shadowBlur = 40; rr(x, y, 540, 150, 24); g.fillStyle = "rgba(24,32,56,0.96)"; g.fill(); g.shadowBlur = 0;
    g.lineWidth = 1.5; g.strokeStyle = "rgba(255,255,255,0.1)"; g.stroke();
    rr(x + 26, y + 28, 52, 52, 14); g.fillStyle = C.gold; g.fill(); bell(x + 52, y + 52, 1.2, C.plate);
    text("Wagent", x + 98, y + 44, 22, 700, C.ink); text("now", x + 510, y + 44, 18, 500, C.muted, "right");
    text("Blocked on Machine 1", x + 98, y + 80, 22, 600, "#ffb4ad"); text("Rule shared with 3 machines · review?", x + 98, y + 112, 19, 500, "#aab4cc"); g.restore(); }

  // vignette
  const vg = g.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, H * 0.95); vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, `rgba(0,0,0,${0.5 + 0.25 * tight})`); g.fillStyle = vg; g.fillRect(0, 0, W, H);
  // headline scrim + headline
  const sc = g.createLinearGradient(0, H - 300, 0, H); sc.addColorStop(0, "rgba(5,8,15,0)"); sc.addColorStop(1, "rgba(5,8,15,0.85)"); g.fillStyle = sc; g.fillRect(0, H - 300, W, 300);
  headline(t);
  // clock (shots 1–4)
  const ck = fadeIO(t, 0.6, S(4) + 0.6, 0.6); if (ck > 0) { g.save(); g.globalAlpha = ck; text("3:07 AM", 150, 90, 22, 500, C.muted, "left", MONO, 1); g.restore(); }

  // title (shot 11): fade to white
  const wh = inOut(seg(t, S(10) - 0.5, S(10) + 0.5));
  if (wh > 0) { g.fillStyle = `rgba(255,255,255,${wh})`; g.fillRect(0, 0, W, H);
    const p1 = out(seg(t, S(10) + 0.15, S(10) + 0.9)), p2 = out(seg(t, S(10) + 0.7, S(10) + 1.4)), p3 = out(seg(t, S(10) + 1.3, S(10) + 2.0));
    g.save(); g.globalAlpha = p1; text("Wagent", W / 2, H / 2 - 70 + (1 - p1) * 20, 168, 700, "#0d0d0d", "center", SANS, -6); g.restore();
    g.save(); g.globalAlpha = p2; text("A warden for your AI agents.", W / 2, H / 2 + 55, 44, 500, "#55555c", "center", SANS, -0.8); g.restore();
    g.save(); g.globalAlpha = p3; flower(W / 2 - 64, H / 2 + 162, 34, "#2b2b31"); text("Built on Flower", W / 2 - 38, H / 2 + 163, 24, 600, "#2b2b31", "left");
    text("github.com/irangareddy/wagent", W / 2, H / 2 + 230, 22, 500, "#8a8a92", "center", MONO); g.restore(); }
  // fades
  const fin = 1 - seg(t, 0, 0.7); if (fin > 0) { g.fillStyle = `rgba(5,8,15,${fin})`; g.fillRect(0, 0, W, H); }
}

window.snap = (t, q) => { frame(t); return cv.toDataURL("image/jpeg", q || 0.92); };
// poster: one frame plus a play button and runtime, for the README
window.poster = (t, q) => {
  frame(t);
  g.fillStyle = "rgba(5,8,15,0.35)"; g.fillRect(0, 0, W, H);
  const x = W / 2, y = H / 2 - 40;
  g.save(); g.shadowColor = "rgba(0,0,0,0.5)"; g.shadowBlur = 50; g.fillStyle = "#ffffff"; g.beginPath(); g.arc(x, y, 92, 0, 7); g.fill(); g.restore();
  g.fillStyle = "#0b1224"; g.beginPath(); g.moveTo(x - 26, y - 40); g.lineTo(x + 46, y); g.lineTo(x - 26, y + 40); g.closePath(); g.fill();
  text("Watch the Wagent film", x, y + 150, 44, 700, "#ffffff", "center", SANS, -0.8);
  text("1 minute · with narration", x, y + 206, 26, 500, "rgba(255,255,255,0.75)", "center");
  return cv.toDataURL("image/jpeg", q || 0.9);
};
window.__ready__ = document.fonts.ready;
if (!window.__FILM__) document.fonts.ready.then(() => { const t0 = performance.now(); (function loop() { frame(((performance.now() - t0) / 1000) % FILM.end); requestAnimationFrame(loop); })(); });
