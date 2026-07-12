def masked_l1(prediction: list[float], target: list[float], masked: list[bool]) -> float:
    selected = [abs(left - right) for left, right, keep in zip(prediction, target, masked) if keep]
    if not selected:
        raise ValueError("at least one masked position is required")
    return sum(selected) / len(selected)
