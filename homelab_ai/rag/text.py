"""Structure-aware chunking.

Splits on Markdown headings / blank-line paragraphs first, then packs the
pieces into ~size windows with overlap; falls back to a sliding character
window for oversized segments. Keeps records and headings intact rather than
slicing mid-sentence like a naive fixed-width cut.
"""
from __future__ import annotations

import re

_HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)


def _segments(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    if _HEADING.search(text):
        parts = re.split(r"(?m)(?=^#{1,6}\s)", text)
    else:
        parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _window(text: str, size: int, overlap: int) -> list[str]:
    out, step = [], max(1, size - overlap)
    for start in range(0, len(text), step):
        piece = text[start:start + size].strip()
        if piece:
            out.append(piece)
        if start + size >= len(text):
            break
    return out


def chunk(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    buf = ""
    for seg in _segments(text):
        if len(seg) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_window(seg, size, overlap))
            continue
        if len(buf) + len(seg) + 1 <= size:
            buf = f"{buf}\n{seg}" if buf else seg
        else:
            if buf:
                chunks.append(buf)
            buf = seg
    if buf:
        chunks.append(buf)
    return chunks
