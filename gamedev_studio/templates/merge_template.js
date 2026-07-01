/* =========================================================
   MERGE GAME ENGINE — игра на слияние (стиль 2048)
   Плейсхолдеры:
     {{GAME_TITLE}}      — название игры
     STAGES_JSON         — JSON-массив из 11 стадий:
                           [{"emoji":"🌱","name":"Росток"}, ...]
     {{SCORE_LABEL}}     — название очков
     {{BG_COLOR}}        — цвет фона страницы
     {{PRIMARY_COLOR}}   — цвет HUD / шапки
     {{SECONDARY_COLOR}} — цвет фона сетки
     {{ACCENT_COLOR}}    — цвет финальной плитки / акцентов
     {{TEXT_COLOR}}      — цвет текста
   ========================================================= */
"use strict";

const CFG = {
  title:         "{{GAME_TITLE}}",
  scoreLabel:    "{{SCORE_LABEL}}",
  stages:        {{STAGES_JSON}},
  colors: {
    bg:        "{{BG_COLOR}}",
    primary:   "{{PRIMARY_COLOR}}",
    secondary: "{{SECONDARY_COLOR}}",
    accent:    "{{ACCENT_COLOR}}",
    text:      "{{TEXT_COLOR}}",
  },
  adEveryMerges: 20,
};

const N      = 4;
const canvas = document.getElementById("canvas");
const ctx    = canvas.getContext("2d");

function resize() {
  canvas.width  = Math.min(window.innerWidth,  480);
  canvas.height = Math.min(window.innerHeight, 720);
}
window.addEventListener("resize", resize);
resize();

// ── Layout ─────────────────────────────────────────────────
const GP      = () => Math.round(canvas.width * 0.032);
const GAP     = () => Math.round(canvas.width * 0.022);
const GW      = () => canvas.width - GP() * 2;
const CELL    = () => Math.floor((GW() - GAP() * (N - 1)) / N);
const HUD_H   = () => Math.round(canvas.height * 0.16);
const GRID_X  = () => GP();
const GRID_Y  = () => HUD_H() + GP();
const cellX   = c => GRID_X() + c * (CELL() + GAP());
const cellY   = r => GRID_Y() + r * (CELL() + GAP());

// ── Tile palette ───────────────────────────────────────────
const TILE_BG = [
  "#b8b3a8","#ede8d5","#ead4b3","#f0a86e",
  "#f07d4b","#ed5e3a","#ed3316","#f2c940",
  "#f0c030","#f0b820","#ffaa00",
];

function tileColor(level) {
  if (level === 0) return CFG.colors.secondary;
  if (level === CFG.stages.length) return CFG.colors.accent;
  return TILE_BG[Math.min(level - 1, TILE_BG.length - 1)];
}

// ── State ─────────────────────────────────────────────────
let grid = [], score = 0, bestScore = 0, mergesSinceAd = 0;
let state = "idle";  // idle | running | won | dead

function emptyGrid() {
  return Array.from({ length: N }, () => Array(N).fill(0));
}

function emptyCells(g) {
  const cells = [];
  for (let r = 0; r < N; r++)
    for (let c = 0; c < N; c++)
      if (g[r][c] === 0) cells.push([r, c]);
  return cells;
}

function spawnTile(g) {
  const cells = emptyCells(g);
  if (!cells.length) return;
  const [r, c] = cells[Math.floor(Math.random() * cells.length)];
  g[r][c] = 1;
}

function resetGame() {
  grid = emptyGrid();
  score = 0; mergesSinceAd = 0;
  spawnTile(grid); spawnTile(grid);
  state = "running";
}

// ── 2048 Mechanics ─────────────────────────────────────────
function slideRow(row) {
  let r = row.filter(v => v !== 0);
  for (let i = 0; i < r.length - 1; i++) {
    if (r[i] === r[i + 1] && r[i] < CFG.stages.length) {
      r[i]++;
      r.splice(i + 1, 1);
      score += r[i] * 10;
      mergesSinceAd++;
      if (r[i] === CFG.stages.length) state = "won";
    }
  }
  while (r.length < N) r.push(0);
  return r;
}

function rotateCW(g) {
  return Array.from({ length: N }, (_, c) =>
    Array.from({ length: N }, (_, r) => g[N - 1 - r][c])
  );
}

function hasMovesLeft(g) {
  for (let r = 0; r < N; r++)
    for (let c = 0; c < N; c++) {
      if (g[r][c] === 0) return true;
      if (c < N - 1 && g[r][c] === g[r][c + 1]) return true;
      if (r < N - 1 && g[r][c] === g[r + 1][c]) return true;
    }
  return false;
}

function applyMove(dir) {
  // dir: 0=left 1=up 2=right 3=down  →  rotate so we always slide left
  if (state !== "running") return;
  let g = grid.map(r => [...r]);
  for (let i = 0; i < dir; i++) g = rotateCW(g);
  const snap = g.map(r => [...r]);
  g = g.map(row => slideRow(row));
  const changed = g.some((row, r) => row.some((v, c) => v !== snap[r][c]));
  for (let i = 0; i < (4 - dir) % 4; i++) g = rotateCW(g);

  if (!changed) return;
  grid = g;

  if (state === "won") {
    if (score > bestScore) bestScore = score;
    showAd(); return;
  }

  spawnTile(grid);

  if (!hasMovesLeft(grid)) {
    if (score > bestScore) bestScore = score;
    state = "dead";
    showAd(); return;
  }

  if (mergesSinceAd >= CFG.adEveryMerges) {
    mergesSinceAd = 0;
    showAd();
  }
}

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

