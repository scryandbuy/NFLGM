# Trades UI handoff

Worktree: nflgm-standings-ui, branch codex/standings-ui.
Based on the previously copied dirty nflgm-bundle-final-check snapshot, not its subsequent edits.

Apply only the new hunks, not whole files: ../trades-ui-only.patch is relative to the pre-edit snapshot. It contains no inherited UI/engine changes.

Source changes:
- docs/app.js: scoped teamTheme/applyTeamTheme, trade components, typed selections, preserved tabs/search/scroll, partner dropdown, summary and action dock. Theme helper also used by player cards and negotiation popup. Initial counter/draft routes now evaluate preloaded packages.
- docs/style.css: appended scoped trade CSS.
- views_personnel.py: typed asset normalization, membership-based legacy resolution, validation/deduplication, typed gathered-offer assets. Existing valuation and execution functions retained.
- session.py: draft log supports typed and legacy pick identifiers.
- test_trade_assets.py: five regression tests (copy separately; not included in patch).

After merging, run test_trade_assets.py and build_web.py in the combined checkout. Regenerate docs/engine and stamps there; do not copy this checkout's generated manifest over a newer build.

Preview: http://127.0.0.1:8773/#personnel/trades
No bundle created.

## Personnel completion
Free Agency, Waivers and Extensions now use the matching team-themed layout, selected-player action panels, preserved subtabs/filters, and original seasonal workflows. Extension Open Talks now opens the existing thread rather than targeting a missing element. Waiver outbound empty state no longer duplicates its message.
Use ../personnel-ui-only.patch for the complete change set (supersedes the Trades-only patch); copy test_trade_assets.py separately. No additional Python changes were needed for these three tabs.

## Header redesign
Includes docs/index.html header-only hunk (compared with current UI checkout header), #rail responsive styling, shared palette, labeled utilities/Quick Links, and corrected cutdown #personnel/wire route. Preserve all header IDs. Browser checks passed at desktop,900px,480px; Advance visible with no header overflow. Rebuild combined checkout for stamps.
