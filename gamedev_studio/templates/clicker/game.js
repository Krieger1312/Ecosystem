"use strict";

/* ============================================================
   МОНЕТНЫЙ КЛИКЕР — игровая логика
   Структура файла:
     1. Константы и настройки
     2. Состояние игры
     3. Инициализация Яндекс SDK
     4. Реклама
     5. Логика клика
     6. Обновление UI
     7. Анимация всплывающего текста
     8. Точка входа
   ============================================================ */

// ── 1. Константы ─────────────────────────────────────────────────────────────

const AD_EVERY_N_CLICKS = 20;   // раз в сколько кликов показывать рекламу

// ── 2. Состояние игры ─────────────────────────────────────────────────────────

const state = {
  score:       0,    // текущее количество монет
  totalClicks: 0,    // всего кликов за сессию
  perClick:    1,    // монет за один клик (расширяемо: апгрейды)
  isPaused:    false // true когда показывается реклама
};

// ── 3. Яндекс SDK ─────────────────────────────────────────────────────────────

// YaGames доступен глобально после загрузки скрипта SDK из <head>
YaGames
  .init()
  .then(ysdk => {
    // Сохраняем объект SDK глобально — он нужен в функции showAd()
    window.ysdk = ysdk;

    // Сообщаем SDK, что игра полностью загружена и показана игроку.
    // Без этого вызова Яндекс может показать бесконечный экран загрузки.
    ysdk.features.LoadingAPI?.ready();

    console.log("[SDK] Яндекс SDK инициализирован");
  })
  .catch(err => {
    // SDK не загрузился (например, при локальной разработке).
    // Игра продолжает работать — реклама просто не будет показываться.
    console.warn("[SDK] Не удалось инициализировать Яндекс SDK:", err);
  });

// ── 4. Реклама ────────────────────────────────────────────────────────────────

/**
 * Показывает полноэкранную рекламу через Яндекс SDK.
 * Во время показа игра ставится на паузу (через #ad-overlay).
 * После закрытия рекламы (onClose) игра автоматически возобновляется.
 */
function showFullscreenAd() {
  if (!window.ysdk) return;  // SDK не инициализирован — пропускаем рекламу

  // Пауза игры
  state.isPaused = true;
  elements.adOverlay.removeAttribute("hidden");

  window.ysdk.adv.showFullscreenAdv({
    callbacks: {
      // Реклама открылась — игра уже на паузе, ничего дополнительно не делаем
      onOpen: () => {
        console.log("[Ad] Полноэкранная реклама открыта");
      },

      // Реклама закрыта (wasShown = true/false — показалась ли реально)
      onClose: (wasShown) => {
        console.log("[Ad] Реклама закрыта, wasShown =", wasShown);
        resumeGame();
      },

      // Ошибка при показе рекламы — тоже снимаем паузу
      onError: (err) => {
        console.warn("[Ad] Ошибка показа рекламы:", err);
        resumeGame();
      },

      // Реклама уже показывается — Яндекс вернул этот колбэк как защиту от двойного вызова
      onOffline: () => {
        console.warn("[Ad] Нет соединения для показа рекламы");
        resumeGame();
      },
    }
  });
}

/** Снимает паузу и скрывает оверлей. */
function resumeGame() {
  state.isPaused = false;
  elements.adOverlay.setAttribute("hidden", "");
}

// ── 5. Логика клика ───────────────────────────────────────────────────────────

/**
 * Главный обработчик нажатия на монету.
 * Вызывается как по pointer-событию, так и по клавиатуре (Enter/Space).
 * @param {number} clientX - X-координата для анимации "+N" (необязательно)
 * @param {number} clientY - Y-координата для анимации "+N" (необязательно)
 */
