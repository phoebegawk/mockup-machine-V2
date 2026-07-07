"""admin_add_site.py

"+ Add Site" admin feature for Mock Up Machine — auto-detects the
transparent billboard window in an uploaded template PNG instead of
requiring manual corner-clicking (find points/click_points.py), and saves
the result both locally (immediate, works this session) and to GitHub
(durable, survives Render redeploys) when GITHUB_TOKEN is configured.

SINGLE-PANEL ONLY. Checked against a real multi-panel template ("Bendigo
(Digital) Kangaroo Flat - 35553-D.png"), the LHS/MID/RHS panels are
genuinely different planes (a wraparound corner billboard), not a
straight-line split of one flat quad, and the transparent cutout in that
template is a single contiguous hole — so there's no pixel evidence to
auto-derive panel boundaries from either way. Multi-panel sites still go
through manual corner-picking (find points/click_points.py) until there's
a real basis for automating that.

Follows the same conventions as the rest of the app:
- Per-job UUID temp directories under TMP_DIR, cleaned up on dialog
  reset/reopen (mirrors tmp/job_{uuid}/ in mockup_web_app_V2.py).
- Same MAX_EDGE / MAX_PIXELS artwork safety limits applied to the
  uploaded template PNG, with lossless PNG resize if exceeded.
- Errors surfaced to st.session_state["admin_errors"] (a dedicated list,
  parallel to "generation_errors" — kept separate since this is a
  distinct workflow from mockup generation), never silently swallowed.
- Explicit try/finally + .close() on every PIL Image, gc.collect() after
  heavy operations.

Integration into mockup_web_app_V2.py:

    from admin_add_site import render_add_site_trigger

    ...
    render_add_site_trigger(
        template_dir=TEMPLATE_DIR / "Digital",
        tmp_dir=TMP_DIR,
        max_edge=MAX_EDGE,
        max_pixels=MAX_PIXELS,
    )

    # Wherever TEMPLATE_COORDINATES is read to build the site list or look
    # up coords during generation, merge in this session's additions:
    all_coordinates = {**TEMPLATE_COORDINATES, **st.session_state.get("custom_templates", {})}

See README_ADD_SITE.md for the full wiring diff and setup notes.
"""

from __future__ import annotations

import gc
import os
import secrets
import shutil
import uuid
from pathlib import Path
from typing import Optional

import streamlit as st
from PIL import Image

import github_sync
from template_detect import (
    compute_ideal_template_height,
    detect_transparent_quad,
    draw_quad_overlay,
    scale_quad,
)

try:
    from streamlit_image_coordinates import streamlit_image_coordinates

    HAS_CLICK_COMPONENT = True
except ImportError:
    HAS_CLICK_COMPONENT = False

PREVIEW_MAX_EDGE = 1000


# ---------------------------
# State management
# ---------------------------
def _cleanup_admin_job_dir() -> None:
    old_dir = st.session_state.get("admin_job_dir")
    if old_dir:
        try:
            shutil.rmtree(Path(old_dir), ignore_errors=True)
        except Exception:
            pass  # best-effort cleanup only; never block the UI on this


def _reset_admin_state(tmp_dir: Path) -> None:
    _cleanup_admin_job_dir()

    job_dir = tmp_dir / f"admin_{uuid.uuid4().hex}"
    job_dir.mkdir(parents=True, exist_ok=True)

    st.session_state["admin_job_dir"] = str(job_dir)
    st.session_state["admin_upload_bytes"] = None
    st.session_state["admin_upload_name"] = None
    st.session_state["admin_quad"] = None
    st.session_state["admin_working_path"] = None
    st.session_state["admin_errors"] = []


def _ensure_admin_state(tmp_dir: Path) -> None:
    if "admin_upload_bytes" not in st.session_state:
        _reset_admin_state(tmp_dir)
    st.session_state.setdefault("custom_templates", {})
    st.session_state.setdefault("admin_errors", [])
    st.session_state.setdefault("admin_authenticated", False)
    st.session_state.setdefault("admin_working_path", None)


