# EVOLVE-BLOCK-START

FNV_OFFSET_BASIS = 2166136261
FNV_PRIME = 16777619


def checksum32(data: bytes) -> int:
    """
    FNV-1a 32-bit hash over bytes.
    """
    h = FNV_OFFSET_BASIS
    for b in data:
        h ^= b
        h = (h * FNV_PRIME) & 0xFFFFFFFF
    return h

# EVOLVE-BLOCK-END
