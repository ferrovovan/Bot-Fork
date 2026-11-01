"""
Сборка статической страницы GitHub Pages для Bot Fork.

Идея: страница не пересказывает возможности — она показывает живой прогон
витринного примера «Марс-Пицца», исполненный настоящим ядром bot_fork прямо
во время сборки (mock-адаптер, без токенов и сети). Обновила ядро — страница
сама обновит лог диалога.

Использование:
    python scripts/build_pages.py        # site/index.html → _site/index.html
"""

from __future__ import annotations

import html
import io
import os
import sys
import contextlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "site", "index.html")
OUT_DIR = os.path.join(ROOT, "_site")
PLACEHOLDER = "<!--TRANSCRIPT-->"


def capture_transcript() -> str:
    """Прогон SCRIPT-а примера на настоящем ядре, ANSI выключен."""
    from examples import demo_mars_pizza as demo

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import asyncio
        asyncio.run(demo.run_scripted(color=False))
    text = buf.getvalue().strip()
    if "Чек" not in text:
        raise SystemExit("build_pages: транскрипт пуст или побит — сборка остановлена")
    return text


def to_html(text: str) -> str:
    """Экранируем и подсвечиваем реплики: 👤 — игроком, ✓ — подсказки возможностей."""
    out = []
    for line in text.splitlines():
        esc = html.escape(line, quote=False)
        if line.startswith("👤"):
            esc = esc.replace("👤", '<b class="who">👤</b>', 1)
        elif line.startswith("   ✓"):
            esc = '<b class="ok">' + esc + "</b>"
        out.append(esc)
    return "\n".join(out)


def main() -> None:
    transcript = to_html(capture_transcript())
    with open(TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    if PLACEHOLDER not in page:
        raise SystemExit("build_pages: в шаблоне нет плейсхолдера транскрипта")
    page = page.replace(PLACEHOLDER, transcript)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    lines = len(transcript.splitlines())
    print(f"build_pages: {out} готов, транскрипт {lines} строк")


if __name__ == "__main__":
    main()
