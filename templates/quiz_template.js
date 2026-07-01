/* =========================================================
   QUIZ GAME ENGINE — текстовая викторина
   Плейсхолдеры:
     {{GAME_TITLE}}      — название игры
     QUESTIONS_JSON      — JSON-массив вопросов:
                           [{"q":"текст","o":["A","B","C","D"],"a":0}, ...]
     {{SCORE_LABEL}}     — название очков ("очки", "баллы"...)
     {{BG_COLOR}}        — цвет фона
     {{PRIMARY_COLOR}}   — цвет HUD / прогресс-бара
     {{SECONDARY_COLOR}} — цвет кнопок ответа
     {{ACCENT_COLOR}}    — цвет правильного ответа / акцентов
     {{TEXT_COLOR}}      — цвет текста
   ========================================================= */
"use strict";

const CFG = {
  title:      "{{GAME_TITLE}}",
  scoreLabel: "{{SCORE_LABEL}}",
  questions:  {{QUESTIONS_JSON}},
  colors: {
    bg:        "{{BG_COLOR}}",
    primary:   "{{PRIMARY_COLOR}}",
    secondary: "{{SECONDARY_COLOR}}",
    accent:    "{{ACCENT_COLOR}}",
    text:      "{{TEXT_COLOR}}",
  },
  adEvery: 5,
};

const canvas = document.getElementById("canvas");
const ctx    = canvas.getContext("2d");

function resize() {
  canvas.width  = Math.min(window.innerWidth,  480);
  canvas.height = Math.min(window.innerHeight, 720);
}
window.addEventListener("resize", resize);
resize();

// ── Layout ─────────────────────────────────────────────────
const W       = () => canvas.width;
const H       = () => canvas.height;
const PAD     = () => Math.round(W() * 0.05);
const Q_FS    = () => Math.round(W() * 0.047);
const BTN_FS  = () => Math.round(W() * 0.042);
const HUD_FS  = () => Math.round(W() * 0.038);
const Q_LINE  = () => Math.round(Q_FS() * 1.25);
const BTN_H   = () => Math.round(H() * 0.10);
const BTN_GAP = () => Math.round(H() * 0.015);

// ── State ─────────────────────────────────────────────────
let state    = "idle";   // idle | question | feedback | done
let qIndex   = 0, score = 0;
let selected = -1, correct = -1;
let questionsSinceAd = 0;
let btnRects = [];

// ── Yandex SDK ─────────────────────────────────────────────
let ysdk = null;
async function initYandex() {
  try {
    ysdk = await YaGames.init();
    ysdk.features.LoadingAPI?.ready();
  } catch (e) {}
}

function showAd(cb = () => {}) {
  if (!ysdk) { cb(); return; }
  ysdk.adv.showFullscreenAdv({ callbacks: { onClose: cb, onError: cb } });
}

// ── Helpers ─────────────────────────────────────────────────
function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function wrapText(text, cx, startY, maxW, lineH) {
  const words = String(text).split(" ");
  let line = "", curY = startY;
  for (const word of words) {
    const test = line ? line + " " + word : word;
    if (ctx.measureText(test).width > maxW && line) {
      ctx.fillText(line, cx, curY);
      curY += lineH;
      line  = word;
    } else {
      line = test;
    }
  }
  if (line) { ctx.fillText(line, cx, curY); curY += lineH; }
  return curY;
}

function clampLine(text, maxW) {
  let t = String(text);
  while (ctx.measureText(t).width > maxW && t.length > 3) {
    t = t.slice(0, -4) + "…";
  }
  return t;
}

