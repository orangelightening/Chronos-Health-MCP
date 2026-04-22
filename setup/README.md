# Service Setup (Linux)

Chronos Health can run as a **systemd user service** that starts automatically on boot, with optional desktop shortcuts for easy start/stop.

## Quick Install

```bash
cd /path/to/Chronos-Health-MCP
chmod +x setup/install-service.sh
./setup/install-service.sh
```

This creates:
- **systemd service** — auto-starts on boot, survives power failures
- **Desktop shortcuts** — double-click Start/Stop on your desktop

## What Gets Installed

| Component | Location | Purpose |
|-----------|----------|---------|
| systemd service | `~/.config/systemd/user/chronos-health.service` | Auto-start on boot |
| Start shortcut | `~/Desktop/start-chronos.desktop` | Double-click to start |
| Stop shortcut | `~/Desktop/stop-chronos.desktop` | Double-click to stop |

## Managing the Service

```bash
# Start / stop manually
systemctl --user start chronos-health
systemctl --user stop chronos-health

# Check status
systemctl --user status chronos-health

# View live logs
journalctl --user -u chronos-health -f
```

## Auto-Start Behavior

After running `install-service.sh`, the servers start automatically when the machine boots. This uses systemd's **linger** feature, which runs user services even before anyone logs in.

If `sudo` is available, the installer enables linger automatically. Otherwise, the service starts on first login instead.

## Remove the Service

```bash
./setup/install-service.sh --remove
```

This stops the service, removes the systemd file, and deletes the desktop shortcuts. Your Chronos Health application files are not touched.
