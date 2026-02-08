# EVOLVE-BLOCK-START

MARKER = 0xFF


def compress(data: bytes) -> bytes:
    """
    Simple RLE-like format:
    - Literal bytes are copied as-is, except MARKER.
    - Runs of length >= 3 are encoded as: MARKER, count(1-255), byte
    - Literal MARKER is encoded as: MARKER, 0, MARKER
    """
    out = bytearray()
    n = len(data)
    i = 0
    while i < n:
        b = data[i]
        # Count run
        run_len = 1
        j = i + 1
        while j < n and data[j] == b and run_len < 255:
            run_len += 1
            j += 1
        if run_len >= 3:
            out.append(MARKER)
            out.append(run_len)
            out.append(b)
            i += run_len
        else:
            # Emit literal(s)
            if b == MARKER:
                out.append(MARKER)
                out.append(0)
                out.append(MARKER)
            else:
                out.append(b)
            i += 1
    return bytes(out)


def decompress(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b != MARKER:
            out.append(b)
            i += 1
            continue
        if i + 2 >= n:
            raise ValueError("truncated marker")
        count = data[i + 1]
        value = data[i + 2]
        if count == 0:
            out.append(value)
        else:
            out.extend([value] * count)
        i += 3
    return bytes(out)

# EVOLVE-BLOCK-END
