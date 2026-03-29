"""Custom service-layer exceptions.

These replace direct HTTPException usage in service code, keeping
services decoupled from FastAPI's HTTP layer.
"""


class AIFeatureDisabledError(Exception):
    """Raised when an AI feature is disabled."""

    def __init__(self, detail: str = "AI feature is disabled"):
        self.detail = detail
        super().__init__(detail)


class AIBudgetExceededError(Exception):
    """Raised when the monthly AI token budget is exceeded."""

    def __init__(self, detail: str = "Monthly AI token budget exceeded"):
        self.detail = detail
        super().__init__(detail)
