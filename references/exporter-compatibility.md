# Exporter compatibility checks

Use this reference only when diagnosing or reviewing `wechat-favorites-exporter`. Obtain approval before editing its checkout.

## Current WeChat UI checks

1. Open **Favorites → Links** and return to the top before a full run.
2. If the list is already open, do not click Favorites again; doing so can activate a smaller main window and hide the intended rows.
3. Find visible link rows across the active WeChat accessibility tree instead of assuming the first window titled `微信` is the content window.
4. Derive the scroll point from visible row positions. Fixed window insets can fail after resizing, display scaling, or a WeChat layout change.
5. Detect the bottom by repeated visible-page signatures or scroll position, not by two pages with no new official-account URL. Consecutive ordinary webpages are valid Favorites rows.
6. Keep screen overlap and URL deduplication. Treat an unchanged page for at least two scroll attempts as the end.

## Article URL validation

Accept only the exact host `mp.weixin.qq.com` and recognized article paths:

- Legacy form: path `/s` with article identifiers in the query.
- Current short form: path `/s/<nontrivial-token>`.

Reject lookalike hosts, credentials in URLs, non-HTTP schemes, and unrelated paths. Remove fragments only for deduplication; preserve the original exported URL separately.

## Count interpretation

Report separate counts for:

- Visible Favorites rows scanned.
- URLs copied.
- Recognizable WeChat article URLs accepted.
- Duplicates rejected.
- Ordinary webpages excluded.

Never claim the accepted article count equals the user's total Favorites count.

## Safe test sequence

1. Type-check or compile the Swift helper without UI automation.
2. Run unit tests for legacy and short article URLs.
3. With approval, run one screen and at most one accepted item.
4. Confirm row detection and copied-link classification without printing full private URLs.
5. Return the list to the top before the approved full run.
