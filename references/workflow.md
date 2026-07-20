# Migration workflow

## Checkpoints

Require explicit user approval before:

- Starting macOS Accessibility automation in WeChat.
- Fetching article bodies from the network.
- Installing or patching a third-party dependency.
- Uploading a stated number of files to a named ima knowledge base.
- Continuing beyond the verified five-item pilot.
- Retrying after an account warning or three repeated failures.

## Responsibility split

| Stage | Script | Agent | User |
|---|---|---|---|
| Export | Produce and preserve CSV | Inspect readiness and bounded settings | Log in, choose Favorites → Links, authorize UI control |
| Archive | Build input and reconcile files | Run approved downloader and classify failures | Approve network retrieval |
| Batch | Select eligible files and write a manifest | Announce target and exact count | Confirm the upload |
| Import | Preserve state and result evidence | Use documented Wandao surfaces | Complete login, QR, CAPTCHA, or ambiguous UI selection |
| Verify | Record item state | Check titles and searchable bodies | Confirm pilot quality when needed |

## Normal run

1. Inspect prerequisites without modifying the machine.
2. Export a bounded pilot and preserve it under `RUN_DIR/original/`.
3. Initialize `queue.jsonl` with the exact user-selected target.
4. Prepare and retrieve five articles after network approval.
5. Reconcile Markdown; hold placeholders and unmatched files as `needs_user`.
6. Create a five-file Wandao batch.
7. Confirm the exact target and count immediately before upload.
8. Record only Wandao-confirmed successes as `imported`.
9. Verify every pilot title and searchable body.
10. Run the full UI export from the top, merge it, and continue in batches no larger than 20.
11. Generate `report.md` after interruption, recovery, and completion.

## Recovery

- Preserve partial exports. Merge later exports; normalized URLs already in the queue are skipped.
- If download stops, rerun `prepare-download`. Existing `download_planned` items remain the active set.
- A `failed` item with `local_markdown` is a later-stage failure; diagnose it before resetting it to `archived`.
- Re-run `reconcile` after replacing a link-only file with a complete Markdown archive. A recovered `needs_user` item becomes `archived`.
- Inspect `unmatched-markdown.json` with `download-plan.json`. Auto-associate only a unique title match from the current plan.
- Do not let reconciliation move batched, importing, imported, verified, or later-stage failed items backward.
- If Wandao partially succeeds, use `mark-item` for confirmed files; never promote the whole batch.
- If ima verification fails, record the mismatch and diagnose the target or parsing issue before retrying.

## Completion

Treat `queued`, `download_planned`, `archived`, `ready_for_wandao`, `importing`, and `imported` as unresolved. `needs_user` is a final handoff state only when the report explains the required manual action.
