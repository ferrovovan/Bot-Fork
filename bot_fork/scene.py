"""
SceneDefinition, StepDefinition, and factory classes for Bot Fork.
Enforces structural integrity and immutability of dialogue scenes.
"""

from __future__ import annotations

import copy
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union
from bot_fork.builder import ButtonBuilder
from bot_fork.exceptions import ConfigError
from bot_fork.models import Button, _check_json_value

ValidatorFunc = Callable[[str], Union[bool, Tuple[bool, str], None]]
# F-05: prompt может быть функцией от сессии (карточка слота, регламент из анкет).
# Вызывается с UserSession (или без аргументов); обязана вернуть непустую str.
PromptFunc = Callable[..., str]
# F-04: действие шага — сид-эффект после валидного ответа (вызов сервиса продукта).
# Принимает (значение, словарь данных сессии — можно дополнять), может быть async.
# Возврат строки трактуется как причина отказа: шаг не завершается, данные не сохраняются.
ActionFunc = Callable[..., Any]
# F-29: клавиатура как функция от сессии (sync или async) — развилки меню по
# состоянию игрока («Анкета» vs «Пройти заново»). Валидируется при резолве
# идентично статической: ≤4 кнопок, уникальные values.
ButtonsFunc = Callable[..., Any]
# F-07 (RfI-06-3): посев данных сцены — dict или функция от сессии (sync/async),
# возвращающая JSON-совместимый dict (домен F-03). Вызывается движком при любом
# входе (команда, кнопка, программный старт/at_step) до первого шага.
SeedFunc = Callable[..., Any]
# F-07 (RfI-06-3): условие применимости шага — функция от данных сессии
# (sync/async), обязана вернуть bool. Невыполнение — шаг пропускается по
# next_step_id; стека «назад» нет по решению D-18/D-19.
RequiresFunc = Callable[..., Any]


