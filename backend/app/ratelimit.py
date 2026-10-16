from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def user_or_ip(request: Request) -> str:
    # current_user() stores the id on request.state before the endpoint runs.
    return getattr(request.state, "user_id", None) or get_remote_address(request)


limiter = Limiter(key_func=user_or_ip)