// ── Draw ─────────────────────────────────────────────────
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

function draw() {
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = CFG.colors.bg;
  ctx.fillRect(0, 0, w, h);

  // HUD
  ctx.textBaseline = "middle";
  const hudMid = HUD_H() / 2;

  ctx.font      = `bold ${Math.round(w * 0.055)}px sans-serif`;
  ctx.fillStyle = CFG.colors.text;
  ctx.textAlign = "left";
  ctx.fillText(CFG.title, GP(), hudMid * 0.7);

  ctx.font      = `bold ${Math.round(w * 0.048)}px sans-serif`;
  ctx.textAlign = "right";
  ctx.fillText(`${CFG.scoreLabel}: ${score}`, w - GP(), hudMid * 0.7);

  ctx.font      = `${Math.round(w * 0.035)}px sans-serif`;
  ctx.fillStyle = CFG.colors.accent;
  ctx.textAlign = "right";
  ctx.fillText(`Рекорд: ${bestScore}`, w - GP(), hudMid * 1.5);

  // Фон сетки
  const gridPad  = GAP() / 2;
  const totalGH  = N * CELL() + (N - 1) * GAP();
  ctx.fillStyle = CFG.colors.secondary;
  roundRect(GRID_X() - gridPad, GRID_Y() - gridPad, GW() + GAP(), totalGH + GAP(), 8);
  ctx.fill();

  // Ячейки
  for (let r = 0; r < N; r++) {
    for (let c = 0; c < N; c++) {
      const v  = grid[r][c];
      const x  = cellX(c), y = cellY(r), cs = CELL();

      ctx.fillStyle = tileColor(v);
      roundRect(x, y, cs, cs, 6);
      ctx.fill();

      if (v > 0 && v <= CFG.stages.length) {
        const st       = CFG.stages[v - 1];
        const emojiSz  = Math.round(cs * 0.44);
        const nameSz   = Math.round(cs * 0.145);

        ctx.textAlign    = "center";
        ctx.textBaseline = "middle";
        ctx.font      = `${emojiSz}px sans-serif`;
        ctx.fillText(st.emoji, x + cs / 2, y + cs * 0.42);

        ctx.font      = `bold ${nameSz}px sans-serif`;
        ctx.fillStyle = v >= 8 ? "#fff8" : "#4448";
        ctx.fillText(st.name, x + cs / 2, y + cs * 0.80);
      }
    }
  }

  // Оверлей
  if (state !== "running") {
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(0, 0, w, h);
    ctx.textAlign = "center"; ctx.textBaseline = "middle";

    if (state === "won") {
      ctx.font      = `bold ${Math.round(w * 0.08)}px sans-serif`;
      ctx.fillStyle = CFG.colors.accent;
      ctx.fillText("🎉 Победа!", w / 2, h * 0.38);
    } else if (state === "dead") {
      ctx.font      = `bold ${Math.round(w * 0.07)}px sans-serif`;
      ctx.fillStyle = "#e74c3c";
      ctx.fillText("Игра окончена!", w / 2, h * 0.38);
      ctx.font      = `${Math.round(w * 0.05)}px sans-serif`;
      ctx.fillStyle = CFG.colors.text;
      ctx.fillText(`${CFG.scoreLabel}: ${score}`, w / 2, h * 0.47);
    } else {
      ctx.font      = `bold ${Math.round(w * 0.065)}px sans-serif`;
      ctx.fillStyle = CFG.colors.text;
      ctx.fillText(CFG.title, w / 2, h * 0.38);
    }

    ctx.font      = `bold ${Math.round(w * 0.055)}px sans-serif`;
    ctx.fillStyle = CFG.colors.accent;
    ctx.fillText(
      state === "idle" ? "Нажми / свайп для начала" : "Нажми для рестарта",
      w / 2, h * 0.56
    );
  }
}

// ── Input ─────────────────────────────────────────────────
let touchStart = null;

canvas.addEventListener("pointerdown", e => {
  e.preventDefault();
  if (state !== "running") { resetGame(); return; }
  const r = canvas.getBoundingClientRect();
  touchStart = {
    x: (e.clientX - r.left) * (canvas.width  / r.width),
    y: (e.clientY - r.top)  * (canvas.height / r.height),
  };
});

canvas.addEventListener("pointerup", e => {
  if (!touchStart || state !== "running") { touchStart = null; return; }
  const r  = canvas.getBoundingClientRect();
  const ex = (e.clientX - r.left) * (canvas.width  / r.width);
  const ey = (e.clientY - r.top)  * (canvas.height / r.height);
  const dx = ex - touchStart.x, dy = ey - touchStart.y;
  touchStart = null;
  if (Math.abs(dx) < 12 && Math.abs(dy) < 12) return;
  applyMove(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 2 : 0) : (dy > 0 ? 3 : 1));
});

window.addEventListener("keydown", e => {
  if (state !== "running") { resetGame(); return; }
  const map = { ArrowLeft: 0, ArrowUp: 1, ArrowRight: 2, ArrowDown: 3 };
  if (e.code in map) { e.preventDefault(); applyMove(map[e.code]); }
});

// ── Loop ──────────────────────────────────────────────────
function loop() { draw(); requestAnimationFrame(loop); }

window.addEventListener("DOMContentLoaded", async () => {
  document.title = CFG.title;
  await initYandex();
  loop();
});
