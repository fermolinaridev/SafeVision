"""Obtém o checkpoint público com versão e SHA-256 fixos."""
import argparse
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen


URL = (
    "https://huggingface.co/iaac-maai/day4-example-ppe-detector/"
    "resolve/2d2f33ccfb0fdd6870c5ed9e0e3df080120d7dcd/model.pt"
)
SHA256 = "8c03c378eeaa80f16e688142730717eca6963e7455bf264b281e1a101a50ebf7"


def fetch(path):
    if path.is_file():
        with path.open("rb") as current:
            if hashlib.file_digest(current, "sha256").hexdigest() == SHA256:
                return
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as folder:
        temporary = Path(folder, "checkpoint.pt")
        with temporary.open("wb") as file, urlopen(URL, timeout=30) as download:
            digest = hashlib.sha256()
            while chunk := download.read(1024 * 1024):
                file.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != SHA256:
            raise ValueError("SHA-256 inesperado para o checkpoint")
        temporary.replace(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/iaac-ppe.pt"))
    fetch(parser.parse_args().output)
