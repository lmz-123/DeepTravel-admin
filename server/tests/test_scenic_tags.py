from __future__ import annotations

import unittest

from content_graph import validate_graph
from content_schema import normalize_experience_tags
from models import Stop, StoryFragment
from schemas import StopInput


class ScenicTagContractTests(unittest.TestCase):
    def test_normalizer_accepts_examples_and_future_tags(self):
        self.assertEqual(
            normalize_experience_tags(
                [" 安静 ", "", "安静", "海边或自然景观", "未来新标签"]
            ),
            ["安静", "海边或自然景观", "未来新标签"],
        )
        with self.assertRaisesRegex(ValueError, "最多 8 个"):
            normalize_experience_tags([f"标签-{index}" for index in range(9)])
        with self.assertRaisesRegex(ValueError, "最多 24 个字符"):
            normalize_experience_tags(["长" * 25])

    def test_stop_input_uses_editorial_field_and_model_uses_json_column(self):
        payload = StopInput(
            route_id="route-1",
            position=1,
            title="城门",
            kicker="抬头看",
            address="旧城",
            latitude=22.5,
            longitude=113.9,
            story_title="城门故事",
            story_body="故事",
            image="images/stop.jpg",
            insight="观察",
            experience_tags=[" 老建筑 ", "老建筑", "城市历史"],
        )
        self.assertEqual(payload.experience_tags, ["老建筑", "城市历史"])
        self.assertIn("experience_tags_json", Stop.__table__.columns)
        self.assertIn("experience_tags_json", StoryFragment.__table__.columns)
        self.assertNotIn("experience_tags_json", payload.model_dump())

    def test_graph_normalizes_fragment_and_nested_stop_tags(self):
        graph = {
            "route": {},
            "story_arc": {},
            "fragments": [
                {
                    "position": 1,
                    "experience_tags": [" 安静 ", "安静", "未来标签"],
                    "stop": {"experience_tags": [" 老建筑 "]},
                }
            ],
        }
        validate_graph(graph, {})
        self.assertEqual(
            graph["fragments"][0]["experience_tags"], ["安静", "未来标签"]
        )
        self.assertEqual(
            graph["fragments"][0]["stop"]["experience_tags"], ["老建筑"]
        )

        invalid = {
            "route": {},
            "story_arc": {},
            "fragments": [{"position": 1, "experience_tags": ["过长" * 13]}],
        }
        result = validate_graph(invalid, {})
        self.assertIn(
            "fragments[0].experience_tags",
            {item["path"] for item in result["errors"]},
        )


if __name__ == "__main__":
    unittest.main()
