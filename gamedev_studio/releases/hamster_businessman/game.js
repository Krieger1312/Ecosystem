"use strict";

/* ============================================================
   ХОМЯК-БИЗНЕСМЕН — игровая логика
   ============================================================ */

// ── Настройки ────────────────────────────────────────────────────────────────

const AD_INTERVAL   = 15;      // кликов между рекламами (оптимизировано)
const TICK_MS       = 100;     // мс между тиками пассивного дохода
const SAVE_MS       = 5_000;   // мс между авто-сохранениями
const BOOST_MS      = 60_000;  // длительность бонуса от rewarded ad

const INTERN_BASE  = 10;      // базовая цена стажёра (×1.5^n)
const SUIT_BASE    = 50;      // базовая цена костюма  (×2.0^n)

// Бизнес-титулы хомяка по числу купленных костюмов
const TITLES = [
  "Стажёр-Хомяк",
  "Менеджер-Хомяк",
  "Директор-Хомяк",
  "CEO-Хомяк",
  "Магнат-Хомяк",
  "Олигарх-Хомяк",
  "Легенда Бизнеса 🏆",
];

// ── Состояние игры ────────────────────────────────────────────────────────────

const state = {
  coins:        0,
  totalClicks:  0,
  interns:      0,
  suits:        0,
  isPaused:     false,
  lastTick:     0,
  boostActive:  false,
  boostEnd:     0,
};

// ── Расчёт текущих показателей ────────────────────────────────────────────────

const perClick  = ()  => Math.pow(2, state.suits) * (state.boostActive ? 2 : 1);
const perSecond = ()  => state.interns;
const internCost= ()  => Math.floor(INTERN_BASE * Math.pow(1.5, state.interns));
const suitCost  = ()  => Math.floor(SUIT_BASE   * Math.pow(2.0, state.suits));
const titleText = ()  => TITLES[Math.min(state.suits, TITLES.length - 1)];

// ── Сохранение / загрузка (localStorage) ─────────────────────────────────────

const SAVE_KEY     = "hb_save_v1";
const TUTORIAL_KEY = "hb_tutorial_v1";
const DAILY_KEY    = "hb_daily_v1";

function save() {
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify({
      coins:       Math.floor(state.coins),
      totalClicks: state.totalClicks,
      interns:     state.interns,
      suits:       state.suits,
    }));
  } catch (_) {}
}

function load() {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return;
    const d = JSON.parse(raw);
    state.coins       = d.coins       || 0;
    state.totalClicks = d.totalClicks || 0;
    state.interns     = d.interns     || 0;
    state.suits       = d.suits       || 0;
  } catch (_) {}
}

// ── Rewarded ad (boost ×2 на 60 сек) ─────────────────────────────────────────

let boostInterval = null;

function activateBoost() {
  state.boostActive = true;
  state.boostEnd = Date.now() + BOOST_MS;
  el.rewardBtn.disabled = true;
  el.boostBadge.removeAttribute("hidden");
  clearInterval(boostInterval);
  boostInterval = setInterval(() => {
    const left = Math.ceil((state.boostEnd - Date.now()) / 1000);
    if (left <= 0) {
      state.boostActive = false;
      el.boostBadge.setAttribute("hidden", "");
      el.rewardBtn.disabled = false;
      el.rewardDesc.textContent = "×2 монеты/клик на 60 сек";
      clearInterval(boostInterval);
    } else {
      el.boostTimerEl.textContent = left;
      el.rewardDesc.textContent   = `⚡ Буст активен ещё ${left} сек`;
    }
    updateUI();
  }, 500);
}

function showRewardedAd() {
  if (state.boostActive) return;
  if (!window.ysdk) {
    activateBoost();
    return;
  }
  state.isPaused = true;
  window.ysdk.adv.showRewardedVideo({
    callbacks: {
      onRewarded: ()  => activateBoost(),
      onClose:    ()  => { state.isPaused = false; state.lastTick = Date.now(); },
      onError:    ()  => { state.isPaused = false; state.lastTick = Date.now(); },
    },
  });
}

// ── Ежедневный бонус ──────────────────────────────────────────────────────────

function checkDailyBonus() {
  const today = new Date().toDateString();
  if (localStorage.getItem(DAILY_KEY) === today) return;
  const bonus = Math.max(50, (state.interns * 30) + (state.suits * 80) + 50);
  state.coins += bonus;
  localStorage.setItem(DAILY_KEY, today);
  el.dailyCoinsEl.textContent = fmt(bonus);
  el.dailyOverlay.removeAttribute("hidden");
  state.isPaused = true;
}

