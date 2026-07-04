/* =========================================================
   FALLING OBJECTS GAME ENGINE — ловилка предметов
   Плейсхолдеры:
     {{GAME_TITLE}}        — название игры
     {{HERO_NAME}}         — имя персонажа-ловца
     {{PLAYER_EMOJI}}      — emoji корзины/ловца
     {{GOOD_OBJECT_EMOJI}} — emoji предмета, который надо поймать
     {{BAD_OBJECT_EMOJI}}  — emoji предмета, которого надо избежать
     {{SCORE_LABEL}}       — название очков
     {{LIVES_LABEL}}       — как называются жизни
     {{BG_COLOR}}          — цвет фона
     {{PRIMARY_COLOR}}     — цвет HUD / панелей
     {{SECONDARY_COLOR}}   — цвет дорожки
     {{ACCENT_COLOR}}      — цвет акцентов
     {{TEXT_COLOR}}        — цвет текста
   ========================================================= */
"use strict";

const CFG = {
  title:      "{{GAME_TITLE}}",
  heroName:   "{{HERO_NAME}}",
  player:     "{{PLAYER_EMOJI}}",
  good:       "{{GOOD_OBJECT_EMOJI}}",
  bad:        "{{BAD_OBJECT_EMOJI}}",
  scoreLabel: "{{SCORE_LABEL}}",
  livesLabel: "{{LIVES_LABEL}}",
  colors: {
    bg:        "{{BG_COLOR}}",
    primary:   "{{PRIMARY_COLOR}}",
    secondary: "{{SECONDARY_COLOR}}",
    accent:    "{{ACCENT_COLOR}}",
    text:      "{{TEXT_COLOR}}",
  },
  maxLives:       3,
  adEveryPoints:  50,
  spawnInterval:  70,   // фреймов между спавном
  speedBase:      3,
  speedGrowth:    0.001,
};

// ── Canvas ────────────────────────────────────────────────────────────────────
const canvas = document.getElementById("canvas");
const ctx    = canvas.getContext("2d");

function resize() {
  canvas.width  = Math.min(window.innerWidth,  480);
  canvas.height = Math.min(window.innerHeight, 720);
}
window.addEventListener("resize", () => { resize(); resetPlayerPos(); });
resize();

const OBJ_SIZE   = () => Math.round(canvas.width * 0.09);
const PLAYER_SIZE = () => Math.round(canvas.width * 0.11);
const HUD_FONT   = () => `bold ${Math.round(canvas.width * 0.05)}px sans-serif`;

// ── Состояние ─────────────────────────────────────────────────────────────────
let state = "idle";
let score = 0, bestScore = 0, lives = CFG.maxLives;
let frame = 0, pointsSinceAd = 0;
let fallingObjects = [];
let particles      = [];

const player = { x: 0, y: 0, targetX: 0, size: 0 };

function resetPlayerPos() {
  player.x       = canvas.width / 2;
  player.targetX = canvas.width / 2;
  player.y       = canvas.height * 0.88;
  player.size    = PLAYER_SIZE();
}

function resetGame() {
  score          = 0;
  lives          = CFG.maxLives;
  frame          = 0;
  pointsSinceAd  = 0;
  fallingObjects = [];
  particles      = [];
  resetPlayerPos();
  state = "running";
}

// ── Яндекс SDK ────────────────────────────────────────────────────────────────
let ysdk = null;

async function initYandex() {
  try {
    ysdk = await YaGames.init();
    ysdk.features.LoadingAPI?.ready();
  } catch (e) { /* offline */ }
}

function showAd(cb = () => {}) {
  if (!ysdk) { cb(); return; }
  ysdk.adv.showFullscreenAdv({ callbacks: {
    onClose: () => cb(),
    onError: () => cb(),
  }});
}

// ── Спавн и физика ────────────────────────────────────────────────────────────
function spawnObject() {
  const isGood  = Math.random() > 0.35;
  const x       = OBJ_SIZE() + Math.random() * (canvas.width - OBJ_SIZE() * 2);
  const speed   = CFG.speedBase + frame * CFG.speedGrowth + Math.random() * 2;
  fallingObjects.push({ x, y: -OBJ_SIZE(), isGood, speed, size: OBJ_SIZE() });
}

function spawnParticle(x, y, good) {
  for (let i = 0; i < 6; i++) {
    particles.push({
      x, y,
      vx: (Math.random() - 0.5) * 6,
      vy: (Math.random() - 0.5) * 6 - 2,
      life: 1,
      color: good ? CFG.colors.accent : "#e94560",
      emoji: good ? CFG.good : CFG.bad,
    });
  }
}

