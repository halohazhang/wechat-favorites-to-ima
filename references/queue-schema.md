# Queue schema

## Contents

1. Files
2. Item fields
3. States
4. Repair rules

## Files

Each run directory contains:

```text
run/
├── original/                 preserved source export
├── run.json                  immutable run origin and target
├── queue.jsonl               current source of truth
├── download-input.txt        current wechat2md input
├── download-plan.json       exact queue IDs in the current download attempt
├── markdown/                 local article archive
├── unmatched-markdown.json    output that could not be mapped to a URL, when present
├── wandao-batches/
│   └── BATCH_ID/
│       ├── files/            upload only this directory
│       ├── manifest.jsonl
│       └── target.json
└── report.md
```

## Item fields

- `id`: first 16 hex characters of SHA-256 over `normalized_url`
- `url`: original exported URL
- `normalized_url`: URL used for deduplication; fragment removed
- `title`: exported title when available
- `favorite_time`: optional exported time
- `target_kb`: user-confirmed ima destination
- `status`: workflow state
- `attempts`: count of import starts or failures recorded by the queue manager
- `local_markdown`: absolute matched Markdown path
- `archive_quality`: `full_text` or `link_only`
- `batch_id`: current Wandao batch
- `last_error`: actionable failure reason
- `note`: most recent `--note` recorded by `mark-item` or `mark-batch`, when provided
- `created_at`, `updated_at`: ISO 8601 timestamps

## States

| State | Meaning | Eligible next action |
|---|---|---|
| `queued` | Valid unique URL | Prepare download |
| `download_planned` | Written to wechat2md input | Run downloader and reconcile |
| `archived` | Full-text Markdown matched | Create Wandao batch |
| `ready_for_wandao` | Copied into batch | Confirm target and import |
| `importing` | Upload attempt started | Inspect Wandao result |
| `imported` | Wandao reported success | Verify in ima |
| `verified` | This item's title/body was confirmed in ima | Final |
| `needs_user` | Manual repair or decision required | Repair, skip, or retry |
| `failed` | Attempt failed with reason; `local_markdown` distinguishes later-stage failures from download failures | Diagnose, then explicitly reset to the appropriate prior state |
| `skipped` | Intentionally excluded | Final |

## Repair rules

- Edit queue state only through `manage_queue.py` when possible.
- `mark-item` and `mark-batch` enforce a forward-transition whitelist; `failed`, `needs_user`, and `skipped` are reachable from any state. A blocked transition names the offending items. Use `--force` only for deliberate manual repair after diagnosis, and record the reason with `--note`.
- Before manual repair, copy `queue.jsonl` and preserve the broken version.
- Never change `id` or `normalized_url` after batching.
- Mark only confirmed files imported or verified after a partial Wandao task.
- Keep failures explicit; do not convert failures to skipped merely to make the report complete.
