def int_payload(payload: str) -> int | None:
    """Преобразует строку payload в целое число."""
    value = payload.strip()
    if not value:
        return None
    try:
        return int(value, 0)
    except ValueError:
        return None


def float_payload(payload: str) -> float | None:
    """Преобразует строку payload в число с плавающей точкой."""
    value = payload.strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def bool_payload(
    payload: str, true_values: tuple[str, ...] = ("ON", "on", "1", "true")
) -> bool | None:
    """Преобразует строку payload в булево значение."""
    value: str = payload.strip()
    if not value:
        return None
    return value in true_values


def str_payload(payload: str) -> str | None:
    """Возвращает строку payload или None, если пустая."""
    value: str = payload.strip()
    return value if value else None
