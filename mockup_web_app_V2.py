import os
import shutil
import uuid
import zipfile
import gc
from contextlib import suppress
from pathlib import Path

from PIL import Image, ImageOps
import streamlit as st

from mockup_utils_V2 import generate_mockup, generate_filename, generate_multi_panel_mockup
from template_coordinates import TEMPLATE_COORDINATES

# --- Artwork Safety Limits ---
MAX_EDGE = 8000            # max width/height in pixels
MAX_PIXELS = 50_000_000    # max total pixel count (50 megapixels)
PREVIEW_THUMBNAIL = (1200, 1200)
RESULT_THUMBNAIL = (300, 300)

# ---------------------------
# Paths
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "Templates"
OUTPUT_DIR = BASE_DIR / "generated_mockups"
UPLOAD_DIR = BASE_DIR / "uploaded_artwork"
TMP_DIR = BASE_DIR / "tmp"

OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)


# ---------------------------
# Helpers
# ---------------------------
def safe_remove_file(path: Path) -> None:
    with suppress(Exception):
        if path.exists() and path.is_file():
            path.unlink()


def safe_remove_dir_contents(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        return
    for item in path.iterdir():
        with suppress(Exception):
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()


def cleanup_job_files(job_dir: Path) -> None:
    with suppress(Exception):
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)


def file_size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0


