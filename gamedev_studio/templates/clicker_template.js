/* =========================================================
   CLICKER GAME ENGINE — шаблон для Яндекс.Игры
   Плейсхолдеры заменяются оркестратором перед сборкой.

   Строковые плейсхолдеры:
     {{GAME_TITLE}}       — заголовок игры
     {{HERO_NAME}}        — имя главного персонажа/объекта
     {{CLICK_EMOJI}}      — emoji кликабельного объекта
     {{CURRENCY_NAME}}    — название игровой валюты (монеты, очки...)
     {{BG_COLOR}}         — цвет фона (#rrggbb)
     {{PRIMARY_COLOR}}    — основной цвет интерфейса
     {{SECONDARY_COLOR}}  — дополнительный цвет панелей
     {{ACCENT_COLOR}}     — цвет кнопок / выделений
     {{TEXT_COLOR}}       — цвет текста
     {{UPGRADE_1_NAME}}   — название апгрейда 1
     {{UPGRADE_1_DESC}}   — описание апгрейда 1 (напр. "+1/сек")
     {{UPGRADE_1_EMOJI}}  — emoji апгрейда 1
     {{UPGRADE_2_NAME}}   — название апгрейда 2
     {{UPGRADE_2_DESC}}   — описание апгрейда 2
     {{UPGRADE_2_EMOJI}}  — emoji апгрейда 2
     {{UPGRADE_3_NAME}}   — название апгрейда 3
     {{UPGRADE_3_DESC}}   — описание апгрейда 3
     {{UPGRADE_3_EMOJI}}  — emoji апгрейда 3
   ========================================================= */

"use strict";

// ── Конфигурация (заполняется оркестратором) ─────────────────────────────────
const CONFIG = {
  gameName:     "{{GAME_TITLE}}",
  heroName:     "{{HERO_NAME}}",
  clickEmoji:   "{{CLICK_EMOJI}}",
  currency:     "{{CURRENCY_NAME}}",
  colors: {
    bg:          "{{BG_COLOR}}",
    primary:     "{{PRIMARY_COLOR}}",
    secondary:   "{{SECONDARY_COLOR}}",
    accent:      "{{ACCENT_COLOR}}",
    text:        "{{TEXT_COLOR}}",
  },
  upgrades: [
    {
      name:    "{{UPGRADE_1_NAME}}",
      desc:    "{{UPGRADE_1_DESC}}",
      emoji:   "{{UPGRADE_1_EMOJI}}",
      base:    15,
      mult:    1.4,
      perSec:  1,
    },
    {
      name:    "{{UPGRADE_2_NAME}}",
      desc:    "{{UPGRADE_2_DESC}}",
      emoji:   "{{UPGRADE_2_EMOJI}}",
      base:    150,
      mult:    1.4,
      perSec:  8,
    },
    {
      name:    "{{UPGRADE_3_NAME}}",
      desc:    "{{UPGRADE_3_DESC}}",
      emoji:   "{{UPGRADE_3_EMOJI}}",
      base:    2000,
      mult:    1.4,
      perSec:  50,
    },
  ],
  // сколько кликов между показами рекламы
  adEveryClicks: 50,
};

// ── Состояние игры ────────────────────────────────────────────────────────────
const STATE = {
  score:         0,
  totalClicks:   0,
  clickPower:    1,
  upgrades:      [0, 0, 0],   // кол-во купленных апгрейдов каждого типа
  perSecond:     0,
};

// ── Яндекс SDK ────────────────────────────────────────────────────────────────
let ysdk    = null;
let yPlayer = null;

async function initYandex() {
  try {
    ysdk    = await YaGames.init();
    yPlayer = await ysdk.getPlayer({ scopes: false });
    ysdk.features.LoadingAPI?.ready();
    await loadProgress();
    console.log("[YaSDK] инициализирован");
  } catch (e) {
    console.warn("[YaSDK] недоступен, работаем в автономном режиме:", e);
    loadProgressLocal();
  }
}

