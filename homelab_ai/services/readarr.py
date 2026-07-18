"""Readarr (ebook/audiobook manager) plugin — thin alias so `services.readarr` loads the shared *arr implementation."""
from .arr import Readarr  # noqa: F401
