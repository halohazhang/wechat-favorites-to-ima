#!/usr/bin/env python3
"""Create and maintain a resumable WeChat-to-ima migration queue."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ALLOWED_STATES = {
    "queued",
    "download_planned",
    "archived",
    "ready_for_wandao",
    "importing",
    "imported",
    "verified",
    "needs_user",
    "failed",
    "skipped",
}
FINAL_STATES = {"verified", "failed", "skipped", "needs_user"}
# States an item may move to via mark-item/mark-batch, keyed by target status.
# "*" means any current status. Repair flows outside this map require --force.
ALLOWED_TRANSITIONS = {
    "failed": {"*"},
    "needs_user": {"*"},
    "skipped": {"*"},
    "queued": {"queued", "failed", "needs_user"},
    "download_planned": {"download_planned", "queued", "failed"},
    "archived": {"archived", "failed", "needs_user"},
    "ready_for_wandao": {"ready_for_wandao", "importing", "failed"},
    "importing": {"importing", "ready_for_wandao", "failed"},
    "imported": {"imported", "importing", "ready_for_wandao"},
    "verified": {"verified", "imported"},
}
EXPECTED_HOST = "mp.weixin.qq.com"
URL_KEYS = ("链接", "url", "URL", "link", "Link")
TITLE_KEYS = ("标题", "title", "Title")
TIME_KEYS = ("收藏时间", "favorite_time", "time", "date")
SOURCE_URL_RE = re.compile(r"^>\s*原文链接[：:]\s*(https?://\S+)\s*$", re.MULTILINE)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_url(url: str) -> str:
    value = url.strip().strip("<>\"'")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"invalid URL: {url}")
    host = (parts.hostname or "").lower()
    scheme = "https" if host == "mp.weixin.qq.com" else parts.scheme.lower()
    netloc = host
    if parts.port and not ((scheme == "https" and parts.port == 443) or (scheme == "http" and parts.port == 80)):
        netloc = f"{host}:{parts.port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def item_id(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]


def pick(row: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def load_source(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    rows = []
    pending_title = ""
    with path.open("r", encoding="utf-8-sig") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith("###"):
                pending_title = line.lstrip("#").strip()
            elif line.startswith(("http://", "https://")):
                rows.append({"title": pending_title, "url": line})
                pending_title = ""
    return rows


def host_summary(items: list[dict]) -> dict:
    hosts = Counter(urlsplit(item["normalized_url"]).hostname or "" for item in items)
    return {
        "hosts": dict(hosts.most_common()),
        "unexpected_hosts": sorted(host for host in hosts if host != EXPECTED_HOST),
    }


def queue_path(run_dir: Path) -> Path:
    return run_dir / "queue.jsonl"


def load_queue(run_dir: Path) -> list[dict]:
    path = queue_path(run_dir)
    if not path.exists():
        raise FileNotFoundError(f"queue not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def save_queue(run_dir: Path, items: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    target = queue_path(run_dir)
    temporary = target.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(target)


def command_init(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if queue_path(run_dir).exists() and not args.force:
        raise FileExistsError(f"queue already exists: {queue_path(run_dir)}; use --force to replace")
    rows = load_source(source)
    seen: set[str] = set()
    items: list[dict] = []
    rejected = 0
    for row in rows:
        raw_url = pick(row, URL_KEYS)
        if not raw_url:
            rejected += 1
            continue
        try:
            normalized = normalize_url(raw_url)
        except ValueError:
            rejected += 1
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        created = now_iso()
        items.append(
            {
                "id": item_id(normalized),
                "title": pick(row, TITLE_KEYS),
                "url": raw_url,
                "normalized_url": normalized,
                "favorite_time": pick(row, TIME_KEYS),
                "target_kb": args.target_kb or "",
                "status": "queued",
                "attempts": 0,
                "local_markdown": "",
                "archive_quality": "",
                "batch_id": "",
                "last_error": "",
                "created_at": created,
                "updated_at": created,
            }
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    original_dir = run_dir / "original"
    original_dir.mkdir(exist_ok=True)
    preserved = original_dir / source.name
    if preserved.resolve() != source:
        shutil.copy2(source, preserved)
    metadata = {
        "created_at": now_iso(),
        "source": str(source),
        "preserved_source": str(preserved),
        "target_kb": args.target_kb or "",
        "input_rows": len(rows),
        "queue_items": len(items),
        "rejected_rows": rejected,
        **host_summary(items),
    }
    (run_dir / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    save_queue(run_dir, items)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


def command_merge(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    items = load_queue(run_dir)
    rows = load_source(source)
    seen = {item["normalized_url"] for item in items}
    target_kb = items[0].get("target_kb", "") if items else ""
    added = 0
    duplicates = 0
    rejected = 0
    for row in rows:
        raw_url = pick(row, URL_KEYS)
        if not raw_url:
            rejected += 1
            continue
        try:
            normalized = normalize_url(raw_url)
        except ValueError:
            rejected += 1
            continue
        if normalized in seen:
            duplicates += 1
            continue
        seen.add(normalized)
        created = now_iso()
        items.append(
            {
                "id": item_id(normalized),
                "title": pick(row, TITLE_KEYS),
                "url": raw_url,
                "normalized_url": normalized,
                "favorite_time": pick(row, TIME_KEYS),
                "target_kb": target_kb,
                "status": "queued",
                "attempts": 0,
                "local_markdown": "",
                "archive_quality": "",
                "batch_id": "",
                "last_error": "",
                "created_at": created,
                "updated_at": created,
            }
        )
        added += 1
    original_dir = run_dir / "original"
    original_dir.mkdir(exist_ok=True)
    preserved = original_dir / source.name
    if preserved.exists() and preserved.resolve() != source:
        preserved = original_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{source.name}"
    if preserved.resolve() != source:
        shutil.copy2(source, preserved)
    metadata_path = run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    metadata.setdefault("merges", []).append(
        {
            "merged_at": now_iso(),
            "source": str(source),
            "preserved_source": str(preserved),
            "input_rows": len(rows),
            "added": added,
            "duplicates": duplicates,
            "rejected": rejected,
        }
    )
    metadata["queue_items"] = len(items)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    save_queue(run_dir, items)
    print(
        json.dumps(
            {"added": added, "duplicates": duplicates, "rejected": rejected, "queue_items": len(items), **host_summary(items)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_prepare_download(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    items = load_queue(run_dir)
    planned = [item for item in items if item["status"] == "download_planned"]
    if planned:
        eligible = planned
    else:
        eligible = [
            item
            for item in items
            if item["status"] == "queued" or (item["status"] == "failed" and not item.get("local_markdown"))
        ]
    selected = eligible[: args.limit] if args.limit else eligible
    output = Path(args.output).expanduser().resolve() if args.output else run_dir / "download-input.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for item in selected:
            if item.get("title"):
                handle.write(f"### {item['title']}\n")
            handle.write(f"{item['url']}\n")
            item["status"] = "download_planned"
            item["updated_at"] = now_iso()
    (run_dir / "download-plan.json").write_text(
        json.dumps(
            {"prepared_at": now_iso(), "input": str(output), "ids": [item["id"] for item in selected]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    save_queue(run_dir, items)
    print(json.dumps({"input": str(output), "count": len(selected)}, ensure_ascii=False, indent=2))
    return 0


def markdown_title(text: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def normalized_title(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def markdown_records(markdown_dir: Path) -> tuple[dict[str, tuple[Path, str]], list[dict]]:
    records: dict[str, tuple[Path, str]] = {}
    unmatched: list[dict] = []
    for path in sorted(markdown_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = SOURCE_URL_RE.search(text)
        if not match:
            unmatched.append({"path": str(path.resolve()), "title": markdown_title(text)})
            continue
        try:
            normalized = normalize_url(match.group(1))
        except ValueError:
            unmatched.append({"path": str(path.resolve()), "title": markdown_title(text)})
            continue
        quality = "link_only" if "正文提取失败" in text else "full_text"
        records[normalized] = (path.resolve(), quality)
    return records, unmatched


def command_reconcile(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    markdown_dir = Path(args.markdown_dir).expanduser().resolve()
    if not markdown_dir.is_dir():
        raise NotADirectoryError(markdown_dir)
    items = load_queue(run_dir)
    records, unmatched = markdown_records(markdown_dir)
    plan_path = run_dir / "download-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {"ids": []}
    plan_ids = set(plan.get("ids", []))
    matched = 0
    needs_user = 0
    for item in items:
        record = records.get(item["normalized_url"])
        if not record:
            continue
        previous_status = item["status"]
        previous_local = item.get("local_markdown", "")
        path, quality = record
        item["local_markdown"] = str(path)
        item["archive_quality"] = quality
        item["updated_at"] = now_iso()
        if quality == "full_text":
            if previous_status in {"queued", "download_planned", "needs_user"} or (
                previous_status == "failed" and not previous_local
            ):
                item["status"] = "archived"
                item["last_error"] = ""
            matched += 1
        else:
            if previous_status in {"queued", "download_planned"} or (previous_status == "failed" and not previous_local):
                item["status"] = "needs_user"
                item["last_error"] = "wechat2md did not extract article body"
            needs_user += 1
    unmatched_manifest = run_dir / "unmatched-markdown.json"
    if unmatched:
        unmatched_manifest.write_text(
            json.dumps({"generated_at": now_iso(), "download_plan": str(plan_path), "files": unmatched}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        candidates = [item for item in items if item["id"] in plan_ids and item["status"] == "download_planned"]
        for orphan in unmatched:
            title_key = normalized_title(orphan.get("title", ""))
            if not title_key:
                continue
            matches = [item for item in candidates if normalized_title(item.get("title", "")) == title_key]
            if len(matches) == 1:
                item = matches[0]
                item["status"] = "needs_user"
                item["local_markdown"] = orphan["path"]
                item["archive_quality"] = "unmatched_source"
                item["last_error"] = f"Markdown lacks a usable source URL; inspect {unmatched_manifest}"
                item["updated_at"] = now_iso()
                needs_user += 1
                candidates.remove(item)
    elif unmatched_manifest.exists():
        unmatched_manifest.unlink()
    save_queue(run_dir, items)
    print(
        json.dumps(
            {
                "matched_full_text": matched,
                "needs_user": needs_user,
                "matched_markdown_files": len(records),
                "unmatched_markdown_files": len(unmatched),
                "unmatched_manifest": str(unmatched_manifest) if unmatched else "",
            },
            indent=2,
        )
    )
    return 0


def command_make_batch(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    items = load_queue(run_dir)
    selected = [item for item in items if item["status"] == "archived" and item.get("local_markdown")]
    selected = selected[: args.limit]
    if not selected:
        print(json.dumps({"count": 0, "message": "no archived items ready"}, indent=2))
        return 0
    batch_id = args.batch_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_dir = run_dir / "wandao-batches" / batch_id
    if batch_dir.exists():
        raise FileExistsError(batch_dir)
    files_dir = batch_dir / "files"
    files_dir.mkdir(parents=True)
    manifest = []
    for item in selected:
        source = Path(item["local_markdown"])
        destination = files_dir / f"{item['id']}-{source.name}"
        shutil.copy2(source, destination)
        item["status"] = "ready_for_wandao"
        item["batch_id"] = batch_id
        item["updated_at"] = now_iso()
        manifest.append({"id": item["id"], "title": item.get("title", ""), "source": str(source), "file": str(destination)})
    with (batch_dir / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in manifest:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (batch_dir / "target.json").write_text(
        json.dumps({"target_kb": selected[0].get("target_kb", ""), "count": len(selected)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_queue(run_dir, items)
    print(json.dumps({"batch_id": batch_id, "batch_dir": str(batch_dir), "files_dir": str(files_dir), "count": len(selected)}, ensure_ascii=False, indent=2))
    return 0


def load_batch_ids(batch_dir: Path) -> set[str]:
    manifest = batch_dir / "manifest.jsonl"
    if not manifest.exists():
        raise FileNotFoundError(manifest)
    with manifest.open("r", encoding="utf-8") as handle:
        return {json.loads(line)["id"] for line in handle if line.strip()}


def update_items(run_dir: Path, ids: set[str], status: str, note: str, force: bool = False) -> int:
    if status not in ALLOWED_STATES:
        raise ValueError(f"unsupported status: {status}")
    items = load_queue(run_dir)
    allowed_from = ALLOWED_TRANSITIONS[status]
    blocked = [
        item
        for item in items
        if item["id"] in ids and "*" not in allowed_from and item["status"] not in allowed_from
    ]
    if blocked and not force:
        details = ", ".join(f"{item['id']}:{item['status']}" for item in blocked[:5])
        raise ValueError(
            f"transition to '{status}' not allowed from [{details}"
            f"{', ...' if len(blocked) > 5 else ''}]; diagnose first or rerun with --force"
        )
    updated = 0
    for item in items:
        if item["id"] not in ids:
            continue
        item["status"] = status
        item["updated_at"] = now_iso()
        item["attempts"] = int(item.get("attempts", 0)) + (1 if status in {"importing", "failed"} else 0)
        if note:
            item["last_error"] = note if status in {"failed", "needs_user"} else ""
            item["note"] = note
        elif status not in {"failed", "needs_user"}:
            item["last_error"] = ""
        updated += 1
    save_queue(run_dir, items)
    return updated


def command_mark_batch(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    batch_dir = Path(args.batch_dir).expanduser().resolve()
    updated = update_items(run_dir, load_batch_ids(batch_dir), args.status, args.note or "", args.force)
    print(json.dumps({"updated": updated, "status": args.status, "batch_dir": str(batch_dir)}, indent=2))
    return 0


def command_mark_item(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    updated = update_items(run_dir, {args.id}, args.status, args.note or "", args.force)
    if updated != 1:
        raise KeyError(f"item not found: {args.id}")
    print(json.dumps({"updated": updated, "id": args.id, "status": args.status}, indent=2))
    return 0


def command_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    items = load_queue(run_dir)
    counts = Counter(item["status"] for item in items)
    unresolved = [item for item in items if item["status"] not in FINAL_STATES]
    manual = [item for item in items if item["status"] in {"needs_user", "failed"}]
    lines = [
        "# WeChat Favorites → ima migration report",
        "",
        f"Generated: {now_iso()}",
        f"Total: {len(items)}",
        "",
        "## Status",
        "",
    ]
    for status in sorted(ALLOWED_STATES):
        if counts[status]:
            lines.append(f"- {status}: {counts[status]}")
    lines.extend(["", "## Manual review / failed", ""])
    if manual:
        for item in manual:
            lines.append(f"- `{item['id']}` {item.get('title') or item['url']} — {item.get('last_error') or item['status']}")
    else:
        lines.append("- None")
    report = run_dir / "report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {"report": str(report), "total": len(items), "counts": dict(counts), "unresolved": len(unresolved)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create queue from CSV, TXT, or JSONL")
    init.add_argument("--source", required=True)
    init.add_argument("--run-dir", required=True)
    init.add_argument("--target-kb", default="")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=command_init)

    merge = commands.add_parser("merge", help="Append a later export to an existing queue")
    merge.add_argument("--source", required=True)
    merge.add_argument("--run-dir", required=True)
    merge.set_defaults(func=command_merge)

    prepare = commands.add_parser("prepare-download", help="Create wechat2md input")
    prepare.add_argument("--run-dir", required=True)
    prepare.add_argument("--limit", type=int, default=5)
    prepare.add_argument("--output")
    prepare.set_defaults(func=command_prepare_download)

    reconcile = commands.add_parser("reconcile", help="Match Markdown files back to queue")
    reconcile.add_argument("--run-dir", required=True)
    reconcile.add_argument("--markdown-dir", required=True)
    reconcile.set_defaults(func=command_reconcile)

    batch = commands.add_parser("make-batch", help="Create Wandao upload batch")
    batch.add_argument("--run-dir", required=True)
    batch.add_argument("--limit", type=int, default=5)
    batch.add_argument("--batch-id")
    batch.set_defaults(func=command_make_batch)

    mark_batch = commands.add_parser("mark-batch", help="Update all items in a batch")
    mark_batch.add_argument("--run-dir", required=True)
    mark_batch.add_argument("--batch-dir", required=True)
    mark_batch.add_argument("--status", required=True, choices=sorted(ALLOWED_STATES))
    mark_batch.add_argument("--note")
    mark_batch.add_argument("--force", action="store_true", help="Bypass the state-transition whitelist for manual repair")
    mark_batch.set_defaults(func=command_mark_batch)

    mark_item = commands.add_parser("mark-item", help="Update one queue item")
    mark_item.add_argument("--run-dir", required=True)
    mark_item.add_argument("--id", required=True)
    mark_item.add_argument("--status", required=True, choices=sorted(ALLOWED_STATES))
    mark_item.add_argument("--note")
    mark_item.add_argument("--force", action="store_true", help="Bypass the state-transition whitelist for manual repair")
    mark_item.set_defaults(func=command_mark_item)

    report = commands.add_parser("report", help="Write a migration report")
    report.add_argument("--run-dir", required=True)
    report.set_defaults(func=command_report)
    return root


def main() -> int:
    try:
        args = parser().parse_args()
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
