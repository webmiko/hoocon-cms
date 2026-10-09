"""Project-wide DRF pagination."""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """``?page=`` + client ``?page_size=`` (capped), default from ``PAGE_SIZE``."""

    page_size_query_param = "page_size"
    max_page_size = 100