@dataclass(frozen=True)
class StepDefinition:
    """
    Immutable description of a scene step.
    Defines prompt, input validation, buttons, and transitions.
    """
    id: str
    prompt: Union[str, PromptFunc]  # F-05: str или Callable[[UserSession], str]
    input_type: str = "text"  # "text" | "choice"
    buttons: Union[Tuple[Button, ...], ButtonsFunc] = ()  # F-29: или Callable[[UserSession], Sequence[Button]]
    validator: Optional[ValidatorFunc] = None
    transitions: Dict[str, str] = field(default_factory=dict)
    next_step_id: Optional[str] = None
    complete: bool = False
    action: Optional[ActionFunc] = None
    # F-07 (RfI-06-3): условие применимости шага — callable от данных сессии
    # (или без аргументов), возвращающий bool. Нет условия — шаг всегда применим.
    requires: Optional[RequiresFunc] = None

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ConfigError("Step id must be a non-empty string")
        if self.requires is not None and not callable(self.requires):
            raise ConfigError(f"Step '{self.id}' requires must be a callable returning bool")
        if not callable(self.prompt) and (not self.prompt or not isinstance(self.prompt, str)):
            raise ConfigError(f"Step '{self.id}' prompt must be a non-empty string or a callable")
        if self.input_type not in ("text", "choice", "info"):
            raise ConfigError(f"Step '{self.id}' input_type must be 'text', 'choice' or 'info', got '{self.input_type}'")
        if callable(self.buttons):
            # F-29: клавиатура-функция проверяется при резолве (≤4, уникальность);
            # инфо-шагу она не положена в любом виде.
            if self.input_type == "info":
                raise ConfigError(f"Step '{self.id}' has input_type='info' but buttons were provided (инфо-шаг не жмёт кнопок)")
        else:
            if len(self.buttons) > 4:
                raise ConfigError(f"Step '{self.id}' cannot have more than 4 buttons (got {len(self.buttons)})")
            if self.input_type == "info" and self.buttons:
                raise ConfigError(f"Step '{self.id}' has input_type='info' but buttons were provided (инфо-шаг не жмёт кнопок)")
            if self.input_type == "choice" and not self.buttons:
                raise ConfigError(f"Step '{self.id}' has input_type='choice' but no buttons were provided")

            values = [b.value for b in self.buttons]
            if len(values) != len(set(values)):
                raise ConfigError(f"Step '{self.id}' has duplicate button values: {values}")

    def render_prompt(self, session: Any = None) -> str:
        """F-05: статический prompt или текст, вычисленный из данных сессии."""
        if not callable(self.prompt):
            return self.prompt
        return self._finish_prompt(self._call_with_session(self.prompt, session))

    async def arender_prompt(self, session: Any = None) -> str:
        """F-29: как render_prompt, но prompt'у разрешено быть async (репозиторий продукта)."""
        if not callable(self.prompt):
            return self.prompt
        result = self._call_with_session(self.prompt, session)
        if inspect.isawaitable(result):
            try:
                result = await result
            except Exception as e:  # продуктная async-ошибка не роняет роутер
                raise ConfigError(f"Step '{self.id}' dynamic prompt raised {e!r}") from e
        return self._finish_prompt(result)

    async def resolve_buttons(self, session: Any = None) -> Tuple[Button, ...]:
        """F-29: статическая клавиатура или клавиатура-функция от сессии (sync/async)."""
        if not callable(self.buttons):
            return self.buttons
        try:
            result = self._call_with_session(self.buttons, session)
            if inspect.isawaitable(result):
                result = await result
        except ConfigError:
            raise
        except Exception as e:
            raise ConfigError(f"Step '{self.id}' dynamic buttons raised {e!r}") from e
        if not isinstance(result, (tuple, list)):
            raise ConfigError(f"Step '{self.id}' dynamic buttons must return a sequence of Button, got {result!r}")
        return ButtonBuilder.keyboard(*result)  # те же лимиты, что у статической

    async def meets_requires(self, data: Any = None) -> bool:
        """F-07 (RfI-06-3): применим ли шаг при посадке на него.

        Без условия — всегда применим (обратная совместимость). Условие
        вызывается движком с данными сессии (арность адаптируется, sync/async,
        конвенция F-05/F-29); обязана вернуть bool. Исключение продукта и
        нелогичный возврат — `ConfigError`: условие относится к конфигурации
        сцены, а не к вводу игрока.
        """
        if self.requires is None:
            return True
        result = self._call_with_session(self.requires, data)
        if inspect.isawaitable(result):
            try:
                result = await result
            except Exception as e:  # async-ошибка продукта не роняет роутер
                raise ConfigError(f"Step '{self.id}' requires raised {e!r}") from e
        if not isinstance(result, bool):
            raise ConfigError(
                f"Step '{self.id}' requires must return a bool, got {result!r}"
            )
        return result

    def _call_with_session(self, fn, session: Any):
        params = inspect.signature(fn).parameters
        takes_arg = any(
            p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            for p in params.values()
        )
        try:
            return fn(session) if takes_arg else fn()
        except Exception as e:  # исключение продукта не должно ронять роутер
            raise ConfigError(f"Step '{self.id}' dynamic callable raised {e!r}") from e

    def _finish_prompt(self, result: Any) -> str:
        if not isinstance(result, str) or not result:
            raise ConfigError(f"Step '{self.id}' dynamic prompt must return a non-empty string")
        return result


class Step:
    """Convenience factory for StepDefinition."""

    @staticmethod
    def text(
        id: str,
        prompt: str,
        validator: Optional[ValidatorFunc] = None,
        next: Optional[str] = None,
        complete: bool = False,
        action: Optional[ActionFunc] = None,
        requires: Optional[RequiresFunc] = None,
    ) -> StepDefinition:
        return StepDefinition(
            id=id,
            prompt=prompt,
            input_type="text",
            buttons=(),
            validator=validator,
            transitions={},
            next_step_id=next,
            complete=complete,
            action=action,
            requires=requires,
        )

    @staticmethod
    def info(
        id: str,
        prompt: str,
        next: Optional[str] = None,
        complete: bool = False,
        action: Optional[ActionFunc] = None,
        requires: Optional[RequiresFunc] = None,
    ) -> StepDefinition:
        """Инфо-шаг: печатает prompt и идёт дальше сам, ввода не ждёт.

        Нужен для сообщений-результатов («О проекте», «Название принято»), после
        которых диалог должен вернуться в меню, а не зависать в ожидании текста —
        иначе следующая кнопка прилетает в шаг-ожидание и FSM отвечает
        «Ответ не должен быть пустым» (баг живой приёмки 2026-11-01).
        """
        return StepDefinition(
            id=id,
            prompt=prompt,
            input_type="info",
            buttons=(),
            validator=None,
            transitions={},
            next_step_id=next,
            complete=complete,
            action=action,
            requires=requires,
        )

    @staticmethod
    def choice(
        id: str,
        prompt: str,
        buttons: Sequence[Button] = (),
        transitions: Optional[Dict[str, str]] = None,
        next: Optional[str] = None,
        complete: bool = False,
        action: Optional[ActionFunc] = None,
        requires: Optional[RequiresFunc] = None,
    ) -> StepDefinition:
        btn_tuple = buttons if callable(buttons) else ButtonBuilder.keyboard(*buttons)
        trans = dict(transitions) if transitions else {}
        return StepDefinition(
            id=id,
            prompt=prompt,
            input_type="choice",
            buttons=btn_tuple,
            validator=None,
            transitions=trans,
            next_step_id=next,
            complete=complete,
            action=action,
            requires=requires,
        )


