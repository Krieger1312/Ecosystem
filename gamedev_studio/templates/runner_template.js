/* =========================================================
   RUNNER GAME ENGINE — шаблон для Яндекс.Игры
   Плейсхолдеры:
     {{GAME_TITLE}}       — название игры
     {{PLAYER_EMOJI}}     — emoji игрока
     {{OBSTACLE_EMOJI}}   — emoji препятствия
     {{COLLECTIBLE_EMOJI}}— emoji подбираемого предмета
     {{SCORE_LABEL}}      — название очков ("м", "монеты", "метры"...)
     {{BG_COLOR}}         — цвет неба/фона
     {{GROUND_COLOR}}     — цвет земли
     {{PRIMARY_COLOR}}    — цвет HUD и панелей
     {{ACCENT_COLOR}}     — цвет акцентов / сообщений
     {{TEXT_COLOR}}       — цвет текста
   ========================================================= */
"use strict";

const CFG = {
  title:       "{{GAME_TITLE}}",
  player:      "{{PLAYER_EMOJI}}",
  obstacle:    "{{OBSTACLE_EMOJI}}",
  collectible: "{{COLLECTIBLE_EMOJI}}",
  scoreLabel:  "{{SCORE_LABEL}}",
  colors: {
    bg:      "{{BG_COLOR}}",
    ground:  "{{GROUND_COLOR}}",
    primary: "{{PRIMARY_COLOR}}",
    accent:  "{{ACCENT_COLOR}}",
    text:    "{{TEXT_COLOR}}",
  },
  adEveryMeters: 300,
};

// ── Canvas ────────────────────────────────────────────────────────────────────
const canvas = document.getElementById("canvas");
const ctx    = canvas.getContext("2d");

function resize() {
  canvas.width  = Math.min(window.innerWidth,  480);
  canvas.height = Math.min(window.innerHeight, 720);
}
window.addEventListener("resize", resize);
resize();

const GROUND_Y   = () => canvas.height * 0.78;
const FONT_SIZE  = () => Math.round(canvas.width * 0.09);
const HUD_FONT   = () => `bold ${Math.round(canvas.width * 0.05)}px sans-serif`;

// ── Состояние ─────────────────────────────────────────────────────────────────
let state = "idle";   // idle | running | dead
let score = 0, bestScore = 0;
let speed = 5, frame = 0, metersSinceAd = 0;

const player = {
  x: 80, y: 0, vy: 0,
  jumps: 0, maxJumps: 2,
  size: 0,
};

let obstacles   = [];
let collectibles = [];

function reset() {
  player.y      = GROUND_Y();
  player.vy     = 0;
  player.jumps  = 0;
  player.size   = FONT_SIZE();
  obstacles     = [];
  collectibles  = [];
  score         = 0;
  speed         = canvas.width * 0.011;
  frame         = 0;
  metersSinceAd = 0;
  state         = "running";
}

// ── Физика ────────────────────────────────────────────────────────────────────
const GRAVITY  = () => canvas.height * 0.0018;
const JUMP_V   = () => -canvas.height * 0.030;

function jump() {
  if (state === "idle") { reset(); return; }
  if (state === "dead") { reset(); return; }
  if (player.jumps < player.maxJumps) {
    player.vy = JUMP_V();
    player.jumps++;
  }
}

function spawnObstacle() {
  const h = FONT_SIZE() * (0.9 + Math.random() * 0.6);
  obstacles.push({ x: canvas.width + 20, y: GROUND_Y(), size: h });
}

function spawnCollectible() {
  const y = GROUND_Y() - FONT_SIZE() * (1 + Math.random() * 2);
  collectibles.push({ x: canvas.width + 20, y, size: FONT_SIZE() * 0.8, alive: true });
}

function rectsOverlap(ax, ay, as_, bx, by, bs) {
  const pad = 0.55;
  return Math.abs(ax - bx) < (as_ + bs) * pad &&
         Math.abs(ay - by) < (as_ + bs) * pad;
}

// ── Яндекс SDK ────────────────────────────────────────────────────────────────
let ysdk = null;

async function initYandex() {
  try {
    ysdk = await YaGames.init();
    ysdk.features.LoadingAPI?.ready();
    const lb = await ysdk.getLeaderboards();
    window._lb = lb;
  } catch (e) { /* offline */ }
}

function showAd(cb = () => {}) {
  if (!ysdk) { cb(); return; }
  ysdk.adv.showFullscreenAdv({ callbacks: {
    onClose:  () => cb(),
    onError:  () => cb(),
  }});
}

