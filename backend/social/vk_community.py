"""VK community profile: description, status, site, cover photo."""

from __future__ import annotations

import json
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from social.copy import PHONE, clip_text, hours_and_phone_line, site_url
from social.publishers import vk_api_call

logger = logging.getLogger("hoocon.social")


def vk_community_screen_name() -> str:
    raw = getattr(settings, "VK_COMMUNITY_SCREEN_NAME", "hoocon_russia").strip().lstrip("@")
    return raw or "hoocon_russia"


def vk_community_url() -> str:
    return f"https://vk.ru/{vk_community_screen_name()}"


def vk_community_write_link() -> str:
    return f"https://vk.me/{vk_community_screen_name()}"


_COVER_STATIC = Path("static/social/vk-community-cover.jpg")
_COVER_PNG = Path("static/social/vk-community-cover.png")
_WELCOME_FALLBACK = Path("static/social/telegram-welcome.webp")
_DESCRIPTION_MAX = 4000
_STATUS_MAX = 140


def community_title() -> str:
    """Public community name."""
    return "Hoocon в России"


def community_status() -> str:
    """Short line under the community title."""
    return clip_text(
        "Электроприводы и арматура для вентиляции и ОВК · hoocon.ru",
        _STATUS_MAX,
    )


def community_description() -> str:
    """Full «Описание» block in VK community settings."""
    site = site_url()
    return clip_text(
        (
            "Официальное сообщество ООО «Хогон» (бренд Hoocon).\n\n"
            "Электроприводы, клапаны и арматура для вентиляции и ОВК:\n"
            "• каталог и подбор аналогов Belimo\n"
            "• новости, наличие и анонсы\n"
            "• документация и статьи по применению\n\n"
            f"Сайт: {site}\n"
            f"Написать нам: {vk_community_write_link()}\n"
            f"Телефон: {PHONE}\n"
            f"Режим: {hours_and_phone_line()}\n\n"
            f"Сообщество: {vk_community_url()}"
        ),
        _DESCRIPTION_MAX,
    )


def welcome_dm_photo_path() -> Path | None:
    """Cover for the first VK DM welcome (reuse Telegram/MAX asset)."""
    configured = getattr(settings, "VK_WELCOME_PHOTO_PATH", "").strip()
    base = Path(settings.BASE_DIR)
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(base / _WELCOME_FALLBACK)
    for path in candidates:
        if path.is_file():
            return path
    return None


