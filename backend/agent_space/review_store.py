"""GitHub-style review store for proposed diffs."""

from __future__ import annotations

import difflib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT, REVIEWS_DIR, ensure_layout
from .snapshot_store import SnapshotStore


class ReviewStore:
    """Persists proposed file changes as review records."""

    def __init__(self) -> None:
        ensure_layout()
        self._cache: dict[str, dict[str, Any]] = {}

    def _path(self, review_id: str) -> Path:
        return REVIEWS_DIR / f"{review_id}.json"

    def create_review(
        self,
        *,
        run_id: str,
        objective: str,
        changes: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        review_id = str(uuid.uuid4())
        diff = self._build_diff(changes)
        summary = self._build_summary(changes)
        payload = {
            "id": review_id,
            "run_id": run_id,
            "objective": objective,
            "status": "pending",
            "created_at": time.time(),
            "updated_at": time.time(),
            "changes": changes,
            "diff": diff,
            "summary": summary,
            "metadata": metadata or {},
            "snapshot_id": None,
            "rejection_reason": None,
        }
        self._write(payload)
        return payload

    def list_reviews(self, limit: int = 200) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        for path in REVIEWS_DIR.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                row = self._ensure_summary(row)
                reviews.append(row)
                review_id = str(row.get("id", ""))
                if review_id:
                    self._cache[review_id] = dict(row)
            except Exception:
                continue
        for cached in self._cache.values():
            if not any(str(row.get("id")) == str(cached.get("id")) for row in reviews):
                reviews.append(self._ensure_summary(dict(cached)))
        reviews.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
        return reviews[: max(1, limit)]

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        cached = self._cache.get(review_id)
        if cached is not None:
            return dict(cached)
        path = self._path(review_id)
        if not path.exists():
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        row = self._ensure_summary(row)
        self._cache[review_id] = dict(row)
        return row

    def approve(self, review_id: str) -> dict[str, Any]:
        review = self._require(review_id)
        review["status"] = "approved"
        review["updated_at"] = time.time()
        self._save(review)
        return review

    def reject(self, review_id: str, reason: str = "") -> dict[str, Any]:
        review = self._require(review_id)
        review["status"] = "rejected"
        review["rejection_reason"] = reason
        review["updated_at"] = time.time()
        self._save(review)
        return review

    def apply(
        self,
        review_id: str,
        *,
        snapshot_store: SnapshotStore,
        create_git_checkpoint: bool = False,
    ) -> dict[str, Any]:
        review = self._require(review_id)
        if review["status"] != "approved":
            raise RuntimeError(f"Cannot apply review in status '{review['status']}'.")

        changes = list(review.get("changes", []))
        snapshot = snapshot_store.create_snapshot(
            run_id=review.get("run_id", "manual"),
            note=f"Pre-apply snapshot for review {review_id}",
            files=changes,
            create_git_checkpoint=create_git_checkpoint,
        )

        for change in changes:
            rel_path = str(change.get("path", "")).replace("\\", "/")
            target = (PROJECT_ROOT / rel_path).resolve()
            if not str(target).startswith(str(PROJECT_ROOT.resolve())):
                raise RuntimeError(f"Refusing to apply unsafe path: {rel_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.get("new_content", ""), encoding="utf-8")

        review["status"] = "applied"
        review["updated_at"] = time.time()
        review["snapshot_id"] = snapshot["id"]
        self._save(review)
        return review

    def mark_undone(self, review_id: str, reason: str = "") -> dict[str, Any]:
        review = self._require(review_id)
        if review.get("status") != "applied":
            raise RuntimeError(f"Cannot undo review in status '{review.get('status')}'.")

        metadata = review.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        undo_history = metadata.get("undo_history")
        if not isinstance(undo_history, list):
            undo_history = []
        undo_history.append(
            {
                "at": time.time(),
                "snapshot_id": review.get("snapshot_id"),
                "reason": reason,
            }
        )
        metadata["undo_history"] = undo_history[-20:]
        review["metadata"] = metadata
        review["status"] = "approved"
        review["updated_at"] = time.time()
        self._save(review)
        return review

    def _build_diff(self, changes: list[dict[str, Any]]) -> str:
        patches: list[str] = []
        for change in changes:
            rel = str(change.get("path", "unknown"))
            old_text = change.get("old_content") or ""
            new_text = change.get("new_content") or ""
            old_lines = old_text.splitlines(keepends=True)
            new_lines = new_text.splitlines(keepends=True)
            patch = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
                lineterm="",
            )
            patches.append("\n".join(patch))
        return "\n\n".join(patches).strip()

    def _build_summary(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        total_added = 0
        total_removed = 0
        reason_counts: dict[str, int] = {}

        for change in changes:
            rel = str(change.get("path", "unknown")).replace("\\", "/")
            reason = str(change.get("reason", "unknown")).strip() or "unknown"
            old_text = str(change.get("old_content") or "")
            new_text = str(change.get("new_content") or "")
            diff_lines = list(difflib.ndiff(old_text.splitlines(), new_text.splitlines()))
            added = sum(1 for line in diff_lines if line.startswith("+ "))
            removed = sum(1 for line in diff_lines if line.startswith("- "))
            total_added += added
            total_removed += removed
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            files.append(
                {
                    "path": rel,
                    "reason": reason,
                    "added": int(added),
                    "removed": int(removed),
                }
            )

        return {
            "file_count": len(files),
            "added_lines": int(total_added),
            "removed_lines": int(total_removed),
            "reason_counts": reason_counts,
            "files": files,
        }

    def _ensure_summary(self, review: dict[str, Any]) -> dict[str, Any]:
        if isinstance(review.get("summary"), dict):
            return review
        changes = list(review.get("changes", []))
        review["summary"] = self._build_summary(changes)
        return review

    def _save(self, review: dict[str, Any]) -> None:
        self._write(review)

    def _write(self, review: dict[str, Any], retries: int = 3, delay_seconds: float = 0.05) -> None:
        review_id = str(review["id"])
        payload = json.dumps(review, indent=2)
        path = self._path(review_id)
        for attempt in range(retries + 1):
            try:
                path.write_text(payload, encoding="utf-8")
                self._cache[review_id] = dict(review)
                return
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                self._cache[review_id] = dict(review)
                return
            except Exception:
                self._cache[review_id] = dict(review)
                return

    def _require(self, review_id: str) -> dict[str, Any]:
        review = self.get_review(review_id)
        if review is None:
            raise FileNotFoundError(f"Review '{review_id}' not found.")
        return review
