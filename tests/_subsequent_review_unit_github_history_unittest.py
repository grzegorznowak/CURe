# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewGithubHistoryTests(SubsequentReviewTestCase):
    def test_github_history_collects_events_thread_markers_and_degraded_statuses(self) -> None:
        pr = PR()

        def fetch(path: str) -> Any:
            if path.endswith("/issues/9999/comments"):
                return [{"id": 101, "html_url": "u1", "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}]
            if path.endswith("/pulls/9999/reviews"):
                return [{"id": 201, "html_url": "u2", "user": {"login": "maintainer"}, "body": "review body", "state": "COMMENTED", "submitted_at": "2026-01-02T00:00:00Z"}]
            if path.endswith("/pulls/9999/comments"):
                return [{"id": 301, "html_url": "u3", "user": {"login": "dev"}, "body": "line note", "path": "a.py", "line": 7, "thread_state": "unresolved", "created_at": "2026-01-03T00:00:00Z"}]
            raise AssertionError(path)

        artifact = collect_pr_discussion(pr=pr, fetch_json=fetch)
        self.assertEqual(artifact.status, ModuleStatus.SUCCESS)
        self.assertEqual(len(artifact.events), 3)
        self.assertEqual({event.kind for event in artifact.events}, {"issue_comment", "review", "review_comment"})
        self.assertIn("unresolved", [event.thread_state for event in artifact.events])
        self.assertTrue(all(marker.complete for marker in artifact.pagination))

        unavailable = collect_pr_discussion(pr=pr, fetch_json=lambda _path: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertEqual(unavailable.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_unavailable", unavailable.status_reasons)

        incomplete = collect_pr_discussion(
            pr=pr,
            fetch_json=lambda _path: {"items": [], "complete": False, "status": "discussion_incomplete"},
        )
        self.assertEqual(incomplete.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_incomplete", incomplete.status_reasons)

    def test_normalized_success_markers_include_fetch_provenance_and_malformed_dicts_degrade(self) -> None:
        root = Path(__file__).parent / "fixtures" / "subsequent_review"
        fixture = json.loads((root / "story_01_regression_goldens.json").read_text(encoding="utf-8"))["a21_github_history"]
        payloads = [fixture["normal_success_payload"], [], []]
        discussion = collect_pr_discussion(pr=PR(), fetch_json=lambda _path: payloads.pop(0))

        self.assertEqual(discussion.status, ModuleStatus.SUCCESS)
        self.assertEqual(len(discussion.events), 1)
        for marker in discussion.pagination:
            self.assertTrue(marker.endpoint)
            self.assertEqual(marker.fetch, "gh_api_list")
            self.assertEqual(marker.status, "complete")

        for malformed in fixture["malformed_payloads"]:
            with self.subTest(payload=malformed):
                discussion = collect_pr_discussion(pr=PR(), fetch_json=lambda _path, payload=malformed: payload)
                self.assertEqual(discussion.status, ModuleStatus.DEGRADED)
                self.assertEqual(discussion.events, ())
                self.assertIn(fixture["expected_malformed_reason"], discussion.status_reasons)
                self.assertTrue(all(not marker.complete for marker in discussion.pagination))
                self.assertEqual({marker.status for marker in discussion.pagination}, {"discussion_payload_malformed"})
                self.assertEqual({marker.cause for marker in discussion.pagination}, {"payload_shape"})

    def test_public_fallback_list_payload_marks_discussion_incomplete(self) -> None:
        auth_error = rf.ReviewflowSubprocessError(
            cmd=["gh", "api"],
            cwd=None,
            exit_code=1,
            stdout="",
            stderr="not authenticated; please run gh auth login",
        )
        with mock.patch.object(rf, "run_cmd", side_effect=auth_error), mock.patch.object(
            rf,
            "_github_public_api_payload",
            return_value=[{"id": 101, "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}],
        ):
            discussion = collect_pr_discussion(
                pr=PR(),
                fetch_json=lambda path: rf.gh_api_list(host="github.com", path=path, allow_public_fallback=True),
            )
        self.assertEqual(discussion.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_incomplete", discussion.status_reasons)
        self.assertTrue(discussion.events)
        self.assertTrue(all(not marker.complete for marker in discussion.pagination))

    def test_public_fallback_list_follows_rest_next_links_but_remains_degraded(self) -> None:
        class Page(list[dict[str, Any]]):
            next_path: str | None = None

        first = Page([{"id": 101}])
        first.next_path = "repos/example/demo/issues/9999/comments?page=2"
        second = Page([{"id": 102}])

        with mock.patch.object(rf, "_github_public_api_payload", side_effect=[first, second]) as payload:
            result = rf._github_public_api_list(path="repos/example/demo/issues/9999/comments")

        self.assertEqual([item["id"] for item in result["items"]], [101, 102])
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "discussion_incomplete")
        self.assertEqual(
            [call.kwargs["path"] for call in payload.call_args_list],
            ["repos/example/demo/issues/9999/comments", "repos/example/demo/issues/9999/comments?page=2"],
        )

    def test_github_list_unsupported_slurp_retries_authenticated_paginate_without_public_fallback(self) -> None:
        slurp_error = rf.ReviewflowSubprocessError(
            cmd=["gh", "api", "--hostname", "github.com", "repos/example/demo/issues/9999/comments", "--paginate", "--slurp"],
            cwd=None,
            exit_code=1,
            stdout="",
            stderr="unknown flag: --slurp",
        )
        no_slurp_result = rf.CommandResult(
            cmd=["gh", "api", "--hostname", "github.com", "repos/example/demo/issues/9999/comments", "--paginate"],
            cwd=None,
            exit_code=0,
            duration_seconds=0.0,
            stdout='[{"id": 1}]\n[{"id": 2}]\n',
            stderr="",
        )
        calls: list[list[str]] = []

        def run(cmd: list[str], **_kwargs: Any) -> rf.CommandResult:
            calls.append(cmd)
            if "--slurp" in cmd:
                raise slurp_error
            return no_slurp_result

        with mock.patch.object(rf, "run_cmd", side_effect=run), mock.patch.object(
            rf, "_github_public_api_payload", side_effect=AssertionError("public fallback should not be used")
        ):
            previous = getattr(rf, "_GH_API_SLURP_SUPPORTED", None)
            try:
                rf._GH_API_SLURP_SUPPORTED = None
                payload = rf.gh_api_list(
                    host="github.com",
                    path="repos/example/demo/issues/9999/comments",
                    allow_public_fallback=True,
                )
                second_payload = rf.gh_api_list(
                    host="github.com",
                    path="repos/example/demo/issues/9999/comments",
                    allow_public_fallback=True,
                )
            finally:
                rf._GH_API_SLURP_SUPPORTED = previous

        self.assertEqual(payload, [{"id": 1}, {"id": 2}])
        self.assertEqual(second_payload, [{"id": 1}, {"id": 2}])
        self.assertEqual(["--slurp" in call for call in calls], [True, False, False])

    def test_github_list_slurp_failure_public_fallback_preserves_cause_detail(self) -> None:
        slurp_error = rf.ReviewflowSubprocessError(
            cmd=["gh", "api", "--paginate", "--slurp"],
            cwd=None,
            exit_code=1,
            stdout="",
            stderr="unknown flag: --slurp",
        )

        def public_payload(*, path: str) -> list[dict[str, Any]]:
            return [{"id": path.rsplit("/", 1)[-1], "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}]

        with mock.patch.object(rf, "run_cmd", side_effect=slurp_error), mock.patch.object(
            rf, "_github_public_api_payload", side_effect=public_payload
        ):
            discussion = collect_pr_discussion(
                pr=PR(),
                fetch_json=lambda path: rf.gh_api_list(host="github.com", path=path, allow_public_fallback=True),
            )

        self.assertEqual(discussion.status, ModuleStatus.DEGRADED)
        self.assertIn("discussion_incomplete", discussion.status_reasons)
        self.assertEqual(len(discussion.events), 3)
        marker_payloads = [marker.to_json() for marker in discussion.pagination]
        self.assertTrue(all(marker["endpoint"].endswith(("/comments", "/reviews")) for marker in marker_payloads))
        self.assertTrue(all(marker["cause"] == "cli_unsupported_flag" for marker in marker_payloads))
        self.assertTrue(all("unknown flag" in marker["stderr"] for marker in marker_payloads))

    def test_github_list_slurp_command_does_not_mask_api_rate_or_transport_failures(self) -> None:
        cases = (
            ("HTTP 500 Internal Server Error", "api_status"),
            ("API rate limit exceeded", "api_rate_limit"),
            ("connection timed out", "transport"),
        )

        def public_payload(*, path: str) -> list[dict[str, Any]]:
            return [{"id": path.rsplit("/", 1)[-1], "user": {"login": "cure-bot"}, "body": "CURe review", "created_at": "2026-01-01T00:00:00Z"}]

        for stderr, expected_cause in cases:
            with self.subTest(stderr=stderr):
                error = rf.ReviewflowSubprocessError(
                    cmd=["gh", "api", "--hostname", "github.com", "repos/example/demo/issues/9999/comments", "--paginate", "--slurp"],
                    cwd=None,
                    exit_code=1,
                    stdout="",
                    stderr=stderr,
                )
                with mock.patch.object(rf, "run_cmd", side_effect=error), mock.patch.object(
                    rf, "_github_public_api_payload", side_effect=public_payload
                ):
                    payload = rf.gh_api_list(
                        host="github.com",
                        path="repos/example/demo/issues/9999/comments",
                        allow_public_fallback=True,
                    )
                self.assertIsInstance(payload, dict)
                self.assertEqual(payload["cause"], expected_cause)
                self.assertIn("--slurp", payload["command"])

                discussion = collect_pr_discussion(pr=PR(), fetch_json=lambda _path, err=error: (_ for _ in ()).throw(err))
                marker_payloads = [marker.to_json() for marker in discussion.pagination]
                self.assertEqual({marker["cause"] for marker in marker_payloads}, {expected_cause})
                self.assertTrue(all("--slurp" in marker["command"] for marker in marker_payloads))


__all__ = ["SubsequentReviewGithubHistoryTests"]
