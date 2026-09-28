"""Write a PyInstaller Windows version resource from branding.APP_VERSION."""

from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import branding  # noqa: E402


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def render_version_info(original_filename: str) -> str:
    match = _VERSION_RE.fullmatch(branding.APP_VERSION)
    if not match:
        raise ValueError("APP_VERSION must use MAJOR.MINOR.PATCH format")
    numbers = tuple(int(part) for part in match.groups()) + (0,)
    version_tuple = "(%s)" % ", ".join(str(n) for n in numbers)
    version_text = branding.APP_VERSION
    product_name = branding.APP_SLUG
    return """# UTF-8 PyInstaller version resource generated from branding.APP_VERSION.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x4,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'SLG-Renpy-Toolkit'),
         StringStruct('FileDescription', '{product_name}'),
         StringStruct('FileVersion', '{version_text}'),
         StringStruct('InternalName', '{product_name}'),
         StringStruct('OriginalFilename', '{original_filename}'),
         StringStruct('ProductName', '{product_name}'),
         StringStruct('ProductVersion', '{version_text}')])
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""".format(
        version_tuple=version_tuple,
        version_text=version_text,
        product_name=product_name,
        original_filename=original_filename,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="destination file for PyInstaller")
    parser.add_argument("--original-filename", required=True)
    args = parser.parse_args(argv)
    with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(render_version_info(args.original_filename))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
