"""Command line interface — thin on purpose. All logic lives in scan/clean."""

from __future__ import annotations

import argparse
import json
import sys

from .clean import clean_report
from .scan import scan_all
from .targets import default_targets, dedupe_targets, extra_target

EXIT_OK = 0
EXIT_ERROR = 1


def format_size(num_bytes: int) -> str:
    """Human-readable size: 512 -> '512 B', 1536 -> '1.5 KB'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # unreachable, keeps type checkers happy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tempwipe",
        description="Report reclaimable space in temp dirs and app caches, "
                    "and clean them only when you say so.",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="actually delete what the scan finds (default: report only)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="show what --clean would delete, without deleting anything",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="skip the confirmation prompt (use in scripts, with care)",
    )
    parser.add_argument(
        "--older-than", type=int, default=0, metavar="DAYS",
        help="only consider files not modified in the last DAYS days (default: all)",
    )
    parser.add_argument(
        "--min-size", type=int, default=0, metavar="BYTES",
        help="ignore files smaller than BYTES bytes (default: 0)",
    )
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="GLOB",
        help="skip files/dirs matching GLOB (repeatable)",
    )
    parser.add_argument(
        "--include", action="append", default=[], metavar="DIR",
        help="also scan DIR (repeatable); only files inside it are ever deleted",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="print the report as JSON instead of a table",
    )
    return parser


def _confirm(total_bytes: int, file_count: int) -> bool:
    answer = input(
        f"Delete {file_count} files ({format_size(total_bytes)})? [y/N] "
    ).strip().lower()
    return answer in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.older_than < 0:
        print("error: --older-than must be 0 or more", file=sys.stderr)
        return EXIT_ERROR
    if args.min_size < 0:
        print("error: --min-size must be 0 or more", file=sys.stderr)
        return EXIT_ERROR

    targets = default_targets()
    for extra in args.include:
        try:
            targets.append(extra_target(extra))
        except ValueError as exc:
            print(f"error: --include {exc}", file=sys.stderr)
            return EXIT_ERROR
    targets = dedupe_targets(targets)
    if not targets:
        print("No temp or cache directories found on this machine.", file=sys.stderr)
        return EXIT_ERROR

    reports = scan_all(
        targets,
        older_than_days=args.older_than,
        exclude=tuple(args.exclude),
        min_size_bytes=args.min_size,
    )
    total_bytes = sum(r.total_bytes for r in reports)
    total_files = sum(r.file_count for r in reports)

    if args.json:
        payload = {
            "targets": [
                {
                    "name": r.target.name,
                    "path": str(r.target.path),
                    "files": r.file_count,
                    "bytes": r.total_bytes,
                    "skipped": r.skipped,
                }
                for r in reports
            ],
            "total_files": total_files,
            "total_bytes": total_bytes,
        }
        print(json.dumps(payload, indent=2))
        # JSON mode never deletes: piping a report into another tool
        # must not have side effects. Use the table mode for cleaning.
        if args.clean or args.dry_run:
            print("note: --json is report-only; rerun without --json to clean",
                  file=sys.stderr)
        return EXIT_OK

    for report in reports:
        print(f"{report.target.name:<14} {str(report.target.path):<45} "
              f"{report.file_count:>6} files  {format_size(report.total_bytes):>10}")
    print(f"{'TOTAL':<14} {'':<45} {total_files:>6} files  {format_size(total_bytes):>10}")

    if args.dry_run or not args.clean:
        if args.clean and args.dry_run:
            print("\nDry run: nothing was deleted.")
        elif not args.clean:
            print("\nReport only: nothing was deleted. Rerun with --clean to delete.")
        return EXIT_OK

    if total_files == 0:
        print("Nothing to delete.")
        return EXIT_OK
    if not args.yes and not _confirm(total_bytes, total_files):
        print("Aborted: nothing was deleted.")
        return EXIT_OK

    for report in reports:
        result = clean_report(report, dry_run=False)
        if result.files_deleted:
            print(f"{report.target.name}: deleted {result.files_deleted} files, "
                  f"freed {format_size(result.bytes_freed)}")
        for err in result.errors:
            print(f"warning: {err}", file=sys.stderr)
    print("Done.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
