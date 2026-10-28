"""Where tempwipe looks, and why each location is on the list.

I deliberately keep this list short and boring: OS temp dirs plus the
well-known caches of tools I actually use. A cleaner that wanders into
random folders is how people lose files they wanted.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    """One directory tempwipe is allowed to scan (and, on request, clean)."""

    name: str
    path: Path
    description: str


def _home() -> Path:
    return Path.home()


def default_targets() -> list[Target]:
    """Build the platform-appropriate target list.

    Directories that don't exist on this machine are dropped — there's
    no point reporting on a cache folder that was never created.
    """
    candidates: list[Target] = [
        Target("system-temp", Path(tempfile.gettempdir()),
               "OS temporary directory"),
        Target("pip-cache", _home() / ".cache" / "pip",
               "pip's downloaded wheels and HTTP cache"),
        Target("npm-cache", _home() / ".npm",
               "npm's package cache"),
    ]
    if sys.platform == "darwin":
        candidates.append(Target("user-caches", _home() / "Library" / "Caches",
                                 "macOS per-app caches"))
        candidates.append(Target("homebrew-cache", _home() / "Library" / "Caches" / "Homebrew",
                                 "Homebrew download cache"))
    elif sys.platform.startswith("linux"):
        candidates.append(Target("user-cache", _home() / ".cache",
                                 "Linux per-app caches (includes pip, so pip-cache is skipped when this exists)"))
        # .cache already covers pip's cache, so don't double-count it.
        candidates = [c for c in candidates if c.name != "pip-cache"]
    elif sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
        if local is not None:
            candidates.append(Target("local-temp", local / "Temp",
                                     "Windows per-user temp directory"))
    return [c for c in candidates if c.path.is_dir()]


def dedupe_targets(targets: list[Target]) -> list[Target]:
    """Drop targets whose resolved path duplicates an earlier one.

    A user passing ``--include /tmp`` shouldn't double-count the
    system-temp target — same files, counted twice, is a wrong report.
    """
    seen: set[Path] = set()
    unique: list[Target] = []
    for target in targets:
        resolved = target.path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(target)
    return unique


def extra_target(path_str: str) -> Target:
    """Turn a user-supplied --include path into a Target.

    Raises ValueError for paths that don't exist or aren't directories —
    failing loudly here beats silently scanning nothing.
    """
    path = Path(path_str).expanduser()
    if not path.is_dir():
        raise ValueError(f"not a directory: {path_str}")
    return Target(f"custom:{path.name}", path, "user-supplied directory")
