"""
CLI / stdin runner for handling an event through Bot Fork.
Takes event JSON via stdin, updates /tmp session state, and prints HandlerResult JSON to stdout.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Ensure bot_fork can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot_fork import BotForkApp, IncomingEvent
from bot_fork.models import SessionKey, UserSession
from examples.demo_info import info_scene


async def main():
    if len(sys.argv) > 1:
        raw_input = sys.argv[1]
    else:
        raw_input = sys.stdin.read()

    data = json.loads(raw_input)
    platform = data.get("platform", "telegram")
    user_id = str(data.get("user_id", "1001"))
    chat_id = str(data.get("chat_id", "1001"))
    text = data.get("text")
    payload = data.get("payload")

    app = BotForkApp(platform=platform)
    app.register_scene(info_scene)

    state_file = f"/tmp/bot_fork_sess_{platform}_{user_id}.json"
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
        if os.path.exists(state_file):
            try:
                os.remove(state_file)
            except OSError:
                pass
    elif result.session_after:
        with open(state_file, "w", encoding="utf-8") as f:
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
    asyncio.run(main())
