from fastapi import HTTPException


def not_found() -> HTTPException:
    return HTTPException(404, detail={"code": "not_found"})


def bad_request(code: str) -> HTTPException:
    return HTTPException(400, detail={"code": code})
