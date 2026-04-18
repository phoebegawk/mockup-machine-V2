#!/usr/bin/env bash
# ---------------------------------------------------------------------
# Mock Up Machine — local repo setup
#
# This script unpacks the project into a target directory, initialises
# git, and creates a Python virtualenv with all dependencies installed
# so the app is ready to run locally.
#
# It does NOT:
#   - Add a git remote
#   - Push anything
#   - Deploy to Render
# You do those steps yourself at the end (it prints the commands).
#
# Usage:
#   ./deploy.sh                                   # creates ./mockup-machine
#   ./deploy.sh /Users/you/Dev/mockup-machine     # custom path
#
# Idempotent: safe to re-run. Existing repo won't be overwritten unless
# you pass --force.
# ---------------------------------------------------------------------

set -euo pipefail

# ---------- Config ----------
DEFAULT_TARGET="./mockup-machine"
FORCE=0

# ---------- Arg parsing ----------
TARGET="$DEFAULT_TARGET"
for arg in "$@"; do
    case "$arg" in
        --force|-f)
            FORCE=1
            ;;
        --help|-h)
            sed -n '3,20p' "$0" | sed 's/^# //; s/^#//'
            exit 0
            ;;
        -*)
            echo "Unknown flag: $arg" >&2
            exit 1
            ;;
        *)
            TARGET="$arg"
            ;;
    esac
done

# ---------- Helpers ----------
say()  { printf '\033[1;35m▶\033[0m  %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m  %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31m✖\033[0m  %s\n' "$*" >&2; exit 1; }

# ---------- Prerequisite checks ----------
say "Checking prerequisites…"

command -v git >/dev/null 2>&1 || die "git is not installed. Install with: brew install git"
command -v python3 >/dev/null 2>&1 || die "python3 is not installed. Install from python.org or: brew install python"

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    die "Python 3.10+ required (found $PY_VERSION). Install a newer Python."
fi
ok "Python $PY_VERSION detected"

# ---------- Determine source dir (where this script lives) ----------
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
if [ ! -f "$SCRIPT_DIR/mockup_web_app_V2.py" ]; then
    die "Expected mockup_web_app_V2.py next to deploy.sh. Run this script from inside the unzipped bundle."
fi

# ---------- Target directory handling ----------
TARGET_ABS="$( cd "$(dirname "$TARGET")" 2>/dev/null && pwd )/$(basename "$TARGET")" || TARGET_ABS="$TARGET"

if [ -d "$TARGET_ABS" ] && [ "$FORCE" -ne 1 ]; then
    if [ -n "$(ls -A "$TARGET_ABS" 2>/dev/null)" ]; then
        warn "Target $TARGET_ABS already exists and is not empty."
        warn "Re-run with --force to overwrite, or choose a different path."
        exit 1
    fi
fi

say "Target directory: $TARGET_ABS"
mkdir -p "$TARGET_ABS"

# ---------- Copy files ----------
say "Copying project files…"

# Preserve directory structure; don't copy deploy.sh itself.
cd "$SCRIPT_DIR"
for item in * .[!.]*; do
    [ "$item" = "deploy.sh" ] && continue
    [ "$item" = "*" ] && continue        # no matches
    [ "$item" = ".[!.]*" ] && continue   # no hidden matches
    cp -R "$item" "$TARGET_ABS/"
done
ok "Files copied"

# ---------- Git init ----------
cd "$TARGET_ABS"
if [ ! -d ".git" ]; then
    say "Initialising git repo…"
    git init -q -b main
    git add .
    git commit -q -m "Initial commit: Mock Up Machine (restyled to match Check My Specs)"
    ok "Git repo initialised with initial commit on 'main'"
else
    ok "Existing git repo detected — leaving history intact"
fi

# ---------- Virtualenv + deps ----------
if [ ! -d ".venv" ]; then
    say "Creating virtualenv at .venv…"
    python3 -m venv .venv
    ok "Virtualenv created"
fi

say "Installing Python dependencies (this takes a minute)…"
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate
ok "Dependencies installed"

# ---------- System packages note ----------
if [ -f "packages.txt" ]; then
    PKGS=$(tr '\n' ' ' < packages.txt | sed 's/ *$//')
    if [ -n "$PKGS" ]; then
        warn "packages.txt lists system packages needed on Linux (Render): $PKGS"
        warn "On macOS these aren't needed — opencv-python-headless ships its own libs."
    fi
fi

# ---------- Done ----------
echo
ok "Setup complete."
echo
echo "─── Next steps ────────────────────────────────────────────────────"
echo
echo "  cd $TARGET_ABS"
echo "  source .venv/bin/activate"
echo "  streamlit run mockup_web_app_V2.py"
echo
echo "  # Drop your PNG templates into Templates/Digital/"
echo "  # Each filename must match a key in template_coordinates.py"
echo
echo "  # To push to Render:"
echo "  git remote add origin git@github.com:<your-user>/<repo>.git"
echo "  git push -u origin main"
echo
echo "───────────────────────────────────────────────────────────────────"