def prepare_artwork_file(uploaded_file, target_dir: Path):
    """
    Saves the uploaded artwork to disk while preserving current logic:
    - Original JPG/JPEG/PNG bytes are kept as-is unless resize is required.
    - Oversized files are resized and stored losslessly as PNG.
    Returns metadata for downstream use.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(uploaded_file.name).name
    base_name = Path(original_name).stem
    original_ext = Path(original_name).suffix.lower()
    original_path = target_dir / original_name
    png_resized_path = target_dir / f"{base_name}.png"

    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    with Image.open(uploaded_file) as opened:
        img = ImageOps.exif_transpose(opened)
        width, height = img.size
        total_pixels = width * height
        needs_resize = (total_pixels > MAX_PIXELS) or (max(width, height) > MAX_EDGE)

        if needs_resize:
            scale_factor = min(MAX_EDGE / width, MAX_EDGE / height)
            new_size = (max(1, int(width * scale_factor)), max(1, int(height * scale_factor)))
            resized = img.resize(new_size, Image.LANCZOS)
            try:
                resized.convert("RGBA").save(png_resized_path, "PNG", optimize=True)
            finally:
                resized.close()
            saved_path = png_resized_path
        else:
            try:
                uploaded_file.seek(0)
            except Exception:
                pass
            with open(original_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            saved_path = original_path

    gc.collect()

    return {
        "original_name": original_name,
        "base_name": base_name,
        "original_ext": original_ext,
        "saved_path": saved_path,
        "original_path": original_path,
        "png_resized_path": png_resized_path,
        "width": width,
        "height": height,
        "total_pixels": total_pixels,
        "needs_resize": needs_resize,
    }


def build_preview_image(path: Path):
    with Image.open(path) as img:
        preview = ImageOps.exif_transpose(img)
        preview.thumbnail(PREVIEW_THUMBNAIL)
        return preview.copy()


def build_result_thumbnail(path: Path):
    with Image.open(path) as img:
        thumb = ImageOps.exif_transpose(img)
        thumb.thumbnail(RESULT_THUMBNAIL)
        return thumb.copy()


def clear_generation_state():
    st.session_state["generated_outputs"] = []
    st.session_state["zip_path"] = None
    st.session_state["zip_name"] = None
    st.session_state["generation_errors"] = []
    st.session_state["rerun_after_generate"] = False
    st.session_state["active_job_dir"] = None


# ---------------------------
# UI Config
# ---------------------------
st.set_page_config(
    page_title="Mock Up Machine",
    layout="wide",
    page_icon="assets/favicon.png",
)

# Header
HEADER_PATH = BASE_DIR / "assets" / "Header-MockUpMachine.png"

if HEADER_PATH.exists():
    st.image(str(HEADER_PATH), use_container_width=True)
else:
    st.warning(f"Header image not found: {HEADER_PATH}")

# ---------------------------
# Style Block (CLEAN + FINAL)
# ---------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');

/* -----------------------------------
   GLOBAL PAGE (background untouched)
----------------------------------- */
.stApp {
    background-color: #542D54 !important;
    background-image: url("https://raw.githubusercontent.com/phoebegawk/mockup-machine/main/assets/MockUpMachine-BG.png") !important;
    background-repeat: no-repeat !important;
    background-size: cover !important;
    background-position: center center !important;
    background-attachment: fixed !important;
}

html, body, .main, .stAppViewContainer {
    background-color: transparent !important;
    color: #FFFFFF !important;
    font-family: 'Montserrat', sans-serif !important;
    font-size: 16px !important;
    margin: 0 !important;
    padding: 0 !important;
}

* {
    font-family: 'Montserrat', sans-serif !important;
    box-sizing: border-box;
}

header, .st-emotion-cache-18ni7ap {
    background-color: transparent !important;
}

.block-container {
    padding-top: 2rem !important;
    max-width: 1200px !important;
}

/* -----------------------------------
   WHITE CARD WRAPPER
   Apply white-card-with-yellow-border styling
   to Streamlit's top-level vertical block groups
   so form controls sit inside panels like Check My Specs.
----------------------------------- */
section.main .block-container > div[data-testid="stVerticalBlock"] {
    background: #FFFFFF !important;
    border-radius: 12px !important;
    border: 3px solid #D7DF23 !important;
    padding: 20px 32px !important;
    margin-bottom: 24px !important;
    color: #542D54 !important;
}

/* Revert the card treatment on nested vertical blocks so we don't
   end up with nested white cards inside the outer card. */
section.main .block-container
    div[data-testid="stVerticalBlock"]
    div[data-testid="stVerticalBlock"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin-bottom: 0 !important;
}

/* Horizontal blocks (st.columns) should stay transparent */
div[data-testid="stHorizontalBlock"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}

/* Header image stays full-width above the cards (no card wrapper) */
section.main .block-container > div[data-testid="stVerticalBlock"]:has(> div[data-testid="stImage"]:first-child:last-child) {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin-bottom: 16px !important;
}

/* -----------------------------------
   LABELS (inside white cards = purple)
----------------------------------- */
label,
.stTextInput label,
.stMultiSelect label,
.stFileUploader label,
.stDateInput label,
div[data-testid="stWidgetLabel"],
div[data-testid="stWidgetLabel"] p {
    color: #542D54 !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    font-family: 'Montserrat', sans-serif !important;
}

/* -----------------------------------
   TEXT INPUTS
----------------------------------- */
.stTextInput input,
.stTextArea textarea,
.stDateInput input {
    background-color: #FFFFFF !important;
    color: #542D54 !important;
    border-radius: 8px !important;
    border: 2px solid #D7DF23 !important;
    box-shadow: none !important;
    font-size: 16px !important;
    font-weight: 600 !important;
    padding: 10px 14px !important;
}

.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #542D54 !important;
    opacity: 0.6 !important;
}

/* -----------------------------------
   MULTISELECT / SELECT (BaseWeb)
----------------------------------- */
div[data-baseweb="select"] {
    background-color: transparent !important;
    box-shadow: none !important;
}

div[data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    border: 2px solid #D7DF23 !important;
    border-radius: 8px !important;
    color: #542D54 !important;
    min-height: 44px !important;
}

div[data-baseweb="select"] div[role="combobox"] {
    color: #542D54 !important;
    outline: none !important;
    border: none !important;
    box-shadow: none !important;
}

div[data-baseweb="select"] input,
div[data-baseweb="select"] input::placeholder {
    color: #542D54 !important;
    -webkit-text-fill-color: #542D54 !important;
    opacity: 0.8 !important;
    font-weight: 600 !important;
}

div[data-baseweb="select"] div[role="combobox"] span,
div[data-baseweb="select"] div[role="combobox"] div,
div[data-baseweb="select"] div[role="combobox"] p {
    color: #542D54 !important;
}

/* Selected tags (multiselect chips) */
div[data-baseweb="tag"],
span[data-baseweb="tag"] {
    background-color: #542D54 !important;
    color: #FFFFFF !important;
    border-radius: 6px !important;
    border: 1px solid #542D54 !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 600 !important;
}
div[data-baseweb="tag"] span,
span[data-baseweb="tag"] span {
    color: #FFFFFF !important;
}
div[data-baseweb="tag"] svg,
span[data-baseweb="tag"] svg {
    fill: #FFFFFF !important;
    color: #FFFFFF !important;
}

/* Dropdown menu popup */
div[data-baseweb="popover"] ul,
div[data-baseweb="menu"] {
    background: #FFFFFF !important;
    border: 2px solid #D7DF23 !important;
    border-radius: 10px !important;
}

div[data-baseweb="popover"] li,
div[data-baseweb="menu"] li {
    color: #542D54 !important;
    font-weight: 600 !important;
}

div[data-baseweb="popover"] li:hover,
div[data-baseweb="menu"] li:hover {
    background: #F2F2F2 !important;
}

/* -----------------------------------
   FILE UPLOADER (dashed purple drop zone)
----------------------------------- */
div[data-testid="stFileUploader"] {
    background-color: #F7F7F7 !important;
    border: 3px dashed #542D54 !important;
    border-radius: 12px !important;
    box-shadow: none !important;
    padding: 8px !important;
}

div[data-testid="stFileUploader"]:hover {
    background-color: #ECECEC !important;
    border-color: #D7DF23 !important;
}

div[data-testid="stFileUploader"] label {
    display: none !important;
    visibility: hidden !important;
}

div[data-testid="stFileUploaderDropzone"] {
    background-color: transparent !important;
    border: none !important;
}

div[data-testid="stFileUploaderDropzone"] * {
    color: #542D54 !important;
    -webkit-text-fill-color: #542D54 !important;
    fill: #542D54 !important;
    opacity: 1 !important;
    font-weight: 600 !important;
}

div[data-testid="stFileUploaderDropzone"] svg,
div[data-testid="stFileUploaderDropzone"] svg * {
    fill: #542D54 !important;
    color: #542D54 !important;
    opacity: 1 !important;
}

/* "Browse files" button inside uploader \u2014 styled as yellow pill */
div[data-testid="stFileUploader"] button {
    background-color: #D7DF23 !important;
    border: none !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-weight: 700 !important;
    padding: 10px 24px !important;
}

div[data-testid="stFileUploader"] button,
div[data-testid="stFileUploader"] button * {
    color: #542D54 !important;
    -webkit-text-fill-color: #542D54 !important;
    opacity: 1 !important;
}

div[data-testid="stFileUploader"] [role="button"],
div[data-testid="stFileUploader"] [role="button"] * {
    color: #542D54 !important;
    -webkit-text-fill-color: #542D54 !important;
    opacity: 1 !important;
}

div[data-testid="stFileUploader"] button:hover {
    background-color: #C8D51E !important;
    border-color: transparent !important;
}

/* Uploaded file list row shown inside uploader after upload */
div[data-testid="stFileUploader"] small,
div[data-testid="stFileUploader"] [data-testid="stFileUploaderFileName"] {
    color: #542D54 !important;
}

/* -----------------------------------
   BUTTONS (Generate / Reset / Download)
   Match Check My Specs .gawk-button pill style
----------------------------------- */
.stButton > button,
.stDownloadButton > button {
    display: block;
    margin: 0 auto;
    background-color: #D7DF23 !important;
    color: #542D54 !important;
    border: none !important;
    border-radius: 999px !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 700 !important;
    font-size: 16px !important;
    padding: 14px 32px !important;
    box-shadow: none !important;
    transition: 0.2s ease !important;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    background-color: #C8D51E !important;
    color: #542D54 !important;
}

.stButton > button:disabled,
.stDownloadButton > button:disabled {
    background-color: #D7DF23 !important;
    color: #542D54 !important;
    opacity: 0.4 !important;
    cursor: not-allowed !important;
}

/* -----------------------------------
   RESULTS: st.success / warning / error
   Match Check My Specs result-box style
----------------------------------- */
div[data-testid="stAlert"] {
    background: #FFFFFF !important;
    border: 3px solid #D7DF23 !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
    color: #542D54 !important;
    font-size: 14px !important;
    line-height: 1.45 !important;
    box-shadow: none !important;
}

div[data-testid="stAlert"] * {
    color: #542D54 !important;
    font-family: 'Montserrat', sans-serif !important;
}

/* Green accent for success alerts */
div[data-testid="stAlert"][class*="success"] strong,
div[data-testid="stAlert"] [data-testid="stAlertContentSuccess"] strong {
    color: #2A7A34 !important;
}

/* Red accent for error alerts */
div[data-testid="stAlert"][class*="error"] strong,
div[data-testid="stAlert"] [data-testid="stAlertContentError"] strong {
    color: #B00020 !important;
}

/* -----------------------------------
   IMAGE CAPTIONS (thumbnails)
----------------------------------- */
div[data-testid="stImage"] caption,
div[data-testid="stImageCaption"],
figcaption {
    color: #542D54 !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    text-align: center !important;
}

/* -----------------------------------
   FOCUS STATES
----------------------------------- */
input:focus,
textarea:focus,
select:focus,
div[data-baseweb="select"]:focus-within > div {
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(215, 223, 35, 0.35) !important;
    border-color: #D7DF23 !important;
}

/* -----------------------------------
   Header image \u2014 keep current placement,
   full-width, no card wrapper
----------------------------------- */
div[data-testid="stImage"] img {
    border-radius: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Session State Init
# ---------------------------
if "generated_outputs" not in st.session_state:
    st.session_state["generated_outputs"] = []
if "zip_path" not in st.session_state:
    st.session_state["zip_path"] = None
if "zip_name" not in st.session_state:
    st.session_state["zip_name"] = None
if "rerun_after_generate" not in st.session_state:
    st.session_state["rerun_after_generate"] = False
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "reset_nonce" not in st.session_state:
    st.session_state["reset_nonce"] = 0
if "generation_errors" not in st.session_state:
    st.session_state["generation_errors"] = []
if "active_job_dir" not in st.session_state:
    st.session_state["active_job_dir"] = None

# force-reset widgets by changing key (multiselect + text inputs)
SELECT_KEY_BASE = "selected_display_names_widget"
CLIENT_KEY_BASE = "client_name_widget"
DATE_KEY_BASE = "live_date_widget"

nonce = st.session_state["reset_nonce"]
SELECT_KEY = f"{SELECT_KEY_BASE}_{nonce}"
CLIENT_KEY = f"{CLIENT_KEY_BASE}_{nonce}"
DATE_KEY = f"{DATE_KEY_BASE}_{nonce}"

# ---------------------------
# Template Selection
# ---------------------------
template_keys = list(TEMPLATE_COORDINATES.keys())
template_display_names = [name.replace(".png", "") for name in template_keys]

selected_display_names = st.multiselect(
    "📍 Select Billboard(s):",
    template_display_names,
    key=SELECT_KEY,
)
selected_templates = [name + ".png" for name in selected_display_names]

# ---------------------------
# Artwork Upload
# ---------------------------
artwork_files = st.file_uploader(
    "🖼️ Upload Artwork File(s):",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
    key=f"artwork_uploader_{st.session_state['uploader_key']}",
)

prepared_artworks = []
preview_images = []

if artwork_files:
    cols = st.columns(4)

    preview_job_dir = TMP_DIR / "preview_cache"
    preview_job_dir.mkdir(exist_ok=True)

    for idx, file in enumerate(artwork_files):
        artwork_path = UPLOAD_DIR / Path(file.name).name

        try:
            metadata = prepare_artwork_file(file, UPLOAD_DIR)
            prepared_artworks.append(metadata)

            if metadata["needs_resize"]:
                st.warning(
                    f"⚠️ {metadata['original_name']} is very large ({metadata['width']}×{metadata['height']}). "
                    f"It will be resized to stay under safe limits, stored LOSSLESS."
                )

            preview = build_preview_image(metadata["saved_path"])
            preview_images.append(preview)

        except Exception as e:
            st.error(f"❌ Error processing {file.name}: {e}")
            continue

        with cols[idx % 4]:
            st.image(preview_images[-1], caption=os.path.basename(str(metadata["saved_path"])), width="stretch")
            st.markdown("<div style='margin-bottom: -10px;'></div>", unsafe_allow_html=True)

# ---------------------------
# Client & Date Input
# ---------------------------
client_name = st.text_input("🔍 Client Name:", key=CLIENT_KEY)
live_date = st.text_input("🗓️ Live Date (DDMMYY):", key=DATE_KEY)

# ---------------------------
# Buttons Row
# ---------------------------
st.markdown(
    "<div style='display: flex; justify-content: center; gap: 2rem; margin-top: 1.5rem;'>",
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns([1, 1, 1], gap="large")

with col1:
    generate_clicked = st.button("Generate", width="stretch")

with col2:
    zip_path_str = st.session_state.get("zip_path")
    zip_path = Path(zip_path_str) if zip_path_str else None
    is_ready = bool(zip_path and zip_path.exists())

    if is_ready:
        with open(zip_path, "rb") as zip_file:
            st.download_button(
                label="Download Mock Ups",
                data=zip_file,
                file_name=st.session_state.get("zip_name") or zip_path.name,
                mime="application/zip",
                disabled=False,
                width="stretch",
                key="download_button",
            )
    else:
        st.download_button(
            label="Download Mock Ups",
            data=b"",
            file_name="mockups.zip",
            mime="application/zip",
            disabled=True,
            width="stretch",
            key="download_button_disabled",
        )

with col3:
    reset_clicked = st.button("Reset All", width="stretch")

st.markdown("</div>", unsafe_allow_html=True)

# ---------------------------
# Reset Logic
# ---------------------------
if reset_clicked:
    old_job_dir = st.session_state.get("active_job_dir")
    clear_generation_state()

    safe_remove_dir_contents(UPLOAD_DIR)
    safe_remove_dir_contents(OUTPUT_DIR)

    if old_job_dir:
        cleanup_job_files(Path(old_job_dir))

    st.session_state["uploader_key"] += 1
    st.session_state["reset_nonce"] += 1

    gc.collect()
    st.rerun()

# ---------------------------
# Generation Logic
# ---------------------------
if generate_clicked:
    old_job_dir = st.session_state.get("active_job_dir")
    if old_job_dir:
        cleanup_job_files(Path(old_job_dir))

    clear_generation_state()

    if not selected_templates:
        st.session_state["generation_errors"].append("Please select at least one template.")
    elif not artwork_files:
        st.session_state["generation_errors"].append("Please upload at least one artwork file.")
    elif not client_name or not live_date:
        st.session_state["generation_errors"].append("Please enter client name and live date.")
    else:
        job_id = uuid.uuid4().hex
        job_dir = TMP_DIR / f"job_{job_id}"
        job_upload_dir = job_dir / "uploaded_artwork"
        job_output_dir = job_dir / "generated_mockups"
        job_upload_dir.mkdir(parents=True, exist_ok=True)
        job_output_dir.mkdir(parents=True, exist_ok=True)
        st.session_state["active_job_dir"] = str(job_dir)

        generation_artworks = []
        try:
            for artwork_file in artwork_files:
                try:
                    generation_artworks.append(prepare_artwork_file(artwork_file, job_upload_dir))
                except Exception as e:
                    st.session_state["generation_errors"].append(f"❌ Error processing {artwork_file.name}: {e}")

            for selected_template in selected_templates:
                template_path = TEMPLATE_DIR / "Digital" / selected_template

                template_data = TEMPLATE_COORDINATES.get(selected_template)
                if not template_data:
                    st.session_state["generation_errors"].append(f"Coordinates not found for {selected_template}.")
                    continue

                panel_keys = [k for k in ("LHS", "MID", "RHS") if k in template_data]
                is_multi_panel = "split_ratios" in template_data and len(panel_keys) >= 2
                coords = template_data if is_multi_panel else template_data["LHS"]

                for artwork_meta in generation_artworks:
                    try:
                        artwork_path = artwork_meta["saved_path"]
                        filename_no_ext = artwork_meta["base_name"]
                        parts = filename_no_ext.split(" - ")
                        campaign_name = parts[1].strip() if len(parts) >= 3 else parts[-1].strip()

                        final_filename = generate_filename(selected_template, client_name, campaign_name, live_date)
                        output_path = job_output_dir / final_filename

                        base = output_path.stem
                        ext = output_path.suffix
                        counter = 1
                        temp_output_path = output_path
                        while temp_output_path.exists():
                            temp_output_path = job_output_dir / f"{base}_{counter}{ext}"
                            counter += 1

                        output_path = temp_output_path
                        final_filename = output_path.name

                        if is_multi_panel:
                            generate_multi_panel_mockup(str(template_path), str(artwork_path), str(output_path), coords)
                        else:
                            generate_mockup(str(template_path), str(artwork_path), str(output_path), coords)

                        st.session_state["generated_outputs"].append((final_filename, str(output_path)))
                        gc.collect()

                    except Exception as e:
                        st.session_state["generation_errors"].append(
                            f"❌ Error generating mockup for {selected_template}: {e}"
                        )

            if st.session_state["generated_outputs"]:
                zip_name = f"Mock_Ups_{client_name}_{live_date}.zip"
                zip_path = job_dir / zip_name

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for filename, file_path in st.session_state["generated_outputs"]:
                        file_path_obj = Path(file_path)
                        if file_path_obj.exists():
                            zipf.write(file_path_obj, arcname=filename)

                st.session_state["zip_path"] = str(zip_path)
                st.session_state["zip_name"] = zip_name
                st.session_state["rerun_after_generate"] = True
                gc.collect()
                st.rerun()

        finally:
            generation_artworks.clear()
            gc.collect()

# ---------------------------
# Thumbnails + Summary
# ---------------------------
if st.session_state["generated_outputs"]:
    cols = st.columns(4)

    for i, (filename, path) in enumerate(st.session_state["generated_outputs"]):
        with cols[i % 4]:
            path_obj = Path(path)
            if path_obj.exists():
                try:
                    thumb = build_result_thumbnail(path_obj)
                    st.image(thumb, caption=filename, width="stretch")
                    thumb.close()
                except Exception as e:
                    st.error(f"⚠️ Could not load {filename}: {e}")
            else:
                st.warning(f"⚠️ Missing file: {filename}")

    successful = [f for f, p in st.session_state["generated_outputs"] if Path(p).exists()]
    missing = [f for f, p in st.session_state["generated_outputs"] if not Path(p).exists()]

    if successful:
        total_mb = sum(file_size_mb(Path(p)) for _, p in st.session_state["generated_outputs"] if Path(p).exists())
        st.success(f"✅ {len(successful)} mockup(s) generated successfully. Total output size: {total_mb:.2f} MB")
    if missing:
        st.warning(f"⚠️ {len(missing)} mockup(s) missing or failed to load.")

if "generation_errors" in st.session_state:
    for error in st.session_state["generation_errors"]:
        st.error(error)

# Release preview images created during this run.
for preview_img in preview_images:
    with suppress(Exception):
        preview_img.close()

gc.collect()
