"""Regression tests for NEXUS Core's deterministic routing."""
import asyncio
import unittest

from backend.native_brain import _math_answer, _skill_relevant, answer


class NativeBrainRoutingTests(unittest.TestCase):
    def test_basic_arithmetic_is_answered_directly(self):
        self.assertEqual(_math_answer("what is 1 + 1?"), "**2**")
        self.assertEqual(_math_answer("145 × 27"), "**3915**")

    def test_percentage_calculation(self):
        self.assertEqual(_math_answer("calculate 25 percent of 800"), "**200**")

    def test_invalid_arithmetic_is_not_fabricated(self):
        self.assertIsNone(_math_answer("what is 1 / 0"))
        self.assertIsNone(_math_answer("hello"))

    def test_skill_retriever_score_is_not_overruled_by_strict_text_coverage(self):
        skill = {
            "name": "API design",
            "description": "Build maintainable HTTP services",
            "category": "backend",
            "tags": ["python", "rest"],
            "triggers": ["endpoint", "route"],
            "score": 0.09,
        }
        self.assertTrue(_skill_relevant(skill, "create a Python API with routes and validation"))

    def test_vague_coding_question_is_not_treated_as_a_build_specification(self):
        response = asyncio.run(answer("can you code an app?"))
        self.assertIn("Tell me what the application should do", response)
        self.assertNotIn("I researched this but could not generate runnable code", response)


if __name__ == "__main__":
    unittest.main()
