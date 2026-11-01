"""
CLI / stdin runner for handling an event through Bot Fork.

Usage:
    python3 scripts/handle_event.py            # read event JSON from stdin, print HandlerResult JSON
    python3 scripts/handle_event.py --reset    # read {platform, user_id, chat_id} from stdin, drop session

Session state lives in a per-user file inside tempfile.gettempdir() so that
consecutive one-shot processes behave like a continuous conversation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

# Ensure bot_fork can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot_fork import BotForkApp, IncomingEvent
from bot_fork.models import SessionKey, UserSession
from examples.demo_info import info_scene

SAFE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def read_payload() -> dict:
    return json.loads(sys.stdin.read())


def session_params(data: dict) -> tuple[str, str, str]:
    platform = str(data.get("platform", "telegram")).strip().lower()
    user_id = str(data.get("user_id", "1001")).strip()
    chat_id = str(data.get("chat_id", "1001")).strip()
    if platform not in ("telegram", "vk"):
        raise ValueError(f"Unsupported platform: {platform!r}")
    for value in (user_id, chat_id):
        if not value or not SAFE_ID_CHARS.issuperset(value):
            raise ValueError(f"Unsupported session id: {value!r}")
    return platform, user_id, chat_id


def state_file_path(platform: str, user_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"bot_fork_sess_{platform}_{user_id}.json")


def reset_session() -> None:
    platform, user_id, _ = session_params(read_payload())
    state_file = state_file_path(platform, user_id)
    cleared = False
    try:
        os.remove(state_file)
        cleared = True
    except FileNotFoundError:
        pass
    print(json.dumps({"ok": True, "cleared": cleared}))


async def main():
    data = read_payload()
    platform, user_id, chat_id = session_params(data)
    text = data.get("text")
    payload = data.get("payload")

    app = BotForkApp(platform=platform)
    app.register_scene(info_scene)

    state_file = state_file_path(platform, user_id)
    key = SessionKey(platform=platform, user_id=user_id, chat_id=chat_id)

    # Restore session state if exists
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                s_dict = json.load(f)
            sess = UserSession(
                session_key=key,
                scene_id=s_dict["scene_id"],
                step_id=s_dict["step_id"],
                data=s_dict.get("data", {}),
            )
            await app.storage.set(sess)
        except Exception:
            pass

    event = IncomingEvent(
        platform=platform,
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        payload=payload,
    )

    result = await app.handle(event)

    # Update or clear persistent state file
    if result.clear_session:
        try:
            os.remove(state_file)
        except FileNotFoundError:
            pass
    elif result.session_after:
        fd = os.open(
            state_file,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "scene_id": result.session_after.scene_id,
                    "step_id": result.session_after.step_id,
                    "data": result.session_after.data,
                },
                f,
                ensure_ascii=False,
            )

    print(json.dumps(result.to_dict(), ensure_ascii=False))


if __name__ == "__main__":
    if "--reset" in sys.argv[1:]:
        reset_session()
    else:
        asyncio.run(main())
