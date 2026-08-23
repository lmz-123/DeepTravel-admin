from __future__ import annotations

import unittest

from content_graph import validate_graph
from content_schema import (
    normalize_experience_tags,
    normalize_footprint_summary_options,
)
from models import Stop, StoryFragment
from multi_city_import import _values, _values_preview
from schemas import StopInput


class ScenicTagContractTests(unittest.TestCase):
    def test_footprint_summary_options_require_stable_unique_ids(self):
        self.assertEqual(
            normalize_footprint_summary_options(
                [
                    {"id": "old-wall", "text": "我留意到墙面的时间层次"},
                    {"id": "daily-life", "text": "城市历史也藏在日常里"},
                ]
            ),
            [
                {"id": "old-wall", "text": "我留意到墙面的时间层次"},
                {"id": "daily-life", "text": "城市历史也藏在日常里"},
            ],
        )
        with self.assertRaisesRegex(ValueError, "id 不能重复"):
            normalize_footprint_summary_options(
                [{"id": "same", "text": "一"}, {"id": "same", "text": "二"}]
            )

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
        self.assertIn("footprint_editorial_summary", StoryFragment.__table__.columns)
        self.assertIn("footprint_summary_options_json", StoryFragment.__table__.columns)
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

    def test_graph_reports_exact_duplicate_footprint_option_path(self):
        graph = {
            "route": {},
            "story_arc": {},
            "fragments": [
                {
                    "position": 1,
                    "experience_tags": ["未来中文主题"],
                    "footprint_editorial_summary": "一段经过审核的概括",
                    "footprint_summary_options": [
                        {"id": "same", "text": "概括一"},
                        {"id": "same", "text": "概括二"},
                    ],
                }
            ],
        }
        result = validate_graph(graph, {})
        self.assertIn(
            "fragments[0].footprint_summary_options",
            {item["path"] for item in result["errors"]},
        )
        self.assertEqual(graph["fragments"][0]["experience_tags"], ["未来中文主题"])

    def test_graph_bounds_footprint_editorial_summary_with_exact_path(self):
        graph = {
            "route": {},
            "story_arc": {},
            "fragments": [
                {
                    "position": 1,
                    "footprint_editorial_summary": "长" * 601,
                    "footprint_summary_options": [
                        {"id": "bounded", "text": "一条简短概括"}
                    ],
                }
            ],
        }
        result = validate_graph(graph, {})
        self.assertIn(
            "fragments[0].footprint_editorial_summary",
            {item["path"] for item in result["errors"]},
        )

    def test_old_draft_packages_warn_and_publishable_blank_fields_fail(self):
        draft = validate_graph(
            {"route": {}, "story_arc": {}, "fragments": [{"position": 1}]},
            {},
        )
        warning_paths = {item["path"] for item in draft["warnings"]}
        self.assertIn("fragments[0].footprint_editorial_summary", warning_paths)
        self.assertIn("fragments[0].footprint_summary_options", warning_paths)

        published = validate_graph(
            {
                "route": {"content_status": "published"},
                "story_arc": {},
                "fragments": [{"position": 1}],
            },
            {},
        )
        error_paths = {item["path"] for item in published["errors"]}
        self.assertIn("fragments[0].footprint_editorial_summary", error_paths)
        self.assertIn("fragments[0].footprint_summary_options", error_paths)

    def test_import_preview_and_persistence_share_footprint_fields(self):
        record = {
            "id": "fragment-1",
            "experience_tags": ["未来中文主题"],
            "footprint_editorial_summary": "同一份审核概括",
            "footprint_summary_options": [
                {"id": "same-copy", "text": "同一条短总结"}
            ],
            "review_state": "reviewed",
        }
        persisted = _values("story_fragments", record)
        previewed = _values_preview("story_fragments", record)
        self.assertEqual(
            persisted["footprint_editorial_summary"],
            previewed["footprint_editorial_summary"],
        )
        self.assertEqual(
            persisted["footprint_summary_options_json"],
            previewed["footprint_summary_options_json"],
        )
        self.assertEqual(persisted["experience_tags_json"], ["未来中文主题"])
        self.assertEqual(persisted["review_state"], "in_review")


if __name__ == "__main__":
    unittest.main()
