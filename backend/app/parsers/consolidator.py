"""Post-processing consolidator that cross-references parsed fields.

After all parsers have run independently, the consolidator:

1. Demotes part_number fields that are actually package names
2. Deduplicates variant groups with the same part number (keeps richest)
3. Deduplicates loose fields with identical values
4. Boosts confidence when table data corroborates text-extracted data
5. Cross-checks manufacturer prefix against part numbers
"""

import re
from .base import ParsedFieldResult

# Known manufacturer prefixes (manufacturer -> part number prefixes)
MANUFACTURER_PREFIXES: dict[str, list[str]] = {
    "Texas Instruments": ["TPS", "TLV", "LM", "TMS", "MSP", "SN74", "SN65", "SN", "OPA", "ADS", "INA", "BQ", "DRV", "TCA", "TXS", "LP", "CD4", "UCC", "TPA"],
    "Analog Devices": ["AD", "ADP", "ADM", "LT", "LTC", "MAX", "HMC"],
    "STMicroelectronics": ["STM", "ST", "L6", "L7", "VN", "TSV", "TS"],
    "NXP Semiconductors": ["NX", "PCA", "PCF", "TJA", "S32"],
    "NXP": ["NX", "PCA", "PCF", "TJA", "S32"],
    "Microchip Technology": ["PIC", "MCP", "ATM", "AT", "SAM"],
    "Microchip": ["PIC", "MCP", "ATM", "AT", "SAM"],
    "Infineon Technologies": ["IFX", "IRF", "TLE", "TLI", "BSP", "IPD"],
    "Infineon": ["IFX", "IRF", "TLE", "TLI", "BSP", "IPD"],
    "ON Semiconductor": ["NCV", "NCS", "NCP", "MC"],
    "onsemi": ["NCV", "NCS", "NCP", "MC"],
    "Maxim Integrated": ["MAX", "DS"],
    "Nordic Semiconductor": ["NRF"],
    "Espressif": ["ESP"],
    "Renesas Electronics": ["R5F", "R7F", "ISL", "RAA"],
    "Renesas": ["R5F", "R7F", "ISL", "RAA"],
    "Silicon Labs": ["SI", "EFM", "EFR", "BGM"],
    "Silicon Laboratories": ["SI", "EFM", "EFR", "BGM"],
}

# Package name patterns (used to demote false part_number matches)
PACKAGE_PATTERN = re.compile(
    r'^(QFN-?\d+|LQFP-?\d+|TSSOP-?\d+|SOIC-?\d+|SOT-?\d+[A-Z]*|'
    r'BGA-?\d*|WLCSP-?\d*|DFN-?\d+|MSOP-?\d+|SSOP-?\d+|'
    r'DIP-?\d+|PDIP-?\d+|HTSSOP-?\d+|VQFN-?\d+|WQFN-?\d+|'
    r'QFP-?\d+|TQFP-?\d+|LFCSP-?\d+|CSP-?\d*|'
    r'TO-?\d+[A-Z]*|D-?PAK|DPAK|D2PAK|PowerPAD|'
    r'SC70|X2SON|DSBGA|SOT-5X3|SON)$',
    re.I,
)


def consolidate(fields: list[ParsedFieldResult]) -> list[ParsedFieldResult]:
    """Cross-reference and deduplicate parsed fields."""
    fields = _demote_package_as_part_number(fields)
    fields = _deduplicate_variants(fields)
    fields = _deduplicate_loose(fields)
    fields = _boost_table_corroborated(fields)
    fields = _boost_manufacturer_prefix(fields)
    fields = _clamp_confidence(fields)
    return fields


def _demote_package_as_part_number(fields: list[ParsedFieldResult]) -> list[ParsedFieldResult]:
    """Demote part_number fields that are actually package names."""
    package_values = {f.value.upper() for f in fields if f.field_type == "package_name"}

    for f in fields:
        if f.field_type == "part_number":
            upper = f.value.upper()
            if PACKAGE_PATTERN.match(upper) or upper in package_values:
                f.confidence = max(f.confidence - 0.4, 0.1)
                f.parser_rule = (f.parser_rule or "") + "+demoted_package"
    return fields


