"""Tests for tempwipe: scanning, filtering, and safe cleaning."""

import json
import os
import time

import pytest

from tempwipe.clean import UnsafeDeleteError, clean_report
from tempwipe.cli import format_size, main
from tempwipe.scan import TargetReport, scan_target
from tempwipe.targets import Target, dedupe_targets, extra_target


def _make_tree(tmp_path, files):
    """Create files; values are (size, age_days). Returns the root path."""
    for name, (size, age_days) in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        mtime = time.time() - age_days * 86400
        os.utime(path, (mtime, mtime))
    return tmp_path


def test_scan_counts_files_and_bytes(tmp_path):
    root = _make_tree(tmp_path, {"a.txt": (100, 0), "sub/b.log": (200, 0)})
    report = scan_target(Target("t", root, "test"))
    assert report.file_count == 2
    assert report.total_bytes == 300


def test_scan_empty_dir(tmp_path):
    report = scan_target(Target("t", tmp_path, "test"))
    assert report.file_count == 0
    assert report.total_bytes == 0


def test_scan_missing_dir_yields_empty_report(tmp_path):
    missing = tmp_path / "nope"
    report = scan_target(Target("t", missing, "test"))
    # os.walk on a missing dir yields nothing: no crash, no files.
    assert report.file_count == 0


def test_older_than_filter(tmp_path):
    root = _make_tree(tmp_path, {"old.txt": (10, 30), "new.txt": (10, 1)})
    report = scan_target(Target("t", root, "test"), older_than_days=7)
    assert report.file_count == 1
    assert report.entries[0].name == "old.txt"


def test_exclude_glob(tmp_path):
    root = _make_tree(tmp_path, {"keep.txt": (10, 0), "skip.log": (10, 0)})
    report = scan_target(Target("t", root, "test"), exclude=("*.log",))
    assert report.file_count == 1
    assert report.entries[0].name == "keep.txt"


def test_symlink_not_followed(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"y" * 50)
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    report = scan_target(Target("t", tmp_path, "test"))
    assert report.file_count == 1  # only outside.txt itself
    assert report.skipped == 1


def test_clean_dry_run_deletes_nothing(tmp_path):
    root = _make_tree(tmp_path, {"a.txt": (100, 0)})
    report = scan_target(Target("t", root, "test"))
    result = clean_report(report, dry_run=True)
    assert result.files_deleted == 1
    assert result.bytes_freed == 100
    assert (root / "a.txt").exists()


def test_clean_real_deletes_files_keeps_root(tmp_path):
    root = _make_tree(tmp_path, {"a.txt": (100, 0), "sub/b.txt": (50, 0)})
    report = scan_target(Target("t", root, "test"))
    result = clean_report(report, dry_run=False)
    assert result.files_deleted == 2
    assert result.bytes_freed == 150
    assert not (root / "a.txt").exists()
    assert root.is_dir()  # the root itself survives


def test_clean_refuses_outside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outsider = tmp_path / "outsider.txt"
    outsider.write_text("nope")
    report = TargetReport(target=Target("t", root, "test"), entries=[outsider])
    with pytest.raises(UnsafeDeleteError):
        clean_report(report, dry_run=False)


def test_dedupe_targets_drops_duplicate_path(tmp_path):
    first = Target("a", tmp_path, "test")
    second = Target("b", tmp_path, "test")
    assert dedupe_targets([first, second]) == [first]


def test_extra_target_rejects_missing_dir(tmp_path):
    with pytest.raises(ValueError):
        extra_target(str(tmp_path / "does-not-exist"))


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(1536) == "1.5 KB"
    assert format_size(5 * 1024 * 1024) == "5.0 MB"


def test_cli_json_report(tmp_path, capsys):
    _make_tree(tmp_path, {"a.txt": (100, 0)})
    assert main(["--include", str(tmp_path), "--json"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["total_files"] >= 1


def test_cli_rejects_negative_older_than(capsys):
    assert main(["--older-than", "-1"]) == 1


def test_cli_bad_flag_exits_2():
    with pytest.raises(SystemExit) as exc:
        main(["--not-a-flag"])
    assert exc.value.code == 2
