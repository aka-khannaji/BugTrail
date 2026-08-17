"""AI cost estimation and usage ledger — measured from day one."""
from __future__ import annotations

from pydantic import BaseModel, Field

# USD per 1M tokens (input, output). Rough public-list prices. Local (Ollama) = $0.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}
DEFAULT_PRICING = (1.00, 2.00)  # unknown model -> conservative default


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    per_in, per_out = MODEL_PRICING.get(model, DEFAULT_PRICING)
    return (input_tokens / 1_000_000 * per_in) + (output_tokens / 1_000_000 * per_out)


def format_cost(usd: float) -> str:
    if usd == 0.0:
        return "$0.000"
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.3f}"


class CostRow(BaseModel):
    task: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0

    @property
    def description(self) -> str:
        return f"{format_cost(self.cost_usd):>8}  {self.task}"


class CostLedger(BaseModel):
    rows: list[CostRow] = Field(default_factory=list)

    def record(self, row: CostRow) -> CostRow:
        self.rows.append(row)
        return row

    def record_deterministic(self, task: str) -> CostRow:
        return self.record(CostRow(task=task, provider="deterministic", model="-"))

    @property
    def total(self) -> float:
        return sum(row.cost_usd for row in self.rows)
