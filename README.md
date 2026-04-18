# Mock Up Machine

Streamlit app that generates billboard mockups by compositing uploaded artwork into predefined site templates. Deployed on Render.

## Tech Stack

- Python 3.11+ / Streamlit 1.56
- Pillow + OpenCV (headless) for image compositing
- NumPy for array operations

## Repo Structure

```
mockup-machine/
├── .streamlit/
│   └── config.toml              # Streamlit server config
├── assets/
│   ├── Header-MockUpMachine.png # Header image
│   ├── MockUpMachine-BG.png     # Page background
│   └── favicon.png              # Browser tab icon
├── Templates/
│   └── Digital/                 # PNG templates (filenames must match template_coordinates.py keys)
├── mockup_web_app_V2.py         # Main Streamlit app (UI + orchestration)
├── mockup_utils_V2.py           # Image compositing logic (warp + panel splitting)
├── template_coordinates.py      # Billboard corner coordinates per template
├── requirements.txt             # Python deps
├── packages.txt                 # Apt packages for Render (libgl1 for OpenCV)
├── LICENSE
└── README.md
```

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run mockup_web_app_V2.py
```

App runs at `http://localhost:8501`.

## Deploy to Render

1. Push this repo to GitHub.
2. On Render, create a new **Web Service** pointing at the repo.
3. Render auto-detects `requirements.txt` and `packages.txt`.
4. Set the start command:
   ```
   streamlit run mockup_web_app_V2.py --server.port $PORT --server.address 0.0.0.0
   ```
5. Deploy.

## Runtime Directories

The app creates these at runtime (gitignored):

- `uploaded_artwork/` — temp staging for uploads
- `generated_mockups/` — output JPEGs
- `tmp/` — per-job working directories (cleaned up on reset)

## Adding New Billboard Templates

1. Drop the PNG into `Templates/Digital/`.
2. Add a matching entry to `template_coordinates.py`:
   ```python
   "Your Site (Digital) - 12345-D.png": {
       "split_ratio": [1.0],
       "LHS": [
           (x1, y1),  # top-left of billboard face
           (x2, y2),  # top-right
           (x3, y3),  # bottom-right
           (x4, y4),  # bottom-left
       ]
   },
   ```
3. The filename must match exactly, including "(Digital)" and the site code.

## Known Issues / Backlog

- **`split_ratio` vs `split_ratios` mismatch.** `template_coordinates.py` uses singular `split_ratio`, but `mockup_utils_V2.py` checks for plural `split_ratios`. Multi-panel routing is therefore dead code. Single-panel works fine. Flagged; not fixed in this revision.
- **No file size cap.** Uploads up to 200MB are accepted, with an 8000px / 50MP resize safety net. A smaller upfront cap (e.g. 50MB) would be a cheap defence.
- **Background image fetched from GitHub raw URL.** The CSS references `raw.githubusercontent.com/phoebegawk/mockup-machine/main/assets/MockUpMachine-BG.png`. If the repo moves/renames, update the URL in `mockup_web_app_V2.py`.
- **Campaign name parsing.** Extracted from uploaded artwork filename using `" - "` as delimiter. Takes `parts[1]` if ≥3 segments, else `parts[-1]`. Undocumented business rule — worth considering a dedicated campaign input field.

## Design Language

Restyled in April 2026 to match the Check My Specs visual system:
- Montserrat font
- White cards with lime-yellow (`#D7DF23`) border
- Purple (`#542D54`) text and accents
- Yellow pill buttons
- Dashed purple drop zone for file uploads
