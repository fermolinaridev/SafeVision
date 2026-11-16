"""Avalia checkpoints com vocabulários diferentes no mesmo split oficial de 200 imagens."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import cv2
import numpy as np
import torch
import yaml
from ultralytics import YOLO

from safevision.vision import canonical_label


LABELS = ["person", "helmet", "vest", "no_helmet", "no_vest"]
THRESHOLDS = np.arange(0.5, 0.951, 0.05)


def iou(first, second):
    top_left = np.maximum(first[:2], second[:2])
    bottom_right = np.minimum(first[2:], second[2:])
    common = float(np.maximum(bottom_right - top_left, 0).prod())
    return common / max(1e-8, float((first[2:] - first[:2]).prod() + (second[2:] - second[:2]).prod()) - common)


def ranked_matches(images, label):
    truths = [[box for kind, box in truth if kind == label] for truth, _ in images]
    predictions = sorted(
        ((score, index, box) for index, (_, preds) in enumerate(images)
         for kind, score, box in preds if kind == label),
        key=lambda item: -item[0],
    )
    overlaps = [(score, index, [iou(box, gt) for gt in truths[index]]) for score, index, box in predictions]
    return sum(map(len, truths)), overlaps


def match(overlaps, threshold):
    seen = defaultdict(set)
    flags = []
    for _, index, values in overlaps:
        choices = ((value, n) for n, value in enumerate(values) if n not in seen[index] and value >= threshold)
        best = max(choices, default=None)
        if best:
            seen[index].add(best[1])
        flags.append(bool(best))
    return np.array(flags, dtype=bool)


def average_precision(flags, n_truth):
    if not n_truth or not len(flags):
        return 0.0
    true = np.cumsum(flags)
    recall = true / n_truth
    precision = true / np.arange(1, len(true) + 1)
    precision = np.maximum.accumulate(precision[::-1])[::-1]
    indices = np.searchsorted(recall, np.linspace(0, 1, 101), side="left")
    return float(np.append(precision, 0)[indices].mean())


def confusion(images, confidence):
    counts = Counter()
    for truth, raw in images:
        preds = [(label, box) for label, score, box in raw if score >= confidence]
        possibilities = sorted(
            ((iou(gt, box), g, p) for g, (_, gt) in enumerate(truth) for p, (_, box) in enumerate(preds)),
            reverse=True,
        )
        used_truth, used_pred = set(), set()
        for overlap, g, p in possibilities:
            if overlap < 0.5:
                break
            if g not in used_truth and p not in used_pred:
                counts[truth[g][0], preds[p][0]] += 1
                used_truth.add(g)
                used_pred.add(p)
        counts.update((label, "background") for g, (label, _) in enumerate(truth) if g not in used_truth)
        counts.update(("background", label) for p, (label, _) in enumerate(preds) if p not in used_pred)
    names = [*LABELS, "background"]
    return {truth: {pred: counts[truth, pred] for pred in names} for truth in names}


def metrics(images, confidence):
    by_class = {}
    for label in LABELS:
        n_truth, overlaps = ranked_matches(images, label)
        if not n_truth:
            continue
        flags = match(overlaps, 0.5)
        active = sum(score >= confidence for score, _, _ in overlaps)
        true = int(flags[:active].sum())
        precision, recall = true / max(1, active), true / n_truth
        by_class[label] = {
            "ground_truth": n_truth, "false_positive": active - true, "false_negative": n_truth - true,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / max(1e-8, precision + recall),
            "map50": average_precision(flags, n_truth),
            "map50_95": mean(average_precision(match(overlaps, iou_threshold), n_truth)
                             for iou_threshold in THRESHOLDS),
        }
    return {
        "images": len(images),
        **{key: round(mean(row[key] for row in by_class.values()), 4) if by_class else None
           for key in ("precision", "recall", "f1", "map50", "map50_95")},
        "classes": {key: {metric: round(value, 4) for metric, value in row.items()}
                    for key, row in by_class.items()},
    }


def evaluate(weights, data, device, size, confidence, conditions):
    torch.set_num_threads(2)
    keys = yaml.safe_load((data / "data.yaml").read_text())["names"]
    files = sorted((data / "images/val").glob("*.jpg"))
    if len(files) != 200:
        raise ValueError("A avaliação requer as 200 imagens oficiais.")
    slices = defaultdict(list)
    models = YOLO(str(weights), task="detect")
    results = models.predict([str(path) for path in files], stream=True, verbose=False, device=device,
                             imgsz=size, conf=0.01, batch=8, max_det=300)
    for path, result in zip(files, results, strict=True):
        height, width = result.orig_shape
        truth = []
        for line in (data / "labels/val" / f"{path.stem}.txt").read_text().splitlines():
            cls, x, y, w, h = map(float, line.split())
            canonical = canonical_label(keys[int(cls)])
            if canonical:
                truth.append((canonical, np.array([(x-w/2)*width, (y-h/2)*height, (x+w/2)*width, (y+h/2)*height])))
        boxes = result.boxes.cpu().numpy()
        predicted = [
            (name, float(score), box)
            for box, score, cls in zip(boxes.xyxy, boxes.conf, boxes.cls)
            if (name := canonical_label(result.names[int(cls)])) in LABELS
        ]
        row = truth, predicted
        slices["all"].append(row)
        gray = cv2.cvtColor(result.orig_img, cv2.COLOR_BGR2GRAY)
        if float(gray.mean()) < 90:
            slices["low_luminance"].append(row)
        person_sizes = [float((box[2:] - box[:2]).prod()) / (height * width) for kind, box in truth if kind == "person"]
        if person_sizes and float(np.median(person_sizes)) < 0.04:
            slices["small_people"].append(row)
        for condition in conditions.get(path.name, []):
            slices[condition].append(row)

    return {
        "weights": weights.name, "device": device, "imgsz": size, "confidence": confidence,
        "split": "Construction-PPE November 2026 / validation",
        "results": {name: metrics(rows, confidence) for name, rows in slices.items()},
        "confusion_matrix_truth_by_prediction": confusion(slices["all"], confidence),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("weights", type=Path)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--conditions", type=Path, default=Path("eval/conditions.csv"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--size", type=int, default=640)
    parser.add_argument("--confidence", type=float, default=0.35)
    parser.add_argument("--min-map", type=float)
    args = parser.parse_args()
    conditions = defaultdict(list)
    if args.conditions.is_file():
        with args.conditions.open(newline="") as file:
            for row in csv.DictReader(file):
                conditions[row["filename"]].append(row["condition"])
    result = evaluate(args.weights, args.dataset, args.device, args.size, args.confidence, conditions)
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(args.output)
    if args.min_map and result["results"]["all"]["map50_95"] < args.min_map:
        raise SystemExit("mAP@50:95 abaixo do limite de regressão.")
