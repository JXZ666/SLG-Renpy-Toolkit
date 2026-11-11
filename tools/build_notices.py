"""Collect license texts for the Python packages and runtime in a frozen build."""

from importlib import metadata
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def _package_licenses(analysis):
    modules = {name.replace("\\", "/").split("/", 1)[0].split(".", 1)[0]
               for name, _, _ in analysis.pure + analysis.binaries}
    providers = metadata.packages_distributions()
    packages = {package for module in modules for package in providers.get(module, ())}
    packages.add("pyinstaller")  # The bootloader and runtime hooks are bundled too.
    for name in sorted(packages, key=str.lower):
        dist = metadata.distribution(name)
        for entry in sorted(set(dist.files or ()), key=str):
            if (any(part.endswith(".dist-info") for part in entry.parts)
                    and ("licenses" in entry.parts
                         or entry.name.lower().startswith(("license", "copying", "notice")))):
                path = Path(dist.locate_file(entry))
                if path.is_file():
                    yield f"{name} {dist.version} / {path.name}", path


def _runtime_licenses(analysis):
    # The regular Windows Python install ships its notices beside python.exe.
    base = Path(sys.base_prefix)
    for name in ("LICENSE_PYTHON.txt", "LICENSE.txt", "LICENSE"):
        path = base / name
        if path.is_file():
            yield "Python and its bundled libraries", path
            break
    for name, source, _ in analysis.datas:
        if Path(name).name == "license.terms":
            yield "Tcl/Tk", Path(source)

    # Conda packages supply separate notices for the DLLs linked to Python.
    prefix = Path(sys.prefix)
    included = set()
    for _, source, _ in analysis.binaries:
        try:
            included.add(Path(source).relative_to(prefix).as_posix().lower())
        except ValueError:
            continue
    for manifest in sorted((prefix / "conda-meta").glob("*.json")):
        package = json.loads(manifest.read_text(encoding="utf-8"))
        if not any(name.lower() in included for name in package.get("files", ())):
            continue
        source = (package.get("link") or {}).get("source")
        if not source:
            continue
        for path in sorted((Path(source) / "info" / "licenses").rglob("*")):
            if path.is_file() and path.suffix.lower() != ".rtf":
                yield f"{package['name']} {package['version']} / {path.name}", path


def bundle_notices(analysis, destination):
    sections = ["SLG-Renpy-Toolkit and bundled components", ""]
    if any("Roboto" in name for name, _, _ in analysis.datas):
        sections.extend([
            "Roboto fonts. Copyright 2011 Google Inc. All Rights Reserved.",
            "Licensed under the Apache License, Version 2.0. The text appears below.",
            "https://www.apache.org/licenses/LICENSE-2.0", "",
        ])
    seen = set()
    sources = [("SLG-Renpy-Toolkit", ROOT / "LICENSE"),
               ("Noto Sans SC", ROOT / "assets" / "OFL.txt")]
    sources.extend(_package_licenses(analysis))
    sources.extend(_runtime_licenses(analysis))
    for title, path in sources:
        data = path.read_bytes()
        if (title, data) in seen:
            continue
        seen.add((title, data))
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        sections.extend((title, "=" * len(title), data.decode(encoding, errors="replace").strip(), ""))
    Path(destination).write_text("\n".join(sections), encoding="utf-8")
    analysis.datas.append(("licenses/LICENSES.txt", destination, "DATA"))
