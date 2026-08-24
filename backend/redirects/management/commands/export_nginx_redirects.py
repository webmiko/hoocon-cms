"""Export active Redirect rows to an nginx map file."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from redirects.models import Redirect
from redirects.services import render_nginx_map


class Command(BaseCommand):
    """Write ``deploy/nginx/redirects.map`` from the database."""

    help = "Export active redirects to an nginx map snippet."

    def add_arguments(self, parser: object) -> None:
        """Register output path flag."""
        default_out = Path(__file__).resolve().parents[4] / "deploy" / "nginx" / "redirects.map"
        parser.add_argument(  # type: ignore[attr-defined]
            "--output",
            type=str,
            default=str(default_out),
            help="Destination file path for the nginx map.",
        )

    def handle(self, *args: object, **options: object) -> None:
        """Write the map file."""
        output = Path(str(options["output"]))
        output.parent.mkdir(parents=True, exist_ok=True)
        qs = list(Redirect.objects.filter(is_active=True).order_by("from_path"))
        output.write_text(render_nginx_map(qs), encoding="utf-8")
        self.stderr.write(self.style.SUCCESS(f"Wrote {len(qs)} rules → {output}"))
