"""Public documentation hub API (list + family zip) and the stable PDF URL."""

from __future__ import annotations

from typing import Any

from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.views import View
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from catalog.docs_hub import (
    FAMILY_ZIP_MAX_BYTES,
    OTHER_FAMILY,
    build_family_zip,
    collect_hub_payload,
    family_zip_etag,
    family_zip_total_bytes,
    files_for_pdf_path,
    published_file_for_pdf_path,
    unique_product_files_for_family,
)
from catalog.models import ProductFile


class DocsHubListView(APIView):
    """GET /api/catalog/docs/ — deduped ProductFiles + family metas."""

    permission_classes = (AllowAny,)
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        """Return filtered hub payload (``q``, ``series``, ``kind``, ``family``)."""
        payload = collect_hub_payload(
            request=request,
            q=request.query_params.get("q", ""),
            series=request.query_params.get("series", ""),
            kind=request.query_params.get("kind", ""),
            family=request.query_params.get("family", ""),
        )
        return Response(payload)


class DocsFamilyZipView(APIView):
    """GET /api/catalog/docs/families/{key}/zip/ — unique PDFs as ZIP."""

    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "docs_zip"
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request, key: str) -> HttpResponse | FileResponse | Response:
        """Stream a zip of deduped family documents; support ETag / 304."""
        family_key = (key or "").strip().upper()
        if not family_key or family_key == OTHER_FAMILY:
            # OTHER is a catch-all bucket — still allow if files exist.
            pass
        files = unique_product_files_for_family(family_key)
        if not files:
            return Response({"detail": "Семейство не найдено."}, status=404)

        etag = family_zip_etag(files)
        if_none = request.META.get("HTTP_IF_NONE_MATCH", "").strip().strip('"')
        if if_none and if_none == etag:
            return HttpResponse(status=304)

        if family_zip_total_bytes(files) > FAMILY_ZIP_MAX_BYTES:
            return Response(
                {"detail": "Документов слишком много для одного архива — скачайте их по отдельности."},
                status=413,
            )

        buf = build_family_zip(files)
        response = FileResponse(buf, as_attachment=True, filename=f"{family_key}-docs.zip")
        response["ETag"] = f'"{etag}"'
        response["Cache-Control"] = "public, max-age=300"
        return response


def _open_stored_pdf(pf: ProductFile) -> Any:
    """Open the stored PDF, or None when the blob is missing."""
    if not pf.file:
        return None
    try:
        return pf.file.open("rb")
    except (OSError, ValueError, FileNotFoundError):
        return None


class CanonicalPdfView(View):
    """GET /dokumentaciya/pdf/<family>/<stem>.pdf — one indexable file per document.

    Copies under ``/media/product_files/`` are not this URL. Those stay on disk
    for the admin and are marked noindex at nginx.
    """

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, family: str, stem: str) -> FileResponse:
        """Stream the winning published copy. A missing blob falls through to the next."""
        path = f"/dokumentaciya/pdf/{family}/{stem}.pdf"
        winner = published_file_for_pdf_path(path)
        handle = _open_stored_pdf(winner) if winner is not None else None
        if handle is None and winner is not None:
            for other in files_for_pdf_path(path):
                if other.pk == winner.pk:
                    continue
                handle = _open_stored_pdf(other)
                if handle is not None:
                    break
        if handle is None:
            raise Http404
        response = FileResponse(handle, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{stem}.pdf"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "public, max-age=86400"
        return response
