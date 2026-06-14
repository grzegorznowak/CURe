# ruff: noqa: F403, F405
from _subsequent_review_test_support import *  # noqa: F401, F403


class SubsequentReviewRuntimeMemoryTests(SubsequentReviewTestCase):
    def test_post_review_updates_shared_memory_from_completed_semantic_ledgers(self) -> None:
        from cure_subsequent_review.contracts import ModuleStatus
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.runtime import update_review_memory_after_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "work" / "subsequent"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "source_verification.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "success",
                        "status_reasons": [],
                        "rows": [
                            {
                                "row_id": "SV-0001",
                                "group_id": "G-0001",
                                "finding_ids": ["A-01"],
                                "source_state": "resolved_from_source",
                                "current_source_citations": [
                                    {"path": "app.py", "start_line": 10, "summary": "fixed"}
                                ],
                                "inspected_source_refs": ["app.py:10"],
                                "unavailable_reasons": [],
                                "provenance": {"rationale": "fresh source check"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (artifact_dir / "disposition_ledger.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "success",
                        "status_reasons": [],
                        "dispositions": [
                            {
                                "row_id": "D-0001",
                                "group_id": "G-0001",
                                "finding_ids": ["A-01"],
                                "action": "confirm_resolved",
                                "source_verification_row_id": "SV-0001",
                                "discussion_signal_row_ids": [],
                                "reconciliation_group_id": "G-0001",
                                "provenance": {"rationale": "confirmed fixed"},
                            }
                        ],
                        "degraded_findings": [],
                    }
                ),
                encoding="utf-8",
            )
            store = ReviewMemoryStore.for_pr(root=root / "pr", pr=PR())
            manifest_path = artifact_dir / "run_manifest.json"
            manifest_path.write_text(
                json.dumps({"schema_version": 1, "modules": {"review_memory_store": {"status": "disabled"}}}),
                encoding="utf-8",
            )

            record = update_review_memory_after_review(
                artifact_dir=artifact_dir,
                memory_store=store,
                current_head="abc123",
                run_provenance={"session_id": "run-1"},
                manifest_path=manifest_path,
            )

            self.assertEqual(record.module.value, "review_memory_store")
            self.assertEqual(record.status, ModuleStatus.SUCCESS)
            self.assertEqual(record.artifact_path, str(store.path))
            payload = json.loads(store.path.read_text(encoding="utf-8"))
            row = payload["findings"]["G-0001"]
            self.assertEqual(row["source_state"], "resolved_from_source")
            self.assertEqual(row["disposition"], "confirm_resolved")
            self.assertEqual(row["last_seen_head"], "abc123")
            self.assertEqual(row["run_provenance"]["session_id"], "run-1")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["modules"]["review_memory_store"]["status"], "success")
            self.assertEqual(manifest["modules"]["review_memory_store"]["artifact_path"], str(store.path))

    def test_post_review_memory_update_degrades_without_source_ledger(self) -> None:
        from cure_subsequent_review.contracts import ModuleStatus
        from cure_subsequent_review.memory_store import ReviewMemoryStore
        from cure_subsequent_review.runtime import update_review_memory_after_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "work" / "subsequent"
            artifact_dir.mkdir(parents=True)
            store = ReviewMemoryStore.for_pr(root=root / "pr", pr=PR())

            record = update_review_memory_after_review(
                artifact_dir=artifact_dir,
                memory_store=store,
                current_head="abc123",
                run_provenance={"session_id": "run-1"},
            )

            self.assertEqual(record.status, ModuleStatus.DEGRADED)
            self.assertIn("missing_artifact:source_verification.json", record.reasons)
            self.assertFalse(store.path.exists())


__all__ = ["SubsequentReviewRuntimeMemoryTests"]
