"""Lidarr (music manager) plugin — thin alias so `services.lidarr` loads the shared *arr implementation."""
from .arr import Lidarr  # noqa: F401
