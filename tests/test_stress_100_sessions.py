"""
Test suite for NFR-01: Performance benchmark under 100 active sessions.
Verifies internal processing of simple text event takes under 1.0 second.
"""

import time
import unittest
from bot_fork.app import BotForkApp
from bot_fork.models import IncomingEvent, SessionKey, UserSession
from examples.demo_info import info_scene


class TestPerformanceNFR01(unittest.IsolatedAsyncioTestCase):
    async def test_100_sessions_processing_under_1_second(self):
        app = BotForkApp(platform="telegram")
        app.register_scene(info_scene)

        # Pre-seed 100 active sessions at step 'name'
        for i in range(100):
            key = SessionKey(platform="telegram", user_id=f"user_{i}", chat_id=f"chat_{i}")
            session = UserSession(session_key=key, scene_id="info", step_id="name", data={})
            await app.storage.set(session)

        # Verify 100 active sessions exist
        count = await app.storage.count()
        self.assertEqual(count, 100)

        # Measure processing time for 100 incoming events
        start_time = time.perf_counter()
        for i in range(100):
            event = IncomingEvent(
                platform="telegram",
                user_id=f"user_{i}",
                chat_id=f"chat_{i}",
                text=f"Пользователь {i}",
            )
            res = await app.handle(event)
            self.assertIsNone(res.error)
            self.assertEqual(res.session_after.step_id, "role")

        total_duration = time.perf_counter() - start_time
        avg_per_event = (total_duration / 100.0) * 1000.0

        # Entire batch of 100 events should easily complete in under 1 second
        self.assertLess(
            total_duration,
            1.0,
            f"100 events took {total_duration:.3f}s (exceeds NFR-01 target of 1.0s)",
        )
        print(f"\n[NFR-01 Benchmark] 100 events processed in {total_duration*1000:.2f}ms (avg {avg_per_event:.3f}ms/event)")


if __name__ == "__main__":
    unittest.main()
