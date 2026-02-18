#!/usr/bin/env bash
set -euo pipefail
NO_BUILD=false

for arg in "$@"; do
    case "$arg" in
        --no-build)
            NO_BUILD=true
            ;;
    esac
done

# ===== Config (edit if you want) =====
APP_NAME="laptop-health"
DISPLAY_NAME="Laptop Health"
ARCH="${ARCH:-amd64}"

# App version (from git tag). Accepts env override VERSION=...
# Uses latest tag like v0.4.0 -> 0.4.0. Falls back to 0.0.0 if no tags exist.
VERSION="${VERSION:-$(
  git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo 0.0.0
)}"

# Debian revision bump. Accepts env override REV=...
# If not set, auto-increments based on existing pkg artifacts for this VERSION.
if [[ -n "${REV:-}" ]]; then
  : # user provided REV
else
  last_rev="$(
    ls -1 "pkg/${APP_NAME}_${VERSION}-"*_"${ARCH}.deb" 2>/dev/null \
      | sed -n "s/.*_${VERSION}-\([0-9]\+\)_${ARCH}\.deb/\1/p" \
      | sort -n \
      | tail -n 1
  )"
  REV="${last_rev:-0}"
  REV="$((REV + 1))"
fi

# PyInstaller spec file
SPEC_FILE="${SPEC_FILE:-laptop-health.spec}"

# Icon path (must be a PNG). Default: icon committed in repo.
ICON_SRC="${ICON_SRC:-assets/laptop-health.png}"

# Build venv dir
BUILD_VENV="${BUILD_VENV:-build-venv}"

# Dependencies for apt (Debian control file)
DEPS="${DEPS:-lm-sensors, powertop, nvme-cli, power-profiles-daemon, network-manager}"

# Output directories
DIST_DIR="dist/${APP_NAME}"
PKG_ROOT="pkg/${APP_NAME}_${VERSION}-${REV}_${ARCH}"
DEB_OUT="pkg/${APP_NAME}_${VERSION}-${REV}_${ARCH}.deb"

# ===== Flags =====
INSTALL_AFTER=0
for arg in "$@"; do
  case "$arg" in
    --install) INSTALL_AFTER=1 ;;
    *) ;;
  esac
done

# ===== Helpers =====
die() { echo "ERROR: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "[i] Version: ${VERSION}-${REV}"
echo "[i] Spec:    ${SPEC_FILE}"
echo "[i] Icon:    ${ICON_SRC}"

# ===== Checks =====
[[ -f "${SPEC_FILE}" ]] || die "Spec file not found: ${SPEC_FILE}"
[[ -f "${ICON_SRC}" ]] || die "Icon not found: ${ICON_SRC}"
have dpkg-deb || die "dpkg-deb not found (install dpkg)"
have python3 || die "python3 not found"
have git || die "git not found"

# ===== Ensure build venv exists + activate =====
if [[ ! -d "${BUILD_VENV}/bin" ]]; then
  echo "[i] Creating build venv at ${BUILD_VENV} ..."
  python3 -m venv "${BUILD_VENV}"
fi

# shellcheck disable=SC1090
source "${BUILD_VENV}/bin/activate"

# Remove Qt TIFF plugin from build environment to avoid libtiff.so.5 warning
TIFF_PLUGIN="${VIRTUAL_ENV}/lib/python3.12/site-packages/PySide6/Qt/plugins/imageformats/libqtiff.so"
if [[ -f "${TIFF_PLUGIN}" ]]; then
  echo "[i] Removing Qt TIFF plugin from build environment"
  rm -f "${TIFF_PLUGIN}"
fi

# Ensure build deps exist in venv
python -c "import PySide6, psutil" >/dev/null 2>&1 || {
  echo "[i] Installing Python build deps into venv ..."
  pip install --upgrade pip
  pip install pyinstaller PySide6 psutil
}

have pyinstaller || die "pyinstaller not available in venv (pip install pyinstaller)"

# ===== Build PyInstaller bundle =====
if [ "$NO_BUILD" = false ]; then
    echo "[i] Building PyInstaller bundle..."
    rm -rf build dist
    pyinstaller "$SPEC"
else
    echo "[i] Skipping PyInstaller build (--no-build)"
fi

[[ -x "${DIST_DIR}/${APP_NAME}" ]] || die "Built binary not found: ${DIST_DIR}/${APP_NAME}"

# Belt-and-braces: also remove TIFF plugin from built bundle if present
rm -f "${DIST_DIR}/_internal/PySide6/Qt/plugins/imageformats/libqtiff.so" 2>/dev/null || true

# ===== Stage Debian package layout =====
echo "[i] Staging deb layout at ${PKG_ROOT} ..."
rm -rf "${PKG_ROOT}"
mkdir -p "${PKG_ROOT}/DEBIAN"
mkdir -p "${PKG_ROOT}/opt/${APP_NAME}"
mkdir -p "${PKG_ROOT}/usr/bin"
mkdir -p "${PKG_ROOT}/usr/share/applications"
mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/256x256/apps"

# Copy full PyInstaller folder into /opt/app
cp -a "${DIST_DIR}/"* "${PKG_ROOT}/opt/${APP_NAME}/"
chmod 755 "${PKG_ROOT}/opt/${APP_NAME}/${APP_NAME}"

# Launcher in /usr/bin
cat > "${PKG_ROOT}/usr/bin/${APP_NAME}" <<EOF
#!/usr/bin/env bash
exec /opt/${APP_NAME}/${APP_NAME} "\$@"
EOF
chmod 755 "${PKG_ROOT}/usr/bin/${APP_NAME}"

# Desktop entry
cat > "${PKG_ROOT}/usr/share/applications/${APP_NAME}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${DISPLAY_NAME}
Exec=${APP_NAME}
Icon=${APP_NAME}
Terminal=false
Categories=System;Utility;
EOF

# Icon
cp -a "${ICON_SRC}" "${PKG_ROOT}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"

# Control file
cat > "${PKG_ROOT}/DEBIAN/control" <<EOF
Package: ${APP_NAME}
Version: ${VERSION}-${REV}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: Aron <git@heis.anonaddy.com>
Depends: ${DEPS}
Description: Laptop Health dashboard (temps, power, wakeups) for Linux.
 A PySide6-based system monitor for temperature, power profiles,
 wakeups investigation, and runtime diagnostics.
EOF

# postinst + postrm (cache refresh)
cat > "${PKG_ROOT}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
update-desktop-database -q || true
update-icon-caches /usr/share/icons/hicolor || true
EOF
chmod 755 "${PKG_ROOT}/DEBIAN/postinst"

cat > "${PKG_ROOT}/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -e
update-desktop-database -q || true
update-icon-caches /usr/share/icons/hicolor || true
EOF
chmod 755 "${PKG_ROOT}/DEBIAN/postrm"

# ===== Build deb =====
echo "[i] Building .deb..."
dpkg-deb --build "${PKG_ROOT}" "${DEB_OUT}"
chmod 644 "${DEB_OUT}"

echo "[✓] Built: ${DEB_OUT}"
echo
echo "Install:"
echo "  sudo dpkg -i ./${DEB_OUT} || sudo apt -f install -y"
echo
echo "Run:"
echo "  ${APP_NAME}"

if [[ "${INSTALL_AFTER}" -eq 1 ]]; then
  echo
  echo "[i] Installing ${DEB_OUT} ..."
  sudo dpkg -i "./${DEB_OUT}" || sudo apt -f install -y
  echo "[✓] Installed. Run: ${APP_NAME}"
fi
