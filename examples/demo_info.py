"""
Demonstration scene /info for Bot Fork.
Universal dialogue scene working identically on Telegram and VKontakte.
Conforms to ScenoMost Bot Fork MVP 3.1 specification.
"""

import os
from dotenv import load_dotenv
from bot_fork import BotForkApp, Scene, Step, Button

load_dotenv()


def validate_name(text: str):
    """Checks that name is between 1 and 80 characters after trim."""
    cleaned = text.strip()
    if not (1 <= len(cleaned) <= 80):
        return False, "Имя должно содержать от 1 до 80 символов. Попробуйте ещё раз."
    return True, ""


def validate_goal(text: str):
    """Checks that goal description is between 1 and 500 characters after trim."""
    cleaned = text.strip()
    if not (1 <= len(cleaned) <= 500):
        return False, "Описание цели проекта должно содержать от 1 до 500 символов."
    return True, ""


# Universal dialogue scene definition
info_scene = Scene(
    id="info",
    entry_commands=("/info",),
    steps=(
        Step.text(
            id="name",
            prompt="Как к вам обращаться?",
            validator=validate_name,
            next="role",
        ),
        Step.choice(
            id="role",
            prompt="Выберите вашу роль:",
            buttons=(
                Button("Разработчик", "developer"),
                Button("Фрилансер", "freelancer"),
                Button("Другое", "other"),
            ),
            next="goal",
        ),
        Step.text(
            id="goal",
            prompt="Кратко опишите цель проекта.",
            validator=validate_goal,
            complete=True,
        ),
    ),
)


def create_app() -> BotForkApp:
    """Configures BotForkApp from environment and registers the /info scene."""
    app = BotForkApp.from_env()
    app.register_scene(info_scene)
    return app


if __name__ == "__main__":
    app = create_app()
    print(f"Starting Bot Fork on platform: {app.platform}...")
    app.run()
