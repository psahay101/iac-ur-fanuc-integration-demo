"""Create a source/asset submission without machine-specific installs or caches."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {".runtime", ".venv", "node_modules", ".git", "__pycache__", ".pytest_cache",
           "test-results", "playwright-report"}


def main():
    destination = ROOT.parent / "IAC_UR_FANUC_Integration_Demo.zip"
    count = 0
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if any(part in EXCLUDE for part in relative.parts) or path.suffix in {".pyc", ".tsbuildinfo"}:
                continue
            if path.is_file():
                if not path.resolve().is_relative_to(ROOT):
                    raise ValueError(f"External symlink cannot enter the submission: {path}")
                archive.write(path, Path(ROOT.name) / relative)
                count += 1
    with ZipFile(destination) as archive:
        assert archive.testzip() is None, "Archive integrity check failed"
    print(f"{destination}\n{count} files, {destination.stat().st_size / 1024 / 1024:.1f} MiB; integrity verified")


if __name__ == "__main__":
    main()