def community_cover_path() -> Path | None:
    """Local wide cover for ``photos.saveOwnerCoverPhoto``."""
    configured = getattr(settings, "VK_COMMUNITY_COVER_PATH", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    base = Path(settings.BASE_DIR)
    candidates.extend(
        [
            base / _COVER_STATIC,
            base / _COVER_PNG,
            base / _WELCOME_FALLBACK,
        ],
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _multipart_file(field_name: str, filename: str, payload: bytes, mime: str) -> tuple[str, bytes]:
    boundary = f"----HooconVk{uuid.uuid4().hex}"
    parts: list[bytes] = []
    disposition = f'form-data; name="{field_name}"; filename="{filename}"'
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f"Content-Disposition: {disposition}\r\n".encode())
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
    parts.append(payload)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return content_type, body


def _post_multipart(
    url: str,
    field_name: str,
    file_path: Path,
    *,
    timeout: float = 180,
) -> dict[str, Any]:
    payload = file_path.read_bytes()
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    content_type, body = _multipart_file(field_name, file_path.name, payload, mime)
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": content_type},
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        raw = response.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("VK upload: invalid JSON")
    return data


def upload_wall_photo(group_id: str, photo: Path) -> tuple[str | None, str]:
    """Upload a photo for ``wall.post``; returns ``photo{owner_id}_{id}`` attachment."""
    gid = group_id.strip().lstrip("-")
    if not gid.isdigit():
        return None, "invalid group_id"
    if not photo.is_file():
        return None, "photo file missing"
    init, err = vk_api_call("photos.getWallUploadServer", {"group_id": gid})
    if init is None:
        return None, err
    upload_url = ""
    if isinstance(init.get("response"), dict):
        upload_url = str(init["response"].get("upload_url") or "").strip()
    if not upload_url:
        return None, "VK: missing wall upload_url"

    try:
        uploaded = _post_multipart(upload_url, "photo", photo)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("vk_wall_photo_upload_failed error=%s", type(exc).__name__)
        return None, f"VK upload: {type(exc).__name__}"

    photo_json = str(uploaded.get("photo") or "").strip()
    hash_val = str(uploaded.get("hash") or "").strip()
    if not photo_json or not hash_val:
        return None, f"VK wall upload incomplete: {uploaded!r}"[:200]

    saved, err = vk_api_call(
        "photos.saveWallPhoto",
        {"group_id": gid, "photo": photo_json, "hash": hash_val},
    )
    if saved is None:
        return None, err
    items = saved.get("response")
    if not isinstance(items, list) or not items:
        return None, "VK: saveWallPhoto empty response"
    first = items[0] if isinstance(items[0], dict) else {}
    owner_id = first.get("owner_id")
    photo_id = first.get("id")
    if owner_id is None or photo_id is None:
        return None, "VK: saveWallPhoto missing photo id"
    return f"photo{owner_id}_{photo_id}", ""


def upload_message_photo(group_id: str, peer_id: str, photo: Path) -> tuple[str | None, str]:
    """Upload a photo for ``messages.send``; returns ``photo{owner_id}_{id}``."""
    gid = group_id.strip().lstrip("-")
    pid = (peer_id or "").strip()
    if not gid.isdigit() or not pid.isdigit():
        return None, "invalid group_id or peer_id"
    if not photo.is_file():
        return None, "photo file missing"
    init, err = vk_api_call(
        "photos.getMessagesUploadServer",
        {"group_id": gid, "peer_id": pid},
    )
    if init is None:
        return None, err
    upload_url = ""
    if isinstance(init.get("response"), dict):
        upload_url = str(init["response"].get("upload_url") or "").strip()
    if not upload_url:
        return None, "VK: missing messages upload_url"

    try:
        uploaded = _post_multipart(upload_url, "photo", photo)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("vk_message_photo_upload_failed error=%s", type(exc).__name__)
        return None, f"VK upload: {type(exc).__name__}"

    photo_json = str(uploaded.get("photo") or "").strip()
    hash_val = str(uploaded.get("hash") or "").strip()
    if not photo_json or not hash_val:
        return None, f"VK message upload incomplete: {uploaded!r}"[:200]

    save_params: dict[str, Any] = {"photo": photo_json, "hash": hash_val}
    server = uploaded.get("server")
    if server is not None:
        save_params["server"] = server

    saved, err = vk_api_call("photos.saveMessagesPhoto", save_params)
    if saved is None:
        return None, err
    items = saved.get("response")
    if not isinstance(items, list) or not items:
        return None, "VK: saveMessagesPhoto empty response"
    first = items[0] if isinstance(items[0], dict) else {}
    owner_id = first.get("owner_id")
    photo_id = first.get("id")
    if owner_id is None or photo_id is None:
        return None, "VK: saveMessagesPhoto missing photo id"
    return f"photo{owner_id}_{photo_id}", ""


def upload_owner_cover(group_id: str, cover: Path) -> tuple[bool, str]:
    """Upload community cover via VK photos API."""
    gid = group_id.strip().lstrip("-")
    if not gid.isdigit():
        return False, "invalid group_id"
    init, err = vk_api_call(
        "photos.getOwnerCoverPhotoUploadServer",
        {
            "group_id": gid,
            "crop_x": 0,
            "crop_y": 0,
            "crop_x2": 1589,
            "crop_y2": 399,
        },
    )
    if init is None:
        return False, err
    upload_url = ""
    if isinstance(init.get("response"), dict):
        upload_url = str(init["response"].get("upload_url") or "").strip()
    if not upload_url:
        return False, "VK: missing upload_url"

    try:
        uploaded = _post_multipart(upload_url, "photo", cover)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("vk_cover_upload_failed error=%s", type(exc).__name__)
        return False, f"VK upload: {type(exc).__name__}"

    photo = str(uploaded.get("photo") or "").strip()
    hash_val = str(uploaded.get("hash") or "").strip()
    if not photo or not hash_val:
        return False, f"VK upload incomplete: {uploaded!r}"[:200]

    saved, err = vk_api_call(
        "photos.saveOwnerCoverPhoto",
        {"group_id": gid, "photo": photo, "hash": hash_val},
    )
    if saved is None:
        return False, err
    return True, "cover_ok"


def apply_community_profile(
    group_id: str,
    *,
    upload_cover: bool = True,
) -> dict[str, str]:
    """Set title, status, description, site, phone; optional cover upload."""
    gid = group_id.strip().lstrip("-")
    results: dict[str, str] = {}
    edit_params: dict[str, Any] = {
        "group_id": gid,
        "title": community_title(),
        "description": community_description(),
        "status": community_status(),
        "site": site_url(),
        "phone": PHONE.replace(" ", "").replace("-", ""),
    }
    data, err = vk_api_call("groups.edit", edit_params)
    if data is None:
        results["profile"] = err
    else:
        results["profile"] = "ok"

    if upload_cover:
        cover = community_cover_path()
        if cover is None:
            results["cover"] = "cover file missing"
        else:
            ok, msg = upload_owner_cover(gid, cover)
            results["cover"] = msg if ok else msg
    else:
        results["cover"] = "skipped"
    return results
