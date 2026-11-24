"""Client media in support chats: MAX, shared ingest, loss notices, SSRF guard.

The MAX payload shapes follow the Bot API object docs: photos arrive as
``type: "image"`` with ``photo_id``/``token``/``url``; video and file carry
``url``/``token`` (file also ``filename``/``size``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from django.test import override_settings

from social.max_bot import handle_max_update
from supportchat.models import Channel, Message

JPEG = b"\xff\xd8\xff\xe0 fake jpeg bytes"
MP4 = b"\x00\x00\x00\x18ftypmp42 fake video"
IMAGE_URL = "https://i.oneme.ru/i?r=BTGBPUwtwgYUeoFhO7rESmr8abc"
VIDEO_URL = "https://vd1.oneme.ru/video/clip.mp4?sig=secret"


def _update(attachments: list[dict[str, Any]], *, text: str | None = "", mid: str = "mid.m1", uid: int = 7001) -> dict:
    body: dict[str, Any] = {"mid": mid, "attachments": attachments}
    if text is not None:
        body["text"] = text
    return {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": uid, "first_name": "Клиент", "is_bot": False},
            "recipient": {"chat_type": "dialog"},
            "body": body,
        },
    }


def _image(url: str = IMAGE_URL) -> dict[str, Any]:
    return {"type": "image", "payload": {"photo_id": 1, "token": "t", "url": url}}


def _video(url: str | None = VIDEO_URL) -> dict[str, Any]:
    payload: dict[str, Any] = {"token": "vt", "width": 640, "height": 360, "duration": 5}
    if url is not None:
        payload["url"] = url
    return {"type": "video", "payload": payload}


def _file(url: str, filename: str = "spec.pdf", size: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"token": "ft", "url": url, "filename": filename}
    if size is not None:
        payload["size"] = size
    return {"type": "file", "payload": payload}


def _fake_download(url: str, **_kw: Any) -> tuple[bytes, str] | None:
    if "oneme.ru/i" in url:
        return JPEG, "i"
    if "clip.mp4" in url:
        return MP4, "clip.mp4"
    if "pdf" in url:
        return b"%PDF-1.4 fake", "spec.pdf"
    return None


def _run(update: dict, *, download: Any = _fake_download) -> list[str]:
    sent: list[str] = []

    def _capture(user_id: str, text: str, **_kw: Any) -> object:
        sent.append(text)
        return object()

    with (
        patch("supportchat.services.is_open_now", return_value=True),
        patch("social.publishers.max_download_attachment", side_effect=download),
        patch("social.max_bot._send_to_user", side_effect=_capture),
    ):
        handle_max_update(update)
    return sent


def _messages(uid: int = 7001) -> list[Message]:
    return list(
        Message.objects.filter(
            conversation__channel=Channel.MAX,
            conversation__external_user_id=str(uid),
        ).order_by("id"),
    )


@pytest.mark.django_db
def test_max_image_type_is_stored_as_photo() -> None:
    """MAX sends photos as ``type: image`` — the old code only knew ``photo``."""
    sent = _run(_update([_image()], text=None))
    (msg,) = _messages()
    assert msg.attachment
    assert msg.attachment_name == "photo-1.jpg"
    assert msg.attachment_mime == "image/jpeg"
    assert sent == []


@pytest.mark.django_db
def test_max_photo_video_and_file_each_become_a_message() -> None:
    """Every attachment of one MAX message is kept, one thread message per file."""
    update = _update(
        [_image(), _video(), _file("https://fd.oneme.ru/f/spec.pdf")],
        text="смотрите",
        mid="mid.multi",
    )
    _run(update)
    msgs = _messages()
    assert [m.external_message_id for m in msgs] == ["mid.multi", "mid.multi#1", "mid.multi#2"]
    assert msgs[0].body == "смотрите"
    assert [m.attachment_name for m in msgs] == ["photo-1.jpg", "clip.mp4", "spec.pdf"]
    assert msgs[1].attachment_mime == "video/mp4"
    assert all(m.attachment for m in msgs)

    _run(update)  # same webhook delivered twice → no duplicates
    assert len(_messages()) == 3


@pytest.mark.django_db
def test_max_unfetchable_media_is_flagged_not_dropped() -> None:
    """Host outside the allowlist: the message survives with a manager notice."""
    sent = _run(_update([_video("https://evil.example.com/clip.mp4")], text=None))
    (msg,) = _messages()
    assert not msg.attachment
    assert "⚠" in msg.body
    assert "видео" in msg.body
    assert "sales@hoocon.ru" in sent[0]


@pytest.mark.django_db
def test_max_video_without_url_is_flagged() -> None:
    sent = _run(_update([_video(None)], text="вот видео"))
    (msg,) = _messages()
    assert msg.body.startswith("вот видео")
    assert "не передал ссылку" in msg.body
    assert sent


@pytest.mark.django_db
def test_max_oversized_file_is_flagged_before_download() -> None:
    calls: list[str] = []

    def _download(url: str, **kw: Any) -> tuple[bytes, str] | None:
        calls.append(url)
        return None

    huge = 200 * 1024 * 1024
    _run(_update([_file("https://fd.oneme.ru/f/big.pdf", "big.pdf", size=huge)], text=None), download=_download)
    (msg,) = _messages()
    assert "слишком большой" in msg.body
    assert calls == []


@pytest.mark.django_db
@override_settings(SUPPORT_MESSENGER_MEDIA_MAX_PER_MESSAGE=2)
def test_max_per_message_cap_flags_the_rest() -> None:
    _run(_update([_image(), _image(), _image()], text=None, mid="mid.cap"))
    msgs = _messages()
    assert sum(1 for m in msgs if m.attachment) == 2
    assert any("лимит" in m.body for m in msgs)


@pytest.mark.django_db
@override_settings(SUPPORT_ATTACHMENT_MAX_FILES=1)
def test_conversation_file_quota_keeps_first_and_leaves_notice() -> None:
    sent = _run(_update([_image(), _video()], text="два файла", mid="mid.quota"))
    (msg,) = _messages()
    assert msg.attachment  # the first file fits the quota of one
    assert "⚠" in msg.body  # the video that did not fit is reported to managers
    assert "видео" in msg.body
    assert sent


@pytest.mark.django_db
def test_max_sticker_only_message_is_ignored_quietly() -> None:
    _run(_update([{"type": "sticker", "payload": {"code": "x"}}], text=None))
    assert _messages() == []


# ── SSRF guard ───────────────────────────────────────────────────────────


def test_max_hosts_allow_oneme_and_block_lookalikes() -> None:
    from social.max_http import max_attachment_url_allowed as allowed

    assert allowed("https://i.oneme.ru/i?r=abc")
    assert allowed("https://oneme.ru/x")
    assert not allowed("https://oneme.ru.evil.com/x")
    assert not allowed("https://evil-oneme.ru/x")
    assert not allowed("http://i.oneme.ru/x")
    assert not allowed("https://10.0.0.1/x")


@override_settings(MAX_ATTACHMENT_EXTRA_HOSTS=(".cdn-extra.test",))
def test_max_extra_hosts_come_from_settings() -> None:
    from social.max_http import max_attachment_url_allowed as allowed

    assert allowed("https://a.cdn-extra.test/x")
    assert not allowed("https://cdn-extra.test.evil.com/x")


def test_redirect_to_a_foreign_host_is_refused() -> None:
    from urllib.request import Request

    from social.max_http import _AllowlistRedirectHandler, max_attachment_url_allowed

    handler = _AllowlistRedirectHandler(max_attachment_url_allowed)
    req = Request("https://i.oneme.ru/i?r=1")
    with pytest.raises(HTTPError):
        handler.redirect_request(req, None, 302, "Found", {}, "https://169.254.169.254/latest")
    with pytest.raises(HTTPError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://i.oneme.ru/x")
    ok = handler.redirect_request(req, None, 302, "Found", {}, "https://fd.oneme.ru/f/1")
    assert ok is not None


# ── VK ───────────────────────────────────────────────────────────────────


def _vk_event(attachments: list[dict[str, Any]], *, text: str = "", message_id: int = 5001, uid: int = 8001) -> dict:
    return {
        "type": "message_new",
        "group_id": 1,
        "object": {
            "message": {
                "id": message_id,
                "date": 1_700_000_000,
                "from_id": uid,
                "peer_id": uid,
                "text": text,
                "out": 0,
                "attachments": attachments,
            },
        },
    }


def _vk_download(url: str, **_kw: Any) -> tuple[bytes, str] | None:
    if "photo" in url:
        return JPEG, "p.jpg"
    if "doc" in url:
        return b"%PDF-1.4 fake", "d.pdf"
    if "voice" in url:
        return b"ID3 voice", "v.mp3"
    return None


def _run_vk(event: dict) -> list[str]:
    from social.vk_bot import handle_vk_callback

    sent: list[str] = []

    def _capture(user_id: str, text: str, **_kw: Any) -> object:
        sent.append(text)
        return object()

    with (
        patch("supportchat.services.is_open_now", return_value=True),
        patch("social.vk_http.vk_download_attachment", side_effect=_vk_download),
        patch("social.vk_bot.send_to_vk_user", side_effect=_capture),
    ):
        handle_vk_callback(event)
    return sent


def _vk_messages(uid: int = 8001) -> list[Message]:
    return list(
        Message.objects.filter(conversation__channel=Channel.VK, conversation__external_user_id=str(uid)).order_by(
            "id",
        ),
    )


@pytest.mark.django_db
def test_vk_photo_doc_voice_and_video_are_all_handled() -> None:
    attachments = [
        {
            "type": "photo",
            "photo": {"sizes": [{"url": "https://sun1.userapi.com/photo.jpg", "width": 9, "height": 9}]},
        },
        {"type": "doc", "doc": {"url": "https://vk.com/doc1.pdf", "title": "spec", "ext": "pdf"}},
        {"type": "audio_message", "audio_message": {"link_mp3": "https://cs1.vkuser.net/voice.mp3"}},
        {"type": "video", "video": {"owner_id": -5, "id": 77, "access_key": "abc"}},
    ]
    sent = _run_vk(_vk_event(attachments, text="смотрите"))
    msgs = _vk_messages()
    files = [m for m in msgs if m.attachment]
    assert [m.attachment_name for m in files] == ["photo-1.jpg", "spec.pdf", "voice-3.mp3"]
    assert files[1].attachment_mime == "application/pdf"
    assert files[2].attachment_mime == "audio/mpeg"
    assert "https://vk.com/video-5_77_abc" in msgs[0].body
    assert "видео" in sent[0]


@pytest.mark.django_db
def test_vk_video_only_message_is_not_dropped() -> None:
    """A message that is only a video used to vanish (no downloadable attachment)."""
    sent = _run_vk(_vk_event([{"type": "video", "video": {"owner_id": 1, "id": 2}}]))
    (msg,) = _vk_messages()
    assert "https://vk.com/video1_2" in msg.body
    assert sent


# ── Telegram ─────────────────────────────────────────────────────────────


def _tg_update(message: dict[str, Any]) -> dict:
    base = {"message_id": 91, "chat": {"id": 9001, "type": "private"}, "from": {"first_name": "Anna"}}
    return {"update_id": 1, "message": {**base, **message}}


def _run_tg(message: dict[str, Any], *, download: Any) -> list[str]:
    from social.telegram_bot import handle_telegram_update

    sent: list[str] = []

    def _capture(**kw: Any) -> object:
        sent.append(kw.get("text", ""))
        return object()

    with (
        patch("supportchat.services.is_open_now", return_value=True),
        patch("social.publishers.telegram_download_file", side_effect=download),
        patch("social.telegram_bot.publish_telegram", side_effect=_capture),
    ):
        handle_telegram_update(_tg_update(message))
    return sent


def _tg_messages(chat: int = 9001) -> list[Message]:
    return list(
        Message.objects.filter(
            conversation__channel=Channel.TELEGRAM,
            conversation__external_user_id=str(chat),
        ).order_by("id"),
    )


@pytest.mark.django_db
def test_telegram_video_only_message_is_stored() -> None:
    """A video without caption used to be ignored by the has-attachment gate."""
    sent = _run_tg(
        {"video": {"file_id": "v1", "file_size": 1000, "mime_type": "video/mp4"}},
        download=lambda *_a, **_k: (MP4, "v.mp4"),
    )
    (msg,) = _tg_messages()
    assert msg.attachment
    assert msg.attachment_name == "video.mp4"
    assert msg.attachment_mime == "video/mp4"
    assert sent == []


@pytest.mark.django_db
def test_telegram_voice_is_stored_and_oversized_video_is_flagged() -> None:
    _run_tg(
        {"voice": {"file_id": "a1", "file_size": 500}},
        download=lambda *_a, **_k: (b"OggS voice", "v.oga"),
    )
    (voice,) = _tg_messages()
    assert voice.attachment_name == "voice.ogg"
    assert voice.attachment_mime == "audio/ogg"

    calls: list[str] = []

    def _never(*a: Any, **k: Any) -> None:
        calls.append("called")

    sent = _run_tg(
        {"message_id": 92, "video": {"file_id": "big", "file_size": 30 * 1024 * 1024}},
        download=_never,
    )
    assert calls == []  # getFile cannot serve > 20 MB: do not even try
    flagged = [m for m in _tg_messages() if "⚠" in m.body]
    assert len(flagged) == 1
    assert "sales@hoocon.ru" in sent[0]


# ── budget, dedupe and notice limits (review findings) ───────────────────


@pytest.mark.django_db
def test_full_thread_does_not_download_anything() -> None:
    """Quota is known before downloading: a full thread must not fetch files."""
    calls: list[str] = []

    def _download(url: str, **kw: Any) -> tuple[bytes, str] | None:
        calls.append(url)
        return JPEG, "i"

    with override_settings(SUPPORT_ATTACHMENT_MAX_FILES=1):
        _run(_update([_image()], text="первое", mid="mid.q1"), download=_download)
        assert len(calls) == 1
        _run(_update([_image(), _image(), _image()], text="ещё", mid="mid.q2"), download=_download)
    assert len(calls) == 1  # nothing fetched for the second message
    flagged = [m for m in _messages() if "⚠" in m.body]
    assert flagged
    assert "3 × фото" in flagged[0].body


@pytest.mark.django_db
def test_redelivered_update_neither_downloads_nor_replies_again() -> None:
    calls: list[str] = []

    def _download(url: str, **kw: Any) -> tuple[bytes, str] | None:
        calls.append(url)
        return None

    update = _update([_image()], text=None, mid="mid.dup")
    first = _run(update, download=_download)
    second = _run(update, download=_download)
    assert len(first) == 1  # client told once
    assert second == []
    assert len(calls) == 1
    assert len(_messages()) == 1


@pytest.mark.django_db
@override_settings(SUPPORT_MESSENGER_MEDIA_MAX_TOTAL_BYTES=30)
def test_total_bytes_per_message_is_capped() -> None:
    """The second file only gets what is left of the per-message byte budget."""
    seen: list[int] = []

    def _download(url: str, **kw: Any) -> tuple[bytes, str] | None:
        seen.append(kw["max_bytes"])
        data = b"x" * 25
        return (data, "a.pdf") if len(data) <= kw["max_bytes"] else None

    _run(
        _update(
            [_file("https://fd.oneme.ru/f/a.pdf"), _file("https://fd.oneme.ru/f/b.pdf")],
            text=None,
            mid="mid.cap",
        ),
        download=_download,
    )
    msgs = _messages()
    assert sum(1 for m in msgs if m.attachment) == 1
    assert seen == [30, 5]  # 30-byte budget, 25 spent on the first file
    assert any("⚠" in m.body for m in msgs)


@pytest.mark.django_db
def test_long_text_with_lost_media_is_not_dropped() -> None:
    """A 3990-char text plus the loss notice used to overflow 4000 and vanish."""
    text = "а" * 3990
    sent = _run(_update([_video(None)], text=text, mid="mid.long"))
    (msg,) = _messages()
    assert len(msg.body) <= 4000
    assert "⚠" in msg.body
    assert msg.body.startswith("ааа")
    assert sent


def test_url_allowlists_reject_parser_differentials() -> None:
    from social.max_http import max_attachment_url_allowed as max_ok
    from social.vk_http import vk_attachment_url_allowed as vk_ok

    for url in (
        "https://evil.com\\@i.oneme.ru/x",
        "https://user@i.oneme.ru/x",
        "https://i.oneme.ru:8443/x",
    ):
        assert not max_ok(url), url
    assert max_ok("https://i.oneme.ru:443/x")
    assert not vk_ok("https://evil.com\\@sun9-1.userapi.com/x.jpg")
    assert not vk_ok("https://sun9-1.userapi.com:8080/x.jpg")
