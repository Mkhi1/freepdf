# Installing Free PDF on another PC

## Build the installer

```
cd app
npx tauri build
```

The setup file ends up in
`app\src-tauri\target\release\bundle\nsis\Free PDF_0.1.0_x64-setup.exe`.

## What the other PC needs

1. The setup file above. It installs for all users (asks for admin) and copies
   the Python engine next to the app.
2. The Python engine setup. The installed app runs the engine with
   `%LOCALAPPDATA%\FreePDF-dev\venv\Scripts\python.exe`, so run
   `setup-dev.ps1` once on that PC too (or set `FREEPDF_PY` to another Python
   that has the engine requirements installed).

## Updates

Installed copies check GitHub releases a few seconds after they open and offer
"Update and restart" when a newer version is out. To publish one:

```
powershell -ExecutionPolicy Bypass -File .\release.ps1 -Version 0.1.1 -Notes "What changed"
```

It needs the signing key in `%USERPROFILE%\.tauri` (`freepdf.key` and
`freepdf.key.password`). Keep a backup of both. Without them no update can be
published, and they must never be committed.

## Nearby devices

- The installer adds Windows Firewall rules named "Free PDF nearby devices"
  (TCP and UDP, private and domain networks). Uninstalling removes them.
- If the network is set to "Public" in Windows, switch it to "Private", or
  allow Free PDF when Windows asks.
- Both PCs must have Free PDF open and be on the same Wi-Fi or network.
  If a PC does not show up, use "Add by IP address" on the Devices page.
