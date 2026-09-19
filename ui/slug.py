import re


def slugify(label: str, taken: set) -> str:
    """Turn a human label into a unique, dict-safe key not already in `taken`."""
    base = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_") or "pozycja"
    key = base
    i = 2
    while key in taken:
        key = f"{base}_{i}"
        i += 1
    return key
