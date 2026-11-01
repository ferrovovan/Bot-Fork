"""
Витринный пример Bot Fork — «Марс-Пицца» 🍕

Не анкета-знакомство, а короткий боевой сценарий, на котором видно почти всё,
что умеет движок: динамические клавиатуры и prompt'ы, асинхронные валидаторы
и действия, отказы со своими кнопками, одно-info-сцены, перезапуск сцены с
нужной шапкой и — гвоздь программы — системная полоса: посреди заказа прилетает
стыковка дрона, перенимает диалог, а заказ бесшельно ждёт и продолжается ровно
с того же шага.

Запуск (токены не нужны, всё на mock-адаптере):

    python -m examples.demo_mars_pizza            # проиграть сценку целиком
    python -m examples.demo_mars_pizza --no-color # тот же прогон без ANSI (для CI/Pages)
    python -m examples.demo_mars_pizza --live     # сесть за игрока самому

Что и где показано (номера F-xx — из рабочего листа дыр движка):
  • запуск сцены кнопкой `scene:<id>`                       (F-23)
  • динамическая клавиатура, sync/async                     (F-29)
  • prompt как функция от сессии (корзина в тексте шага)    (F-05)
  • async-валидатор шага («реестр куполов»)                  (F-04)
  • отказ действия со своими кнопками Reject(text, buttons) (F-28)
  • текстовый побег с choice-шага зовёт обратно             (F-30)
  • сцена из одного info-шага авто-завершается              (F-33)
  • системная полоса: перехват диалога, основной ждёт       (F-06)
  • программный запуск сцены app.start_scene (job про дрона)(F-22)
  • своё завершение сцены on_complete (чек вместо отчёта)   (F-09)
  • шапка перезапуска сцены restart_text                    (F-27)
  • отмена подсказывает живые команды сцены                 (F-32)
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_fork import BotForkApp, Button, IncomingEvent, Reject
from bot_fork.adapters.telegram import TelegramAdapter
from bot_fork.scene import Scene, Step

USER_ID = "pioneer-1"
CHAT_ID = "pioneer-1"
DRONE_ID = 42

# «Микросервис» доставки: job про дрона пишет сюда итог стыковки, чек заказа
# читает. В продукте на этом месте настоящий репозиторий — движку всё равно.
_DELIVERY: dict = {}
_STATS = {"delivered": 0}

PRICES = {"20": 740, "30": 1180}
TOPPING_PRICE = 90


# --------------------------------------------------------------------------- #
# Сцена «меню» — корневая. Клавиатура живая (F-29): после первой доставки
# появляется статистика, которую никто руками не перекраивал.
# ---------------------------------------------------------------------------          

async def menu_buttons(session):
    buttons = [
        Button("🍕 Заказать пиццу", "scene:order"),
        Button("ℹ️ Правила", "scene:rules"),
    ]
    if _STATS["delivered"]:
        buttons.append(Button(f"📊 Доставлено: {_STATS['delivered']}", "scene:orders"))
    return buttons


menu_scene = Scene(
    id="menu",
    entry_commands=("/start", "/меню"),
    restart_text="",  # меню перезапускаем молча (F-27)
    steps=(
        Step.choice(
            "root",
            "🍕 Марс-Пицца у купола. Что прикажете?",
            buttons=menu_buttons,  # async-клавиатура (F-29)
        ),
    ),
)


# --------------------------------------------------------------------------- #
# Сцена «заказ». Динамические prompt'ы (F-05) показывают корзину прямо в тексте
# шага; ананас получает Reject со своими кнопками (F-28); адрес проверяет
# async-валидатор (F-04); финал — свой чек, а не generic-отчёт (F-09).
# ---------------------------------------------------------------------------          

def _cart(session) -> tuple:
    # Движок сам сохраняет нажатие в data[step_id]; свои поля держим под своими
    # ключами, чтобы не столкнуть их с машинной записью ответов.
    d = session.data
    toppings = [t for t in d.get("cart_toppings", "").split(",") if t]
    items = [d.get("cart_size", "—")] + toppings
    total = int(d.get("cart_price", 0)) + TOPPING_PRICE * len(toppings)
    return " + ".join(items), total


def toppings_prompt(session) -> str:
    items, total = _cart(session)
    return f"🛒 В корзине: {items} — {total} кр.\nДобавьте топпинг или жмите «Готово»:"


def pick_size(value, data):
    data["cart_size"] = "Марсианская 20 см" if value == "size_20" else "Олимпова 30 см"
    data["cart_price"] = str(PRICES[value.removeprefix("size_")])


def add_topping(value, data):
    if value == "pineapple":
        return Reject(
            "🚫 Ананас запрещён Марсианской хартией о вкусах, §1.\n"
            "Так что даже не проси — выберите из честного:",
            buttons=(Button("🍄 Грибы", "mushroom"), Button("🧀 Сыр", "cheese")),
        )
    if value == "done":
        return
    label = {"mushroom": "грибы", "cheese": "сыр"}[value]
    data["cart_toppings"] = data.get("cart_toppings", "") + label + ","


async def check_dome(text: str):
    await asyncio.sleep(0)  # настоящий код полез бы в реестр куполов по сети
    if not re.fullmatch(r"[Кк]упол-\d{1,3}", text.strip()):
        return False, "🛰 Реестр куполов Марса не знает «" + text.strip() + "». Формат: Купол-7."
    return True


def receipt(session) -> str:
    items, total = _cart(session)
    way = _DELIVERY.get("way", "дрон подождёт у шлюза")
    lines = [
        "🧾 Чек «Марс-Пиццы»",
        f"Заказ: {items} — {total} кр.",
        f"Доставка: {way} (дрон-курьер №{DRONE_ID})",
        "Пицца найдёт вас сама. Марс любит пунктуальных!",
    ]
    return "\n".join(lines)


order_scene = Scene(
    id="order",
    entry_commands=("/заказ",),
    restart_text="🔁 Новый заказ — начинаем с диаметра.",  # F-27
    on_complete=receipt,  # F-09: свой финал вместо отчёта ядра
    steps=(
        Step.choice(
            "size",
            "Какой диаметр с орбитальной печи?",
            buttons=(
                Button("🅼 Марсианская 20 см", "size_20"),
                Button("🅻 Олимпова 30 см", "size_30"),
            ),
            transitions={"size_20": "toppings", "size_30": "toppings"},
            action=pick_size,
        ),
        Step.choice(
            "toppings",
            toppings_prompt,  # callable-подсказка (F-05)
            buttons=(
                Button("🍄 Грибы", "mushroom"),
                Button("🧀 Сыр", "cheese"),
                Button("🍍 Ананас", "pineapple"),
                Button("🏁 Готово", "done"),
            ),
            transitions={
                "mushroom": "toppings",
                "cheese": "toppings",
                "pineapple": "toppings",
                "done": "address",
            },
            action=add_topping,
        ),
        Step.text(
            "address",
            "Куда везти дрону? Формат: Купол-<номер>.",
            validator=check_dome,  # async-валидатор (F-04)
            complete=True,
        ),
    ),
)


# --------------------------------------------------------------------------- #
# Сцена «правила» — вся из одного info-шага. С 1.11.5 (F-33) она печатается и
# завершается сама, не заглатывая следующее сообщение.
# ---------------------------------------------------------------------------          

rules_scene = Scene(
    id="rules",
    entry_commands=("/правила",),
    restart_text="",  # из меню в правила и обратно — без служебных шапок
    steps=(
        Step.info(
            "rules",
            "📜 Правила: тесто из орбитальной печи, сыр с купола Павсонида,\n"
            "ананас под межпланетным эмбарго. Дроид ждёт у шлюза 3 минуты.",
        ),
    ),
    on_complete=lambda session: None,
)

orders_scene = Scene(
    id="orders",
    entry_commands=("/доставки",),
    restart_text="",
    steps=(
        Step.info(
            "orders",
            lambda session: f"📊 За смену доставлено: {_STATS['delivered']}. Дроид не подводит.",
        ),
    ),
    on_complete=lambda session: None,
)


# --------------------------------------------------------------------------- #
# Гвоздь программы: системная полоса (F-06). Стыковка дрона — не реплика бота,
# а отдельная сцена в полосе system, которую «будит» фоновый job (F-22):
# app.start_scene(). Заказ тем временем ждёт в своей полосе и продолжится
# ровно с того же шага.
# ---------------------------------------------------------------------------          

def note_delivery(value, data):
    data["cart_method"] = value
    _DELIVERY["way"] = (
        "коробка пристёгнута магнитом у шлюза" if value == "doorstep"
        else "дрон занёс коробку в шлюз"
    )
    _STATS["delivered"] += 1


drone_scene = Scene(
    id="drone",
    entry_commands=("/дрон",),  # вручную; в бою зовёт job через app.start_scene
    lane="system",  # F-06
    on_complete=lambda session: {
        "airlock": "✅ Дрон занёс коробку в шлюз. Заказ не пострадал, стыковка закрыта.",
        "doorstep": "✅ Коробка пристёгнута магнитом у шлюза. Заказ не пострадал.",
    }.get(session.data.get("cart_method", ""), "✅ Стыковка завершена."),  # F-09
    steps=(
        Step.choice(
            "dock",
            f"🛸 ВНИМАНИЕ: дрон-курьер №{DRONE_ID} у вашего шлюза. Как принимаем?\n"
            "(это системное событие — ваш незавершённый заказ подождёт)",
            buttons=(
                Button("🚪 Впустить в шлюз", "airlock"),
                Button("📦 Оставить у двери", "doorstep"),
            ),
            complete=True,
            action=note_delivery,
        ),
    ),
)


def create_app() -> BotForkApp:
    """Собирает приложение на telegram-адаптере с mock-отправкой: без токенов."""
    app = BotForkApp(
        platform="telegram",
        adapter=TelegramAdapter(mock_sender=lambda p: None),
        cancel_commands=("/cancel", "/отмена"),  # F-31: отмена по-русски
    )
    for scene in (menu_scene, order_scene, rules_scene, orders_scene, drone_scene):
        app.register_scene(scene)
    return app


# --------------------------------------------------------------------------- #
# Рендер transcripts
# --------------------------------------------------------------------------- #

class Paint:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def wrap(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.enabled else s

    def bold(self, s): return self.wrap("1", s)
    def dim(self, s): return self.wrap("2", s)
    def red(self, s): return self.wrap("31", s)
    def green(self, s): return self.wrap("32", s)
    def yellow(self, s): return self.wrap("33", s)
    def cyan(self, s): return self.wrap("36", s)


def render_result(res, paint: Paint, labels: dict) -> None:
    for msg in res.messages:
        lines = [paint.bold("🤖 ") + msg.text]
        for i, b in enumerate(msg.buttons, 1):
            lines.append(paint.dim("      ") + paint.yellow(f"[{i}] {b.label}"))
        print("\n".join(lines))
        for b in msg.buttons:
            labels[b.value] = b.label  # копилка value → label: чем свежее, тем сильнее
    if res.error and not res.messages:
        print(paint.red("⚠ ") + res.error.message)


# Скриптованный прогон: живая сценка из 15 реплик, показывающая 12 возможностей.
SCRIPT = [
    ("cmd", "/start", "игрок заходит в бота", "F-23"),
    ("press", "scene:order", None, "запуск сцены кнопкой"),
    ("say", "двойную с обоих сторон!", "игрок пишет текстом в выбор кнопками", "F-30"),
    ("press", "size_30", None, "корзина живёт прямо в prompt'е шага"),
    ("press", "cheese", None, "действие шага копит корзину"),
    ("press", "pineapple", None, "F-28: отказ со своими кнопками"),
    ("press", "mushroom", None, "кнопки отказа — живые кнопки шага"),
    ("press", "done", None, None),
    ("system", None, None, "F-22+F-06: job будит сцену в полосе system"),
    ("press", "doorstep", None, "перехваченный диалог отвечает системе"),
    ("say", "Ленина, 5", "async-валидатор держит формат", "F-04"),
    ("say", "Купол-7", "F-09: вместо отчёта ядра — свой чек", None),
    ("cmd", "/start", None, "F-29: клавиатура изменилась сама"),
    ("press", "scene:orders", None, "F-33: сцена из одного info"),
    ("press", "scene:order", None, None),
    ("cmd", "/заказ", "игрок передумал и… начинает заново", "F-27: шапка перезапуска"),
    ("cmd", "/отмена", None, "F-32: подсказывает, как вернуться"),
]


async def run_scripted(color: bool) -> None:
    paint = Paint(color)
    app = create_app()
    labels: dict = {}
    n = 0
    for kind, arg, note, tag in SCRIPT:
        n += 1
        print()
        if kind == "system":
            print(paint.cyan("— ⚙ фоновый job: app.start_scene(\"drone\") — полоса system —"))
            res = await app.start_scene("drone", user_id=USER_ID, chat_id=CHAT_ID)
            render_result(res, paint, labels)
            continue
        if kind == "cmd":
            print(paint.bold("👤 ") + arg)
            res = await app.handle(IncomingEvent(
                platform="telegram", user_id=USER_ID, chat_id=CHAT_ID, text=arg))
        elif kind == "say":
            print(paint.bold("👤 ") + arg)
            res = await app.handle(IncomingEvent(
                platform="telegram", user_id=USER_ID, chat_id=CHAT_ID, text=arg))
        else:  # press
            label = labels.get(arg, arg)
            print(paint.bold("👤 ") + "〈" + label + "〉")
            res = await app.handle(IncomingEvent(
                platform="telegram", user_id=USER_ID, chat_id=CHAT_ID, payload=arg))
        render_result(res, paint, labels)
        if note or tag:
            print(paint.green("   ✓ ") + paint.dim(" · ".join(x for x in (note, tag) if x)))


async def run_live(color: bool) -> None:
    paint = Paint(color)
    app = create_app()
    labels: dict = {}
    print(paint.dim("Режим игрока: /старт, /заказ, /правила, /дрон — как обычно; "
                    "цифра — нажатие кнопки; /выход — выйти."))
    last_buttons = []
    while True:
        try:
            line = input().strip()
        except EOFError:
            return
        if not line:
            continue
        if line in ("/выход", "/exit"):
            return
        res = None
        if re.fullmatch(r"\d+", line) and last_buttons:
            btn = last_buttons[int(line) - 1]
            print(paint.bold("👤 ") + "〈" + btn.label + "〉")
            res = await app.handle(IncomingEvent(
                platform="telegram", user_id=USER_ID, chat_id=CHAT_ID, payload=btn.value))
        elif line == "/дрон":
            print(paint.cyan("— ⚙ job: start_scene(\"drone\") —"))
            res = await app.start_scene("drone", user_id=USER_ID, chat_id=CHAT_ID)
        else:
            print(paint.bold("👤 ") + line)
            res = await app.handle(IncomingEvent(
                platform="telegram", user_id=USER_ID, chat_id=CHAT_ID, text=line))
        render_result(res, paint, labels)
        last_buttons = list(res.messages[-1].buttons) if res.messages else []


def main() -> None:
    live = "--live" in sys.argv
    color = "--no-color" not in sys.argv and sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    if not live and not color:
        # прогон в pipe (CI → GitHub Pages): ANSI не нужен автоматически
        color = False
    print(Paint(color).bold("🍕 Bot Fork · витринный пример «Марс-Пицца» — настоящее ядро, mock-отправка"))
    asyncio.run(run_live(color) if live else run_scripted(color))


if __name__ == "__main__":
    main()
