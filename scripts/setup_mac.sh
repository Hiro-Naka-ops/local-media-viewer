#!/bin/sh
# One-time (or one-per-machine) environment setup for scripts/build_mac.sh.
#
# Creates .venv/ using a Python that satisfies pyproject.toml's requirement
# (>=3.11,<3.15) and installs the exact dependency versions the build needs
# into it — independent of whatever `python3` happens to resolve to
# system-wide. macOS's own /usr/bin/python3 (from the Xcode Command Line
# Tools) is often older than that, which is why "Pillow==12.1.1" can fail to
# resolve: Pillow's wheels for it don't exist for a too-old Python, and an
# old system pip can misreport that as "no matching distribution" rather
# than naming the real cause.
set -eu
cd "$(dirname "$0")/.."

find_python() {
    # Newest first. Checks common command names plus the well-known install
    # locations for the python.org installer and Homebrew (both CPU types),
    # since a freshly installed Python often isn't on PATH as plain python3.
    candidates="
        python3.14 python3.13 python3.12 python3.11
        /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11
        /opt/homebrew/bin/python3.14
        /opt/homebrew/bin/python3.13
        /opt/homebrew/bin/python3.12
        /opt/homebrew/bin/python3.11
        /usr/local/bin/python3.14
        /usr/local/bin/python3.13
        /usr/local/bin/python3.12
        /usr/local/bin/python3.11
    "
    for candidate in $candidates; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON="$(find_python)" || {
    echo "No Python 3.11-3.14 found on this Mac." >&2
    echo "Install one from https://www.python.org/downloads/macos/" >&2
    echo "(the \"macOS 64-bit universal2 installer\" for 3.14)," >&2
    echo "then re-run this script." >&2
    exit 1
}

echo "Using $("$PYTHON" --version 2>&1) at $PYTHON"

rm -rf .venv
"$PYTHON" -m venv .venv
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install "Pillow==12.1.1" "pillow-heif==1.8.0" "PySide6==6.10.2" "pyinstaller==6.19.0"

# build_mac.sh signs the .app so macOS's privacy (TCC) prompts — e.g. for
# reading the Documents/Desktop folders, or for the widget's shared App
# Group container — only need answering once. An ad-hoc signature (the
# no-Apple-account fallback) is keyed off the binary's own hash, so every
# rebuild looks like a different app to macOS and re-triggers every prompt.
# A local self-signed certificate instead gives every build the same,
# stable signing identity, so consent granted once keeps working across
# rebuilds.
# One-time per machine; skipped if it's already there from a previous run.
CERT_NAME="Local Media Viewer Dev"
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"
if security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -q "$CERT_NAME"; then
    echo "Local signing certificate \"$CERT_NAME\" already present."
else
    echo "Creating local signing certificate \"$CERT_NAME\"..."
    CERTDIR="$(mktemp -d)"
    trap 'rm -rf "$CERTDIR"' EXIT
    cat > "$CERTDIR/codesign.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $CERT_NAME
[ext]
basicConstraints=critical,CA:false
keyUsage=critical,digitalSignature
extendedKeyUsage=critical,codeSigning
EOF
    openssl req -x509 -newkey rsa:2048 -keyout "$CERTDIR/key.pem" -out "$CERTDIR/cert.pem" \
        -days 3650 -nodes -config "$CERTDIR/codesign.cnf"
    # -legacy: OpenSSL 3's default PKCS#12 cipher/MAC (AES + SHA-256) isn't
    # one macOS's own importer understands ("MAC verification failed"); the
    # older algorithms it needs live behind this flag now.
    openssl pkcs12 -export -out "$CERTDIR/cert.p12" -legacy \
        -inkey "$CERTDIR/key.pem" -in "$CERTDIR/cert.pem" -passout pass:temporary
    security import "$CERTDIR/cert.p12" -k "$KEYCHAIN" -P temporary \
        -T /usr/bin/codesign -T /usr/bin/security
    # Trusting it for code signing (in this user's own keychain, not the
    # system one) is what lets `codesign --sign "$CERT_NAME"` find and use
    # it without a "not trusted" complaint, since it has no real CA behind it.
    security add-trusted-cert -p codeSign -k "$KEYCHAIN" "$CERTDIR/cert.pem"
    echo "Certificate created. If macOS pops up a Keychain prompt the first"
    echo "time scripts/build_mac.sh signs with it, choose \"Always Allow\"."
fi

echo "Environment ready in .venv/. Run scripts/build_mac.sh to build the app."
