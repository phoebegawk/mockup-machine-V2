import os
import zipfile
from PIL import Image
import streamlit as st

from mockup_utils_V2 import generate_mockup, generate_filename, generate_multi_panel_mockup
from template_coordinates import TEMPLATE_COORDINATES

# --- Artwork Safety Limits ---
MAX_EDGE = 8000            # max width/height in pixels
MAX_PIXELS = 50_000_000    # max total pixel count (50 megapixels)

# UI Config
st.set_page_config(page_title="Mock Up Machine", layout="wide")

# Header
st.image("https://raw.githubusercontent.com/phoebegawk/mockup-machine/main/Header-UI-Mock.png", use_container_width=True)

# Style Block
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat&display=swap');

    html, body, .main, .stApp, .stAppViewContainer {
        background-color: #542D54 !important;
        color: white !important;
        font-family: 'Montserrat', sans-serif !important;
        font-size: 18px !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    header, .st-emotion-cache-18ni7ap {
        background-color: #542D54 !important;
    }

    .block-container {
        padding-top: 2rem !important;
    }

    /* Generic input + Streamlit widgets */
    input, textarea, select,
    .stTextInput input,
    .stTextArea textarea,
    .stDateInput input,
    .stMultiSelect > div,
    .stSelectbox > div {
        border-radius: 8px !important;
        border: 1px solid white !important;
        box-shadow: none !important;
        background-color: #A27DA2 !important;
        color: black !important;
        font-family: 'Montserrat', sans-serif !important;
    }

    /* Multiselect container */
    div[data-baseweb="select"] {
        background-color: transparent !important;
        box-shadow: none !important;
    }

    /* Multiselect dropdown */
    div[data-baseweb="select"] > div {
        background-color: #A27DA2 !important;
        border: 1px solid white !important;
        border-radius: 8px !important;
        color: white !important;
    }

    /* Remove stroke line (border/outline) from combobox */
    div[data-baseweb="select"] div[role="combobox"] {
        color: white !important;
        outline: none !important;
        border: none !important;
        box-shadow: none !important;
    }

    /* "Choose options" + multiselect typed text -> WHITE (overrides global input color:black) */
    div[data-baseweb="select"] input {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    div[data-baseweb="select"] input::placeholder {
        color: #FFFFFF !important;
        opacity: 1 !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    /* "Choose options" is often rendered as text/span inside combobox (not placeholder) */
    div[data-baseweb="select"] div[role="combobox"] span,
    div[data-baseweb="select"] div[role="combobox"] div,
    div[data-baseweb="select"] div[role="combobox"] p {
        color: #FFFFFF !important;
    }

    /* Multiselect selected tags/chips -> Gawk Purple */
    div[data-baseweb="tag"],
    span[data-baseweb="tag"] {
        background-color: #542D54 !important;
        color: #FFFFFF !important;
        border-radius: 6px !important;
        border: 1px solid #542D54 !important;
        font-family: 'Montserrat', sans-serif !important;
    }

    /* Tag text */
    div[data-baseweb="tag"] span,
    span[data-baseweb="tag"] span {
        color: #FFFFFF !important;
    }

    /* Tag remove "x" icon */
    div[data-baseweb="tag"] svg,
    span[data-baseweb="tag"] svg {
        fill: #FFFFFF !important;
        color: #FFFFFF !important;
    }

    /* File uploader container */
    section[data-testid="stFileUploader"] {
        background-color: #A27DA2 !important;
        border: 1px solid white !important;
        border-radius: 8px !important;
        box-shadow: none !important;
    }

    /* Uploaded file name text -> WHITE */
    section[data-testid="stFileUploader"] ul,
    section[data-testid="stFileUploader"] li,
    section[data-testid="stFileUploader"] li * {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    section[data-testid="stFileUploader"] label > div {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        text-align: left;
    }

    section[data-testid="stFileUploader"] p {
        text-align: left;
    }

    /* Browse files button text + icon -> GREY (visible on light container) */
    section[data-testid="stFileUploader"] button,
    section[data-testid="stFileUploader"] button span,
    section[data-testid="stFileUploader"] button * {
        color: #6B6B6B !important;
        -webkit-text-fill-color: #6B6B6B !important;
    }

    /* SVG icon inside the button */
    section[data-testid="stFileUploader"] button svg,
    section[data-testid="stFileUploader"] button svg * {
        fill: #6B6B6B !important;
        color: #6B6B6B !important;
    }

    /* Fix hover state */
    section[data-testid="stFileUploader"] button:hover {
        background-color: #C8A7C9 !important;
        color: #542D54 !important;
    }

    /* Fix disabled state */
    section[data-testid="stFileUploader"] button:disabled {
        background-color: #d0c0d3 !important;
        color: #542D54 !important;
        opacity: 0.5 !important;
        cursor: not-allowed !important;
    }

    /* Main buttons + download */
    .stButton > button,
    .stDownloadButton > button {
        display: block;
        margin: 0 auto;
        background-color: #A27DA2 !important;
        color: white !important;
        border: 1px solid white !important;
        border-radius: 8px !important;
        font-family: 'Montserrat', sans-serif !important;
    }

    .stButton > button:hover {
        background-color: #C8A7C9 !important;
        color: white !important;
    }

    .stButton > button:disabled,
    .stDownloadButton > button:disabled {
        background-color: #d0c0d3 !important;
        color: grey !important;
        opacity: 0.5;
        cursor: not-allowed !important;
    }

    .stDownloadButton > button:disabled {
        color: white !important;
        opacity: 0.4 !important;
    }

    /* Labels and headings */
    label, .css-1cpxqw2 {
        color: white !important;
        font-family: 'Montserrat', sans-serif !important;
    }

    /* Remove focus border glow from all inputs */
    input:focus,
    textarea:focus,
    select:focus,
    div[data-baseweb="select"]:focus {
        outline: none !important;
        box-shadow: none !important;
    }
    </style>
""", unsafe_allow_html=True)

if "generated_outputs" not in st.session_state:
    st.session_state["generated_outputs"] = []

if "zip_bytes" not in st.session_state:
    st.session_state["zip_bytes"] = None

if "zip_name" not in st.session_state:
    st.session_state["zip_name"] = None

# Paths
TEMPLATE_DIR = "Templates"
OUTPUT_DIR = "generated_mockups"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Template Selection
template_keys = list(TEMPLATE_COORDINATES.keys())
template_display_names = [name.replace(".png", "") for name in template_keys]
selected_display_names = st.multiselect("📍 Select Billboard(s):", template_display_names)
selected_templates = [name + ".png" for name in selected_display_names]

# Artwork Upload
artwork_files = st.file_uploader("🖼️ Upload Artwork File(s):", type=["jpg", "jpeg"], accept_multiple_files=True)

# Artwork preview with filename (SAFE VERSION WITH LIMIT + AUTO-RESIZE)
if artwork_files:
    os.makedirs("uploaded_artwork", exist_ok=True)

    cols = st.columns(4)  # Up to 4 previews per row

    for idx, file in enumerate(artwork_files):
        artwork_path = os.path.join("uploaded_artwork", file.name)

        try:
            # Load uploaded file into Pillow
            img = Image.open(file)
            width, height = img.size
            total_pixels = width * height

            # Check if image exceeds safe limits
            if total_pixels > MAX_PIXELS or max(width, height) > MAX_EDGE:
                st.warning(
                    f"⚠️ {file.name} is very large ({width}×{height}). "
                    f"It will be automatically resized to stay under the safe limit "
                    f"({MAX_EDGE}px max edge / 50MP)."
                )

                # Auto-resize proportionally
                scale_factor = min(MAX_EDGE / width, MAX_EDGE / height)
                new_size = (int(width * scale_factor), int(height * scale_factor))
                img = img.resize(new_size, Image.LANCZOS)

            # Save processed or original image
            img.save(artwork_path, "JPEG", quality=95)

            # --- Final safety check (image MUST be safe at this point) ---
            img_check = Image.open(artwork_path)
            w, h = img_check.size
            if (w * h) > MAX_PIXELS or max(w, h) > MAX_EDGE:
                st.error(
                    f"❌ {file.name} still exceeds safe size after resizing: {w}×{h}. "
                    "This file may be corrupted or unsupported."
                )
                continue

        except Exception as e:
            st.error(f"❌ Error processing {file.name}: {e}")
            continue

        # Display preview
        with cols[idx % 4]:
            st.image(artwork_path, caption=file.name, use_container_width=True)
            st.markdown("<div style='margin-bottom: -10px;'></div>", unsafe_allow_html=True)

# Client & Date Input
client_name = st.text_input("🔍 Client Name:")
live_date = st.text_input("🗓️ Live Date (DDMMYY):")

# --- Centered Row with Always-Visible Buttons ---
st.markdown("""
    <div style='display: flex; justify-content: center; gap: 2rem; margin-top: 1.5rem;'>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    generate_clicked = st.button("Generate", use_container_width=True)

with col2:
    is_ready = st.session_state["zip_bytes"] is not None

    st.download_button(
        label="Download Mock Ups",
        data=st.session_state["zip_bytes"] if is_ready else b"",
        file_name=st.session_state["zip_name"] if is_ready else "mockups.zip",
        mime="application/zip",
        disabled=not is_ready,
        use_container_width=True,
        key="download_button"
    )

st.markdown("</div>", unsafe_allow_html=True)

# Trigger generation logic
if generate_clicked:
    st.session_state["generated_outputs"] = []
    st.session_state["generation_errors"] = []
    st.session_state["zip_bytes"] = None
    st.session_state["zip_name"] = None

    if not selected_templates:
        st.session_state["generation_errors"].append("Please select at least one template.")
    elif not artwork_files:
        st.session_state["generation_errors"].append("Please upload at least one artwork file.")
    elif not client_name or not live_date:
        st.session_state["generation_errors"].append("Please enter client name and live date.")
    else:
        for selected_template in selected_templates:
            if not selected_template.endswith(".png"):
                selected_template += ".png"

            template_path = os.path.join(TEMPLATE_DIR, "Digital", selected_template)

            template_data = TEMPLATE_COORDINATES.get(selected_template)
            if not template_data:
                st.session_state["generation_errors"].append(f"Coordinates not found for {selected_template}.")
                continue

            panel_keys = [k for k in ("LHS", "MID", "RHS") if k in template_data]
            is_multi_panel = "split_ratios" in template_data and len(panel_keys) >= 2
            coords = template_data if is_multi_panel else template_data["LHS"]

            for artwork_file in artwork_files:
                try:
                    artwork_path = os.path.join("uploaded_artwork", artwork_file.name)

                    # If preview step didn't write it for some reason, write it now
                    if not os.path.exists(artwork_path):
                        os.makedirs("uploaded_artwork", exist_ok=True)
                        with open(artwork_path, "wb") as f:
                            f.write(artwork_file.getbuffer())

                    filename_no_ext = os.path.splitext(artwork_file.name)[0]
                    parts = filename_no_ext.split(" - ")

                    if len(parts) >= 3:
                        campaign_name = parts[1].strip()
                    else:
                        campaign_name = parts[-1].strip()

                    final_filename = generate_filename(selected_template, client_name, campaign_name, live_date)

                    output_path = os.path.join(OUTPUT_DIR, final_filename)
                    base, ext = os.path.splitext(output_path)

                    counter = 1
                    temp_output_path = output_path
                    while os.path.exists(temp_output_path):
                        temp_output_path = f"{base}_{counter}{ext}"
                        counter += 1

                    output_path = temp_output_path
                    final_filename = os.path.basename(output_path)

                    if is_multi_panel:
                        generate_multi_panel_mockup(template_path, artwork_path, output_path, coords)
                    else:
                        generate_mockup(template_path, artwork_path, output_path, coords)

                    st.session_state["generated_outputs"].append((final_filename, output_path))

                except Exception as e:
                    st.session_state["generation_errors"].append(
                        f"❌ Error generating mockup for {selected_template}: {e}"
                    )

        # ✅ Build ZIP bytes immediately so Download activates on the same click
        if st.session_state["generated_outputs"]:
            import io

            zip_name = f"Mock_Ups_{client_name}_{live_date}.zip"
            buffer = io.BytesIO()

            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for filename, file_path in st.session_state["generated_outputs"]:
                    if os.path.exists(file_path):
                        zipf.write(file_path, arcname=filename)

            buffer.seek(0)
            st.session_state["zip_bytes"] = buffer.getvalue()
            st.session_state["zip_name"] = zip_name

# ✅ Display thumbnails in a 4-column layout (lower memory)
if st.session_state["generated_outputs"]:
    from PIL import Image

    cols = st.columns(4)
    for i, (filename, path) in enumerate(st.session_state.generated_outputs):
        with cols[i % 4]:
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    img.thumbnail((300, 300))
                    st.image(img, caption=filename, use_container_width=True)
                except Exception as e:
                    st.error(f"⚠️ Could not load {filename}: {e}")
            else:
                st.warning(f"⚠️ Missing file: {filename}")

# Summary feedback
    successful = [f for f, p in st.session_state.generated_outputs if os.path.exists(p)]
    missing = [f for f, p in st.session_state.generated_outputs if not os.path.exists(p)]

    if successful:
        st.success(f"✅ {len(successful)} mockup(s) generated successfully.")
    if missing:
        st.warning(f"⚠️ {len(missing)} mockup(s) missing or failed to load.")
        
# Display error messages after generation
if "generation_errors" in st.session_state:
    for error in st.session_state["generation_errors"]:
        st.error(error)
