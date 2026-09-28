"""Build the versioned GUI and CLI executables into a caller-chosen directory."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import branding  # noqa: E402
from tools.write_version_info import render_version_info  # noqa: E402


TARGETS = (
    ("SLG-Renpy-Toolkit.spec", "RPYKIT_GUI_VERSION_FILE", "SLG-Renpy-Toolkit.exe"),
    ("SLG-Renpy-Toolkit-CLI.spec", "RPYKIT_CLI_VERSION_FILE", "SLG-Renpy-Toolkit-CLI.exe"),
)


def build(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="rpykit-build-") as temp_name:
        temp_dir = Path(temp_name)
        env = os.environ.copy()
        for spec_name, env_key, exe_name in TARGETS:
            version_file = temp_dir / (exe_name + ".version.txt")
            version_file.write_text(
                render_version_info(exe_name), encoding="utf-8", newline="\n"
            )
            env[env_key] = str(version_file)
            work_dir = temp_dir / (Path(spec_name).stem + "-work")
            command = [
                sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                "--distpath", str(output_dir), "--workpath", str(work_dir),
                str(ROOT / spec_name),
            ]
            print("Building %s %s..." % (exe_name, branding.APP_VERSION))
            result = subprocess.run(command, cwd=ROOT, env=env)
            if result.returncode:
                return result.returncode
    return 0


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir", nargs="?", default=str(ROOT / "release" / branding.APP_VERSION),
        help="destination directory (default: release/<version>); dist/ and build/ are untouched",
    )
    args = parser.parse_args(argv)
    return build(Path(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
