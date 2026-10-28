"""Scanning: walk a target directory and measure what can be reclaimed.

Symlinks are never followed — a cache dir that links elsewhere is not
ours to measure, let alone delete. Permission errors are counted and
skipped, not fatal: one unreadable folder shouldn't kill the whole report.
"""

from __future__ import annotations

import fnmatch
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .targets import Target

# Anything modified more recently than this is treated as "in use" by
# default pruning logic only when the user asks for an age filter; the
# constant exists so the default isn't a magic number buried in cli.py.
DEFAULT_MIN_AGE_DAYS = 0


@dataclass
class TargetReport:
    """Measured contents of one target directory."""

    target: Target
    file_count: int = 0
    dir_count: int = 0
    total_bytes: int = 0
    skipped: int = 0  # entries skipped (symlink, unreadable, excluded)
    entries: list[Path] = field(default_factory=list)  # files/dirs found, for cleaning

    @property
    def reclaimable_bytes(self) -> int:
        return self.total_bytes


def _excluded(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def scan_target(
    target: Target,
    *,
    older_than_days: int = 0,
    exclude: tuple[str, ...] = (),
    min_size_bytes: int = 0,
) -> TargetReport:
    """Walk *target* and measure everything matching the filters.

    Age is measured against file mtime. ``older_than_days=0`` (the
    default) means no age filter — report everything.
    """
    report = TargetReport(target=target)
    cutoff = time.time() - older_than_days * 86400 if older_than_days > 0 else 0
    for root, dirs, files in os.walk(target.path, topdown=True, followlinks=False):
        # Prune symlinked dirs and excluded dirs before descending.
        kept_dirs = []
        for d in dirs:
            full = Path(root) / d
            if full.is_symlink() or _excluded(d, exclude):
                report.skipped += 1
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs
        for name in files:
            full = Path(root) / name
            if full.is_symlink() or _excluded(name, exclude):
                report.skipped += 1
                continue
            try:
                stat = full.stat()
            except OSError:
                report.skipped += 1
                continue
            if cutoff and stat.st_mtime > cutoff:
                continue
            if stat.st_size < min_size_bytes:
                continue
            report.file_count += 1
            report.total_bytes += stat.st_size
            report.entries.append(full)
        report.dir_count += len(dirs)
    return report


def scan_all(
    targets: list[Target],
    *,
    older_than_days: int = 0,
    exclude: tuple[str, ...] = (),
    min_size_bytes: int = 0,
) -> list[TargetReport]:
    """Scan every target; a missing directory yields an empty report, not a crash."""
    reports = []
    for target in targets:
        if not target.path.is_dir():
            reports.append(TargetReport(target=target))
            continue
        reports.append(scan_target(
            target,
            older_than_days=older_than_days,
            exclude=exclude,
            min_size_bytes=min_size_bytes,
        ))
    return reports
