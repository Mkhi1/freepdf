"""Turns the 1024 px icon into the Windows .ico and the top bar logo."""
import base64
import io
import sys
from pathlib import Path

from PIL import Image

ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
LOGO_PIXELS = 64
LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 138 32" width="138" height="32" role="img" aria-label="Free PDF">
  <style>
    text {{ fill: #14202b; font: 700 22px "Segoe UI", system-ui, sans-serif; }}
    @media (prefers-color-scheme: dark) {{ text {{ fill: #eef3f6; }} }}
  </style>
  <image width="32" height="32" href="data:image/png;base64,{png}"/>
  <text x="40" y="24">Free PDF</text>
</svg>
"""

source, app = Path(sys.argv[1]), Path(sys.argv[2])
icon = Image.open(source)
icon.save(app / "src-tauri" / "icons" / "icon.ico", sizes=ICO_SIZES)
small = icon.resize((LOGO_PIXELS, LOGO_PIXELS), Image.LANCZOS)
buffer = io.BytesIO()
small.save(buffer, "PNG", optimize=True)
encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
(app / "public" / "logo.svg").write_text(LOGO.format(png=encoded), encoding="utf-8")
