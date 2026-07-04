# src/nightlife/extraction/imagehash.py
from __future__ import annotations

from pathlib import Path

from PIL import Image


def dhash(image_path: Path | str) -> str:
    """Difference hash (64 bits, hex) — identifica o CONTEUDO da imagem.

    Robusto a redimensionamento/recompressao (repost do mesmo flyer);
    imagens diferentes divergem. Puro dado o arquivo; sem scipy/imagehash.
    """
    with Image.open(image_path) as img:
        small = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        px = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            left = px[row * 9 + col]
            right = px[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"
