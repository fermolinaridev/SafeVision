"""Exporte o checkpoint ou meça latência, throughput e memória em um processo isolado."""
import argparse
import json
import resource
import sys
from pathlib import Path
from statistics import mean
from time import perf_counter

import cv2
import numpy as np
import torch
from ultralytics import YOLO


def benchmark(weights, paths, device, size, samples, threads):
    torch.set_num_threads(threads)
    batch = [cv2.imread(str(path)) for path in paths]
    if not all(image is not None for image in batch):
        raise ValueError("Leia apenas caminhos de imagens válidas.")
    model = YOLO(str(weights), task="detect")
    predict = dict(device=device, imgsz=size, conf=0.35, verbose=False, rect=False)
    for image in batch:
        model.predict(image, **predict)
    timings = []
    for index in range(samples):
        start = perf_counter()
        model.predict(batch[index % len(batch)], **predict)
        timings.append((perf_counter() - start) * 1000)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform != "darwin":
        peak *= 1024
    return {
        "weights": weights.name, "device": device, "size": size, "samples": samples,
        "torch_threads": threads, "image_count": len(paths), "mean_ms": round(mean(timings), 2),
        "p95_ms": round(float(np.percentile(timings, 95)), 2),
        "fps": round(1000 / mean(timings), 2), "peak_rss_mib": round(peak / 1024 ** 2, 2),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("weights", type=Path)
    parser.add_argument("images", type=Path, nargs="*")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--size", type=int, default=640)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.export:
        torch.set_num_threads(args.threads)
        YOLO(str(args.weights), task="detect").export(
            format="onnx", imgsz=args.size, device="cpu", opset=17, dynamic=False, simplify=False,
        )
    else:
        if not args.images or args.samples < 1:
            parser.error("informe imagens para medir e pelo menos uma amostra")
        print(json.dumps(benchmark(args.weights, args.images, args.device, args.size, args.samples, args.threads)))
