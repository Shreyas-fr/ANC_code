#!/usr/bin/env bash
set -euo pipefail

# SIH 26052 Tactical ANC Debian Package Builder
# Builds standalone .deb package containing:
# - anc-edge daemon
# - anc-bench benchmark tool
# - anc-frontend tactical HUD GUI
# - systemd real-time audio service
# - desktop launcher

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PACKAGE_NAME="anc-tactical-suite"
VERSION="0.1.0"
ARCH="amd64"
BUILD_DIR="${REPO_ROOT}/target/debian_pkg/${PACKAGE_NAME}_${VERSION}_${ARCH}"

echo "============================================================"
echo "  BUILDING DEBIAN PACKAGE: ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo "============================================================"

# 1. Compile release binaries
echo ">>> Compiling optimized release binaries..."
cargo build --release --workspace

# 2. Prepare staging directory layout
echo ">>> Staging files in ${BUILD_DIR}..."
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/lib/systemd/system"
mkdir -p "${BUILD_DIR}/usr/share/applications"

# 3. Copy binaries
cp "${REPO_ROOT}/target/release/anc-edge" "${BUILD_DIR}/usr/bin/"
cp "${REPO_ROOT}/target/release/anc-bench" "${BUILD_DIR}/usr/bin/"
cp "${REPO_ROOT}/target/release/anc-frontend" "${BUILD_DIR}/usr/bin/anc-frontend"

# 4. Copy control and service files
cp "${SCRIPT_DIR}/debian/control" "${BUILD_DIR}/DEBIAN/"
cp "${SCRIPT_DIR}/debian/anc-edge.service" "${BUILD_DIR}/lib/systemd/system/"
cp "${SCRIPT_DIR}/debian/anc-hud.desktop" "${BUILD_DIR}/usr/share/applications/"

# Set executable permissions
chmod 755 "${BUILD_DIR}/usr/bin/anc-edge"
chmod 755 "${BUILD_DIR}/usr/bin/anc-bench"
chmod 755 "${BUILD_DIR}/usr/bin/anc-frontend"

# 5. Build deb archive with dpkg-deb if available
if command -v dpkg-deb >/dev/null 2>&1; then
    echo ">>> Packaging with dpkg-deb..."
    dpkg-deb --build --root-owner-group "${BUILD_DIR}" "${REPO_ROOT}/target/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
    echo ">>> SUCCESS: Package created at target/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
else
    echo ">>> dpkg-deb not found, packaging as tar.gz release bundle..."
    tar -czf "${REPO_ROOT}/target/${PACKAGE_NAME}_${VERSION}_${ARCH}.tar.gz" -C "${BUILD_DIR}" .
    echo ">>> SUCCESS: Release tarball created at target/${PACKAGE_NAME}_${VERSION}_${ARCH}.tar.gz"
fi
