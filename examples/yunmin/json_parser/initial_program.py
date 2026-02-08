# EVOLVE-BLOCK-START

def parse_json_subset(s: str):
    """
    Parse a restricted JSON subset:
    - Objects with string keys
    - Arrays
    - Strings without escapes
    - Integers (no exponent)
    - true/false/null
    - Arbitrary whitespace between tokens
    """
    n = len(s)

    def skip_ws(i: int) -> int:
        while i < n and s[i].isspace():
            i += 1
        return i

    def parse_string(i: int):
        # s[i] == '"'
        i += 1
        start = i
        while i < n and s[i] != '"':
            i += 1
        if i >= n:
            raise ValueError("unterminated string")
        return s[start:i], i + 1

    def parse_number(i: int):
        start = i
        if s[i] == '-':
            i += 1
        while i < n and s[i].isdigit():
            i += 1
        if i == start or (i == start + 1 and s[start] == '-'):
            raise ValueError("invalid number")
        return int(s[start:i]), i

    def parse_array(i: int):
        # s[i] == '['
        i += 1
        arr = []
        i = skip_ws(i)
        if i < n and s[i] == ']':
            return arr, i + 1
        while True:
            i = skip_ws(i)
            val, i = parse_value(i)
            arr.append(val)
            i = skip_ws(i)
            if i >= n:
                raise ValueError("unterminated array")
            if s[i] == ']':
                return arr, i + 1
            if s[i] != ',':
                raise ValueError("expected ',' in array")
            i += 1

    def parse_object(i: int):
        # s[i] == '{'
        i += 1
        obj = {}
        i = skip_ws(i)
        if i < n and s[i] == '}':
            return obj, i + 1
        while True:
            i = skip_ws(i)
            if i >= n or s[i] != '"':
                raise ValueError("expected string key")
            key, i = parse_string(i)
            i = skip_ws(i)
            if i >= n or s[i] != ':':
                raise ValueError("expected ':' in object")
            i += 1
            i = skip_ws(i)
            val, i = parse_value(i)
            obj[key] = val
            i = skip_ws(i)
            if i >= n:
                raise ValueError("unterminated object")
            if s[i] == '}':
                return obj, i + 1
            if s[i] != ',':
                raise ValueError("expected ',' in object")
            i += 1

    def parse_value(i: int):
        i = skip_ws(i)
        if i >= n:
            raise ValueError("unexpected end")
        ch = s[i]
        if ch == '"':
            return parse_string(i)
        if ch == '{':
            return parse_object(i)
        if ch == '[':
            return parse_array(i)
        if ch == 't' and s.startswith('true', i):
            return True, i + 4
        if ch == 'f' and s.startswith('false', i):
            return False, i + 5
        if ch == 'n' and s.startswith('null', i):
            return None, i + 4
        if ch == '-' or ch.isdigit():
            return parse_number(i)
        raise ValueError(f"unexpected char: {ch}")

    value, idx = parse_value(0)
    idx = skip_ws(idx)
    if idx != n:
        raise ValueError("trailing characters")
    return value


def serialize_json_subset(obj) -> str:
    """
    Serialize an object into JSON with no extra whitespace.
    Strings contain only non-escaped characters in this benchmark.
    """
    parts = []

    def emit(val):
        if val is None:
            parts.append("null")
        elif val is True:
            parts.append("true")
        elif val is False:
            parts.append("false")
        elif isinstance(val, int):
            parts.append(str(val))
        elif isinstance(val, str):
            parts.append('"')
            parts.append(val)
            parts.append('"')
        elif isinstance(val, list):
            parts.append('[')
            first = True
            for item in val:
                if not first:
                    parts.append(',')
                first = False
                emit(item)
            parts.append(']')
        elif isinstance(val, dict):
            parts.append('{')
            first = True
            for k, v in val.items():
                if not first:
                    parts.append(',')
                first = False
                parts.append('"')
                parts.append(str(k))
                parts.append('"')
                parts.append(':')
                emit(v)
            parts.append('}')
        else:
            raise TypeError(f"unsupported type: {type(val)}")

    emit(obj)
    return ''.join(parts)

# EVOLVE-BLOCK-END


def parse_and_serialize(s: str) -> str:
    return serialize_json_subset(parse_json_subset(s))
