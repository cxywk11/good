from decimal import Decimal, InvalidOperation


def parse_line(raw: str | float | Decimal | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        parts = str(raw).strip().split("/")
        if len(parts) > 2:
            raise ValueError("Invalid split line")
        values = [Decimal(part.strip()) for part in parts]
        if any(not value.is_finite() for value in values):
            raise ValueError("Non-finite line")
        if len(values) == 2 and (abs(values[0] - values[1]) != Decimal("0.5") or values[0] * values[1] < 0):
            raise ValueError("Ambiguous split line")
        result = sum(values, Decimal(0)) / len(values)
        if result % Decimal("0.25") != 0:
            raise ValueError("Line must use quarter increments")
        return result
    except InvalidOperation as exc:
        raise ValueError("Invalid line") from exc


def decimal_odds(raw: str, format: str = "decimal") -> Decimal:
    try:
        if format == "fractional":
            numerator, denominator = raw.split("/")
            result = Decimal(1) + Decimal(numerator) / Decimal(denominator)
        else:
            value = Decimal(raw)
            if format == "american":
                if abs(value) < 100:
                    raise ValueError("Invalid American odds")
                result = 1 + value / 100 if value > 0 else 1 + 100 / abs(value)
            elif format == "hong_kong":
                result = value + 1
            elif format == "decimal":
                result = value
            else:
                raise ValueError("Unsupported odds format")
        if not result.is_finite() or result <= 1:
            raise ValueError("Odds must be finite and greater than 1")
        return result
    except (InvalidOperation, ArithmeticError) as exc:
        raise ValueError("Invalid odds") from exc
