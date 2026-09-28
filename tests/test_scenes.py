"""
Test suite for T3: SceneDefinition, StepDefinition, and configuration checks.
"""

import unittest
from bot_fork.exceptions import ConfigError
from bot_fork.models import Button
from bot_fork.scene import Scene, Step


class TestScenes(unittest.TestCase):
    def test_valid_scene(self):
        scene = Scene(
            id="test_scene",
            entry_commands=("/test",),
            steps=(
                Step.text("step1", "Вопрос 1", next="step2"),
                Step.choice(
                    "step2",
                    "Вопрос 2",
                    buttons=(Button("Да", "yes"), Button("Нет", "no")),
                    transitions={"yes": "step3", "no": "step3"},
                ),
                Step.text("step3", "Вопрос 3", complete=True),
            ),
        )
        self.assertEqual(scene.id, "test_scene")
        self.assertEqual(scene.start_step_id, "step1")
        self.assertEqual(len(scene.steps), 3)

    def test_duplicate_step_id_rejected(self):
        with self.assertRaises(ConfigError):
            Scene(
                id="dup_scene",
                steps=(
                    Step.text("step1", "Промпт 1", next="step1"),
                    Step.text("step1", "Промпт 2", complete=True),
                ),
            )

    def test_broken_transition_rejected(self):
        # Target step 'non_existent' does not exist
        with self.assertRaises(ConfigError):
            Scene(
                id="broken_scene",
                steps=(
                    Step.text("step1", "Промпт", next="non_existent"),
                ),
            )

    def test_broken_choice_transition_rejected(self):
        with self.assertRaises(ConfigError):
            Scene(
                id="broken_choice",
                steps=(
                    Step.choice(
                        "step1",
                        "Выберите",
                        buttons=(Button("A", "a"),),
                        transitions={"a": "missing_step"},
                    ),
                ),
            )

    def test_choice_without_transition_or_next_rejected(self):
        # Button value 'b' has no transition and step has no next
        with self.assertRaises(ConfigError):
            Scene(
                id="missing_trans",
                steps=(
                    Step.choice(
                        "step1",
                        "Выберите",
                        buttons=(Button("A", "a"), Button("B", "b")),
                        transitions={"a": "step2"},
                    ),
                    Step.text("step2", "Конец", complete=True),
                ),
            )

    def test_more_than_4_buttons_rejected(self):
        buttons = tuple(Button(f"L{i}", f"v{i}") for i in range(5))
        with self.assertRaises(ConfigError):
            Step.choice("step1", "Prompt", buttons=buttons, complete=True)

    def test_more_than_50_steps_rejected(self):
        steps = [Step.text(f"s{i}", f"Prompt {i}", next=f"s{i+1}") for i in range(51)]
        steps[-1] = Step.text("s50", "Final", complete=True)
        with self.assertRaises(ConfigError):
            Scene("too_many", steps=steps)


if __name__ == "__main__":
    unittest.main()
