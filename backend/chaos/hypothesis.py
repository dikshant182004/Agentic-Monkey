"""Hypothesis generation and validation helpers for chaos experiments."""


def generate_hypothesis(monkeys: list[str], intensity: int) -> str:
    """Generate a default hypothesis statement from experiment settings."""
    monkey_text = ", ".join(monkeys) if monkeys else "cti"
    return f"At intensity {intensity}, the agent may degrade under {monkey_text} scenarios."


def validate_hypothesis(hypothesis: str) -> bool:
    """Validate hypothesis has enough content to be meaningful."""
    return len(hypothesis.strip()) >= 10

