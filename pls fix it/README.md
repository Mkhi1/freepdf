# Publish Free PDF v0.1.1 (fixes blank PDF icons)

The fix is merged into `main` at https://github.com/Mkhi1/freepdf (PR #3, merge
commit `754d387`). Code and version (0.1.1) are already done. Only the signed
release is missing. It has to be published from the PC that has the signing key.

## Steps

1. Get the latest code:
   ```
   cd <freepdf repo folder>
   git checkout main
   git pull
   ```
   Check that `app/src-tauri/tauri.conf.json` says `"version": "0.1.1"`.

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

4. Publish:
   ```
   powershell -ExecutionPolicy Bypass -File .\release.ps1 -Version 0.1.1 -Notes "Fixes blank PDF icons in File Explorer"
   ```
   This builds the signed installer and creates the GitHub release `v0.1.1`
   with `FreePDF_0.1.1_x64-setup.exe` and `latest.json`.

5. Check:
   - `gh release list` shows **Free PDF 0.1.1** as Latest.
   - Install it, then confirm PDFs show the Free PDF icon in File Explorer and
     that right-click → "Open with Free PDF" works.
   - `git status` should be clean, because `release.ps1` rewrites the version
     files with the same version.

Once it's published, installed copies offer "Update and restart" the next time
they open.

## What the fix does

In v0.1.0, PDF icons were blank because the `FreePDF.Document` file type still
pointed at the old per-user exe (`%LOCALAPPDATA%\Programs\FreePDF\Free PDF.exe`).
That exe no longer exists, because the app now installs to
`C:\Program Files\Free PDF\free-pdf.exe`.

The installer hook in `app/src-tauri/installer-hooks.nsh` now:
- registers the `FreePDF.Document` icon and open command, "Open with" and the
  right-click "Open with Free PDF" entry against the installed exe
- removes the old per-user registry keys that pointed at the missing exe
- removes these entries on uninstall, but not during an auto-update, so the
  user's PDF default survives

`install/register-right-click.ps1` was deleted because it wrote the old path.
