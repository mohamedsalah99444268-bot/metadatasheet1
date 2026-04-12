"""Explicit vendor adapters for deterministic parser logic."""

from .base import VendorAdapter
from .registry import resolve_vendor_adapter

__all__ = ["VendorAdapter", "resolve_vendor_adapter"]