function showAd(type = "interstitial", onClose = () => {}) {
  if (!ysdk) { onClose(); return; }
  if (type === "rewarded") {
    ysdk.adv.showRewardedVideo({
      callbacks: {
        onOpen:   () => pauseGame(),
        onRewarded: () => { STATE.score += STATE.clickPower * 100; updateUI(); },
        onClose:  () => { resumeGame(); onClose(); },
        onError:  () => { resumeGame(); onClose(); },
      },
    });
  } else {
    ysdk.adv.showInterstitialAdv({
      callbacks: {
        onOpen:   () => pauseGame(),
        onClose:  () => { resumeGame(); onClose(); },
        onError:  () => { resumeGame(); onClose(); },
      },
    });
  }
}

// ── Сохранение / загрузка ─────────────────────────────────────────────────────
function serializeState() {
  return {
    score:       STATE.score,
    totalClicks: STATE.totalClicks,
    upgrades:    STATE.upgrades,
  };
}

async function saveProgress() {
  const data = serializeState();
  localStorage.setItem("clicker_save", JSON.stringify(data));
  if (yPlayer) {
    try { await yPlayer.setData(data, true); }
    catch (e) { /* молча пропускаем — localStorage уже сохранён */ }
  }
}

async function loadProgress() {
  let data = null;
  if (yPlayer) {
    try { data = await yPlayer.getData(); }
    catch (e) { /* fallback на localStorage */ }
  }
  if (!data || !Object.keys(data).length) loadProgressLocal();
  else applyLoadedData(data);
}

function loadProgressLocal() {
  try {
    const raw = localStorage.getItem("clicker_save");
    if (raw) applyLoadedData(JSON.parse(raw));
  } catch (e) { /* первый запуск */ }
}

function applyLoadedData(data) {
  STATE.score       = data.score       ?? 0;
  STATE.totalClicks = data.totalClicks ?? 0;
  STATE.upgrades    = data.upgrades    ?? [0, 0, 0];
  recalcPassive();
  updateUI();
}

// ── Физика кликов ─────────────────────────────────────────────────────────────
let gamePaused = false;
let passiveTimer = null;
let saveTimer   = null;
let clicksSinceAd = 0;

function onClick(event) {
  if (gamePaused) return;

  STATE.score       += STATE.clickPower;
  STATE.totalClicks += 1;
  clicksSinceAd     += 1;

  animateClick(event);
  spawnFloatingText(event, `+${STATE.clickPower}`);
  updateUI();

  if (clicksSinceAd >= CONFIG.adEveryClicks) {
    clicksSinceAd = 0;
    showAd("interstitial");
  }
}

function animateClick(event) {
  const hero = document.getElementById("hero");
  hero.classList.remove("bounce");
  // принудительный reflow чтобы анимация сработала повторно
  void hero.offsetWidth;
  hero.classList.add("bounce");
}

function spawnFloatingText(event, text) {
  const el   = document.createElement("div");
  el.className = "float-text";
  el.textContent = text;

  const rect = document.getElementById("hero").getBoundingClientRect();
  const x = rect.left + rect.width  / 2 + (Math.random() - 0.5) * 60;
  const y = rect.top  + rect.height / 2 + (Math.random() - 0.5) * 40;

  el.style.left = x + "px";
  el.style.top  = y + "px";
  el.style.color = CONFIG.colors.accent;
  document.body.appendChild(el);

  // удаляем после анимации
  el.addEventListener("animationend", () => el.remove());
}

// ── Пассивный доход ───────────────────────────────────────────────────────────
function recalcPassive() {
  STATE.perSecond = STATE.upgrades.reduce(
    (sum, count, i) => sum + count * CONFIG.upgrades[i].perSec, 0
  );
  // мощность клика растёт с суммарным количеством апгрейдов
  STATE.clickPower = 1 + Math.floor(STATE.upgrades.reduce((a, b) => a + b, 0) / 3);
}

