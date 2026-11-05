# Publish Free PDF v0.1.1 (PDF icons + compress fixes)

Hand this whole file to the agent on the PC that has the signing key.

Everything is already merged into `main` at https://github.com/Mkhi1/freepdf:
- PR #3: blank PDF icons in File Explorer
- PR #5: compress progress bar froze at 10% and Stop did nothing

The code and version (0.1.1) are done. Only the signed release is missing, and
it can only be built on the PC that has the signing key.

## Steps

1. Get the latest code:
   ```
   cd <freepdf repo folder>
   git checkout main
   git pull
   ```
   Check that `app/src-tauri/tauri.conf.json` says `"version": "0.1.1"`, and
   that `engine/freepdf_engine/tools/_compress_worker.py` exists.

2. Check that the signing key files are in `%USERPROFILE%\.tauri\`:
   - `freepdf.key`
   - `freepdf.key.password`

   If they're somewhere else on this PC, copy them there. Never commit them to git.

3. Install dependencies (`@tauri-apps/plugin-updater` must be present):
   ```
   cd app
   npm install
   cd ..
   ```

4. Run the compress tests in the dev engine environment:
   ```
   cd engine
   python -m pytest tests/test_optimize.py -k compress -q
   cd ..
   ```
   All 6 should pass.

5. Publish:
   ```
   powershell -ExecutionPolicy Bypass -File .\release.ps1 -Version 0.1.1 -Notes "Fixes blank PDF icons in File Explorer. Compress now shows live progress and Stop works."
   ```
   This builds the signed installer and creates the GitHub release `v0.1.1`
   with `FreePDF_0.1.1_x64-setup.exe` and `latest.json`.

6. Check:
   - `gh release list` shows **Free PDF 0.1.1** as Latest.
   - Install it, then confirm PDFs show the Free PDF icon in File Explorer and
     that right-click → "Open with Free PDF" works.
   - Compress a big image-heavy PDF. The bar should keep climbing (not stuck
     at 10%), and pressing Stop should end it right away with no output file.
   - `git status` should be clean, because `release.ps1` rewrites the version
     files with the same version.

Once it's published, installed copies offer "Update and restart" the next time
they open.

## Fix 1: PDF icons (PR #3)

In v0.1.0, PDF icons were blank because the `FreePDF.Document` file type still
pointed at the old per-user exe (`%LOCALAPPDATA%\Programs\FreePDF\Free PDF.exe`).
The app now installs to `C:\Program Files\Free PDF\free-pdf.exe`.

The installer hook in `app/src-tauri/installer-hooks.nsh` now:
- registers the `FreePDF.Document` icon and open command, "Open with" and the
  right-click "Open with Free PDF" entry against the installed exe
- removes the old per-user registry keys that pointed at the missing exe
- removes these entries on uninstall, but not during an auto-update, so the
  user's PDF default survives

`install/register-right-click.ps1` was deleted because it wrote the old path.

## Fix 2: compress progress and Stop (PR #5)

MuPDF's `rewrite_images` is one long call with no progress or cancel hook, so
the bar sat at 10% for the whole image step and Stop was ignored until it ended.

- `engine/freepdf_engine/tools/_compress_worker.py` (new) runs the image
  rewrite, font subsetting and save in a low-priority child Python process.
  It gets its settings as JSON on stdin.
- `compress` in `engine/freepdf_engine/tools/optimize.py` estimates the work
  from the images' total megapixels and moves the bar about every 0.4 s
  toward 90%. If the job runs long, the message changes to "Still working".
  Stop kills the child within about 0.1 s. Output sizes are unchanged.
- `engine/tests/test_optimize.py` has 3 new tests: the bar only moves forward,
  it stays below "done" until the end, and Stop ends the work with no output.