def _deduplicate_variants(fields: list[ParsedFieldResult]) -> list[ParsedFieldResult]:
    """Deduplicate variant groups that share the same part number.

    When the same part number appears in multiple tables across pages,
    keep the variant group with the most fields (richest data).
    Boost confidence slightly for variants corroborated by multiple tables.
    """
    # Separate variant-linked and non-variant fields
    variant_groups: dict[str, list[ParsedFieldResult]] = {}
    non_variant: list[ParsedFieldResult] = []

    for f in fields:
        if f.variant_group:
            variant_groups.setdefault(f.variant_group, []).append(f)
        else:
            non_variant.append(f)

    # For each variant group, extract its part number
    # Then deduplicate: same part_number -> keep richest group
    pn_to_groups: dict[str, list[str]] = {}  # part_number_upper -> [group_ids]
    for gid, gfields in variant_groups.items():
        pn = next((f.value.upper() for f in gfields if f.field_type == "part_number"), None)
        if pn:
            pn_to_groups.setdefault(pn, []).append(gid)
        else:
            # No part number in this group — keep but it's low value
            pn_to_groups.setdefault(f"__nopart_{gid}", []).append(gid)

    # For each set of groups with the same part number, keep the richest
    kept_groups: dict[str, list[ParsedFieldResult]] = {}
    for pn, group_ids in pn_to_groups.items():
        if len(group_ids) == 1:
            kept_groups[group_ids[0]] = variant_groups[group_ids[0]]
        else:
            # Pick the group with the most fields
            best_gid = max(group_ids, key=lambda gid: len(variant_groups[gid]))
            best_fields = variant_groups[best_gid]
            # Boost confidence: corroborated by N tables
            corroboration_boost = min(0.05 * (len(group_ids) - 1), 0.1)
            for f in best_fields:
                f.confidence = min(f.confidence + corroboration_boost, 1.0)
            kept_groups[best_gid] = best_fields

    # Reassemble
    result = non_variant[:]
    for gfields in kept_groups.values():
        result.extend(gfields)

    return result


def _deduplicate_loose(fields: list[ParsedFieldResult]) -> list[ParsedFieldResult]:
    """Deduplicate non-variant fields with identical (field_type, value).
    Keep highest confidence. If a variant-linked version exists, boost it
    and drop the loose one."""
    # Collect variant values for cross-check
    variant_values: dict[str, set[str]] = {}  # field_type -> set of upper values
    for f in fields:
        if f.variant_group:
            variant_values.setdefault(f.field_type, set()).add(f.value.upper())

    best_loose: dict[tuple[str, str], ParsedFieldResult] = {}
    result: list[ParsedFieldResult] = []

    for f in fields:
        if f.variant_group:
            result.append(f)
            continue

        key = (f.field_type, f.value.upper())

        # If this value already exists in a variant group, skip the loose version
        if f.value.upper() in variant_values.get(f.field_type, set()):
            continue

        existing = best_loose.get(key)
        if existing is None:
            best_loose[key] = f
        elif f.confidence > existing.confidence:
            best_loose[key] = f

    result.extend(best_loose.values())
    return result


def _boost_table_corroborated(fields: list[ParsedFieldResult]) -> list[ParsedFieldResult]:
    """Boost confidence for loose values that also appear in table variants."""
    table_values: dict[str, set[str]] = {}
    for f in fields:
        if f.variant_group:
            table_values.setdefault(f.field_type, set()).add(f.value.upper())

    for f in fields:
        if not f.variant_group:
            tv = table_values.get(f.field_type, set())
            if f.value.upper() in tv:
                f.confidence = min(f.confidence + 0.1, 1.0)
                f.parser_rule = (f.parser_rule or "") + "+table_corroborated"

    return fields


def _boost_manufacturer_prefix(fields: list[ParsedFieldResult]) -> list[ParsedFieldResult]:
    """If manufacturer is known, boost part numbers with matching prefixes."""
    manufacturers = [f for f in fields if f.field_type == "manufacturer"]
    if not manufacturers:
        return fields

    mfr = max(manufacturers, key=lambda f: f.confidence)
    prefixes = MANUFACTURER_PREFIXES.get(mfr.value, [])
    if not prefixes:
        return fields

    # Sort prefixes longest first so SN74 matches before SN
    prefixes_sorted = sorted(prefixes, key=len, reverse=True)

    for f in fields:
        if f.field_type != "part_number":
            continue
        upper = f.value.upper()
        if any(upper.startswith(p) for p in prefixes_sorted):
            f.confidence = min(f.confidence + 0.05, 1.0)
            f.parser_rule = (f.parser_rule or "") + "+mfr_prefix_match"
        elif not f.variant_group:
            # Only demote loose (non-table) part numbers
            f.confidence = max(f.confidence - 0.05, 0.1)

    return fields


def _clamp_confidence(fields: list[ParsedFieldResult]) -> list[ParsedFieldResult]:
    """Ensure all confidence values are in [0, 1] and rounded."""
    for f in fields:
        f.confidence = round(max(0.0, min(1.0, f.confidence)), 2)
    return fields
