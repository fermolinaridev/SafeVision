import io
import logging
import re
from statistics import mean
from threading import Lock
from time import perf_counter

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

from .config import settings
from .rules import Detection, Person, associate


logger = logging.getLogger(__name__)
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
LABELS = {
    "person": "person", "worker": "person", "hardhat": "helmet", "hard_hat": "helmet",
    "helmet": "helmet", "safety_helmet": "helmet", "vest": "vest", "safety_vest": "vest",
    "no_hardhat": "no_helmet", "no_hard_hat": "no_helmet", "no_helmet": "no_helmet",
    "no_safety_helmet": "no_helmet", "no_vest": "no_vest", "no_safety_vest": "no_vest",
}


class MediaError(ValueError):
    pass


class ModelError(RuntimeError):
    pass


class Analysis(BaseModel):
    width: int
    height: int
    detections: list[Detection]
    people: list[Person]
    inference_ms: float


def decode_image(data: bytes, mime: str | None = None):
    import numpy as np

    try:
        with Image.open(io.BytesIO(data)) as image:
            actual_type = FORMATS.get(image.format)
            if not actual_type or (mime and actual_type != mime):
                raise MediaError("Envie uma imagem JPG, PNG ou WebP válida.")
            if image.width * image.height > 24_000_000 or image.width < 16 or image.height < 16:
                raise MediaError("A imagem precisa ter entre 16 × 16 pixels e 24 megapixels.")
            if getattr(image, "is_animated", False):
                raise MediaError("Envie uma imagem estática.")
            return np.ascontiguousarray(np.asarray(ImageOps.exif_transpose(image).convert("RGB"))[:, :, ::-1])
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise MediaError("O arquivo de imagem não pôde ser lido.") from exc


def canonical_label(name: str) -> str | None:
    return LABELS.get(re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"))


class Detector:
    def __init__(self):
        self.model = None
        self.lock = Lock()
        self.calls = 0
        self.latency_ms: list[float] = []

    def _load(self):
        from ultralytics import YOLO
        import torch

        cfg = settings()
        if not cfg.weights.is_file():
            raise ModelError("Checkpoint indisponível. Execute scripts/fetch_model.py.")
        torch.set_num_threads(cfg.torch_threads)
        self.model = YOLO(str(cfg.weights), task="detect")

    def metrics(self):
        return {
            "model_configured": settings().weights.is_file(),
            "model_loaded": self.model is not None,
            "analyses": self.calls,
            "average_inference_ms": round(mean(self.latency_ms), 1) if self.latency_ms else None,
        }

    def analyze(self, frame, tracker=None, *, wait: bool = True) -> Analysis:
        cfg = settings()
        height, width = frame.shape[:2]
        start = perf_counter()
        if not self.lock.acquire(blocking=wait):
            raise ModelError("O modelo está ocupado. Tente novamente em instantes.")
        try:
            if self.model is None:
                self._load()
            results = self.model.predict(
                frame, conf=min(0.1, cfg.confidence) if tracker else cfg.confidence,
                imgsz=cfg.image_size, device=cfg.device, verbose=False, max_det=300,
            )[0]
            labels = {key: canonical_label(value) for key, value in results.names.items()}
            if not {"person", "helmet", "vest"}.issubset(labels.values()):
                raise ModelError("O checkpoint precisa detectar pessoas, capacetes e coletes.")
            boxes = results.boxes.cpu().numpy()
            tracked = tracker.update(boxes, labels, frame) if tracker else {}
            detections = []
            for index, (box, class_id, confidence) in enumerate(zip(boxes.xyxy, boxes.cls, boxes.conf)):
                label = labels.get(int(class_id))
                track_id = tracked.get(index)
                if label and (float(confidence) >= cfg.confidence or track_id is not None):
                    detections.append(Detection(
                        label=label, confidence=round(float(confidence), 4),
                        box=tuple(round(float(value), 2) for value in box),
                        track_id=track_id,
                    ))
            elapsed = round((perf_counter() - start) * 1000, 2)
            self.calls += 1
            self.latency_ms = [*self.latency_ms[-99:], elapsed]
        except ModelError:
            raise
        except Exception as exc:
            logger.exception("Falha na inferência")
            raise ModelError("Falha ao executar o checkpoint de detecção.") from exc
        finally:
            self.lock.release()

        return Analysis(width=width, height=height, detections=detections,
                        people=associate(detections, width, height), inference_ms=elapsed)


class PersonTracker:
    def __init__(self, fps: float):
        from types import SimpleNamespace
        from ultralytics.trackers.byte_tracker import BYTETracker

        self.tracker = BYTETracker(SimpleNamespace(
            track_high_thresh=0.25, track_low_thresh=0.1, new_track_thresh=0.25,
            track_buffer=max(2, round(fps * 3)), match_thresh=0.8, fuse_score=True,
        ))

    def update(self, boxes, labels, frame):
        import numpy as np

        indices = np.array(
            [i for i, class_id in enumerate(boxes.cls) if labels.get(int(class_id)) == "person"],
            dtype=int,
        )
        results = self.tracker.update(boxes[indices], frame)
        return {int(indices[int(row[-1])]): int(row[4]) for row in results}


detector = Detector()
