#!/usr/bin/env python3
"""Попиксельное сравнение двух изображений (корректнее, чем cmp по байтам)."""
import sys
import numpy as np
from PIL import Image

def compare(p1, p2):
    a = np.array(Image.open(p1).convert("RGB"))
    b = np.array(Image.open(p2).convert("RGB"))
    if a.shape != b.shape:
        print(f"РАЗНЫЕ РАЗМЕРЫ: {a.shape} vs {b.shape}")
        return
    if np.array_equal(a, b):
        print("IDENTICAL: картинки побитово идентичны")
    else:
        diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
        changed = int((diff.sum(axis=2) > 0).sum())
        total = a.shape[0] * a.shape[1]
        print("DIFFERENT: есть отличия")
        print(f"  Различающихся пикселей: {changed} из {total} ({changed/total*100:.3f}%)")
        print(f"  Max diff на канал: {int(diff.max())}")
        print(f"  Mean diff: {diff.mean():.4f}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python compare_images.py img1.png img2.png")
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
