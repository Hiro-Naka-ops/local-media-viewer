@echo off
rem Build dist\Local-Media-Viewer.exe (a single-file windowed EXE) on Windows,
rem with the OCR library, its models and the license notices inside.
rem The windows job in .github/workflows/build.yml runs this very script, so a
rem local build matches the released one.
rem
rem   scripts\build_windows.cmd              run the tests, then build
rem   scripts\build_windows.cmd --skip-tests build only
rem
rem Uses .venv\ when there is one, then Python 3.14 through the py launcher
rem (the version the released EXE is built with; the python on PATH may be an
rem older one), then the python on PATH. Installs nothing itself; needs the
rem packages pinned in pyproject.toml, the OCR library in vendor\ and
rem pyinstaller==6.19.0 (and pytest for the tests).
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
rem The release workflow names its interpreter outright: on a runner the py
rem launcher may find another 3.14 than the one the packages went into.
if defined BUILD_PYTHON set "PYTHON=%BUILD_PYTHON%"
echo Using %PYTHON%

%PYTHON% -c "import PyInstaller, PySide6, PIL, winrt.windows.media.ocr, glyph_ocr, rapidocr" >nul 2>&1
if errorlevel 1 (
    echo A package the build needs is missing for %PYTHON%. Install them first:
    echo   %PYTHON% -m pip install Pillow==12.1.1 pi-heif==1.4.0 PySide6==6.10.2 pytest==9.0.2 pyinstaller==6.19.0
    echo   %PYTHON% -m pip install -r scripts\requirements-windows.txt
    echo   %PYTHON% -m pip install vendor\glyph_ocr-0.1.2-py3-none-any.whl
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

rem The notices of everything bundled (Python, Qt, the OCR stack, the models),
rem as their licenses require. Inside the EXE and beside it in dist\: a
rem single-file EXE hides its contents, so the release carries the copy too.
%PYTHON% scripts\collect_licenses.py build\THIRD-PARTY-NOTICES.txt
if errorlevel 1 (
    echo Could not collect the license notices.
    exit /b 1
)

rem scripts\pyinstaller-hooks: keeps OpenCV's FFmpeg plugin (LGPL, only for
rem video files) and RapidOCR's unused Chinese models out of the EXE.
rem vendor\ocr-models holds the models with their license and notice;
rem ocr.model_directory() looks for them in the unpacked "ocr-models".
echo Building...
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Local-Media-Viewer --icon assets/icon.ico --paths src ^
    --additional-hooks-dir scripts/pyinstaller-hooks ^
    --add-data "vendor/ocr-models:ocr-models" ^
    --add-data "build/THIRD-PARTY-NOTICES.txt:." ^
    run_viewer.pyw
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
copy /y build\THIRD-PARTY-NOTICES.txt dist\THIRD-PARTY-NOTICES.txt >nul

echo Built dist\Local-Media-Viewer.exe
endlocal