@dataclass(frozen=True)
class SceneDefinition:
    """
    Immutable definition of an entire dialogue scene.
    F-06: lane="system" — приоритетная сцена: её активная сессия перехватывает события чата,
    пока не завершится; пользовательские диалоги (lane="user") при этом не теряются.
    """
    id: str
    entry_commands: Tuple[str, ...]
    start_step_id: str
    steps: Tuple[StepDefinition, ...]
    lane: str = "user"
    # F-09: чем сцена отвечает на завершение. Вызывается с UserSession;
    # возврат: None (тихо) | str | list[str] | list[OutgoingMessage] | list смешанно.
    # Без него — прежний generic-отчёт. Ядро больше не знает текстов конкретных сцен.
    on_complete: Optional[Callable[..., Any]] = None
    # F-27: шапка при перезапуске сцены, где уже шёл диалог. Раньше ядро вшивало
    # «Анкета начата заново.» во все сцены — врали и админка, и дневник.
    # None → generic «Диалог начат заново.», "" → шапки нет вовсе (меню-сцены).
    restart_text: Optional[str] = None
    # F-07 (RfI-06-3): предзаполнение данных сцены при ЛЮБОМ входе (команда,
    # кнопка scene:<id>, программный старт, at_step) — dict или callable
    # (UserSession → dict, sync/async, арность адаптируется). Применяется до
    # первого шага; явный initial_data старшего посева; значения — JSON-домен F-03.
    seed: Optional[Union[SeedFunc, Dict[str, Any]]] = None
    _step_map: Dict[str, StepDefinition] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ConfigError("Scene id must be a non-empty string")
        if self.lane not in ("user", "system"):
            raise ConfigError(f"Scene '{self.id}' lane must be 'user' or 'system', got '{self.lane}'")
        # F-07: форма посева проверяется на построении (норма scenes: битая
        # конфигурация вскрывается до диалога); dict-посев валидуется в JSON-домене F-03.
        if self.seed is not None and not callable(self.seed):
            if isinstance(self.seed, dict):
                for k, v in self.seed.items():
                    if not isinstance(k, str):
                        raise ConfigError(
                            f"Scene '{self.id}' seed: ключ {k!r} типа "
                            f"'{type(k).__name__}' — ключи посева должны быть str"
                        )
                    _check_json_value(v, f"Scene '{self.id}' seed[{k!r}]")
            else:
                raise ConfigError(
                    f"Scene '{self.id}' seed must be a dict or a callable returning "
                    f"a dict, got '{type(self.seed).__name__}'"
                )
        if not self.steps:
            raise ConfigError(f"Scene '{self.id}' must define at least 1 step (max 50)")
        if len(self.steps) > 50:
            raise ConfigError(f"Scene '{self.id}' exceeds maximum of 50 steps (got {len(self.steps)})")

        step_map: Dict[str, StepDefinition] = {}
        for s in self.steps:
            if s.id in step_map:
                raise ConfigError(f"Duplicate step id '{s.id}' in scene '{self.id}'")
            step_map[s.id] = s

        object.__setattr__(self, "_step_map", step_map)

        if not self.start_step_id or self.start_step_id not in step_map:
            raise ConfigError(
                f"Scene '{self.id}' start_step_id '{self.start_step_id}' does not exist in steps"
            )

        # Validate transitions and next_step_id references
        for s in self.steps:
            if s.next_step_id and s.next_step_id not in step_map:
                raise ConfigError(
                    f"Step '{s.id}' in scene '{self.id}' references non-existent next_step_id '{s.next_step_id}'"
                )
            for val, target_id in s.transitions.items():
                if target_id not in step_map:
                    raise ConfigError(
                        f"Step '{s.id}' transition for '{val}' points to non-existent step '{target_id}'"
                    )

            if s.input_type == "choice" and not callable(s.buttons):
                # Ensure each button value either has an explicit transition or default next_step_id.
                # F-23: launch-кнопки `scene:<id>` перехватывает DialogRouter до FSM — переход не нужен.
                for btn in s.buttons:
                    if btn.value.startswith("scene:"):
                        continue
                    if btn.value not in s.transitions and not s.next_step_id and not s.complete:
                        raise ConfigError(
                            f"Step '{s.id}' choice button '{btn.value}' has no transition and no default next_step_id"
                        )

    def get_step(self, step_id: str) -> Optional[StepDefinition]:
        return self._step_map.get(step_id)

    async def resolve_seed(self, session: Any) -> Dict[str, Any]:
        """F-07 (RfI-06-3): предзаполнение `data` при входе в сцену.

        Dict-посев копируется глубоко (F-03: вызывающий код не должен mutable-ить
        сессию). Callable вызывается движком с сессией (арность адаптируется,
        sync/async — конвенция F-05/F-29). Исключение продукта, возврат не-dict и
        значение вне JSON-домена — `ConfigError`, а не тихий пустой вход.
        """
        if self.seed is None:
            return {}
        if not callable(self.seed):
            return copy.deepcopy(self.seed)
        try:
            params = inspect.signature(self.seed).parameters
            takes_arg = any(
                p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                for p in params.values()
            )
            result = self.seed(session) if takes_arg else self.seed()
            if inspect.isawaitable(result):
                result = await result
        except ConfigError:
            raise
        except Exception as e:  # продуктная ошибка посева не роняет роутер
            raise ConfigError(f"Scene '{self.id}' seed callable raised {e!r}") from e
        if not isinstance(result, dict):
            raise ConfigError(
                f"Scene '{self.id}' seed must return a dict, got {result!r}"
            )
        for k, v in result.items():
            if not isinstance(k, str):
                raise ConfigError(
                    f"Scene '{self.id}' seed: ключ {k!r} типа "
                    f"'{type(k).__name__}' — ключи посева должны быть str"
                )
            _check_json_value(v, f"Scene '{self.id}' seed[{k!r}]")
        return copy.deepcopy(result)

    async def landing_step(
        self, step: Optional[StepDefinition], data: Any
    ) -> Optional[StepDefinition]:
        """F-07 (RfI-06-3): шаг, на который реально приземляемся, начиная со `step`.

        Шаги с невыполненным `requires` пропускаются по `next_step_id` — движок
        их не рендерит и не паркуется на них. None — цепочка дошла до конца
        (шаг завершающий или без next): сцена считается завершённой, вызывающий
        даёт нейтральный ответ. Взаимно указывающие невыполнимые шаги — цикл
        пропуска — `ConfigError` (битая конфигурация).
        """
        cur = step
        for _ in range(len(self.steps) + 1):
            if cur is None:
                return None
            if await cur.meets_requires(data):
                return cur
            if cur.complete or not cur.next_step_id:
                return None
            cur = self.get_step(cur.next_step_id)
        raise ConfigError(
            f"Scene '{self.id}' has a skip loop: steps with unmet requires "
            "reference each other via next_step_id"
        )


def Scene(
    id: str,
    entry_commands: Sequence[str] = (),
    steps: Sequence[StepDefinition] = (),
    start_step_id: Optional[str] = None,
    lane: str = "user",
    on_complete: Optional[Callable[..., Any]] = None,
    restart_text: Optional[str] = None,
    seed: Optional[Union[SeedFunc, Dict[str, Any]]] = None,
) -> SceneDefinition:
    """
    Factory function matching MVP target API specification:
    info = Scene(
        id="info",
        entry_commands=("/info",),
        steps=(...),
    )
    """
    step_tuple = tuple(steps)
    start_id = start_step_id if start_step_id is not None else (step_tuple[0].id if step_tuple else "")
    norm_commands = tuple(cmd.strip() for cmd in entry_commands if cmd.strip())
    return SceneDefinition(
        id=id,
        entry_commands=norm_commands,
        start_step_id=start_id,
        restart_text=restart_text,
        steps=step_tuple,
        lane=lane,
        on_complete=on_complete,
        seed=seed,
    )
