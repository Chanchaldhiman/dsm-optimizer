#!/bin/bash
# DSM Optimizer - Mac/Linux EXE Builder
set -e
echo ""
echo "====================================================="
echo " DSM Optimizer - Mac/Linux App Builder"
echo "====================================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found. Install from python.org"
    exit 1
fi
echo "[OK] $(python3 --version)"

# Build inside an isolated venv, not your regular Python environment. If
# other projects' packages (torch, pandas, jupyter, etc.) are installed
# alongside this project, PyInstaller's static import scanner can pick up
# optional/guarded imports from those and bundle them in for no reason -
# adding gigabytes and minutes to the build. A clean venv means the build
# only ever sees what this project actually needs.
if [ ! -d ".venv_build" ]; then
    echo ""
    echo "Creating isolated build environment (.venv_build)..."
    python3 -m venv .venv_build
fi
source .venv_build/bin/activate

echo ""
echo "Installing libraries into the isolated environment..."
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q || { echo "[ERROR] pip install failed"; deactivate; exit 1; }
pip install pyinstaller -q || { echo "[ERROR] PyInstaller install failed"; deactivate; exit 1; }
echo "[OK] Libraries ready"

echo ""
echo "Cleaning previous build..."
rm -rf dist/DSM_Optimizer build/DSM_Optimizer "dist/DSM Optimizer.app"

echo ""
echo "Building app (2-5 minutes)..."
pyinstaller DSM_Optimizer.spec --clean --noconfirm

deactivate

if [ ! -f "dist/DSM_Optimizer/DSM_Optimizer" ] && [ ! -d "dist/DSM Optimizer.app" ]; then
    echo "[ERROR] Build failed. Check output above."
    exit 1
fi

echo ""
echo "====================================================="
echo " BUILD SUCCESSFUL"
echo "====================================================="
echo ""
if [ -d "dist/DSM Optimizer.app" ]; then
    echo "App is at: dist/DSM Optimizer.app"
    echo "Zip it (ditto -c -k --sequesterRsrc --keepParent \"dist/DSM Optimizer.app\" DSM_Optimizer_mac.zip)"
    echo "for a GitHub Release - plain 'zip' can strip the .app's resource fork on some setups."
else
    echo "App is at: dist/DSM_Optimizer/DSM_Optimizer"
    echo "Share the entire dist/DSM_Optimizer/ folder, or zip it"
    echo "for a GitHub Release."
fi
echo ""
