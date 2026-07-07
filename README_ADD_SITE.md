# Add Site — Auto Detect Admin Feature (single-panel only)

`mockup_web_app_V2.py` is already patched and ready to deploy as-is — the three wiring changes (import, trigger call, merged coordinates dict used in both the site list and the generation loop) are done. `template_coordinates.py` and `mockup_utils_V2.py` are untouched.

## Files in this drop

- `mockup_web_app_V2.py` — patched (see diff below for exactly what changed)
- `template_detect.py` — auto-detection, single-panel only
- `github_sync.py` — best-effort GitHub persistence
- `admin_add_site.py` — the dialog UI
- `requirements.txt` — updated with `requests` + `streamlit-image-coordinates`

## Why single-panel only

Checked against the real "Bendigo (Digital) Kangaroo Flat - 35553-D.png" template: its three panels are genuinely different planes (a wraparound corner billboard), not a straight-line split of one flat quad, and its transparent cutout is a single contiguous hole — no pixel evidence to detect panel boundaries from either way. Multi-panel is also currently dead code in production (`split_ratio`/`split_ratios` mismatch), so descoping it costs nothing today. Multi-panel sites still go through `find points/click_points.py` by hand.

## Housekeeping fixes applied in this pass

Earlier drafts of `admin_add_site.py` and `template_detect.py` didn't match several of your established conventions. Fixed now:

1. **`gc.collect()`** added after every heavy PIL/OpenCV/array operation in `template_detect.py` and `admin_add_site.py`, matching the pattern in `mockup_utils_V2.py`'s `warp_panel()`.
2. **Job-scoped temp directories.** The dialog now creates `TMP_DIR / f"admin_{uuid4().hex}"` on open (mirrors `tmp/job_{uuid}/`), cleaned up via `shutil.rmtree` both on dialog reopen/reset and after a successful save — no more flat `/tmp/admin_preview_{name}` path that could collide between concurrent admins.
3. **Artwork safety limits reused.** The uploaded template PNG now goes through the same `MAX_EDGE`/`MAX_PIXELS` check as regular artwork uploads (`_resize_if_oversized()`, mirroring `prepare_artwork_file()`'s resize branch) — losslessly resized to PNG if it exceeds them, with a visible warning. `render_add_site_trigger()` takes `max_edge`/`max_pixels` as parameters so the app passes its actual constants rather than the module guessing at its own copy.
4. **Errors surfaced to a session-state list**, not ad-hoc inline `st.error()` calls — `st.session_state["admin_errors"]`, rendered in one place at the end of the dialog. Kept as a separate list from `generation_errors` rather than merged into it, since it's a distinct workflow (adding a site vs. generating mockups) and mixing them would make either list harder to reason about — flagging that choice explicitly in case you'd rather they share one list.
5. **`try/finally` tightened** around every PIL `Image` object opened in the dialog (the preview image, the full-res image opened just to compute a scale factor) so a mid-render exception can't leak them.

## What was validated before shipping (re-confirmed after these fixes)

- `detect_transparent_quad()` against the real "Geelong East (Digital) Try Boys - 32191-D.png" template: still within 2–6px of the existing hand-picked coordinates.
- `format_entry()` + `insert_entry()` round-tripped through `ast.parse`/`exec`: still produces valid, importable Python, in the exact format of existing single-panel entries.
- `admin_add_site.py` imports cleanly standalone, and the `streamlit-image-coordinates` fallback (manual x/y inputs) correctly activates when that package isn't installed.

**Not yet tested:** the live `st.dialog` + click-to-adjust flow end-to-end, since that needs a running Streamlit session rather than something runnable from a sandbox. Worth clicking through it once locally before relying on it — the manual x/y fallback is the simpler path to trust first if you want to skip installing `streamlit-image-coordinates` initially.

## Diff summary for `mockup_web_app_V2.py`

```python
# imports, added:
from admin_add_site import render_add_site_trigger

# right after the header image block, added:
render_add_site_trigger(
    template_dir=TEMPLATE_DIR / "Digital",
    tmp_dir=TMP_DIR,
    max_edge=MAX_EDGE,
    max_pixels=MAX_PIXELS,
)

# template list building — was:
template_keys = list(TEMPLATE_COORDINATES.keys())
# now:
all_coordinates = {**TEMPLATE_COORDINATES, **st.session_state.get("custom_templates", {})}
template_keys = list(all_coordinates.keys())

# generation loop — was:
template_data = TEMPLATE_COORDINATES.get(selected_template)
# now:
template_data = all_coordinates.get(selected_template)
```

## Render environment variable (for durable persistence)

Add `GITHUB_TOKEN` in Render's dashboard under the service's Environment settings:

1. Generate a **fine-grained personal access token** on GitHub, scoped to *only* this repo, with **Contents: Read and write** permission.
2. Generate it from the account that should actually own commits to this repo going forward — worth resolving alongside the fact that Render's existing Git credential is still tied to the previous owner's personal login.
3. Set it as `GITHUB_TOKEN` in Render, not committed anywhere in the repo.

Without it, "Add Site" still fully works for the current session — new sites are usable immediately, and a copy-paste-ready snippet is shown for manual persistence.

## Known limitation carried over

`insert_entry()` does a targeted text insertion (finds the file's final closing brace) rather than a full re-serialization, so it doesn't reformat the existing 60+ entries. It validates the result with `ast.parse` before writing. If `template_coordinates.py`'s structure ever changes shape (e.g. a trailing comment after the closing brace), that insertion point logic would need revisiting.

## Later: revisiting multi-panel

If/when `split_ratio`/`split_ratios` gets fixed and multi-panel is worth automating, check whether a given template's transparent window is a single contiguous hole (like Kangaroo Flat) or genuinely separate per-panel cutouts first — only the latter has real pixel evidence to detect from.