def _verify_password(entered: str) -> bool:
    """
    Constant-time comparison against the ADMIN_PASSWORD env var. Fails
    CLOSED: if ADMIN_PASSWORD isn't set at all, no input can ever match, so
    access is denied entirely rather than silently letting everyone through
    on a misconfiguration — the opposite of GITHUB_TOKEN's fail-open
    degradation, deliberately, since this gate exists specifically to
    restrict who can reach the upload/detect/save/commit flow at all.
    """
    expected = os.environ.get("ADMIN_PASSWORD")
    if not expected:
        return False
    return secrets.compare_digest(entered, expected)


def _resize_if_oversized(src_path: Path, dest_path: Path, max_edge: int, max_pixels: int) -> Path:
    """
    Mirrors prepare_artwork_file()'s resize behaviour: if the uploaded
    template exceeds the app's safety limits, resize losslessly to PNG and
    return the resized path; otherwise return src_path unchanged.
    """
    img = None
    resized = None
    try:
        img = Image.open(src_path)
        width, height = img.size
        total_pixels = width * height

        if total_pixels <= max_pixels and max(width, height) <= max_edge:
            return src_path

        scale_factor = min(max_edge / width, max_edge / height)
        new_size = (max(1, int(width * scale_factor)), max(1, int(height * scale_factor)))
        resized = img.resize(new_size, Image.LANCZOS)
        resized.convert("RGBA").save(dest_path, "PNG", optimize=True)
        return dest_path
    finally:
        if resized is not None:
            resized.close()
        if img is not None:
            img.close()
        gc.collect()


# ---------------------------
# Public entry point
# ---------------------------
def render_add_site_trigger(
    template_dir: Path,
    tmp_dir: Path,
    max_edge: int = 8000,
    max_pixels: int = 50_000_000,
) -> None:
    """
    Renders the 'Add Site' button, fixed to the bottom-right corner via CSS
    (see the .gawk-addsite-anchor rules in mockup_web_app_V2.py's style
    block — same sentinel-container trick already used for the white card).
    """
    _ensure_admin_state(tmp_dir)

    trigger_container = st.container()
    trigger_container.markdown('<span class="gawk-addsite-anchor"></span>', unsafe_allow_html=True)
    with trigger_container:
        if st.button("➕ Add Site", key="open_add_site_dialog"):
            _reset_admin_state(tmp_dir)
            _add_site_dialog(template_dir, tmp_dir, max_edge, max_pixels)


