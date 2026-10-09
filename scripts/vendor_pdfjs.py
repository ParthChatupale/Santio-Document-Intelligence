"""Fetch a pinned PDF.js package from the official npm registry for offline viewing."""

import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen


def main():
    dest = Path(__file__).resolve().parents[1] / "src/pbl_docintel/gui/static/vendor"
    # Resolve once; vendor.json records the installed version and integrity.
    pin = dest / "vendor.json"
    if pin.exists():
        version = json.loads(pin.read_text())["version"]
        url = f"https://registry.npmjs.org/pdfjs-dist/{version}"
    else:
        url = "https://registry.npmjs.org/pdfjs-dist/latest"
    with urlopen(url, timeout=60) as response:
        metadata = json.load(response)
    with urlopen(metadata["dist"]["tarball"], timeout=90) as response:
        archive = response.read()
    if hashlib.sha1(archive).hexdigest() != metadata["dist"]["shasum"]:
        raise ValueError("npm package checksum mismatch")
    dest.mkdir(parents=True, exist_ok=True)
    names = {"package/build/pdf.mjs": "pdf.mjs", "package/build/pdf.worker.mjs": "pdf.worker.mjs",
             "package/web/pdf_viewer.css": "pdf_viewer.css", "package/LICENSE": "LICENSE"}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        for member in package.getmembers():
            relative = names.get(member.name)
            if relative is None and any(member.name.startswith(f"package/{folder}/") for folder in
                                        ("cmaps", "standard_fonts", "wasm")):
                relative = member.name.removeprefix("package/")
            if relative is None or not member.isfile():
                continue
            output = (dest / relative).resolve()
            if not output.is_relative_to(dest.resolve()):
                raise ValueError("Invalid npm member path")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(package.extractfile(member).read())
    pin.write_text(json.dumps({"package": "pdfjs-dist", "version": metadata["version"],
                              "source": metadata["dist"]["tarball"],
                              "sha256": hashlib.sha256(archive).hexdigest(),
                              "license": "Apache-2.0"}, indent=2) + "\n", encoding="utf-8")
    print(f"Vendored PDF.js {metadata['version']} with license and rendering resources")


if __name__ == "__main__":
    main()
