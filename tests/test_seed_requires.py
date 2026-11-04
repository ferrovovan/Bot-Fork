"""F-07 (v1.12.10): посев данных, применимость шага и приземление на шаг.

Решение комнаты `D-19` (RFC-06 §5, метка `ARCH-CHANGE: RfI-06-3`):

- `SceneDefinition.seed` — предзаполнение `data` при ЛЮБОМ входе (команда,
  кнопка `scene:<id>`, программный старт, `at_step`): dict или callable
  (`UserSession` → dict, sync/async). Применяется до первого шага; явный
  `initial_data`/`data` старшего посева; значения — JSON-домен F-03,
  несериализуемое — `ConfigError` (не тихая пустая анкета).
- `Step.requires` — условие применимости шага (callable от данных → bool);
  невыполнимый шаг пропускается по `next_step_id`; весь путь недоступен —
  нейтральное завершение. Стека «назад» нет (снято D-18/D-19).
- `at_step` в `begin_scene`/`App.start_scene` — старт с произвольного шага
  «как если дошли»; шаг вне сцены — `ConfigError`.

Закрывает дыру командного входа: `initial_data` (F-22) была доступна только
программному запуску, игрок с командой получал пустую сцену.
"""

import unittest

from bot_fork import BotForkApp, Button, IncomingEvent, TelegramAdapter
from bot_fork.exceptions import ConfigError
from bot_fork.models import SessionKey, UserSession
from bot_fork.router import DialogRouter, SceneRegistry
from bot_fork.scene import Scene, Step
from bot_fork.storage import MemoryStateStorage


def _survey(seed=None, s1_requires=None, s2_requires=None):
    """Анкета из двух шагов: ранг (кнопки) → позывной (текст, финал)."""
    return Scene(
        id="reg",
        entry_commands=("/reg",),
        seed=seed,
        steps=(
            Step.choice(
                id="rank", prompt="Ваш ранг?",
                buttons=(Button(label="Капитан", value="captain"),
                         Button(label="Матрос", value="sailor")),
                next="callsign",
                requires=s1_requires,
            ),
            Step.text(id="callsign", prompt="Позывной?", complete=True,
                      requires=s2_requires),
        ),
    )


def _menu():
    """Меню с кнопкой запуска анкеты (F-23: payload `scene:<id>`)."""
    return Scene(
        id="menu",
        entry_commands=("/menu",),
        steps=(
            Step.choice(
                id="main", prompt="Меню",
                buttons=(Button(label="Анкета", value="scene:reg"),),
            ),
        ),
    )


def _event(text=None, payload=None, user_id="1001"):
    return IncomingEvent(platform="telegram", user_id=user_id, chat_id=user_id,
                         text=text, payload=payload)


def _key(user_id="1001"):
    return SessionKey(platform="telegram", user_id=user_id, chat_id=user_id)


class SeedTestCase(unittest.IsolatedAsyncioTestCase):
    def _router(self, *scenes):
        registry = SceneRegistry()
        for s in scenes:
            registry.register(s)
        return DialogRouter(registry=registry, storage=MemoryStateStorage())


