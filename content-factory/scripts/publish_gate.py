#!/usr/bin/env python3
"""
Слой 5: публикация — ВСЕГДА требует подтверждения, без исключений,
независимо от того, насколько хорошо прошёл QA в Слое 4.

Использование:
    python3 publish_gate.py --video-id <uuid>  # ставит в очередь Decision Hub
    python3 publish_gate.py --video-id <uuid> --confirm --platform youtube  # публикует после approve
"""

import argparse
import os


def push_to_decision_hub(video_id: str, title: str) -> None:
    """Заглушка: decision_hub.py add --subsystem content --layer publish
    --stakes high (публикация — высокие ставки всегда)."""
    raise NotImplementedError("Дописать вызов decision_hub.py")


def check_decision_approved(video_id: str, conn_params: dict) -> bool:
    """Заглушка: проверить в brain.pending_decisions, что решение
    по этому video_id имеет status='approved'."""
    raise NotImplementedError("Дописать SELECT")


def publish_to_platform(video_path: str, platform: str, metadata: dict) -> str:
    """Заглушка: реальная публикация через API площадки
    (YouTube Data API / TikTok API), вернуть platform_post_id."""
    raise NotImplementedError("Дописать вызов API площадки")


def save_publication_record(video_id: str, platform: str, platform_post_id: str,
                             conn_params: dict) -> str:
    """Заглушка: INSERT в content.publications."""
    raise NotImplementedError("Дописать INSERT")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--confirm", action="store_true",
                         help="Подтвердить и опубликовать (после approve в Decision Hub)")
    parser.add_argument("--platform", choices=["youtube", "tiktok"])
    args = parser.parse_args()

    conn_params = {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB", "brain"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
    }

    if not args.confirm:
        push_to_decision_hub(args.video_id, title="")  # NOTE: подтянуть title из content.videos/ideas
        print(f"Видео {args.video_id} поставлено в очередь на подтверждение публикации.")
        return

    if not args.platform:
        raise SystemExit("--platform обязателен при --confirm")

    if not check_decision_approved(args.video_id, conn_params):
        raise SystemExit(
            "Решение по этому видео ещё не одобрено в Decision Hub. "
            "Публикация без явного approve запрещена (Слой 5, always_confirm)."
        )

    video_path = ""  # NOTE: подтянуть file_path из content.videos
    post_id = publish_to_platform(video_path, args.platform, metadata={})
    pub_id = save_publication_record(args.video_id, args.platform, post_id, conn_params)

    print(f"Опубликовано: {pub_id} на {args.platform}, platform_post_id={post_id}")


if __name__ == "__main__":
    main()