// ── Draw ─────────────────────────────────────────────────
function draw() {
  const w = W(), h = H(), pad = PAD();
  ctx.fillStyle = CFG.colors.bg;
  ctx.fillRect(0, 0, w, h);

  if (state === "idle" || state === "done") { drawOverlay(w, h); return; }

  const q = CFG.questions[qIndex];

  // Прогресс-бар
  ctx.fillStyle = CFG.colors.primary;
  ctx.fillRect(0, 0, w, 7);
  ctx.fillStyle = CFG.colors.accent;
  ctx.fillRect(0, 0, w * (qIndex / CFG.questions.length), 7);

  // HUD
  ctx.font         = `bold ${HUD_FS()}px sans-serif`;
  ctx.textBaseline = "top";
  ctx.fillStyle    = CFG.colors.text;
  ctx.textAlign    = "left";
  ctx.fillText(`${qIndex + 1} / ${CFG.questions.length}`, pad, 16);
  ctx.textAlign = "right";
  ctx.fillText(`${CFG.scoreLabel}: ${score}`, w - pad, 16);

  // Текст вопроса
  ctx.font         = `${Q_FS()}px sans-serif`;
  ctx.fillStyle    = CFG.colors.text;
  ctx.textAlign    = "center";
  ctx.textBaseline = "top";
  const afterQ = wrapText(q.q, w / 2, Math.round(h * 0.10), w - pad * 2, Q_LINE());

  // Кнопки ответов
  const startY = Math.max(afterQ + pad, Math.round(h * 0.42));
  btnRects = [];
  q.o.forEach((opt, i) => {
    const by = startY + i * (BTN_H() + BTN_GAP());
    const bw = w - pad * 2;
    btnRects.push({ x: pad, y: by, w: bw, h: BTN_H(), i });

    let bg = CFG.colors.secondary;
    if (state === "feedback") {
      if (i === correct)       bg = "#2ecc71";
      else if (i === selected) bg = "#e74c3c";
    }
    ctx.fillStyle = bg;
    roundRect(pad, by, bw, BTN_H(), 10);
    ctx.fill();

    ctx.font         = `${BTN_FS()}px sans-serif`;
    ctx.fillStyle    = CFG.colors.text;
    ctx.textAlign    = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(clampLine(opt, bw - 24), pad + bw / 2, by + BTN_H() / 2);
  });
}

function drawOverlay(w, h) {
  ctx.fillStyle = "rgba(0,0,0,0.62)";
  ctx.fillRect(0, 0, w, h);
  ctx.textAlign    = "center";
  ctx.textBaseline = "middle";

  if (state === "done") {
    ctx.font      = `bold ${Math.round(w * 0.065)}px sans-serif`;
    ctx.fillStyle = CFG.colors.accent;
    ctx.fillText("Викторина завершена!", w / 2, h * 0.37);
    ctx.font      = `${Math.round(w * 0.05)}px sans-serif`;
    ctx.fillStyle = CFG.colors.text;
    ctx.fillText(
      `${CFG.scoreLabel}: ${score} из ${CFG.questions.length * 10}`,
      w / 2, h * 0.47
    );
  } else {
    ctx.font      = `bold ${Math.round(w * 0.07)}px sans-serif`;
    ctx.fillStyle = CFG.colors.text;
    ctx.fillText(CFG.title, w / 2, h * 0.37);
  }
  ctx.font      = `bold ${Math.round(w * 0.055)}px sans-serif`;
  ctx.fillStyle = CFG.colors.accent;
  ctx.fillText(
    state === "done" ? "Нажми для рестарта" : "Нажми для начала",
    w / 2, h * 0.58
  );
}

// ── Logic ─────────────────────────────────────────────────
function startGame() {
  qIndex = 0; score = 0; questionsSinceAd = 0;
  selected = -1; correct = -1;
  state = "question";
}

function nextQuestion() {
  qIndex++;
  questionsSinceAd++;

  if (qIndex >= CFG.questions.length) {
    state = "done";
    showAd(() => {});
    return;
  }

  if (questionsSinceAd >= CFG.adEvery) {
    questionsSinceAd = 0;
    showAd(() => { state = "question"; });
  } else {
    state = "question";
  }
}

function handleAnswer(i) {
  if (state !== "question") return;
  const q = CFG.questions[qIndex];
  selected = i;
  correct  = q.a;
  if (i === correct) score += 10;
  state = "feedback";
  setTimeout(nextQuestion, 1200);
}

// ── Input ─────────────────────────────────────────────────
canvas.addEventListener("pointerdown", e => {
  e.preventDefault();
  if (state === "idle" || state === "done") { startGame(); return; }
  if (state !== "question") return;

  const r   = canvas.getBoundingClientRect();
  const scX = canvas.width  / r.width;
  const scY = canvas.height / r.height;
  const cx  = (e.clientX - r.left) * scX;
  const cy  = (e.clientY - r.top)  * scY;

  for (const btn of btnRects) {
    if (cx >= btn.x && cx <= btn.x + btn.w && cy >= btn.y && cy <= btn.y + btn.h) {
      handleAnswer(btn.i);
      return;
    }
  }
});

window.addEventListener("keydown", e => {
  if (state === "idle" || state === "done") { startGame(); return; }
  if (state !== "question") return;
  const map = { Digit1: 0, Digit2: 1, Digit3: 2, Digit4: 3,
                Numpad1: 0, Numpad2: 1, Numpad3: 2, Numpad4: 3 };
  if (e.code in map) handleAnswer(map[e.code]);
});

// ── Loop ──────────────────────────────────────────────────
function loop() { draw(); requestAnimationFrame(loop); }

window.addEventListener("DOMContentLoaded", async () => {
  document.title = CFG.title;
  await initYandex();
  loop();
});
