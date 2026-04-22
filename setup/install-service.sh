#!/bin/bash
#
# Install Chronos Health as a system service with desktop shortcuts.
#
# Usage:
#   cd /path/to/Chronos-Health-MCP
#   setup/install-service.sh          # Install everything
#   setup/install-service.sh --remove # Remove everything
#
# What it does:
#   1. Generates a systemd user service (auto-start on boot)
#   2. Generates desktop shortcuts (double-click start/stop)
#   3. Enables the service to start automatically
#
# Prerequisites:
#   - Chronos Health installed and working (venv, requirements, etc.)
#   - Linux with systemd (Ubuntu 22.04+, Debian 12+)
#   - A desktop environment (GNOME, KDE, XFCE, etc.)
#

set -e

# --- Determine the install path ---
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_PATH="$( cd "$SCRIPT_DIR/.." && pwd )"

# --- Colors for output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}✅ $1${NC}"; }
warn()  { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; exit 1; }

# --- Remove mode ---
if [[ "$1" == "--remove" ]]; then
    echo "Removing Chronos Health service and desktop shortcuts..."

    # Stop the service if running
    systemctl --user stop chronos-health.service 2>/dev/null || true
    systemctl --user disable chronos-health.service 2>/dev/null || true

    # Remove service file
    rm -f ~/.config/systemd/user/chronos-health.service
    systemctl --user daemon-reload 2>/dev/null || true

    # Remove desktop shortcuts
    rm -f ~/Desktop/start-chronos.desktop
    rm -f ~/Desktop/stop-chronos.desktop

    info "Removed successfully."
    echo ""
    echo "The Chronos Health application files are still in:"
    echo "  $INSTALL_PATH"
    echo ""
    echo "To fully uninstall, delete that directory."
    exit 0
fi

# --- Validate install ---
if [[ ! -f "$INSTALL_PATH/start_multi_mode.sh" ]]; then
    error "start_multi_mode.sh not found in $INSTALL_PATH"
fi

if [[ ! -d "$INSTALL_PATH/venv" ]]; then
    error "Virtual environment not found at $INSTALL_PATH/venv. Run pip install first."
fi

echo ""
echo "Chronos Health Service Installer"
echo "================================="
echo ""
echo "Install path: $INSTALL_PATH"
echo ""

# --- Step 1: Generate systemd service ---
echo "Step 1: Creating systemd user service..."

SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

# Generate service file from template
sed "s|{{INSTALL_PATH}}|$INSTALL_PATH|g" \
    "$SCRIPT_DIR/chronos-health.service.template" \
    > "$SERVICE_DIR/chronos-health.service"

# Reload systemd
systemctl --user daemon-reload

info "Service file created: $SERVICE_DIR/chronos-health.service"

# --- Step 2: Generate desktop shortcuts ---
echo ""
echo "Step 2: Creating desktop shortcuts..."

DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR"

# Generate start shortcut
sed "s|{{INSTALL_PATH}}|$INSTALL_PATH|g" \
    "$SCRIPT_DIR/start-chronos.desktop.template" \
    > "$DESKTOP_DIR/start-chronos.desktop"
chmod +x "$DESKTOP_DIR/start-chronos.desktop"

# Generate stop shortcut
sed "s|{{INSTALL_PATH}}|$INSTALL_PATH|g" \
    "$SCRIPT_DIR/stop-chronos.desktop.template" \
    > "$DESKTOP_DIR/stop-chronos.desktop"
chmod +x "$DESKTOP_DIR/stop-chronos.desktop"

# Mark as trusted (GNOME)
if command -v gvfs-set-attribute &> /dev/null; then
    gvfs-set-attribute "$DESKTOP_DIR/start-chronos.desktop" metadata::trusted true 2>/dev/null || true
    gvfs-set-attribute "$DESKTOP_DIR/stop-chronos.desktop" metadata::trusted true 2>/dev/null || true
fi

info "Desktop shortcuts created:"
info "  $DESKTOP_DIR/start-chronos.desktop"
info "  $DESKTOP_DIR/stop-chronos.desktop"

# --- Step 3: Enable auto-start ---
echo ""
echo "Step 3: Enabling auto-start on boot..."

systemctl --user enable chronos-health.service

# Enable linger so the service runs even when not logged in
# (required for headless / server deployments)
sudo loginctl enable-linger "$USER" 2>/dev/null && \
    info "Linger enabled — service will start on boot" || \
    warn "Could not enable linger (needs sudo). Service starts on first login instead."

# --- Summary ---
echo ""
echo "================================="
info "Installation complete!"
echo ""
echo "Commands:"
echo "  systemctl --user start chronos-health    # Start"
echo "  systemctl --user stop chronos-health     # Stop"
echo "  systemctl --user status chronos-health   # Status"
echo "  journalctl --user -u chronos-health -f   # View logs"
echo ""
echo "Desktop shortcuts:"
echo "  Double-click Start/Stop Chronos Health on your desktop"
echo ""
echo "Auto-start:"
echo "  Enabled. Servers start automatically on boot."
echo ""
echo "To remove:"
echo "  $SCRIPT_DIR/install-service.sh --remove"
echo ""
