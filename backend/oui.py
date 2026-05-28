"""Offline best-effort MAC-prefix -> vendor lookup.

Bundled subset covering common consumer device makers so the dashboard can hint
"Apple", "Samsung", etc. when a device is first seen. No network calls. This is
intentionally small; unknown prefixes simply return None.
"""
from __future__ import annotations

# Maps the 24-bit OUI prefix (first 3 octets, uppercase, no separators) to a
# vendor name. A handful of common prefixes per vendor is enough to be useful.
_OUI: dict[str, str] = {
    # Apple
    "F0D1A9": "Apple", "A4B197": "Apple", "DC2B2A": "Apple", "ACBC32": "Apple",
    "F4F15A": "Apple", "3C0754": "Apple", "A85C2C": "Apple", "D0817A": "Apple",
    "BCD074": "Apple", "8866A5": "Apple", "F0989D": "Apple", "C82A14": "Apple",
    # Samsung
    "FCC734": "Samsung", "E8508B": "Samsung", "5CF6DC": "Samsung",
    "8425DB": "Samsung", "D0C1B1": "Samsung", "A02BB8": "Samsung",
    # Google
    "F4F5E8": "Google", "3C5AB4": "Google", "A4778E": "Google",
    # Xiaomi
    "F0B429": "Xiaomi", "64B473": "Xiaomi", "286C07": "Xiaomi",
    # Huawei
    "00E0FC": "Huawei", "48AD08": "Huawei", "ACE215": "Huawei",
    # OnePlus
    "94652D": "OnePlus", "C0EEFB": "OnePlus",
    # Amazon
    "FCA667": "Amazon", "44650D": "Amazon", "68DBF5": "Amazon",
    # Intel (laptops)
    "3C9863": "Intel", "94659C": "Intel", "A0A8CD": "Intel",
}


def normalize_mac(mac: str) -> str:
    """Uppercase, strip separators."""
    return mac.upper().replace(":", "").replace("-", "").replace(".", "").strip()


def lookup_vendor(mac: str) -> str | None:
    norm = normalize_mac(mac)
    if len(norm) < 6:
        return None
    # Locally-administered (randomized private) MACs have the 2nd-least-
    # significant bit of the first octet set. Flag those clearly.
    try:
        first_octet = int(norm[0:2], 16)
    except ValueError:
        return None
    vendor = _OUI.get(norm[0:6])
    if vendor:
        return vendor
    if first_octet & 0x02:
        return "Private (randomized)"
    return None
