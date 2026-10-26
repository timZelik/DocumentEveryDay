"""Tracks one batch's AI spend and refuses any call that could push it past the hard limit."""


class BatchBudgetExceeded(RuntimeError):
    pass


class BatchBudgetLedger:
    def __init__(self, limit_dollars: float, already_spent_dollars: float = 0.0):
        self.limit_dollars = limit_dollars
        self.spent_dollars = already_spent_dollars

    def ensure_affordable(self, worst_case_dollars: float) -> None:
        if self.spent_dollars + worst_case_dollars > self.limit_dollars:
            raise BatchBudgetExceeded(
                f"Next AI call could cost up to ${worst_case_dollars:.4f}; batch has spent "
                f"${self.spent_dollars:.4f} of its ${self.limit_dollars:.2f} limit."
            )

    def record(self, dollars: float) -> None:
        self.spent_dollars += dollars