function closeDailyBonus() {
  el.dailyOverlay.setAttribute("hidden", "");
  state.isPaused = false;
  state.lastTick = Date.now();
  updateUI();
  save();
  if (!localStorage.getItem(TUTORIAL_KEY)) showTutorial();
}

// ── Туториал ─────────────────────────────────────────────────────────────────

function showTutorial() {
  el.tutorial.removeAttribute("hidden");
  state.isPaused = true;
}

function hideTutorial() {
  el.tutorial.setAttribute("hidden", "");
  state.isPaused = false;
  state.lastTick = Date.now();
  try { localStorage.setItem(TUTORIAL_KEY, "1"); } catch (_) {}
}

// ── Яндекс SDK ────────────────────────────────────────────────────────────────

YaGames
  .init()
  .then(ysdk => {
    window.ysdk = ysdk;
    ysdk.features.LoadingAPI?.ready();
    console.log("[SDK] Яндекс SDK инициализирован");
  })
  .catch(err => {
    console.warn("[SDK] SDK не загрузился (локальная разработка?):", err);
  });

// ── Реклама ───────────────────────────────────────────────────────────────────

function showAd() {
  if (!window.ysdk) return;
  state.isPaused = true;
  el.adOverlay.removeAttribute("hidden");

  window.ysdk.adv.showFullscreenAdv({
    callbacks: {
      onOpen:    ()  => console.log("[Ad] открыта"),
      onClose:   ()  => resumeGame(),
      onError:   ()  => resumeGame(),
      onOffline: ()  => resumeGame(),
    },
  });
}

function resumeGame() {
  state.isPaused = false;
  state.lastTick = Date.now();
  el.adOverlay.setAttribute("hidden", "");
}

// ── Клик по хомяку ────────────────────────────────────────────────────────────

function handleClick(x, y) {
  if (state.isPaused) return;

  const earned = perClick();
  state.coins       += earned;
  state.totalClicks += 1;

  spawnFloat(`+${fmt(earned)}`, x, y);

  el.hamBtn.classList.add("pressed");
  setTimeout(() => el.hamBtn.classList.remove("pressed"), 100);

  updateUI();
  save();

  if (state.totalClicks % AD_INTERVAL === 0) showAd();
}

// ── Покупки ───────────────────────────────────────────────────────────────────

function buyIntern() {
  const cost = internCost();
  if (state.coins < cost) return;
  state.coins -= cost;
  state.interns++;
  updateUI();
  save();
}

function buySuit() {
  const cost = suitCost();
  if (state.coins < cost) return;
  state.coins -= cost;
  state.suits++;
  applyLevelVisual();
  updateUI();
  save();
}

// ── Пассивный доход (тик) ─────────────────────────────────────────────────────

function tick() {
  const now = Date.now();
  if (!state.isPaused && state.interns > 0) {
    const dt = (now - state.lastTick) / 1000;
    state.coins += perSecond() * dt;
    updateUI();
  }
  state.lastTick = now;
}

// ── Форматирование чисел ──────────────────────────────────────────────────────

function fmt(n) {
  n = Math.floor(n);
  if (n >= 1_000_000_000) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  if (n >= 1_000_000)     return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000)         return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return String(n);
}

// ── Всплывающий текст ─────────────────────────────────────────────────────────

function spawnFloat(text, x, y) {
  const div = document.createElement("div");
  div.className   = "float-text";
  div.textContent = text;
  div.style.left  = `${x}px`;
  div.style.top   = `${y}px`;
  document.body.appendChild(div);
  div.addEventListener("animationend", () => div.remove(), { once: true });
}

// ── Визуальная прогрессия хомяка ──────────────────────────────────────────────

function applyLevelVisual() {
  const suits = state.suits;

  // Класс уровня на #hamster-wrap (меняет цвет свечения и заголовка)
  el.hamWrap.className = suits > 0 ? `suit-${Math.min(suits, 4)}` : "";

  // Бейдж с новым титулом (исчезает через 3с)
  el.levelBadge.textContent = titleText();
  el.levelBadge.removeAttribute("hidden");
  clearTimeout(el.levelBadge._t);
  el.levelBadge._t = setTimeout(
    () => el.levelBadge.setAttribute("hidden", ""),
    3000
  );
}

// ── Кэш DOM-элементов ────────────────────────────────────────────────────────

