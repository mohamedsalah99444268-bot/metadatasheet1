"""Vendor adapter resolution."""

from __future__ import annotations

from .base import VendorAdapter
from .catalog import VENDOR_ADAPTERS


def resolve_vendor_adapter(vendor_name: str | None) -> VendorAdapter | None:
    for adapter in VENDOR_ADAPTERS:
        if adapter.matches(vendor_name):
            return adapter
    return None
