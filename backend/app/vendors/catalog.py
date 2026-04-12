"""Vendor catalog extracted from existing parser heuristics."""

from .base import VendorAdapter


VENDOR_ADAPTERS: tuple[VendorAdapter, ...] = (
    VendorAdapter(
        name="Texas Instruments",
        part_number_prefixes=("TPS", "TLV", "LM", "TMS", "MSP", "SN74", "SN65", "SN", "OPA", "ADS", "INA", "BQ", "DRV", "TCA", "TXS", "LP", "CD4", "UCC", "TPA"),
    ),
    VendorAdapter(name="Analog Devices", aliases=("Maxim Integrated",), part_number_prefixes=("AD", "ADP", "ADM", "LT", "LTC", "MAX", "HMC")),
    VendorAdapter(name="STMicroelectronics", part_number_prefixes=("STM", "ST", "L6", "L7", "VN", "TSV", "TS")),
    VendorAdapter(name="NXP Semiconductors", aliases=("NXP",), part_number_prefixes=("NX", "PCA", "PCF", "TJA", "S32")),
    VendorAdapter(name="Microchip Technology", aliases=("Microchip",), part_number_prefixes=("PIC", "MCP", "ATM", "AT", "SAM")),
    VendorAdapter(name="Infineon Technologies", aliases=("Infineon",), part_number_prefixes=("IFX", "IRF", "TLE", "TLI", "BSP", "IPD")),
    VendorAdapter(name="ON Semiconductor", aliases=("onsemi",), part_number_prefixes=("NCV", "NCS", "NCP", "MC")),
    VendorAdapter(name="Nordic Semiconductor", part_number_prefixes=("NRF",)),
    VendorAdapter(name="Espressif", part_number_prefixes=("ESP",)),
    VendorAdapter(name="Renesas Electronics", aliases=("Renesas",), part_number_prefixes=("R5F", "R7F", "ISL", "RAA")),
    VendorAdapter(name="Silicon Labs", aliases=("Silicon Laboratories",), part_number_prefixes=("SI", "EFM", "EFR", "BGM")),
)

