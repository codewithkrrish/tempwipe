# tempwipe

I kept running low on disk and every "cleaner" app I tried wanted to delete
things before telling me what they were. So I built the tool I actually
wanted: one that shows you exactly what's sitting in your temp folders and
app caches, how much space each one takes, and deletes nothing until you
explicitly say so.

## What it does

```
$ tempwipe
system-temp    /tmp                            42 files     312.4 MB
user-cache     /home/krrish/.cache            318 files       1.2 GB
TOTAL                                            360 files       1.5 GB

Report only: nothing was deleted. Rerun with --clean to delete.
```

By default tempwipe only reports. Deletion is a separate, deliberate step:

```
$ tempwipe --clean --older-than 30
system-temp    /tmp                            18 files     210.1 MB
...
Delete 210 files (1.1 GB)? [y/N] y
system-temp: deleted 18 files, freed 210.1 MB
Done.
```

## Install

```bash
pip install git+https://github.com/codewithkrrish/tempwipe.git
```

Requires Python 3.9+. No third-party dependencies.

## Usage

```
tempwipe [--clean] [--dry-run] [--yes] [--older-than DAYS]
         [--min-size BYTES] [--exclude GLOB] [--include DIR] [--json]
```

| Flag | What it does |
| --- | --- |
| (none) | Report only — safe, deletes nothing |
| `--clean` | Actually delete what the scan finds, after a confirmation prompt |
| `--dry-run` | Show what `--clean` would delete, without deleting |
| `--yes` | Skip the confirmation prompt (for scripts; use with care) |
| `--older-than 30` | Only touch files untouched for 30+ days |
| `--min-size 1048576` | Ignore files smaller than 1 MB |
| `--exclude "*.log"` | Skip matching names (repeatable) |
| `--include ~/Downloads/tmp` | Also scan an extra directory (repeatable) |
| `--json` | Machine-readable report (report-only, never deletes) |

A few examples:

```bash
# Just see what's there
tempwipe

# What would a 30-day prune free up?
tempwipe --dry-run --older-than 30

# Clean caches, skip the prompt, keep anything touched this week
tempwipe --clean --yes --older-than 7 --exclude "*.lock"

# Pipe a report into another tool
tempwipe --json | jq .total_bytes
```

## What it scans

- The OS temp directory (`/tmp`, `%TEMP%`, or macOS equivalent)
- `~/.cache` on Linux, `~/Library/Caches` on macOS
- pip, npm, and Homebrew caches where they exist

Directories that don't exist on your machine are simply skipped. Symlinks
are never followed, and a target's own root folder is never deleted — only
things inside it.

## Safety rules

These are non-negotiable in the code, not just documentation:

1. Default mode is report-only. Nothing is deleted by accident.
2. `--clean` asks for confirmation unless you pass `--yes`.
3. Only files inside a scanned target are ever deleted. Anything else
   raises an error instead of being touched.
4. Empty directories are removed deepest-first, and only if they're
   actually empty after the files go.
5. `--json` mode never deletes, even with `--clean` — piping a report
   into another tool must not have side effects.

## Limitations

Honest ones, because a disk cleaner that oversells is dangerous:

- It only knows the cache locations listed above. Some apps keep caches
  elsewhere; add those with `--include` if you want them covered.
- Size is measured by file size, not disk blocks, so the freed space
  your OS reports may differ slightly.
- It can't tell whether a running app still needs a "temp" file — that's
  what `--older-than` is for. Don't `--clean --yes` a temp dir while a
  big job is running.
- On Windows, some system temp files will fail to delete while in use;
  those are reported as warnings, not crashes.

## Project structure

```
tempwipe/
  tempwipe/
    __init__.py    version
    __main__.py    python -m tempwipe entry point
    cli.py         argument parsing and output (thin layer)
    scan.py        walking directories, filters, measuring
    clean.py       deletion rules and safety checks
    targets.py     which directories are scanned, per OS
  tests/
    test_tempwipe.py
```

## Development

```bash
pip install pytest
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE).

## Author

[Krrish](https://github.com/codewithkrrish)
