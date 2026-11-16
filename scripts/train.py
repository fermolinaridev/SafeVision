"""Treina em Construction-PPE e preserva as 200 imagens da validação oficial para avaliação."""
import argparse
import hashlib
import random
from pathlib import Path

import yaml
from ultralytics import YOLO


ARCHIVE_SHA = "e5817aa9c73f33e525d76ca6bc6af4e4eac9dcea9bcfef1cfd1a71c09fbc1232"


def train(data: Path, archive: Path, epochs: int, device: str, image_size: int, train_limit: int):
    with archive.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != ARCHIVE_SHA:
            raise ValueError("Versão inesperada do dataset Construction-PPE.")
    data = data.resolve()
    source = yaml.safe_load((data / "data.yaml").read_text())
    items = sorted((data / "images/train").glob("*.jpg"))
    if len(items) != 800 or len(list((data / "images/val").glob("*.jpg"))) != 200:
        raise ValueError("O dataset precisa conter o split oficial de 800/200 imagens.")
    random.Random(713).shuffle(items)
    validation, training = items[:80], items[80:]
    if train_limit:
        training = training[:train_limit]
    for filename, split in [("training.txt", training), ("development.txt", validation)]:
        (data / filename).write_text("".join(f"{path}\n" for path in split))
    definition = data / "safevision.yaml"
    definition.write_text(yaml.safe_dump({
        "path": str(data), "train": "training.txt", "val": "development.txt",
        "test": "images/val", "names": source["names"],
    }))
    YOLO("models/yolo26n.pt").train(
        data=str(definition), device=device, epochs=epochs, imgsz=image_size,
        batch=8, workers=0, seed=713, amp=False, plots=True,
        project=str(Path("runs").resolve()), name="construction-ppe", exist_ok=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--size", type=int, default=640)
    parser.add_argument("--train-limit", type=int, default=0)
    args = parser.parse_args()
    train(args.dataset, args.archive, args.epochs, args.device, args.size, args.train_limit)