@st.dialog("Add New Site (single-panel)", width="large")
def _add_site_dialog(template_dir: Path, tmp_dir: Path, max_edge: int, max_pixels: int) -> None:
    _ensure_admin_state(tmp_dir)

    if not st.session_state["admin_authenticated"]:
        gate_placeholder = st.empty()
        with gate_placeholder.container():
            just_unlocked = _render_password_gate()
        if not just_unlocked:
            return
        # Clear the password UI immediately — same render pass, no rerun.
        # Without this, the password prompt (already drawn to the page by
        # the time we know it succeeded) would stay stacked above the form
        # that renders next, since Streamlit can't "un-render" elements
        # that already executed earlier in the same script run.
        gate_placeholder.empty()

    job_dir = Path(st.session_state["admin_job_dir"])

    if not github_sync.is_configured():
        st.info(
            "GITHUB_TOKEN isn't set, so new sites will work for this session only "
            "and won't survive a redeploy. Add GITHUB_TOKEN to Render's environment "
            "variables for sites to persist automatically."
        )

    st.caption(
        "Multi-panel (split-screen) sites aren't supported here yet — use the "
        "existing click_points.py tool for those and add the entry by hand."
    )

    uploaded = st.file_uploader(
        "Template PNG (with transparent billboard window)", type=["png"], key="admin_upload"
    )

    if uploaded is not None and st.session_state["admin_upload_name"] != uploaded.name:
        st.session_state["admin_upload_bytes"] = uploaded.getvalue()
        st.session_state["admin_upload_name"] = uploaded.name
        st.session_state["admin_quad"] = None
        st.session_state["admin_working_path"] = None

    if not st.session_state["admin_upload_bytes"]:
        st.caption("Upload a template to auto-detect the billboard window.")
        _render_admin_errors()
        return

    raw_path = job_dir / f"raw_{st.session_state['admin_upload_name']}"
    raw_path.write_bytes(st.session_state["admin_upload_bytes"])

    resized_path = job_dir / f"resized_{st.session_state['admin_upload_name']}"
    try:
        safety_capped_path = _resize_if_oversized(raw_path, resized_path, max_edge, max_pixels)
    except Exception as e:
        st.session_state["admin_errors"].append(f"❌ Could not process uploaded template: {e}")
        _render_admin_errors()
        return

    if st.session_state["admin_quad"] is None:
        with st.spinner("Detecting billboard window…"):
            try:
                detected_quad = detect_transparent_quad(safety_capped_path)
            except ValueError as e:
                st.session_state["admin_errors"].append(
                    f"❌ {e} If this site has more than one transparent window (multi-panel), "
                    "this tool can't handle it yet — use click_points.py instead."
                )
                _render_admin_errors()
                return

            # Silent, quality-aware resize — never surfaced to the admin. Shrinks
            # the template (and scales its detected quad to match) down to what
            # this specific photo's own framing geometry actually needs for a
            # crisp result, calibrated against a real confirmed test. Never
            # upscales: if the source can't reach the target even at full
            # resolution, it's left as-is rather than faking quality.
            img = None
            try:
                img = Image.open(safety_capped_path)
                native_w, native_h = img.size
            finally:
                if img is not None:
                    img.close()

            quad_h = max(p[1] for p in detected_quad) - min(p[1] for p in detected_quad)
            ideal_h = compute_ideal_template_height(native_h, quad_h)

            if ideal_h < native_h:
                scale = ideal_h / native_h
                final_path = job_dir / f"final_{st.session_state['admin_upload_name']}"
                src_img = None
                resized_img = None
                try:
                    src_img = Image.open(safety_capped_path)
                    new_size = (round(native_w * scale), round(native_h * scale))
                    resized_img = src_img.resize(new_size, Image.LANCZOS)
                    resized_img.convert("RGBA").save(final_path, "PNG", optimize=True)
                finally:
                    if resized_img is not None:
                        resized_img.close()
                    if src_img is not None:
                        src_img.close()
                    gc.collect()

                st.session_state["admin_working_path"] = str(final_path)
                st.session_state["admin_quad"] = scale_quad(detected_quad, scale)
            else:
                st.session_state["admin_working_path"] = str(safety_capped_path)
                st.session_state["admin_quad"] = detected_quad

    working_path = Path(st.session_state["admin_working_path"])
    quad = st.session_state["admin_quad"]

    st.markdown("**Detected billboard window** — corners are TL / TR / BR / BL.")

    preview = None
    try:
        if HAS_CLICK_COMPONENT:
            corner_choice = st.selectbox(
                "To fix a corner: select it here, then click its correct position on the image.",
                ["(none — looks correct)", "TL", "TR", "BR", "BL"],
                key="admin_adjust_corner_select",
            )
            preview = draw_quad_overlay(working_path, quad, max_edge=PREVIEW_MAX_EDGE)
            full = None
            try:
                full = Image.open(working_path)
                scale = preview.width / full.width
            finally:
                if full is not None:
                    full.close()

            click = streamlit_image_coordinates(preview, key="admin_click")

            if corner_choice != "(none — looks correct)" and click is not None:
                idx = ["TL", "TR", "BR", "BL"].index(corner_choice)
                new_point = (int(click["x"] / scale), int(click["y"] / scale))
                quad = list(quad)
                quad[idx] = new_point
                st.session_state["admin_quad"] = quad
                st.rerun()
        else:
            preview = draw_quad_overlay(working_path, quad, max_edge=PREVIEW_MAX_EDGE)
            st.image(preview)
            st.caption(
                "Install `streamlit-image-coordinates` (see requirements.txt) to enable "
                "click-to-adjust. Manual overrides for now:"
            )
            cols = st.columns(4)
            labels = ["TL", "TR", "BR", "BL"]
            new_quad = []
            for i, label in enumerate(labels):
                with cols[i]:
                    x = st.number_input(f"{label} x", value=quad[i][0], key=f"admin_{label}_x")
                    y = st.number_input(f"{label} y", value=quad[i][1], key=f"admin_{label}_y")
                    new_quad.append((int(x), int(y)))
            st.session_state["admin_quad"] = new_quad
            quad = new_quad
    finally:
        if preview is not None:
            preview.close()
        gc.collect()

    st.divider()

    site_name = st.text_input(
        "Site filename (must match the naming convention, e.g. 'Geelong (Digital) - 32201-D.png')",
        value=st.session_state["admin_upload_name"] or "",
        key="admin_site_name",
    )

    save_clicked = st.button("Save Site", type="primary", width="stretch")

    if save_clicked:
        _handle_save(site_name, quad, working_path, template_dir, job_dir)

    _render_admin_errors()


