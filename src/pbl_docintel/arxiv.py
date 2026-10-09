"""Small, cached, sequential arXiv PDF downloads for local research use."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_ID = re.compile(r"(?:\d{2}(?:0[1-9]|1[0-2])\.\d{4,5}|[a-z][a-z.-]*/\d{7})(?:v[1-9]\d*)?")
_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


def normalize_arxiv_id(value: str) -> str:
    value = value.strip()
    if value.startswith("arxiv:"):
        value = value[6:]
    if "://" in value:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.netloc not in {"arxiv.org", "www.arxiv.org"}:
            raise ValueError("Only HTTPS arxiv.org abstract/PDF URLs are accepted")
        if parsed.query or parsed.fragment:
            raise ValueError("Remove URL query parameters and fragments")
        if not parsed.path.startswith(("/abs/", "/pdf/")):
            raise ValueError("Expected an arXiv /abs/ or /pdf/ URL")
        value = parsed.path.split("/", 2)[2]
    value = value.removesuffix(".pdf")
    if not _ID.fullmatch(value):
        raise ValueError("Invalid arXiv identifier")
    return value


def download_arxiv_pdf(identifier: str, output_dir: Path = Path("data/pdfs"), *,
                       max_bytes: int = 100 * 1024 * 1024) -> Path:
    """No bulk crawling or overwrites. Explicit versions are reproducible.

    Network requests are serialized and spaced by at least three seconds within
    this process. Coordinate separate processes externally. HTTP blocks and
    rate-limit responses are surfaced without trying alternative hosts.
    """
    arxiv_id = normalize_arxiv_id(identifier)
    if max_bytes < 5:
        raise ValueError("max_bytes must be at least 5")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / (arxiv_id.replace("/", "_") + ".pdf")
    receipt_path = destination.with_suffix(".download.json")
    if destination.exists():
        raw = destination.read_bytes()
        if not raw.startswith(b"%PDF-"):
            raise ValueError("Cached file is not a PDF; preserve it and inspect it before retrying")
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt["sha256"] != hashlib.sha256(raw).hexdigest() or receipt["arxiv_id"] != arxiv_id:
                raise ValueError("Cached PDF no longer matches its download receipt")
        return destination
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    request = Request(url, headers={"User-Agent": "PBLDocumentIntelligence/0.2 (local research prototype)",
                                   "Accept": "application/pdf"})
    global _LAST_REQUEST
    with _LOCK:
        pause = 3.0 - (time.monotonic() - _LAST_REQUEST)
        if pause > 0:
            time.sleep(pause)
        _LAST_REQUEST = time.monotonic()
        with urlopen(request, timeout=45) as response:
            raw = response.read(max_bytes + 1)
            final_url = response.url
            content_type = response.headers.get("Content-Type", "")
    if len(raw) > max_bytes:
        raise ValueError("PDF exceeds configured download size limit")
    if not raw.startswith(b"%PDF-"):
        raise ValueError(f"arXiv returned non-PDF content ({content_type}); nothing saved")
    receipt = {"arxiv_id": arxiv_id, "requested_url": url, "final_url": final_url,
               "downloaded_at": datetime.now(timezone.utc).isoformat(),
               "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
               "version_explicit": bool(re.search(r"v[1-9]\d*$", arxiv_id))}
    # Exclusive creation prevents replacing a file created by another caller.
    with destination.open("xb") as stream:
        stream.write(raw)
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identifier", help="arXiv ID or HTTPS abstract/PDF URL")
    parser.add_argument("--output-dir", type=Path, default=Path("data/pdfs"))
    args = parser.parse_args()
    try:
        print(download_arxiv_pdf(args.identifier, args.output_dir).resolve())
        return 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"arXiv download failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