class TestSeed(SeedTestCase):
    async def test_seed_applied_on_command_entry_before_first_step(self):
        # игрок набирает /reg: посев отработал ДО рендера первого шага —
        # prompt-функция уже видит засеянный ранг (дыра router-а времен F-22)
        scene = Scene(
            id="reg", entry_commands=("/reg",),
            seed=lambda session: {"rank": "Капитан"},
            steps=(Step.text("q", lambda session: f"Ранг: {session.data['rank']}?",
                             complete=True),),
        )
        router = self._router(scene)
        r = await router.route(_event("/reg"))
        self.assertEqual(r.session_after.data, {"rank": "Капитан"})
        self.assertEqual(r.messages[0].text, "Ранг: Капитан?")

    async def test_seed_receives_session(self):
        seen = {}

        def seed(session):
            seen["session"] = session
            return {"a": 1}

        router = self._router(_survey(seed=seed))
        r = await router.route(_event("/reg"))
        self.assertIsInstance(seen["session"], UserSession)
        self.assertEqual(seen["session"].scene_id, "reg")
        self.assertEqual(r.session_after.data["a"], 1)

    async def test_seed_applied_on_button_entry(self):
        router = self._router(_survey(seed={"hero": "Герман"}), _menu())
        await router.route(_event("/menu"))
        r = await router.route(_event(payload="scene:reg"))
        self.assertEqual(r.session_after.scene_id, "reg")
        self.assertEqual(r.session_after.data, {"hero": "Герман"})

    async def test_seed_dict_and_async_callable(self):
        async def aseed(session):
            return {"from": "async"}

        for seed, expected in (({"k": "v"}, "v"), (aseed, "async")):
            router = self._router(_survey(seed=seed))
            r = await router.route(_event("/reg"))
            self.assertEqual(r.session_after.data["k" if seed is not aseed else "from"],
                             expected)

    async def test_seed_called_once_per_entry(self):
        calls = {"n": 0}

        def seed(session):
            calls["n"] += 1
            return {"n": calls["n"]}

        router = self._router(_survey(seed=seed))
        await router.route(_event("/reg"))
        await router.route(_event("/reg"))  # перезапуск — посев заново
        self.assertEqual(calls["n"], 2)
        self.assertEqual((await router.storage.get(_key())).data["n"], 2)

    async def test_explicit_data_wins_over_seed(self):
        # порядок посева: seed → поверх initial_data (явный аргумент старшего)
        router = self._router(_survey(seed={"rank": "из посева", "hero": "Герман"}))
        key = _key()
        r = await router.begin_scene(
            router.registry.get_scene("reg"), key.with_lane("user"), "1001",
            initial_data={"rank": "явный"},
        )
        self.assertEqual(r.session_after.data["rank"], "явный")
        self.assertEqual(r.session_after.data["hero"], "Герман")

    async def test_unserializable_seed_value_is_config_error(self):
        for bad in ({"tags": {"a", "b"}},          # set вне JSON-домена
                    {"x": float("nan")},           # NaN вне JSON-домена (F-03)
                    {"when": object()}):           # произвольный объект
            router = self._router(_survey(seed=lambda s, bad=bad: dict(bad)))
            with self.assertRaises(ConfigError):
                await router.route(_event("/reg"))

    async def test_static_seed_dict_validated_on_build(self):
        with self.assertRaises(ConfigError):
            _survey(seed={"tags": {"a", "b"}})  # set — видно на построении сцены
        with self.assertRaises(ConfigError):
            _survey(seed=42)                    # ни dict, ни callable

    async def test_seed_bad_return_is_config_error(self):
        router = self._router(_survey(seed=lambda s: ["не", "dict"]))
        with self.assertRaises(ConfigError):
            await router.route(_event("/reg"))

    async def test_seed_product_error_is_config_error(self):
        def seed(session):
            raise RuntimeError("репозиторий продукта лёг")

        router = self._router(_survey(seed=seed))
        with self.assertRaises(ConfigError):
            await router.route(_event("/reg"))


class TestRequires(SeedTestCase):
    async def test_requires_skips_step_on_transition(self):
        # шаг callsign невыполним → ответ на rank приземляется на завершение
        # через пропуск callsign по next_step_id
        router = self._router(_survey(
            s2_requires=lambda data: "nope" in data,
        ))
        await router.route(_event("/reg"))
        r = await router.route(_event(payload="captain"))
        self.assertTrue(r.clear_session)          # callsign пропущен, дальше финал
        self.assertIsNone(r.session_after)

        # выполнимое условие — шаг обычным: встал на callsign
        router2 = self._router(_survey(s2_requires=lambda data: "rank" in data))
        await router2.route(_event("/reg"))
        r2 = await router2.route(_event(payload="captain"))
        self.assertEqual(r2.session_after.step_id, "callsign")
        self.assertEqual(r2.messages[0].text, "Позывной?")

    async def test_start_step_requires_evaluated_after_seed(self):
        # посев → requires: rank-шаг просит data["can"], посев его и приносит
        gate = Scene(
            id="reg", entry_commands=("/reg",),
            seed=lambda s: {"can": True},
            steps=_survey(
                s1_requires=lambda data: data.get("can") is True,
            ).steps,
        )
        router = self._router(gate)
        r = await router.route(_event("/reg"))
        self.assertEqual(r.session_after.step_id, "rank")  # seed принёс can → встали

        # без посева условие ложно — стартовый шаг пропущен, сцена стартует со второго
        router2 = self._router(_survey(s1_requires=lambda data: data.get("can") is True))
        r2 = await router2.route(_event("/reg"))
        self.assertEqual(r2.session_after.step_id, "callsign")
        self.assertEqual(r2.messages[0].text, "Позывной?")

    async def test_whole_scene_unavailable_gives_neutral_completion(self):
        scene = Scene(
            id="reg", entry_commands=("/reg",),
            steps=_survey(
                s1_requires=lambda data: False,
                s2_requires=lambda data: False,
            ).steps,
            on_complete=lambda session: "Сейчас нечего заполнять.",
        )
        router = self._router(scene)
        r = await router.route(_event("/reg"))
        self.assertTrue(r.clear_session)
        self.assertIsNone(r.session_after)
        self.assertEqual(r.messages[0].text, "Сейчас нечего заполнять.")
        self.assertIsNone(await router.storage.get(_key()))

    async def test_requires_must_return_bool_or_raise_config_error(self):
        router = self._router(_survey(s2_requires=lambda data: "не bool"))
        await router.route(_event("/reg"))
        with self.assertRaises(ConfigError):
            await router.route(_event(payload="captain"))

    async def test_requires_error_is_config_error(self):
        def req(data):
            raise KeyError("can")

        router = self._router(_survey(s1_requires=req))
        with self.assertRaises(ConfigError):
            await router.route(_event("/reg"))

    async def test_requires_async_supported(self):
        async def req(data):
            return False

        router = self._router(_survey(s1_requires=req))
        r = await router.route(_event("/reg"))
        self.assertEqual(r.session_after.step_id, "callsign")  # async-условие сработало

    async def test_mutual_skip_is_config_error(self):
        # два невыполнимых шага указывают друг на друга — пропуск по циклу
        scene = Scene(
            id="loop", entry_commands=("/loop",),
            steps=(
                Step.text("a", "A", next="b"),
                Step.text("b", "B", next="c", requires=lambda d: False),
                Step.text("c", "C", next="b", requires=lambda d: False),
            ),
        )
        router = self._router(scene)
        await router.route(_event("/loop"))
        with self.assertRaises(ConfigError):
            await router.route(_event("ответ"))


