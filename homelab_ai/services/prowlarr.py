"""Prowlarr (indexer manager) plugin — thin alias so `services.prowlarr` loads the shared *arr implementation."""
from .arr import Prowlarr  # noqa: F401
