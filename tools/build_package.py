"""Builds the release download: dist/phone-trackpad-<version>.zip

Usage (repo root, any supported Python):
    python tools/build_package.py

The zip holds one folder, "Phone Trackpad", with the two launchers, the desktop/ app (code,
web page, requirements.txt), README.md and LICENSE. Tests, tools, docs for maintainers and any
local .venv or caches are left out. Phone Trackpad.command keeps its executable bit, so it can
be double-clicked after unzipping on a Mac. File times and line endings are fixed, so the same
sources give the same contents on any system. The compressed bytes (and so the zip's sha256)
can still differ with the zlib library of the Python that builds it; the printed "contents"
digest covers names, permissions and uncompressed data, and is the one to compare.
"""
import argparse
import hashlib
import re
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "Phone Trackpad"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)

# Everything shipped, relative to the repo root. desktop/ is walked for the files below.
FILES = ["Phone Trackpad.command", "Phone Trackpad.bat", "README.md", "LICENSE"]
APP_DIR = "desktop"
APP_SUFFIXES = {".py", ".txt", ".html", ".js", ".css", ".svg", ".webmanifest"}
SKIP_PARTS = {".venv", "venv", "__pycache__", ".DS_Store"}


def version():
    """The version in desktop/version.py (the release workflow checks the tag against it)."""
    text = (ROOT / APP_DIR / "version.py").read_text(encoding="utf-8")
    return re.search(r'^VERSION = "([^"]+)"', text, re.M).group(1)


def app_files():
    for path in sorted((ROOT / APP_DIR).rglob("*")):
        rel = path.relative_to(ROOT)
        if path.is_file() and not SKIP_PARTS & set(rel.parts) and path.suffix in APP_SUFFIXES:
            yield rel


def normalized(rel, data):
    """Line endings fixed by the build, not by the checkout: CRLF for .bat (cmd needs it), LF
    for every other file. So a checkout or copy that went through Windows gives the same zip."""
    data = data.replace(b"\r\n", b"\n")
    return data.replace(b"\n", b"\r\n") if rel.suffix == ".bat" else data


def build(out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"phone-trackpad-{version()}.zip"
    entries = [Path(f) for f in FILES] + list(app_files())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in entries:
            info = zipfile.ZipInfo(f"{TOP}/{rel.as_posix()}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if rel.suffix == ".command" else 0o644
            info.external_attr = (0o100000 | mode) << 16  # regular file + permissions (Unix)
            z.writestr(info, normalized(rel, (ROOT / rel).read_bytes()))
    return zip_path, entries


def contents_digest(zip_path):
    """sha256 over each entry's name, permissions and uncompressed data, in order."""
    h = hashlib.sha256()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            h.update(f"{info.filename}\0{info.external_attr}\0".encode())
            h.update(hashlib.sha256(z.read(info)).digest())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", default=str(ROOT / "dist"))
    args = ap.parse_args()
    zip_path, entries = build(Path(args.output_dir))
    print(f"built {zip_path} ({zip_path.stat().st_size / 1024:.1f} KB, {len(entries)} files)")
    print(f"  contents {contents_digest(zip_path)}")
    print(f"  zip sha256 {hashlib.sha256(zip_path.read_bytes()).hexdigest()} (zlib {zlib.ZLIB_RUNTIME_VERSION})")


if __name__ == "__main__":
    sys.exit(main())
