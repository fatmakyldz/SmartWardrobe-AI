"""AI error codes. Routers translate them to HTTP (see app.main)."""

STATUS = {
    "budget_exceeded": 429,
    "feature_not_allowed": 403,
    "ai_busy": 503,
    "ai_unavailable": 503,
    "ai_bad_reply": 502,
    "ai_not_configured": 503,
    "prompt_not_found": 500,
}


class AIError(Exception):
    def __init__(self, code: str, **detail):
        super().__init__(code)
        self.code = code
        self.detail = detail  # extra fields for the response, e.g. reset_at, remaining

    @property
    def status(self) -> int:
        return STATUS.get(self.code, 500)