function handleCoinClick(clientX, clientY) {
  if (state.isPaused) return;   // игра на паузе → игнорируем клики

  // Начисляем монеты
  state.score       += state.perClick;
  state.totalClicks += 1;

  // Обновляем интерфейс
  updateUI();

  // Запускаем анимацию всплывающего текста в точке касания
  if (clientX !== undefined && clientY !== undefined) {
    spawnFloatText(`+${state.perClick}`, clientX, clientY);
  }

  // Анимация нажатия кнопки
  elements.coinBtn.classList.add("pressed");
  setTimeout(() => elements.coinBtn.classList.remove("pressed"), 100);

  // Каждые AD_EVERY_N_CLICKS кликов — показываем рекламу
  if (state.totalClicks % AD_EVERY_N_CLICKS === 0) {
    showFullscreenAd();
  }
}

// ── 6. Обновление UI ─────────────────────────────────────────────────────────

/** Кешируем DOM-ссылки — не ищем элементы при каждом клике */
const elements = {
  scoreValue:   document.getElementById("score-value"),
  perClickVal:  document.getElementById("per-click-val"),
  totalClicks:  document.getElementById("total-clicks"),
  adCountdown:  document.getElementById("ad-countdown"),
  coinBtn:      document.getElementById("coin-btn"),
  adOverlay:    document.getElementById("ad-overlay"),
  container:    document.getElementById("game-container"),
};

/** Форматируем большие числа (1 000 000 → «1M») */
function formatNumber(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(".0", "") + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1).replace(".0", "") + "K";
  return String(n);
}

/** Перерисовывает HUD и футер по текущему state */
function updateUI() {
  // Счётчик очков — анимируем небольшим "прыжком"
  elements.scoreValue.textContent = formatNumber(state.score);
  elements.scoreValue.style.transform = "scale(1.15)";
  requestAnimationFrame(() => {
    elements.scoreValue.style.transform = "";
  });

  // "+N за клик" бейдж
  elements.perClickVal.textContent = state.perClick;

  // Всего кликов
  elements.totalClicks.textContent = state.totalClicks;

  // Обратный отсчёт до рекламы: остаток от деления
  const remaining = AD_EVERY_N_CLICKS - (state.totalClicks % AD_EVERY_N_CLICKS);
  elements.adCountdown.textContent = remaining;
}

// ── 7. Анимация всплывающего текста ──────────────────────────────────────────

/**
 * Создаёт div с текстом text и запускает CSS-анимацию floatUp.
 * После окончания анимации элемент удаляется из DOM.
 *
 * @param {string} text   - отображаемый текст, например "+1"
 * @param {number} x      - X viewport-координата (пиксели)
 * @param {number} y      - Y viewport-координата (пиксели)
 */
function spawnFloatText(text, x, y) {
  const el = document.createElement("div");
  el.className   = "float-text";
  el.textContent = text;

  // Позиционируем относительно viewport
  el.style.left = `${x}px`;
  el.style.top  = `${y}px`;
  el.style.transform = "translate(-50%, -50%)";

  elements.container.appendChild(el);

  // Удаляем элемент после завершения анимации (0.9s в CSS)
  el.addEventListener("animationend", () => el.remove(), { once: true });
}

// ── 8. Точка входа ────────────────────────────────────────────────────────────

/** Инициализируем обработчики событий после полной загрузки DOM */
window.addEventListener("DOMContentLoaded", () => {

  // Клик/тап по монете
  elements.coinBtn.addEventListener("pointerdown", (e) => {
    e.preventDefault();  // отключаем задержку 300мс на мобиле
    handleCoinClick(e.clientX, e.clientY);
  });

  // Поддержка клавиатуры (Enter и Space) — доступность
  elements.coinBtn.addEventListener("keydown", (e) => {
    if (e.code === "Enter" || e.code === "Space") {
      e.preventDefault();
      const rect = elements.coinBtn.getBoundingClientRect();
      handleCoinClick(rect.left + rect.width / 2, rect.top + rect.height / 2);
    }
  });

  // Первоначальный рендер UI
  updateUI();
  console.log("[Game] Монетный Кликер запущен");
});