const el = {};

// ── Обновление интерфейса ────────────────────────────────────────────────────

function updateUI() {
  const coins = Math.floor(state.coins);

  // Счётчик монет
  el.scoreVal.textContent    = fmt(coins);
  el.scoreVal.style.transform = "scale(1.1)";
  requestAnimationFrame(() => { el.scoreVal.style.transform = ""; });

  // Бейджи доходности
  el.perClickEl.textContent  = fmt(perClick());
  el.perSecEl.textContent    = fmt(perSecond());

  // Бизнес-титул
  el.titleEl.textContent     = titleText();

  // Футер
  el.clickCountEl.textContent = fmt(state.totalClicks);
  el.adTimerEl.textContent    = AD_INTERVAL - (state.totalClicks % AD_INTERVAL);

  // Апгрейды
  const ic = internCost();
  const sc = suitCost();
  el.internOwned.textContent  = `×${state.interns}`;
  el.suitOwned.textContent    = `×${state.suits}`;
  el.internPrice.textContent  = fmt(ic);
  el.suitPrice.textContent    = fmt(sc);
  el.buyInternBtn.disabled    = coins < ic;
  el.buySuitBtn.disabled      = coins < sc;
}

// ── Точка входа ───────────────────────────────────────────────────────────────

window.addEventListener("DOMContentLoaded", () => {

  // Кэшируем элементы
  el.scoreVal     = document.getElementById("score-val");
  el.perClickEl   = document.getElementById("per-click");
  el.perSecEl     = document.getElementById("per-sec");
  el.titleEl      = document.getElementById("business-title");
  el.clickCountEl = document.getElementById("click-count");
  el.adTimerEl    = document.getElementById("ad-timer");
  el.hamBtn       = document.getElementById("hamster-btn");
  el.hamWrap      = document.getElementById("hamster-wrap");
  el.levelBadge   = document.getElementById("level-badge");
  el.adOverlay    = document.getElementById("ad-overlay");
  el.buyInternBtn  = document.getElementById("buy-intern");
  el.buySuitBtn    = document.getElementById("buy-suit");
  el.internOwned   = document.getElementById("intern-owned");
  el.suitOwned     = document.getElementById("suit-owned");
  el.internPrice   = document.getElementById("intern-price");
  el.suitPrice     = document.getElementById("suit-price");
  el.tutorial      = document.getElementById("tutorial");
  el.tutorialClose = document.getElementById("tutorial-close");
  el.helpBtn       = document.getElementById("help-btn");
  el.rewardBtn     = document.getElementById("buy-reward");
  el.rewardDesc    = document.getElementById("reward-desc");
  el.boostBadge    = document.getElementById("boost-badge");
  el.boostTimerEl  = document.getElementById("boost-timer");
  el.dailyOverlay  = document.getElementById("daily-overlay");
  el.dailyCoinsEl  = document.getElementById("daily-coins");
  el.dailyClose    = document.getElementById("daily-close");

  // Загружаем прогресс
  load();
  applyLevelVisual();
  updateUI();

  // Клик / тап по хомяку
  el.hamBtn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    handleClick(e.clientX, e.clientY);
  });

  // Поддержка клавиатуры (доступность)
  el.hamBtn.addEventListener("keydown", (e) => {
    if (e.code === "Enter" || e.code === "Space") {
      e.preventDefault();
      const r = el.hamBtn.getBoundingClientRect();
      handleClick(r.left + r.width / 2, r.top + r.height / 2);
    }
  });

  // Кнопки магазина
  el.buyInternBtn.addEventListener("click", buyIntern);
  el.buySuitBtn.addEventListener("click",   buySuit);

  // Туториал
  el.tutorialClose.addEventListener("click", hideTutorial);
  el.helpBtn.addEventListener("click", showTutorial);
  el.rewardBtn.addEventListener("click", showRewardedAd);
  el.dailyClose.addEventListener("click", closeDailyBonus);

  // Ежедневный бонус при первом запуске сессии (до туториала)
  checkDailyBonus();
  if (el.dailyOverlay.hasAttribute("hidden") && !localStorage.getItem(TUTORIAL_KEY)) {
    showTutorial();
  }

  // Запускаем пассивный доход
  state.lastTick = Date.now();
  setInterval(tick, TICK_MS);
  setInterval(save, SAVE_MS);

  console.log("[HamsterBiz] 🐹 Игра запущена! Удачи, хомяк.");
});
