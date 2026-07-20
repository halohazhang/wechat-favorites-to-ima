#!/usr/bin/env python3
"""Inspect local prerequisites without installing or modifying anything."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def first_existing(candidates: list[Path]) -> str | None:
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return None


def resolve_entry(explicit: str | None, candidates: list[Path], entry: str) -> str | None:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_dir():
            path = path / entry
        return str(path.resolve()) if path.exists() else None
    direct = first_existing(candidates)
    if not direct:
        return None
    path = Path(direct)
    if path.is_dir():
        path = path / entry
    return str(path.resolve()) if path.exists() else None


def inspect_wechat2md(entry: str | None) -> dict[str, bool | None]:
    if not entry:
        return {
            "tls_verification_disabled": None,
            "suppresses_tls_warnings": None,
            "opens_output_automatically": None,
        }
    text = Path(entry).read_text(encoding="utf-8", errors="replace")
    compact = "".join(text.split())
    return {
        "tls_verification_disabled": "verify=False" in compact,
        "suppresses_tls_warnings": "disable_warnings" in text,
        "opens_output_automatically": any(
            marker in text
            for marker in ("subprocess.run(['open'", 'subprocess.run(["open"', "os.system('open ", 'os.system("open ')
        ),
    }


def git_revision(entry: str | None) -> str | None:
    if not entry or not shutil.which("git"):
        return None
    path = Path(entry)
    directory = path if path.is_dir() else path.parent
    try:
        completed = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and revision else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wechat-exporter", help="Repository directory or exporter entry file")
    parser.add_argument("--wechat2md", help="Repository directory or download_markdown.py")
    parser.add_argument("--wandao", help="Wandao application or source directory")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when a prerequisite is missing")
    args = parser.parse_args()

    home = Path.home()
    exporter = resolve_entry(
        args.wechat_exporter,
        [home / "Tools/wechat-favorites-exporter", home / "Projects/wechat-favorites-exporter"],
        "export_wechat_ui_favorites.py",
    )
    wechat2md = resolve_entry(
        args.wechat2md,
        [home / "Tools/wechat2md", home / "Projects/wechat2md"],
        "download_markdown.py",
    )
    wandao_candidates = [
        Path(args.wandao).expanduser() if args.wandao else Path("/__missing__"),
        Path("/Applications/Wandao.app"),
        home / "Applications/Wandao.app",
        home / "Tools/wandao",
        home / "Projects/wandao",
    ]
    wandao = first_existing(wandao_candidates)

    checks = {
        "platform": platform.system(),
        "platform_supported_for_exporter": platform.system() == "Darwin",
        "python": shutil.which("python3"),
        "python_version": platform.python_version(),
        "python_3_10_or_newer": sys.version_info >= (3, 10),
        "wechat_favorites_exporter": exporter,
        "wechat_favorites_exporter_revision": git_revision(exporter),
        "wechat2md": wechat2md,
        "wechat2md_revision": git_revision(wechat2md),
        "wechat2md_safety": inspect_wechat2md(wechat2md),
        "wandao": wandao,
    }
    missing = [
        name
        for name, value in {
            "macOS": checks["platform_supported_for_exporter"],
            "Python 3.10+": checks["python_3_10_or_newer"],
            "wechat-favorites-exporter": exporter,
            "wechat2md": wechat2md,
            "Wandao": wandao,
        }.items()
        if not value
    ]
    checks["missing"] = missing
    tls_disabled = checks["wechat2md_safety"]["tls_verification_disabled"]
    checks["warnings"] = [
        warning
        for warning, active in {
            "wechat2md disables TLS certificate verification; patch or replace it before network retrieval": tls_disabled,
            "wechat2md suppresses TLS warnings": checks["wechat2md_safety"]["suppresses_tls_warnings"],
            "wechat2md may open its output automatically": checks["wechat2md_safety"]["opens_output_automatically"],
        }.items()
        if active
    ]
    checks["ready"] = not missing and not tls_disabled
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 1 if args.strict and not checks["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
