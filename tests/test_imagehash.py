# tests/test_imagehash.py
from PIL import Image

from nightlife.extraction.imagehash import dhash


def _gradient(path, size=(160, 120), reverse=False):
    img = Image.new("L", size)
    w = size[0]
    img.putdata([
        (255 - (x * 255 // w)) if reverse else (x * 255 // w)
        for _ in range(size[1]) for x in range(w)
    ])
    img.save(path)
    return path


def test_same_content_same_hash_even_resized(tmp_path):
    a = _gradient(tmp_path / "a.png")
    h1 = dhash(a)
    # mesma imagem redimensionada (como um repost/screenshot) -> mesmo hash
    with Image.open(a) as img:
        img.resize((320, 240)).save(tmp_path / "b.png")
    assert dhash(tmp_path / "b.png") == h1
    assert len(h1) == 16  # 64 bits em hex


def test_different_content_different_hash(tmp_path):
    a = _gradient(tmp_path / "a.png")
    b = _gradient(tmp_path / "b.png", reverse=True)
    assert dhash(a) != dhash(b)
