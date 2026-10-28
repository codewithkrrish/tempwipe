"""Cleaning: turn a scan report into deletions, carefully.

Rules I refuse to bend:
- The target root itself is never deleted, only things inside it.
- Nothing outside a scanned target is ever touched.
- Dry-run is the default mode of ``plan``; real deletion only happens
  when the caller passes ``dry_run=False`` explicitly.
- Empty directories are removed deepest-first, so parents only go
  once their children are gone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .scan import TargetReport


class UnsafeDeleteError(ValueError):
    """Raised when a deletion request would touch something it must not."""


@dataclass
class DeletionResult:
    """Outcome of one clean run."""

    files_deleted: int = 0
    dirs_deleted: int = 0
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)


def _check_inside(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise UnsafeDeleteError(f"refusing to delete outside target root: {path}")
    if path.resolve() == root.resolve():
        raise UnsafeDeleteError(f"refusing to delete target root itself: {path}")


def clean_report(report: TargetReport, *, dry_run: bool) -> DeletionResult:
    """Delete (or pretend to delete) everything in *report*.

    Files are removed first; then their parent directories, deepest
    first, but only if now empty. Directories that still hold files
    the scan skipped (symlinks, excluded names, fresh files) are left
    alone — ``rmdir`` failing on a non-empty dir is expected, not an
    error worth reporting.
    """
    result = DeletionResult()
    root = report.target.path
    for path in report.entries:
        _check_inside(path, root)
        if dry_run:
            result.files_deleted += 1
            try:
                result.bytes_freed += path.stat().st_size
            except OSError:
                pass
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            result.files_deleted += 1
            result.bytes_freed += size
        except OSError as exc:
            result.errors.append(f"{path}: {exc.strerror or exc}")
    if dry_run:
        return result
    # Deepest-first so a parent is only removed after its children.
    parents = sorted(
        {p.parent for p in report.entries},
        key=lambda p: len(p.parts),
        reverse=True,
    )
    for parent in parents:
        try:
            _check_inside(parent, root)
        except UnsafeDeleteError:
            continue
        try:
            parent.rmdir()
            result.dirs_deleted += 1
        except OSError:
            pass  # non-empty or permission-denied: leave it, it's fine
    return result
