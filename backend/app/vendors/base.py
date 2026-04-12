"""Vendor adapter interface."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VendorAdapter:
    name: str
    aliases: tuple[str, ...] = ()
    part_number_prefixes: tuple[str, ...] = field(default_factory=tuple)

    def matches(self, vendor_name: str | None) -> bool:
        if not vendor_name:
            return False
        values = {self.name, *self.aliases}
        return vendor_name in values

