"""Bazarr (subtitle manager) plugin — thin alias so `services.bazarr` loads the shared *arr implementation."""
from .arr import Bazarr  # noqa: F401