class TestAtStep(SeedTestCase):
    async def test_at_step_lands_on_target_step(self):
        # begin_scene — общий путь входа (команда/кнопка/программный старт):
        # at_step доступен и на нём, приземление «как если дошли»
        router = self._router(_survey())
        r = await router.begin_scene(
            router.registry.get_scene("reg"), _key().with_lane("user"), "1001",
            at_step="callsign",
        )
        self.assertEqual(r.session_after.step_id, "callsign")
        self.assertEqual(r.messages[0].text, "Позывной?")
        self.assertEqual(r.messages[0].buttons, ())

    async def test_at_step_with_seed_and_requires(self):
        # посев отработал до requires и до prompt'а целевого шага
        scene = Scene(
            id="reg", entry_commands=("/reg",),
            seed=lambda s: {"ready": True, "who": "Игрок"},
            steps=(
                Step.text("intro", "Инфо", next="deep"),
                Step.text("deep", lambda s: f"Привет, {s.data['who']}?",
                          next="end", requires=lambda d: d.get("ready") is True),
                Step.text("end", "Конец", complete=True),
            ),
        )
        router = self._router(scene)
        r = await router.begin_scene(
            scene, _key().with_lane("user"), "1001", at_step="deep",
        )
        self.assertEqual(r.messages[0].text, "Привет, Игрок?")
        self.assertEqual(r.session_after.step_id, "deep")

    async def test_at_step_unknown_step_is_config_error(self):
        router = self._router(_survey())
        with self.assertRaises(ConfigError):
            await router.begin_scene(
                router.registry.get_scene("reg"), _key().with_lane("user"),
                "1001", at_step="ghost",
            )

    async def test_app_start_scene_at_step(self):
        adapter = TelegramAdapter()  # mock-режим
        app = BotForkApp(platform="telegram", adapter=adapter,
                         storage=MemoryStateStorage())
        app.register_scene(_survey(seed={"rank": "Капитан"}))
        res = await app.start_scene("reg", user_id="77", chat_id="77",
                                    at_step="callsign")
        self.assertEqual(res.session_after.step_id, "callsign")
        self.assertEqual(res.session_after.data["rank"], "Капитан")  # посев и здесь
        self.assertEqual(len(adapter.sent_messages), 1)
        with self.assertRaises(ConfigError):
            await app.start_scene("reg", user_id="77", chat_id="77", at_step="ghost")


class TestBackwardCompatibility(SeedTestCase):
    async def test_scene_without_seed_and_requires_unchanged(self):
        router = self._router(_survey())
        r = await router.route(_event("/reg"))
        self.assertEqual(r.session_after.step_id, "rank")
        self.assertEqual(r.session_after.data, {})       # посева нет — пусто как раньше
        self.assertEqual(r.messages[0].text, "Ваш ранг?")
        r = await router.route(_event(payload="captain"))
        self.assertEqual(r.session_after.step_id, "callsign")
        self.assertEqual(r.session_after.data["rank"], "captain")
        r = await router.route(_event("Неведомый"))
        self.assertTrue(r.clear_session)                    # финал как раньше
        self.assertEqual(r.messages[0].text, "Сценарий завершён.")


if __name__ == "__main__":
    unittest.main()
