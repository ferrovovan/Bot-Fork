"""
FSMEngine implementation for Bot Fork.
Validates input, transitions states, accumulates survey data, and appends mandatory branding.
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from bot_fork.exceptions import ConfigError

logger = logging.getLogger("bot_fork")
from bot_fork.builder import ButtonBuilder
from bot_fork.models import (
    Button,
    ErrorInfo,
    HandlerResult,
    IncomingEvent,
    OutgoingMessage,
    Reject,
    UserSession,
)
from bot_fork.scene import SceneDefinition, StepDefinition

BRANDING_SUFFIX = ""
BRANDING_WATERMARK = "\n\nMade with Bot Fork"
MAX_MESSAGE_LENGTH = 4096


def _action_takes_session(action) -> bool:
    """True, если экшен объявляет третий аргумент (session) — F-04 контекст действия."""
    try:
        sig = inspect.signature(action)
    except (TypeError, ValueError):
        return False
    positional = [
        p
        for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 3


def apply_branding(text: str) -> str:
    """
    Validates message length limit (4096 characters).
    Proprietary watermark suffix removed in version 1.0 (clean text).
    F-16: env BOT_FORK_BRANDING=on/off (default off) — явный флаг возврата водного знака.
    """
    clean_text = text.rstrip()
    if os.environ.get("BOT_FORK_BRANDING", "off").strip().lower() in ("on", "1", "true"):
        clean_text = clean_text + BRANDING_WATERMARK
    if len(clean_text) > MAX_MESSAGE_LENGTH:
        raise ConfigError(
            f"Message exceeds {MAX_MESSAGE_LENGTH} characters limit (len={len(clean_text)})"
        )
    return clean_text


class FSMEngine:
    """Finite State Machine engine for dialogue scenes."""

    def __init__(self) -> None:
        pass

    async def process_step(
        self,
        event: IncomingEvent,
        session: UserSession,
        scene: SceneDefinition,
    ) -> HandlerResult:
        """
        Processes an incoming event against the active step of a session.
        Async (F-04): validators и actions шага могут быть корутинами.
        """
        step = scene.get_step(session.step_id)
        if step is None:
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding("Произошла внутренняя ошибка: шаг не найден."),
                    ),
                ),
                clear_session=True,
                error=ErrorInfo(code="INTERNAL_ERROR", message="Step not found in scene", retryable=False),
            )

        # 1. Validate & extract answer
        value_to_save: Optional[str] = None

        if step.input_type == "text" and event.payload:
            # Нажатие кнопки, которая не относится к текущему шагу (например,
            # «О проекте» посреди анкеты): честный INVALID_BUTTON, а не «пустой ответ».
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding("Эта кнопка не из текущего шага. Наберите /cancel, чтобы сбросить диалог."),
                    ),
                ),
                session_after=session,
                clear_session=False,
                error=ErrorInfo(code="INVALID_BUTTON", message="Payload at text step", retryable=True),
            )

        if step.input_type == "text":
            raw_text = event.text or ""
            trimmed = raw_text.strip()
            if not trimmed:
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text=apply_branding("Ответ не должен быть пустым. Попробуйте ещё раз."),
                        ),
                    ),
                    session_after=session,
                    clear_session=False,
                    error=ErrorInfo(
                        code="INVALID_INPUT",
                        message="Ответ не должен быть пустым. Попробуйте ещё раз.",
                        retryable=True,
                    ),
                )

            # Check custom validator if provided
            if step.validator is not None:
                try:
                    res = step.validator(trimmed)
                    if inspect.isawaitable(res):  # async-валидатор (F-04)
                        res = await res
                    is_valid = True
                    err_msg = "Некорректный ввод. Попробуйте ещё раз."
                    if isinstance(res, tuple) and len(res) == 2:
                        is_valid, err_msg = bool(res[0]), str(res[1])
                    elif isinstance(res, bool):
                        is_valid = res

                    if not is_valid:
                        return HandlerResult(
                            messages=(
                                OutgoingMessage(
                                    chat_id=event.chat_id,
                                    text=apply_branding(err_msg),
                                ),
                            ),
                            session_after=session,
                            clear_session=False,
                            error=ErrorInfo(code="INVALID_INPUT", message=err_msg, retryable=True),
                        )
                except Exception as e:
                    return HandlerResult(
                        messages=(
                            OutgoingMessage(
                                chat_id=event.chat_id,
                                text=apply_branding(f"Ошибка проверки ввода: {e}"),
                            ),
                        ),
                        session_after=session,
                        clear_session=False,
                        error=ErrorInfo(code="INVALID_INPUT", message=str(e), retryable=True),
                    )

            value_to_save = trimmed

        elif step.input_type == "choice":
            # F-29: клавиатура может быть функцией от сессии — матчим по живой клавиатуре.
            step_buttons = await step.resolve_buttons(session)
            # For choice: value comes from payload or fallback text matching button value or label
            chosen_val = event.payload
            if not chosen_val and event.text:
                # Fallback: check if text matches button value or label
                match = next(
                    (b.value for b in step_buttons if b.value == event.text or b.label.lower() == event.text.lower()),
                    None,
                )
                chosen_val = match

            allowed_values = {b.value for b in step_buttons}
            if not chosen_val or chosen_val not in allowed_values:
                # F-30: два разных побега — и разные слова. Прислан payload, но
                # его нет среди живых кнопок → кнопка устарела. Текст без payload
                # → игрок ушёл в свободный ввод: его зовут обратно, а не ругают.
                if event.payload:
                    reply = "Эта кнопка уже недействительна. Повторите выбор."
                    code = "INVALID_BUTTON"
                else:
                    reply = "Давайте так: выберите вариант кнопкой ниже 👇 Я их понимаю лучше всего."
                    code = "NEED_BUTTON"
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text=apply_branding(reply),
                            buttons=step_buttons,
                        ),
                    ),
                    session_after=session,
                    clear_session=False,
                    error=ErrorInfo(code=code, message=reply, retryable=True),
                )

            value_to_save = chosen_val

        # 2. Advance state and store data
        new_session = session.clone()
        new_session.data[step.id] = value_to_save or ""

        # 2.5 Шаг-действие (F-04): сид-эффект после валидного ответа — вызов сервиса
        # продукта (запись голоса, сохранение согласия). Действие получает значение и
        # словарь данных (может его дополнять), может быть async. Строка-возврат —
        # причина отказа: данные НЕ сохраняются, игрок остаётся на шаге.
        # F-28: Reject(text, buttons) — тот же отказ, но под текстом свои кнопки.
        if step.action is not None:
            try:
                action_args: Tuple = (value_to_save or "", new_session.data)
                # F-04: контекст действия — экшены с третьим параметром получают session
                if _action_takes_session(step.action):
                    action_args += (new_session,)
                action_res = step.action(*action_args)
                if inspect.isawaitable(action_res):
                    action_res = await action_res
            except Exception as e:
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text=apply_branding(f"Не получилось сохранить ответ. Попробуйте ещё раз."),
                        ),
                    ),
                    session_after=session,
                    clear_session=False,
                    error=ErrorInfo(code="ACTION_ERROR", message=str(e), retryable=True),
                )
            if isinstance(action_res, Reject):
                # F-28: отказ со своими кнопками (обычно launch `scene:<id>`) —
                # под текстом отказа то, чем игрок может выйти из тупика.
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text=apply_branding(action_res.text),
                            buttons=ButtonBuilder.keyboard(*action_res.buttons),
                        ),
                    ),
                    session_after=session,
                    clear_session=False,
                    error=ErrorInfo(code="ACTION_REJECTED", message=action_res.text, retryable=True),
                )
            if isinstance(action_res, str) and action_res.strip():
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text=apply_branding(action_res),
                            buttons=await step.resolve_buttons(session),
                        ),
                    ),
                    session_after=session,
                    clear_session=False,
                    error=ErrorInfo(code="ACTION_REJECTED", message=action_res, retryable=True),
                )

        # 3. Determine next step
        next_step_id: Optional[str] = None
        if step.input_type == "choice" and value_to_save in step.transitions:
            next_step_id = step.transitions[value_to_save]
        elif step.next_step_id:
            next_step_id = step.next_step_id

        # 4. Check if complete
        if step.complete or not next_step_id:
            # F-09: сцена сама решает, чем завершаться (текст/сообщения/тишина).
            messages = await self._completion_messages(scene, new_session, event.chat_id)
            return HandlerResult(
                messages=tuple(messages),
                session_after=None,
                clear_session=True,
                error=None,
            )

        # 5. Move to next step
        next_step = scene.get_step(next_step_id)
        if next_step is None:
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding("Сценарий успешно завершён."),
                    ),
                ),
                session_after=None,
                clear_session=True,
            )

        # F-25: инфо-шаги не требуют ввода — печатаем и идём по цепочке дальше,
        # пока не упрёмся в шаг с вводом (сессия встаёт на него) или в конец сцены.
        messages: List[OutgoingMessage] = []
        cur = next_step
        for _ in range(10):  # защита от цикла info→info
            # F-07 (RfI-06-3): шаг с невыполненным requires — не место посадки:
            # пропускаем по next_step_id; дошли до конца — нейтральное завершение.
            cur = await scene.landing_step(cur, new_session.data)
            if cur is None:
                messages.extend(
                    await self._completion_messages(scene, new_session, event.chat_id)
                )
                return HandlerResult(messages=tuple(messages), session_after=None,
                                     clear_session=True, error=None)
            new_session.step_id = cur.id
            messages.append(
                OutgoingMessage(
                    chat_id=event.chat_id,
                    text=apply_branding(await cur.arender_prompt(new_session)),
                    buttons=await cur.resolve_buttons(new_session),
                )
            )
            if cur.input_type != "info":
                return HandlerResult(
                    messages=tuple(messages),
                    session_after=new_session,
                    clear_session=False,
                    error=None,
                )
            if cur.action is not None:
                action_args: Tuple = ("", new_session.data)
                if _action_takes_session(cur.action):
                    action_args += (new_session,)
                res = cur.action(*action_args)
                if inspect.isawaitable(res):
                    await res
            if cur.complete or not cur.next_step_id:
                messages.extend(await self._completion_messages(scene, new_session, event.chat_id))
                return HandlerResult(messages=tuple(messages), session_after=None,
                                     clear_session=True, error=None)
            nxt = scene.get_step(cur.next_step_id)
            if nxt is None:
                messages.append(OutgoingMessage(chat_id=event.chat_id,
                                                text=apply_branding("Сценарий успешно завершён.")))
                return HandlerResult(messages=tuple(messages), session_after=None,
                                     clear_session=True, error=None)
            cur = nxt
        return HandlerResult(
            messages=(OutgoingMessage(chat_id=event.chat_id,
                                      text=apply_branding("Внутренняя ошибка: цикл инфо-шагов.")),),
            session_after=None, clear_session=True,
            error=ErrorInfo(code="INTERNAL_ERROR", message="info-step loop", retryable=False),
        )

    async def _completion_messages(
        self, scene: SceneDefinition, session: Any, chat_id: str
    ) -> List[OutgoingMessage]:
        """F-09: on_complete сцены (async ok) → сообщения; ошибка — generic-отчёт, молчание — допустимо."""
        if scene.on_complete is not None:
            try:
                result = scene.on_complete(session)
                if inspect.isawaitable(result):
                    result = await result
            except Exception:
                logger.exception("Scene '%s' on_complete crashed; falling back to generic report", scene.id)
            else:
                if result is None:
                    return []
                items = result if isinstance(result, (list, tuple)) else [result]
                messages: List[OutgoingMessage] = []
                for item in items:
                    if isinstance(item, OutgoingMessage):
                        messages.append(item if item.chat_id else OutgoingMessage(chat_id=chat_id, text=item.text, buttons=item.buttons))
                    elif isinstance(item, str) and item:
                        messages.append(OutgoingMessage(chat_id=chat_id, text=apply_branding(item)))
                    else:
                        raise ConfigError(
                            f"Scene '{scene.id}' on_complete returned unsupported item {item!r}"
                        )
                return messages
        return [OutgoingMessage(chat_id=chat_id, text=apply_branding(self._build_completion_report(scene, session.data)))]

    def _build_completion_report(self, scene: SceneDefinition, data: Dict[str, str]) -> str:
        """Generic-отчёт для сцен без on_complete — нейтральный, без значений данных (Д-2, v1.12.3)."""
        # ПДн в чат не выводим (SOUL продукта, данные.md п.7): ни ключи, ни
        # значения session.data в текст не попадают — только нейтральная строка.
        # Сцене с персональными данными нужен свой финал: on_complete (F-09) —
        # строка/список (текст решает сама сцена) или None (молчание).
        return "Сценарий завершён."
