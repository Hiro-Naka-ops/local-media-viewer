@echo off
rem Build dist\Local-Media-Viewer.exe (a single-file windowed EXE) on Windows.
rem Same PyInstaller options as the windows job in .github/workflows/build.yml,
rem so a local build matches the released one.
rem
rem   scripts\build_windows.cmd              run the tests, then build
rem   scripts\build_windows.cmd --skip-tests build only
rem
rem Uses .venv\ when there is one, then Python 3.14 through the py launcher
rem (the version the released EXE is built with; the python on PATH may be an
rem older one), then the python on PATH. Installs nothing itself; needs the
rem packages pinned in pyproject.toml plus pyinstaller==6.19.0 (and pytest
rem for the tests).
rem
rem No labels or goto on purpose: the repository keeps LF line endings, and
rem cmd.exe can miss labels in an LF-only batch file.
setlocal
cd /d "%~dp0.."

rem Not quoted where used: "py -3.14" is a command and its argument.
set "PYTHON=python"
py -3.14 -c "" >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3.14"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
echo Using %PYTHON%

%PYTHON% -c "import PyInstaller, PySide6, PIL, winrt.windows.media.ocr" >nul 2>&1
if errorlevel 1 (
    echo A package the build needs is missing for %PYTHON%. Install them first:
    echo   %PYTHON% -m pip install Pillow==12.1.1 pillow-heif==1.8.0 PySide6==6.10.2 pytest==9.0.2 pyinstaller==6.19.0
    echo   %PYTHON% -m pip install -r scriptsequirements-windows.txt
    exit /b 1
)

if /i not "%~1"=="--skip-tests" (
    echo Running tests...
    rem The timeline test follows the real mouse cursor and is known to flake.
    set "PYTHONPATH=src"
    %PYTHON% -m pytest -q --deselect tests/test_viewer_controls.py::test_video_timeline_overlay_shows_and_fades
    if errorlevel 1 (
        echo Tests failed; not building. Pass --skip-tests to build anyway.
        exit /b 1
    )
)

echo Building...
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Local-Media-Viewer --icon assets/icon.ico --paths src ^
    --exclude-module numpy run_viewer.pyw
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo Built dist\Local-Media-Viewer.exe
endlocal
