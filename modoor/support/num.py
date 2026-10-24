"""Small number coercions shared across platform and web."""


def seqno(value: object, default: int) -> int:
    """序号。缺值或无法转换时用 ``default``，``0`` 保留。"""
    if value is None or value == "":
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
