from __future__ import annotations

import tempfile

from _subsequent_review_test_support import Path, SubsequentReviewTestCase, SubsequentReviewModule, json


class SubsequentReviewLandmarkTraceTests(SubsequentReviewTestCase):
    def test_landmark_trace_runner_matches_deterministic_golden(self) -> None:
        from cure_subsequent_review.landmark_trace import run_landmark_trace

        fixture_dir = Path(__file__).parent / "fixtures" / "subsequent_review" / "landmark_trace"
        with tempfile.TemporaryDirectory() as tmp:
            result = run_landmark_trace(fixture_dir=fixture_dir, output_dir=Path(tmp))
            expected = json.loads((fixture_dir / "golden" / "landmark_trace_summary.json").read_text(encoding="utf-8"))

            self.assertEqual(result.summary, expected)
            self.assertEqual(result.record.module, SubsequentReviewModule.LANDMARK_TRACE_RUNNER)
            self.assertEqual((Path(tmp) / "work" / "subsequent" / "landmark_trace_summary.json").read_text(encoding="utf-8"), json.dumps(expected, indent=2, sort_keys=True) + "\n")

    def test_landmark_trace_runner_is_test_only_and_not_runtime_registered(self) -> None:
        from cure_subsequent_review.semantic_pipeline import MODULE_REGISTRY

        self.assertNotIn(SubsequentReviewModule.LANDMARK_TRACE_RUNNER, MODULE_REGISTRY)
