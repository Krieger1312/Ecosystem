"""
B2B Lead Machine — Главный конвейер.

Запуск:
    python main_pipeline.py --query "строительные компании Казань"
    python main_pipeline.py --query "рекламные агентства Новосибирск" --max 30
    python main_pipeline.py --query "автосервисы Екатеринбург" --output my_leads.csv

Шаги:
  1. Парсинг Яндекс.Карт (maps_scraper.py)
  2. Загрузка сайтов и поиск email (site_analyzer.py)
  3. Генерация персонализированного письма через Claude (site_analyzer.py)
  4. Экспорт в leads_report.csv
"""

import argparse
import asyncio
import csv
import sys
import time
from pathlib import Path

from maps_scraper import scrape_yandex_maps
from site_analyzer import analyze_company

# ── Настройки ─────────────────────────────────────────────────────────────────

DEFAULT_OUTPUT  = Path("leads_report.csv")
DEFAULT_MAX     = 20
MAX_PARALLEL    = 3       # параллельных запросов к сайтам компаний
DELAY_BETWEEN   = (1.0, 2.5)  # пауза между запросами (сек) — вежливость к серверам

CSV_FIELDS = [
    "Название",
    "Сайт",
    "Email",
    "Телефон",
    "Адрес",
    "Письмо",
    "Статус",
]

# ── Конвейер ──────────────────────────────────────────────────────────────────


async def _process_company(
    company: dict,
    sem: asyncio.Semaphore,
    idx: int,
    total: int,
) -> dict:
    """Шаги 2–3 для одной компании: скачать сайт, найти email, сгенерировать письмо."""
    import random
    async with sem:
        name = company["name"]
        url  = company.get("site", "")
        print(f"[{idx}/{total}] Анализирую: {name[:55]}")

        analysis = await analyze_company(name, url)

        status_emoji = {
            "ok":          "✓",
            "no_site":     "○",
            "fetch_error": "✗",
            "no_content":  "~",
        }.get(analysis["status"], "?")

        print(
            f"      {status_emoji} email: {analysis['email'] or '—'} | "
            f"статус: {analysis['status']}"
        )

        # Небольшая пауза между запросами к разным сайтам
        await asyncio.sleep(random.uniform(*DELAY_BETWEEN))

        return {
            "Название": name,
            "Сайт":     url,
            "Email":    analysis["email"],
            "Телефон":  company.get("phone", ""),
            "Адрес":    company.get("address", ""),
            "Письмо":   analysis["offer_letter"],
            "Статус":   analysis["status"],
        }


async def run_pipeline(
    query: str,
    max_results: int,
    output_path: Path,
    headless: bool = True,
) -> None:
    t_start = time.monotonic()

    print(f"\n{'='*62}")
    print(f"  B2B Lead Machine")
    print(f"  Запрос:   «{query}»")
    print(f"  Лидов:    до {max_results}")
    print(f"  Файл:     {output_path}")
    print(f"{'='*62}\n")

    # ── Шаг 1: Парсинг карт ───────────────────────────────────────────────────
    print("── Шаг 1: Парсинг Яндекс.Карт ──────────────────────────────────")
    companies = await scrape_yandex_maps(
        query,
        max_results=max_results,
        headless=headless,
    )

    if not companies:
        print("\n[Pipeline] Компании не найдены.")
        print("  • Проверь подключение к интернету")
        print("  • Попробуй headless=False (флаг --visible) чтобы увидеть браузер")
        print("  • Яндекс мог показать капчу — попробуй позже или с другого IP")
        return

    # ── Шаги 2–3: Анализ сайтов + письма ─────────────────────────────────────
    print(f"\n── Шаги 2–3: Анализ {len(companies)} сайтов и генерация писем ──────────")
    sem = asyncio.Semaphore(MAX_PARALLEL)
    tasks = [
        _process_company(c, sem, i + 1, len(companies))
        for i, c in enumerate(companies)
    ]
    leads = await asyncio.gather(*tasks)

    # ── Шаг 4: Экспорт в CSV ─────────────────────────────────────────────────
    print(f"\n── Шаг 4: Экспорт в {output_path} ──────────────────────────────────")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(leads)

    # ── Итоги ─────────────────────────────────────────────────────────────────
    elapsed = time.monotonic() - t_start
    ok_count    = sum(1 for l in leads if l["Статус"] == "ok")
    email_count = sum(1 for l in leads if l["Email"])

    print(f"\n{'='*62}")
    print(f"  ✅  Готово за {elapsed:.0f}с")
    print(f"  Всего лидов:      {len(leads)}")
    print(f"  Сайт найден:      {ok_count}")
    print(f"  Email найден:     {email_count}")
    print(f"  Файл:             {output_path.resolve()}")
    print(f"{'='*62}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="B2B Lead Machine — автоматическая лидогенерация из Яндекс.Карт",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python main_pipeline.py --query "строительные компании Казань"
  python main_pipeline.py --query "рекламные агентства Новосибирск" --max 30
  python main_pipeline.py --query "автосервисы Екатеринбург" --output ekb_leads.csv
  python main_pipeline.py --query "туристические агентства Сочи" --visible
        """,
    )
    parser.add_argument(
        "--query", "-q", required=True,
        help='Поисковый запрос для Яндекс.Карт (например: "строительные компании Казань")',
    )
    parser.add_argument(
        "--max", "-m", type=int, default=DEFAULT_MAX, dest="max_results",
        help=f"Максимальное количество лидов (по умолчанию: {DEFAULT_MAX})",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=DEFAULT_OUTPUT,
        help=f"Путь к выходному CSV-файлу (по умолчанию: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--visible", action="store_true",
        help="Открыть браузер в окне (headless=False) — полезно при отладке/капче",
    )
    args = parser.parse_args()

    asyncio.run(
        run_pipeline(
            query=args.query,
            max_results=args.max_results,
            output_path=args.output,
            headless=not args.visible,
        )
    )


if __name__ == "__main__":
    main()
