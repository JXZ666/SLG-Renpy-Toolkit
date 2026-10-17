"""Install/revert real bundled fonts in temporary MV/MZ API samples.

The samples are deliberately minimal JS API fixtures, not full RPG Maker or
NW.js games. Node verifies plugin behavior; this does not verify browser glyph
rendering or commercial-game plugin compatibility.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", help="built CLI exe; defaults to source app_main.py")
    parser.add_argument("--node", default=shutil.which("node"), help="Node.js executable")
    args = parser.parse_args(argv)
    if not args.node:
        raise SystemExit("Node.js is required for minimal API runtime verification")
    command = [str(Path(args.cli).resolve())] if args.cli else [sys.executable, str(ROOT / "app_main.py")]
    with tempfile.TemporaryDirectory(prefix="rpykit-rpg-samples-") as folder:
        temp = Path(folder)
        for engine, prefix in (("MV", "www"), ("MZ", "")):
            root = temp / (engine + "-minimal-api-sample")
            base = root / prefix
            (base / "js/plugins").mkdir(parents=True)
            stem = "rpg" if engine == "MV" else "rmmz"
            (base / ("js/" + stem + "_core.js")).write_text(
                'Utils.RPGMAKER_VERSION="minimal-sample"; Bitmap.prototype._makeFontNameText=function(){};', encoding="utf-8")
            (base / ("js/" + stem + "_scenes.js")).write_text(
                "Scene_Boot.prototype.isReady=function(){};", encoding="utf-8")
            original = ("// Minimal API sample; not a full RPG Maker game\nvar $plugins=" +
                        json.dumps([{"name": "ExistingSamplePlugin", "status": False,
                                     "description": "Preserve this record", "parameters": {"value": "中文"}}], ensure_ascii=False) + ";\n").encode("utf-8")
            (base / "js/plugins.js").write_bytes(original)
            env = os.environ.copy()
            work = temp / (engine + "-work")
            env["RPYKIT_WORK"] = str(work)
            def run(arguments):
                result = subprocess.run(arguments, env=env, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=60)
                if result.returncode:
                    raise RuntimeError(result.stdout + result.stderr)
                return result.stdout
            run(command + [str(root), "--features", "fontfix", "--dry-run"])
            assert not (base / "fonts").exists() and not work.exists()
            run(command + [str(root), "--features", "fontfix"])
            font = base / "fonts/RPYKit-NotoSansSC.ttf"
            assert font.read_bytes() == (ROOT / "assets/NotoSansSC-VF.ttf").read_bytes()
            run(command + [str(root), "--features", "fontfix"])
            output = run([args.node, str(ROOT / "tools/validate_rpgmaker.js"),
                          str(base / "js/plugins/RPYKit_CJK_Font.js")])
            run(command + [str(root), "--revert"])
            assert (base / "js/plugins.js").read_bytes() == original
            assert not font.exists()
            print(engine + ": CLI dry-run/install/reinstall/revert + " + output.strip())
    print("Passed minimal API samples only; full NW.js/browser/game runtime remains unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
