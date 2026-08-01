@echo off
echo.
echo =====================================================
echo  DSM Optimizer - Windows App Builder
echo =====================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install from python.org
    exit /b 1
)
python --version

REM Build inside an isolated venv, not your global Python install. If your
REM global environment has other projects' packages installed (torch,
REM pandas, jupyter, etc.), PyInstaller's static import scanner can pick up
REM optional/guarded imports from those and bundle them in for no reason -
REM adding gigabytes and minutes to the build. A clean venv means the build
REM only ever sees what this project actually needs.
if not exist ".venv_build" (
    echo.
    echo Creating isolated build environment ^(.venv_build^)...
    python -m venv .venv_build
)
call .venv_build\Scripts\activate.bat

echo.
echo Installing libraries into the isolated environment...
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] pip install failed
    exit /b 1
)
pip install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] PyInstaller install failed
    exit /b 1
)
echo [OK] Libraries ready

echo.
echo Cleaning previous build...
rmdir /s /q dist\DSM_Optimizer 2>nul
rmdir /s /q build\DSM_Optimizer 2>nul

echo.
echo Building app (2-5 minutes)...
pyinstaller DSM_Optimizer.spec --clean --noconfirm

call .venv_build\Scripts\deactivate.bat

if not exist "dist\DSM_Optimizer\DSM_Optimizer.exe" (
    echo [ERROR] Build failed. Check output above.
    exit /b 1
)

echo.
echo =====================================================
echo  BUILD SUCCESSFUL
echo =====================================================
echo.
echo App is at: dist\DSM_Optimizer\DSM_Optimizer.exe
echo Zip the dist\DSM_Optimizer\ folder for a GitHub Release.
echo.
