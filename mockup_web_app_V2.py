import os
import zipfile
from PIL import Image
import streamlit as st

from mockup_utils_V2 import generate_mockup, generate_filename, generate_multi_panel_mockup
from template_coordinates import TEMPLATE_COORDINATES

# UI Config
st.set_page_config(page_title="Mock Up Machine", layout="wide")

# Header
st.image("https://raw.githubusercontent.com/phoebegawk/mockup-machine/main/Header-UI-Mock.png", width="stretch")

# Finalized Style Block
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

    /* Input fields and dropdowns */
    .stTextInput input,
    .stTextArea textarea,
    .stDateInput input,
    .stMultiSelect > div,
    .stSelectbox > div,
    .stSelectbox label,
    div[data-baseweb="select"] {
        background-color: #A27DA2 !important;
        color: black !important;
        border: none !important;
        box-shadow: none !important;
    }

    /* Remove border highlight on focus */
    input:focus,
    textarea:focus,
    select:focus,
    .stSelectbox:focus,
    .stMultiSelect:focus,
    .stTextInput:focus,
    .stDateInput:focus,
    div[data-baseweb="select"]:focus {
        outline: none !important;
        box-shadow: none !important;
    }

    /* File uploader */
    section[data-testid="stFileUploader"] {
        background-color: #A27DA2 !important;
        border: none !important;
        box-shadow: none !important;
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

    /* Browse Files button */
    section[data-testid="stFileUploader"] button {
        background-color: #A27DA2 !important;
        color: #542D54 !important;
        border: none !important;
        font-weight: bold;
    }

    /* Buttons */
    .stButton > button {
        display: block;
        margin: 0 auto;
        background-color: #A27DA2 !important;
        color: white !important;
        border: none !important;
        font-family: 'Montserrat', sans-serif !important;
    }

    .stButton > button:hover {
        background-color: #C8A7C9 !important;
        color: white !important;
    }

    .stButton > button:disabled {
        background-color: #d0c0d3 !important;
        color: grey !important;
        opacity: 0.5;
        cursor: not-allowed !important;
    }

    /* Labels and headings */
    label, .css-1cpxqw2 {
        color: white !important;
        font-family: 'Montserrat', sans-serif !important;
    }
    </style>
""", unsafe_allow_html=True)

if "generated_outputs" not in st.session_state:
    st.session_state["generated_outputs"] = []

# Paths
TEMPLATE_DIR = "templates"
OUTPUT_DIR = "generated_mockups"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Template Selection
template_keys = list(TEMPLATE_COORDINATES.keys())
template_display_names = [name.replace(".png", "") for name in template_keys]
selected_display_names = st.multiselect("📍 Select Billboard(s):", template_display_names)
selected_templates = [name + ".png" for name in selected_display_names]

# Artwork Upload
artwork_files = st.file_uploader("🖼️ Upload Artwork File(s):", type=["jpg", "jpeg"], accept_multiple_files=True)

# Artwork preview with filename
if artwork_files:
    os.makedirs("uploaded_artwork", exist_ok=True)
    
    cols = st.columns(4)  # Up to 4 previews per row
    for idx, file in enumerate(artwork_files):
        artwork_path = os.path.join("uploaded_artwork", file.name)
        with open(artwork_path, "wb") as f:
            f.write(file.getbuffer())
        with cols[idx % 4]:
            st.image(artwork_path, caption=file.name, width="stretch")
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
    zip_name = f"Mock_Ups_{client_name}_{live_date}.zip"
    zip_path = os.path.join("generated_mockups", zip_name)

    is_ready = bool(st.session_state.generated_outputs)

    if is_ready:
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for filename, file_path in st.session_state.generated_outputs:
                zipf.write(file_path, arcname=filename)

        with open(zip_path, "rb") as f:
            st.download_button(
                label="Download Mock Ups",
                data=f,
                file_name=zip_name,
                mime="application/zip",
                key="download_button_ready",
                use_container_width="stretch"
            )
    else:
        st.download_button(
            label="Download Mock Ups",
            data=b"",
            file_name="",
            mime="application/zip",
            key="download_button_disabled",
            disabled=True,
            use_container_width="stretch"
        )

st.markdown("</div>", unsafe_allow_html=True)

# Trigger generation logic
if generate_clicked:
    st.write("DEBUG: Generate button clicked")
    st.session_state["generated_outputs"] = []
    st.session_state["generation_errors"] = []

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
            template_path = os.path.join("Templates", "Digital", selected_template)

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
                    st.write(f"DEBUG: Generated {final_filename}")

                except Exception as e:
                    st.session_state["generation_errors"].append(
                        f"❌ Error generating mockup for {selected_template}: {e}"
                    )
                    st.error(f"DEBUG: Exception - {e}")

# ✅ Controlled cache clear and rerun logic (safer and more stable)
import time

# Only clear caches and rerun once after generation completes
if generate_clicked:
    time.sleep(0.5)  # Allow Streamlit to settle after generation
    st.cache_resource.clear()
    st.cache_data.clear()
    st.rerun()

# ✅ Display thumbnails in a 4-column layout with resized previews
if st.session_state.generated_outputs:
    import io
    from PIL import Image

    cols = st.columns(4)
    for i, (filename, path) in enumerate(st.session_state.generated_outputs):
        with cols[i % 4]:
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        img_bytes = f.read()
                        image = Image.open(io.BytesIO(img_bytes))
                        image.thumbnail((300, 300))  # Resize to max 300x300 for faster preview
                        st.image(image, caption=filename, use_container_width=True)
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

# Safely check and prepare generated_outputs
if "generated_outputs" in st.session_state and st.session_state.generated_outputs:
    zip_name = f"Mock_Ups_{client_name}_{live_date}.zip"
    zip_path = os.path.join("generated_mockups", zip_name)

    # Create ZIP with all generated mockups
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for filename, file_path in st.session_state.generated_outputs:
            zipf.write(file_path, arcname=filename)
