# Third-party tool contracts

## Trust boundary

The skill does not bundle the following projects. Pin installations to a user-approved source and exact commit, inspect changes before upgrading, and respect each project's license. Record the revisions printed by `check_environment.py` in the run handoff. Article URLs and generated archives can reveal private reading interests; never publish run directories.

## wechat-favorites-exporter

- Repository: <https://github.com/pengyulong/wechat-favorites-exporter>
- License: MIT in the upstream repository
- Platform: macOS
- Entry point: `export_wechat_ui_favorites.py`
- Requirements: Python 3.10+, Swift, logged-in Mac WeChat, Accessibility permission
- Output header: `收藏时间,标题,链接`
- Scope: recognizable visible official-account article links; not every favorite type or ordinary webpage

Pilot pattern:

```bash
python3 export_wechat_ui_favorites.py \
  --max-items 20 \
  --max-screens 20 \
  --delay 0.8 \
  --output /absolute/path/to/pilot.csv
```

Full-run pattern after pilot verification:

```bash
python3 export_wechat_ui_favorites.py \
  --max-items 10000 \
  --max-screens 3000 \
  --delay 0.8 \
  --output /absolute/path/to/full.csv
```

Run only after the user authorizes foreground mouse, keyboard, and clipboard control. Require the list to start at the top. Increase delay instead of repeating rapid actions. Read [exporter-compatibility.md](exporter-compatibility.md) before patching or diagnosing the exporter.

## wechat2md

- Repository: <https://github.com/shiyan521/wechat2md>
- License: MIT in the upstream repository
- Entry point: `download_markdown.py`
- Input: one URL per line, optionally preceded by `### Title`
- Expected output: one Markdown file per article with a source line such as `> 原文链接：URL`

```bash
python3 download_markdown.py INPUT.txt OUTPUT_DIR
```

Before use, inspect the checked-out version for `verify=False`, disabled urllib3 warnings, custom certificate handling, and automatic `open`/Finder launches. Do not retrieve private material with TLS certificate or hostname verification disabled. Patch the reviewed checkout or use a browser-backed downloader that preserves normal TLS verification.

Treat `正文提取失败` and equivalent empty-body output as link-only placeholders. Never upload those as article bodies.

## Wandao

- Repository: <https://github.com/tllovesxs/wandao>
- License: AGPL-3.0 in the upstream repository; the skill invokes it as an external tool and does not bundle or modify it
- Product flow: Wandao → Platform Center → ima → Import
- Input: the generated Markdown batch directory
- Destination: an exact user-selected ima knowledge base or existing folder
- Authentication: Wandao's supported user-facing login/configuration flow

Use task progress, result counts, failure lists, and target-table-of-contents checks as evidence. Upload only `wandao-batches/BATCH_ID/files`, never the entire run directory.

Wandao versions may expose either a GUI or a flag-based backend. Inspect `--help` before invoking a backend and do not invent subcommands. Never read, print, copy, or package saved ima credentials. Never substitute an undocumented private ima API.

## Agent control

- Prefer a supported browser-control surface for login-dependent browser work.
- Use desktop control only after observing the current UI and receiving approval for that exact stage.
- Never guess coordinates or continue when the selected knowledge base, folder, or success indicator is ambiguous.
- Hand control to the user for login, QR codes, CAPTCHA, permissions, and account warnings.