function update() {
  if (state !== "running") return;
  frame++;

  // плавное движение игрока
  player.x += (player.targetX - player.x) * 0.2;

  // спавн
  if (frame % (CFG.spawnInterval - Math.floor(frame / 300)) === 0) {
    spawnObject();
  }

  // обновление объектов
  for (const o of fallingObjects) o.y += o.speed;

  // коллизии
  const pHalf = player.size * 0.45;
  const caught = [], missed = [];
  for (const o of fallingObjects) {
    const oHalf = o.size * 0.45;
    const hit =
      Math.abs(o.x - player.x) < pHalf + oHalf &&
      Math.abs(o.y - player.y) < pHalf * 0.5;

    if (hit) {
      caught.push(o);
      if (o.isGood) {
        score       += 5;
        pointsSinceAd += 5;
        spawnParticle(o.x, o.y, true);
      } else {
        lives--;
        spawnParticle(o.x, o.y, false);
      }
    } else if (o.y > canvas.height + 20) {
      if (o.isGood) { lives--; spawnParticle(o.x, canvas.height - 20, false); }
      missed.push(o);
    }
  }

  const remove = new Set([...caught, ...missed]);
  fallingObjects = fallingObjects.filter(o => !remove.has(o));

  // частицы
  particles.forEach(p => { p.x += p.vx; p.y += p.vy; p.life -= 0.05; });
  particles = particles.filter(p => p.life > 0);

  // реклама
  if (pointsSinceAd >= CFG.adEveryPoints) {
    pointsSinceAd = 0;
    showAd();
  }

  // смерть
  if (lives <= 0) {
    if (score > bestScore) bestScore = score;
    state = "dead";
    showAd();
  }
}

// ── Отрисовка ─────────────────────────────────────────────────────────────────
function draw() {
  const W = canvas.width, H = canvas.height;

  ctx.fillStyle = CFG.colors.bg;
  ctx.fillRect(0, 0, W, H);

  // дорожки (декор)
  ctx.fillStyle = CFG.colors.secondary;
  for (let i = 0; i < 4; i++) {
    ctx.fillRect(W / 4 * i, 0, 2, H);
  }

  // объекты
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const o of fallingObjects) {
    ctx.font = `${o.size}px sans-serif`;
    ctx.fillText(o.isGood ? CFG.good : CFG.bad, o.x, o.y);
  }

  // частицы
  for (const p of particles) {
    ctx.globalAlpha = p.life;
    ctx.font = `${OBJ_SIZE() * 0.6}px sans-serif`;
    ctx.fillText(p.emoji, p.x, p.y);
  }
  ctx.globalAlpha = 1;

  // игрок
  ctx.font = `${player.size}px sans-serif`;
  ctx.fillText(CFG.player, player.x, player.y);

  // HUD
  ctx.font = HUD_FONT();
  ctx.fillStyle = CFG.colors.text;
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText(`${CFG.scoreLabel}: ${score}`, 12, 12);

  const hearts = "❤️".repeat(lives) + "🖤".repeat(Math.max(0, CFG.maxLives - lives));
  ctx.textAlign = "right";
  ctx.fillText(hearts, W - 12, 12);

  ctx.textAlign = "right";
  ctx.fillText(`Рекорд: ${bestScore}`, W - 12, 12 + Math.round(W * 0.055));

  // оверлей
  if (state !== "running") {
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(0, 0, W, H);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    if (state === "dead") {
      ctx.font = `bold ${Math.round(W * 0.07)}px sans-serif`;
      ctx.fillStyle = CFG.colors.accent;
      ctx.fillText("Игра окончена!", W / 2, H * 0.36);
      ctx.font = `${Math.round(W * 0.05)}px sans-serif`;
      ctx.fillStyle = CFG.colors.text;
      ctx.fillText(`${CFG.scoreLabel}: ${score}  Рекорд: ${bestScore}`, W / 2, H * 0.46);
    } else {
      ctx.font = `bold ${Math.round(W * 0.09)}px sans-serif`;
      ctx.fillStyle = CFG.colors.accent;
      ctx.fillText(CFG.player, W / 2, H * 0.35);
      ctx.font = `bold ${Math.round(W * 0.065)}px sans-serif`;
      ctx.fillText(CFG.heroName, W / 2, H * 0.47);
    }

    ctx.font = `bold ${Math.round(W * 0.055)}px sans-serif`;
    ctx.fillStyle = CFG.colors.accent;
    ctx.fillText(state === "dead" ? "Нажми для рестарта" : "Нажми для начала", W / 2, H * 0.62);
  }
}

// ── Петля ─────────────────────────────────────────────────────────────────────
function loop() { update(); draw(); requestAnimationFrame(loop); }

// ── Ввод ─────────────────────────────────────────────────────────────────────
function handlePointer(x) {
  if (state !== "running") { resetGame(); return; }
  player.targetX = Math.max(player.size / 2, Math.min(canvas.width - player.size / 2, x));
}

canvas.addEventListener("pointermove", e => {
  if (state !== "running") return;
  const r = canvas.getBoundingClientRect();
  const scaleX = canvas.width / r.width;
  handlePointer((e.clientX - r.left) * scaleX);
});
canvas.addEventListener("pointerdown", e => {
  const r = canvas.getBoundingClientRect();
  const scaleX = canvas.width / r.width;
  handlePointer((e.clientX - r.left) * scaleX);
});
window.addEventListener("keydown", e => {
  if (state !== "running") { resetGame(); return; }
  if (e.code === "ArrowLeft")  player.targetX = Math.max(player.size / 2, player.targetX - 40);
  if (e.code === "ArrowRight") player.targetX = Math.min(canvas.width - player.size / 2, player.targetX + 40);
});

// ── Старт ─────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
  resetPlayerPos();
  document.title = CFG.title;
  await initYandex();
  loop();
});