function startPassiveIncome() {
  passiveTimer = setInterval(() => {
    if (gamePaused) return;
    STATE.score += STATE.perSecond;
    updateUI();
  }, 1000);

  saveTimer = setInterval(() => saveProgress(), 15_000);
}

// ── Магазин апгрейдов ─────────────────────────────────────────────────────────
function upgradeCost(index) {
  const u = CONFIG.upgrades[index];
  return Math.floor(u.base * Math.pow(u.mult, STATE.upgrades[index]));
}

function buyUpgrade(index) {
  const cost = upgradeCost(index);
  if (STATE.score < cost) return;
  STATE.score        -= cost;
  STATE.upgrades[index] += 1;
  recalcPassive();
  updateUI();
  renderShop();
}

// ── UI ────────────────────────────────────────────────────────────────────────
function fmt(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return Math.floor(n).toString();
}

function updateUI() {
  document.getElementById("score").textContent =
    `${fmt(STATE.score)} ${CONFIG.currency}`;
  document.getElementById("per-sec").textContent =
    STATE.perSecond > 0 ? `+${fmt(STATE.perSecond)}/сек` : "";
  document.getElementById("click-power").textContent =
    `+${STATE.clickPower} за клик`;

  // подсвечиваем доступные апгрейды
  CONFIG.upgrades.forEach((_, i) => {
    const btn = document.getElementById(`upgrade-btn-${i}`);
    if (!btn) return;
    const affordable = STATE.score >= upgradeCost(i);
    btn.disabled = !affordable;
    btn.style.opacity = affordable ? "1" : "0.5";
  });
}

function renderShop() {
  const shop = document.getElementById("shop");
  shop.innerHTML = "";
  CONFIG.upgrades.forEach((upg, i) => {
    const cost  = upgradeCost(i);
    const count = STATE.upgrades[i];
    const div   = document.createElement("div");
    div.className = "upgrade-card";
    div.innerHTML = `
      <span class="upg-emoji">${upg.emoji}</span>
      <div class="upg-info">
        <strong>${upg.name}</strong>
        <small>${upg.desc} &bull; куплено: ${count}</small>
      </div>
      <button id="upgrade-btn-${i}" class="upg-btn" onclick="buyUpgrade(${i})">
        ${fmt(cost)} ${CONFIG.currency}
      </button>
    `;
    shop.appendChild(div);
  });
}

// ── Пауза / возобновление (реклама) ──────────────────────────────────────────
function pauseGame()  { gamePaused = true; }
function resumeGame() { gamePaused = false; }

// ── Инициализация DOM ─────────────────────────────────────────────────────────
function buildDOM() {
  const c = CONFIG.colors;
  document.body.style.background   = c.bg;
  document.body.style.color        = c.text;
  document.title                   = CONFIG.gameName;

  document.getElementById("game-title").textContent   = CONFIG.gameName;
  document.getElementById("hero").textContent          = CONFIG.clickEmoji;
  document.getElementById("hero-name").textContent     = CONFIG.heroName;

  // Инжектируем CSS-переменные для динамической окраски
  const style = document.createElement("style");
  style.textContent = `
    :root {
      --primary:   ${c.primary};
      --secondary: ${c.secondary};
      --accent:    ${c.accent};
      --text:      ${c.text};
    }
  `;
  document.head.appendChild(style);

  renderShop();
  updateUI();
}

// ── Старт ─────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
  buildDOM();
  startPassiveIncome();
  await initYandex();

  document.getElementById("hero").addEventListener("click", onClick);
  document.getElementById("ad-btn").addEventListener("click", () =>
    showAd("rewarded")
  );

  // сохраняем при уходе со страницы
  window.addEventListener("visibilitychange", () => {
    if (document.hidden) saveProgress();
  });
});
