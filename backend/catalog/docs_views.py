"""Public documentation hub API (list + family zip)."""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.docs_hub import (
    OTHER_FAMILY,
    build_family_zip_bytes,
    collect_hub_payload,
    family_zip_etag,
    unique_product_files_for_family,
)


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
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request, key: str) -> HttpResponse | Response:
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

        payload = build_family_zip_bytes(files)
        response = HttpResponse(payload, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{family_key}-docs.zip"'
        response["ETag"] = f'"{etag}"'
        response["Cache-Control"] = "public, max-age=300"
        response["Content-Length"] = str(len(payload))
        return response
