"""Small string coercions shared by platform and web."""


def text(value: object, *, strip: bool = False) -> str:
    """空值收成 ``""``。``0`` 和 ``False`` 也算空，与 ``str(value or "")`` 相同。"""
    out = str(value or "")
    return out.strip() if strip else out


def texts(value: object, *, unique: bool = False) -> list[str]:
    """列表（或单个字符串）收成去空白后的非空字符串。"""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        piece = text(item, strip=True)
        if not piece or (unique and piece in out):
            continue
        out.append(piece)
    return out


def flag(value: object, *, default: bool = False) -> bool:
    """布尔、数字，以及 ``1`` / ``true`` / ``yes`` / ``on``。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return text(value, strip=True).lower() in {"1", "true", "yes", "on"}