function submitScore(s) {
  try { window._lb?.setLeaderboardScore("runnerLeaderboard", s); } catch (_) {}
}

// ── Обновление ────────────────────────────────────────────────────────────────
let lastObstacle = 0, lastCollectible = 0;

function update() {
  if (state !== "running") return;
  frame++;

  // ускорение
  speed = canvas.width * 0.011 + frame * 0.003;

  // игрок
  player.vy += GRAVITY();
  player.y  += player.vy;
  if (player.y >= GROUND_Y()) {
    player.y    = GROUND_Y();
    player.vy   = 0;
    player.jumps = 0;
  }

  // спавн препятствий (каждые ~90–140 фреймов)
  if (frame - lastObstacle > 90 + Math.random() * 50) {
    spawnObstacle();
    lastObstacle = frame;
  }
  // спавн предметов
  if (frame - lastCollectible > 70 + Math.random() * 60) {
    spawnCollectible();
    lastCollectible = frame;
  }

  // сдвиг
  obstacles    = obstacles.filter(o => { o.x -= speed; return o.x > -50; });
  collectibles = collectibles.filter(c => { c.x -= speed; return c.x > -50; });

  // коллизия
  for (const o of obstacles) {
    if (rectsOverlap(player.x, player.y, player.size, o.x, o.y, o.size)) {
      state = "dead";
      if (score > bestScore) bestScore = score;
      submitScore(score);
      showAd();
      return;
    }
  }
  for (const c of collectibles) {
    if (c.alive && rectsOverlap(player.x, player.y, player.size, c.x, c.y, c.size)) {
      c.alive = false;
      score  += 10;
    }
  }

  score++;
  metersSinceAd++;
  if (metersSinceAd >= CFG.adEveryMeters) {
    metersSinceAd = 0;
    showAd();
  }
}

// ── Отрисовка ─────────────────────────────────────────────────────────────────
function draw() {
  const W = canvas.width, H = canvas.height;
  const gY = GROUND_Y();
  const fs = FONT_SIZE();

  // фон
  ctx.fillStyle = CFG.colors.bg;
  ctx.fillRect(0, 0, W, H);

  // земля
  ctx.fillStyle = CFG.colors.ground;
  ctx.fillRect(0, gY + fs * 0.55, W, H - gY - fs * 0.55);

  // препятствия
  ctx.font = `${fs}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "bottom";
  for (const o of obstacles) ctx.fillText(CFG.obstacle, o.x, o.y + fs * 0.6);

  // предметы
  ctx.font = `${fs * 0.75}px sans-serif`;
  for (const c of collectibles) if (c.alive) ctx.fillText(CFG.collectible, c.x, c.y);

  // игрок
  ctx.font = `${fs}px sans-serif`;
  ctx.fillText(CFG.player, player.x, player.y + fs * 0.55);

  // HUD
  ctx.font = HUD_FONT();
  ctx.fillStyle = CFG.colors.text;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText(`${CFG.scoreLabel}: ${score}`, 12, 12);
  ctx.textAlign = "right";
  ctx.fillText(`Рекорд: ${bestScore}`, W - 12, 12);

  // экран смерти / idle
  if (state !== "running") {
    ctx.fillStyle = "rgba(0,0,0,0.5)";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = CFG.colors.accent;
    ctx.textAlign = "center";
    ctx.font = `bold ${Math.round(W * 0.07)}px sans-serif`;
    ctx.textBaseline = "middle";
    if (state === "dead") {
      ctx.fillText("Игра окончена!", W / 2, H * 0.38);
      ctx.font = `${Math.round(W * 0.05)}px sans-serif`;
      ctx.fillStyle = CFG.colors.text;
      ctx.fillText(`${CFG.scoreLabel}: ${score}`, W / 2, H * 0.48);
    }
    ctx.font = `bold ${Math.round(W * 0.06)}px sans-serif`;
    ctx.fillStyle = CFG.colors.accent;
    ctx.fillText("Нажми / коснись для старта", W / 2, H * 0.60);
  }
}

// ── Петля ─────────────────────────────────────────────────────────────────────
function loop() {
  update();
  draw();
  requestAnimationFrame(loop);
}

// ── Ввод ─────────────────────────────────────────────────────────────────────
window.addEventListener("keydown", e => {
  if (e.code === "Space" || e.code === "ArrowUp") { e.preventDefault(); jump(); }
});
canvas.addEventListener("pointerdown", e => { e.preventDefault(); jump(); });

// ── Старт ─────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
  player.y    = GROUND_Y();
  player.size = FONT_SIZE();
  document.title = CFG.title;
  await initYandex();
  loop();
});
