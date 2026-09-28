"""
FSMEngine implementation for Bot Fork.
Validates input, transitions states, accumulates survey data, and appends mandatory branding.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from bot_fork.exceptions import ConfigError
from bot_fork.models import (
    Button,
    ErrorInfo,
    HandlerResult,
    IncomingEvent,
    OutgoingMessage,
    UserSession,
)
from bot_fork.scene import SceneDefinition, StepDefinition

BRANDING_SUFFIX = "\n\nMade with Bot Fork"
MAX_MESSAGE_LENGTH = 4096


def apply_branding(text: str) -> str:
    """
    Appends 'Made with Bot Fork' branding exactly once to visible text.
    Enforces maximum limit of 4096 characters.
    """
    clean_text = text.rstrip()
    if clean_text.endswith("Made with Bot Fork"):
        return clean_text
    branded = clean_text + BRANDING_SUFFIX
    if len(branded) > MAX_MESSAGE_LENGTH:
        raise ConfigError(
            f"Message with branding exceeds {MAX_MESSAGE_LENGTH} characters limit (len={len(branded)})"
        )
    return branded


class FSMEngine:
    """Finite State Machine engine for dialogue scenes."""

    def __init__(self) -> None:
        pass

    def process_step(
        self,
        event: IncomingEvent,
        session: UserSession,
        scene: SceneDefinition,
    ) -> HandlerResult:
        """
        Processes an incoming event against the active step of a session.
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
            # For choice: value comes from payload or fallback text matching button value or label
            chosen_val = event.payload
            if not chosen_val and event.text:
                # Fallback: check if text matches button value or label
                match = next(
                    (b.value for b in step.buttons if b.value == event.text or b.label.lower() == event.text.lower()),
                    None,
                )
                chosen_val = match

            allowed_values = {b.value for b in step.buttons}
            if not chosen_val or chosen_val not in allowed_values:
                return HandlerResult(
                    messages=(
                        OutgoingMessage(
                            chat_id=event.chat_id,
                            text=apply_branding("Эта кнопка уже недействительна. Повторите выбор."),
                            buttons=step.buttons,
                        ),
                    ),
                    session_after=session,
                    clear_session=False,
                    error=ErrorInfo(
                        code="INVALID_BUTTON",
                        message="Эта кнопка уже недействительна. Повторите выбор.",
                        retryable=True,
                    ),
                )

            value_to_save = chosen_val

        # 2. Advance state and store data
        new_session = session.clone()
        new_session.data[step.id] = value_to_save or ""

        # 3. Determine next step
        next_step_id: Optional[str] = None
        if step.input_type == "choice" and value_to_save in step.transitions:
            next_step_id = step.transitions[value_to_save]
        elif step.next_step_id:
            next_step_id = step.next_step_id

        # 4. Check if complete
        if step.complete or not next_step_id:
            # Build completion report
            report_text = self._build_completion_report(scene, new_session.data)
            return HandlerResult(
                messages=(
                    OutgoingMessage(
                        chat_id=event.chat_id,
                        text=apply_branding(report_text),
                    ),
                ),
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

        new_session.step_id = next_step.id
        return HandlerResult(
            messages=(
                OutgoingMessage(
                    chat_id=event.chat_id,
                    text=apply_branding(next_step.prompt),
                    buttons=next_step.buttons,
                ),
            ),
            session_after=new_session,
            clear_session=False,
            error=None,
        )

    def _build_completion_report(self, scene: SceneDefinition, data: Dict[str, str]) -> str:
        """
        Builds the final survey report.
        For the standard /info demo scene: formats name, role, goal cleanly.
        """
        if scene.id == "info":
            name = data.get("name", "—")
            role = data.get("role", "—")
            role_display_map = {
                "developer": "Разработчик",
                "freelancer": "Фрилансер",
                "other": "Другое",
            }
            role_label = role_display_map.get(role, role)
            goal = data.get("goal", "—")
            return (
                "Спасибо за ответы! Итоги анкеты:\n"
                f"• Имя: {name}\n"
                f"• Роль: {role_label}\n"
                f"• Цель проекта: {goal}"
            )

        # Generic summary
        lines = ["Анкета успешно завершена. Ваши ответы:"]
        for k, v in data.items():
            lines.append(f"• {k}: {v}")
        return "\n".join(lines)
