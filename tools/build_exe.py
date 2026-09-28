"""Build the versioned GUI and CLI executables (onedir and/or onefile)."""

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

BUILD_MODES = ("onedir", "onefile")
DEFAULT_BUILD_MODE = "both"


def selected_modes(build_mode: str):
    """Expand the 'both' shorthand into the ordered list of concrete modes."""
    if build_mode == "both":
        return list(BUILD_MODES)
    return [build_mode]


def mode_output_dir(output_dir: Path, build_mode: str) -> Path:
    """Pick a dist path per mode.

    onedir keeps the historical layout (folders directly under output_dir) so the
    existing release/1.0.0 tree stays valid. onefile gets its own subdirectory:
    its exe is named like the onedir folder, and PyInstaller's --noconfirm would
    otherwise race the two against each other. A dedicated root guarantees the
    standalone exe can never clobber the onedir tree.
    """
    if build_mode == "onefile":
        return output_dir / "onefile"
    return output_dir


def build(output_dir: Path, build_mode: str = DEFAULT_BUILD_MODE) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="rpykit-build-") as temp_name:
        temp_dir = Path(temp_name)
        for mode in selected_modes(build_mode):
            dist_dir = mode_output_dir(output_dir, mode)
            dist_dir.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["RPYKIT_BUILD_MODE"] = mode
            for spec_name, env_key, exe_name in TARGETS:
                # Mode is in the filename too: distinct onedir/onefile temp dirs
                # must not share a version resource file either.
                version_file = temp_dir / (exe_name + "." + mode + ".version.txt")
                version_file.write_text(
                    render_version_info(exe_name), encoding="utf-8", newline="\n"
                )
                env[env_key] = str(version_file)
                # One work dir per spec *and* mode, or the two builds collide.
                work_dir = temp_dir / (Path(spec_name).stem + "-" + mode + "-work")
                command = [
                    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(dist_dir), "--workpath", str(work_dir),
                    str(ROOT / spec_name),
                ]
                print("Building %s [%s] %s..." % (exe_name, mode, branding.APP_VERSION))
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
    parser.add_argument(
        "--mode", choices=("onedir", "onefile", "both"), default=DEFAULT_BUILD_MODE,
        help="onedir (default layout) writes <output_dir>/<name>/; onefile writes "
             "the standalone exe to <output_dir>/onefile/; both builds each without "
             "overwriting the other (default: both)",
    )
    args = parser.parse_args(argv)
    return build(Path(args.output_dir), args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
