"""VK community profile copy (description / status) and wall photo upload."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from social.vk_community import (
    community_description,
    community_status,
    community_title,
    upload_wall_photo,
)


def test_community_title_brand() -> None:
    assert "Hoocon" in community_title()


def test_community_description_has_site_and_support(settings) -> None:
    settings.SITE_URL = "https://hoocon.ru"
    text = community_description()
    assert "hoocon.ru" in text
    assert "vk.me/hoocon_russia" in text
    assert len(text) <= 4000


def test_community_status_length() -> None:
    assert len(community_status()) <= 140


def test_upload_wall_photo_returns_attachment(tmp_path: Path) -> None:
    """saveWallPhoto response becomes wall.post attachment string."""
    photo = tmp_path / "wall.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xd9")

    def fake_api(method: str, params: dict) -> tuple[dict | None, str]:
        if method == "photos.getWallUploadServer":
            return {"response": {"upload_url": "https://upload.vk.example/w"}}, ""
        if method == "photos.saveWallPhoto":
            return {"response": [{"owner_id": -1, "id": 55}]}, ""
        return None, method

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"photo":"[]","hash":"h"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with (
        patch("social.vk_community.vk_api_call", side_effect=fake_api),
        patch("social.vk_community.urlopen", return_value=mock_resp),
    ):
        att, err = upload_wall_photo("242719752", photo)
    assert err == ""
    assert att == "photo-1_55"
