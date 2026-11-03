# Free PDF

A free, offline PDF toolkit for Windows. Every tool is included, nothing is uploaded, and your files stay on your computer.

**Developed by MK.**

## Download

Get the latest installer from **[Releases](https://github.com/Mkhi1/freepdf/releases/latest)**: `FreePDF_x.y.z_x64-setup.exe`.

If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**.

## What it does

**Organize:** read and study PDFs (search, highlights, notes, drawing), merge, split, reorder pages, rotate, crop.

**Optimize:** compress, repair, convert to PDF/A, recognize text in scans (OCR, English and Arabic).

**Convert:** Word, PowerPoint, Excel, images and web pages to PDF. PDF to Word, PowerPoint, Excel, images and text. Translate and summarize, all on your computer.

**Edit:** add text, images and shapes, annotate, watermark, number pages.

**Security:** protect with a password, remove a password, sign, redact, compare two PDFs.

## New: send files to your other PC

Open **Devices** in the left menu to send files straight to another PC running Free PDF on the same Wi-Fi.

- **No server and no cloud.** Files go directly from one PC to the other.
- **Fast.** Files travel over a direct connection in large chunks.
- **Exact.** Every file is checked byte for byte (BLAKE3) when it arrives. If anything is wrong, the copy is deleted and you are told.
- **You decide.** The other PC asks Accept or Decline, or you can choose "Always accept from this device".
- Received files are saved in `Downloads\Free PDF` and show up in Recents.

If a PC does not show up, set the Wi-Fi to **Private** in Windows settings on both PCs, or add it with **Add by IP address**.

## Automatic updates

Free PDF checks for a new version a few seconds after it opens and offers **Update and restart**. You only install it by hand once.

## For developers

```
powershell -ExecutionPolicy Bypass -File .\setup-dev.ps1
cd app
npx tauri dev
```

- `app/`: Tauri 2 shell and UI (Preact, TypeScript, Vite). Rust in `app/src-tauri`.
- `engine/`: Python engine (PyMuPDF and friends).
- Publish a new version: `.\release.ps1 -Version 0.1.1 -Notes "What changed"`. This needs the signing key in `%USERPROFILE%\.tauri`.

See [PLAN.md](PLAN.md) for the architecture and [INSTALL-NOTES.md](INSTALL-NOTES.md) for installing on another PC.
