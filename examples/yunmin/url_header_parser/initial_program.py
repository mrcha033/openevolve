# EVOLVE-BLOCK-START

def parse_http_request(buf: bytes):
    """
    Parse a minimal HTTP request (request line + headers).

    Returns:
        (method: str, path: str, version: str, headers: dict[str, str])
    """
    lines = buf.split(b"\r\n")
    if not lines:
        raise ValueError("empty request")

    request_line = lines[0].decode("ascii")
    parts = request_line.split(" ")
    if len(parts) != 3:
        raise ValueError("invalid request line")
    method, path, version = parts

    headers = {}
    for line in lines[1:]:
        if not line:
            break
        if b":" not in line:
            raise ValueError("invalid header")
        name, value = line.split(b":", 1)
        name_str = name.strip().decode("ascii").lower()
        value_str = value.strip().decode("ascii")
        headers[name_str] = value_str

    return method, path, version, headers

# EVOLVE-BLOCK-END
