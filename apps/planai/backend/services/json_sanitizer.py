
import math
from typing import Any

try:
    import numpy as np
except Exception:
    np = None


def sanitize_json(value: Any):
    """Convert NaN/Inf/NumPy values into JSON-safe Python values."""
    if value is None:
        return None

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if np is not None:
        try:
            if isinstance(value, np.generic):
                return sanitize_json(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(k): sanitize_json(v) for k, v in value.items()}

    if isinstance(value, list):
        return [sanitize_json(v) for v in value]

    if isinstance(value, tuple):
        return [sanitize_json(v) for v in value]

    return value