def _render_admin_errors() -> None:
    for error in st.session_state.get("admin_errors", []):
        st.error(error)


def _render_password_gate() -> bool:
    """
    The actual security boundary for this feature. The '+ Add Site' button
    itself stays visible to everyone — hiding a button client-side isn't
    real protection anyway, since nothing prevents inspecting/re-triggering
    it. The real gate is here: no upload/detect/save/GitHub-commit code
    in the caller ever executes without a correct password, checked
    server-side in Python before anything else in the dialog runs.

    Returns True only on the exact render pass where the correct password
    was just submitted — the caller uses this to fall through immediately
    into the rest of the dialog in the SAME call, rather than relying on
    st.rerun() to reopen a separate dialog invocation (which is what caused
    the "have to click Add Site again" bug this replaces).
    """
    if not os.environ.get("ADMIN_PASSWORD"):
        st.error(
            "❌ Adding sites is locked, and ADMIN_PASSWORD isn't configured, so "
            "nobody can unlock it right now. Set ADMIN_PASSWORD in Render's "
            "environment variables (and export it locally for local testing) to "
            "enable access."
        )
        return False

    st.markdown("**This area is password-protected.**")
    entered = st.text_input("Password", type="password", key="admin_password_input")

    if st.button("Unlock", key="admin_password_submit"):
        if _verify_password(entered):
            st.session_state["admin_authenticated"] = True
            return True
        else:
            st.session_state["admin_errors"].append("❌ Incorrect password.")

    _render_admin_errors()
    return False


def _handle_save(site_name: str, quad, working_path: Path, template_dir: Path, job_dir: Path) -> None:
    if not site_name.strip():
        st.session_state["admin_errors"].append("Please enter a site filename.")
        return

    if (template_dir / site_name).exists():
        st.session_state["admin_errors"].append(
            f"❌ '{site_name}' already exists in Templates/Digital/. Choose a different "
            f"filename, or delete/rename the existing template first if you meant to replace it."
        )
        return

    png_bytes = working_path.read_bytes()
    coords_payload = {"split_ratio": [1.0], "LHS": quad}

    # 1. Immediate, this-session availability: write locally + merge into
    #    the in-memory template list (TEMPLATE_COORDINATES was already
    #    imported at process start, so a disk write alone wouldn't show up
    #    in the running app without this).
    try:
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / site_name).write_bytes(png_bytes)
        st.session_state["custom_templates"][site_name] = coords_payload
    except Exception as e:
        st.session_state["admin_errors"].append(f"❌ Could not save template locally: {e}")
        return

    # 2. Durable persistence via GitHub — best-effort, never silent.
    if github_sync.is_configured():
        try:
            github_sync.commit_site(site_name, quad, png_bytes)
            st.success(
                f"✅ '{site_name}' is ready to use now, and committed to GitHub for future deploys."
            )
        except Exception as e:
            st.warning(
                f"⚠️ '{site_name}' is ready to use for this session, but the GitHub commit "
                f"failed: {e}\n\nPaste this into template_coordinates.py manually to persist it:"
            )
            st.code(github_sync.format_entry(site_name, quad), language="python")
    else:
        st.success(f"✅ '{site_name}' is ready to use for this session.")
        st.caption("GITHUB_TOKEN not set — paste this into template_coordinates.py to persist it:")
        st.code(github_sync.format_entry(site_name, quad), language="python")

    # Working files are already copied to template_dir / committed to GitHub;
    # the job-scoped tmp copy is no longer needed.
    _cleanup_admin_job_dir()
    st.session_state["admin_upload_bytes"] = None
    st.session_state["admin_upload_name"] = None
    gc.collect()
