"""Turn database rejection of a NUL byte into 400, not a 500 alert."""

from __future__ import annotations

from django.db import DataError
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest


class RejectNulMiddleware:
    """Postgres raises DataError on ``\\x00``. That is bad input, not an outage."""

    def __init__(self, get_response: object) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)  # type: ignore[operator]

    def process_exception(self, request: HttpRequest, exception: BaseException) -> HttpResponse | None:
        if not isinstance(exception, DataError):
            return None
        text = str(exception)
        if "NUL" not in text and "0x00" not in text:
            return None
        return HttpResponseBadRequest("Некорректный запрос.")
