"""YouTube publisher against googleapiclient's HttpMockSequence: no network, no token."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.http import HttpMockSequence

from factory.adapters import media
from factory.adapters.publishing.base import PublishError
from factory.adapters.publishing.youtube import (
    YouTubePublisher,
    build_service,
    description,
    publish_error,
    video_body,
)
from factory.contracts import PublishPackage
from tests.adapters.conformance import check_publisher

PACKAGE = PublishPackage(
    episode_id="en-A2-x01", video_uri="render/master.mp4",
    title={"en": "At the station", "vi": "Ở nhà ga"}, description={"en": "Learn travel words.", "vi": "Từ vựng."},
    tags={"en": ["english", "A2"]}, chapters=[{"start_s": 0, "title": "Intro"}, {"start_s": 75.4, "title": "Dialogue"}],
    made_for_kids=False, contains_synthetic_media=True,
)
CHANNEL = {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUabc"}}}]}
PLAYLIST = {"items": [{"contentDetails": {"videoId": "old1"}}, {"contentDetails": {"videoId": "vid42"}}]}


def ok(body) -> tuple[dict, str]:
    return {"status": "200"}, json.dumps(body)


def error(status: int, reason: str, message: str = "nope") -> tuple[dict, str]:
    return {"status": str(status)}, json.dumps({"error": {"code": status, "message": message,
                                                          "errors": [{"reason": reason, "message": message}]}})


def publisher(*responses) -> tuple[YouTubePublisher, HttpMockSequence]:
    http = HttpMockSequence(list(responses))
    return YouTubePublisher(service=build_service(http=http)), http


def video(vid: str, tags=()) -> dict:
    return {"id": vid, "snippet": {"tags": list(tags)}}


def test_the_upload_body_is_private_with_chapters_localizations_and_the_episode_tag():
    body = video_body(PACKAGE, "27")
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                              "containsSyntheticMedia": True}
    snippet = body["snippet"]
    assert snippet["title"] == "At the station" and snippet["defaultLanguage"] == "en"
    assert snippet["tags"] == ["english", "A2", "ep-en-A2-x01"] and snippet["categoryId"] == "27"
    assert snippet["description"] == "Learn travel words.\n\n0:00 Intro\n1:15 Dialogue"
    assert body["localizations"] == {"vi": {"title": "Ở nhà ga", "description": "Từ vựng.\n\n0:00 Intro\n1:15 Dialogue"}}
    assert description(PACKAGE.model_copy(update={"chapters": []}), "en") == "Learn travel words."


def test_upload_sends_the_video_resumably_when_the_episode_is_not_on_the_channel(tmp_path):
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\0" * 1024)
    yt, http = publisher(ok(CHANNEL), ok(PLAYLIST), ok({"items": [video("old1"), video("vid42")]}),
                         ({"status": "200", "location": "https://upload.example/session"}, ""), ok({"id": "new7"}))
    done = yt.upload(clip, PACKAGE)
    assert (done.external_id, done.quota_units) == ("new7", 3)
    insert = http.request_sequence[3]
    assert "uploadType=resumable" in insert[0] and "part=snippet%2Cstatus%2Clocalizations" in insert[0]
    assert json.loads(insert[2])["status"]["privacyStatus"] == "private"


def test_upload_finds_the_episode_already_on_the_channel_and_does_not_upload_again(tmp_path):
    yt, http = publisher(ok(CHANNEL), ok(PLAYLIST), ok({"items": [video("old1"), video("vid42", ["ep-en-A2-x01"])]}))
    done = yt.upload(tmp_path / "unused.mp4", PACKAGE)
    assert (done.external_id, done.quota_units) == ("vid42", 3)
    assert len(http.request_sequence) == 3  # no insert


def test_the_first_upload_to_a_channel_without_an_uploads_playlist_goes_ahead(tmp_path):
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\0" * 1024)
    yt, http = publisher(ok(CHANNEL), error(404, "playlistNotFound"),
                         ({"status": "200", "location": "https://upload.example/session"}, ""), ok({"id": "new7"}))
    assert yt.upload(clip, PACKAGE).external_id == "new7"


def test_a_failed_chunk_is_retried_within_the_same_upload_session(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\0" * 1024)
    yt, http = publisher(ok(CHANNEL), ok({"items": []}),
                         ({"status": "200", "location": "https://upload.example/session"}, ""),
                         ({"status": "503"}, ""), ok({"id": "new7"}))
    assert yt.upload(clip, PACKAGE).external_id == "new7"
    assert [m for _, m, *_ in http.request_sequence] == ["GET", "GET", "POST", "PUT", "PUT"]


def test_schedule_sets_publish_at_in_utc_and_is_idempotent():
    at = datetime(2026, 11, 2, 18, 30, tzinfo=timezone(timedelta(hours=7)))
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    yt, http = publisher(ok({"items": [{"id": "vid42", "status": status}]}), ok({"id": "vid42"}))
    assert yt.schedule("vid42", at, PACKAGE) == 51
    update = http.request_sequence[1]
    assert update[1] == "PUT" and json.loads(update[2])["status"] == {**status, "publishAt": "2026-11-02T11:30:00Z"}
    already = {**status, "publishAt": "2026-11-02T11:30:00Z"}
    yt, http = publisher(ok({"items": [{"id": "vid42", "status": already}]}))
    assert yt.schedule("vid42", at.astimezone(UTC), PACKAGE) == 1 and len(http.request_sequence) == 1


def test_schedule_takes_the_labels_from_the_package_not_from_the_api_echo():
    echoed = {"privacyStatus": "private", "publishAt": "2026-11-02T11:30:00Z"}  # labels missing from the response
    yt, http = publisher(ok({"items": [{"id": "vid42", "status": echoed}]}), ok({"id": "vid42"}))
    assert yt.schedule("vid42", datetime(2026, 11, 2, 11, 30, tzinfo=UTC), PACKAGE) == 51
    sent = json.loads(http.request_sequence[1][2])["status"]
    assert sent["containsSyntheticMedia"] is True and sent["selfDeclaredMadeForKids"] is False


def test_schedule_refuses_a_naive_time_or_an_unknown_video():
    yt, _ = publisher()
    with pytest.raises(PublishError, match="timezone"):
        yt.schedule("vid42", datetime(2026, 11, 2, 18, 30), PACKAGE)
    yt, _ = publisher(ok({"items": []}))
    with pytest.raises(PublishError, match="no YouTube video vid42"):
        yt.schedule("vid42", datetime(2026, 11, 2, tzinfo=UTC), PACKAGE)


def test_quota_and_expired_tokens_become_actionable_errors(tmp_path):
    yt, _ = publisher(error(403, "quotaExceeded"))
    with pytest.raises(PublishError, match="quota exhausted .*export provider"):
        yt.upload(tmp_path / "unused.mp4", PACKAGE)
    yt, _ = publisher(({"status": "400"}, json.dumps({"error": "invalid_grant",
                                                      "error_description": "Token has been expired or revoked."})))
    with pytest.raises(PublishError, match="expired or was revoked; run `factory media auth youtube`"):
        yt.upload(tmp_path / "unused.mp4", PACKAGE)
    refresh = publish_error(RefreshError("invalid_grant: Token has been expired or revoked."))
    assert "factory media auth youtube" in str(refresh)


def test_a_missing_token_file_says_how_to_make_one(tmp_path):
    yt = YouTubePublisher(token=tmp_path / "missing.json")
    with pytest.raises(PublishError, match=r"no YouTube token .*factory media auth youtube"):
        yt.service


def test_an_unusable_token_file_says_how_to_make_a_new_one(tmp_path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    with pytest.raises(PublishError, match=r"not usable .*factory media auth youtube"):
        YouTubePublisher(token=token).service


def test_the_live_profile_publishes_to_youtube_with_the_token_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("YOUTUBE_TOKEN_PATH", str(tmp_path / "token.json"))
    yt = media.publisher_for("live", tmp_path)
    assert yt.platform == "youtube" and yt.token == tmp_path / "token.json" and yt.category_id == "27"


def test_youtube_passes_the_publisher_conformance(tmp_path):
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\0" * 1024)
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    scheduled = {**status, "publishAt": "2030-01-01T09:00:00Z"}
    tagged = {"id": "new7", "snippet": {"channelId": "UCme", "tags": ["english", "ep-en-A2-x01"]}}
    yt, http = publisher(ok(CHANNEL), ok({"items": []}),  # find before the upload
                         ok(CHANNEL), ok({"items": []}),  # the upload's own lookup
                         ({"status": "200", "location": "https://upload.example/session"}, ""), ok({"id": "new7"}),
                         ok(CHANNEL), ok({"items": [{"contentDetails": {"videoId": "new7"}}]}),
                         ok({"items": [tagged]}),  # find after the upload
                         ok({"items": [{"id": "UCme"}]}), ok({"items": [tagged]}),  # video_tags
                         ok({"items": [{"id": "new7", "status": status}]}), ok({"id": "new7"}),
                         ok({"items": [{"id": "new7", "status": scheduled}]}))
    assert check_publisher(yt, clip, PACKAGE) == "new7"
    assert [m for _, m, *_ in http.request_sequence] == ["GET"] * 4 + ["POST", "PUT"] + ["GET"] * 6 + ["PUT", "GET"]


def test_video_tags_only_for_a_video_of_the_token_s_channel():
    mine = {"id": "vid42", "snippet": {"channelId": "UCme", "tags": ["ep-en-A2-x01"]}}
    yt, _ = publisher(ok({"items": [{"id": "UCme"}]}), ok({"items": [mine]}))
    assert yt.video_tags("vid42") == ["ep-en-A2-x01"]
    theirs = {"id": "vid42", "snippet": {"channelId": "UCother", "tags": ["ep-en-A2-x01"]}}
    yt, _ = publisher(ok({"items": [{"id": "UCme"}]}), ok({"items": [theirs]}))
    assert yt.video_tags("vid42") is None
    yt, _ = publisher(ok({"items": [{"id": "UCme"}]}), ok({"items": []}))
    assert yt.video_tags("vid42") is None


def test_a_refused_upload_before_any_bytes_says_no_video_exists(tmp_path):
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\0" * 1024)
    yt, _ = publisher(ok(CHANNEL), ok({"items": []}), error(403, "quotaExceeded"))
    with pytest.raises(PublishError, match="quota exhausted") as refused:
        yt.upload(clip, PACKAGE)
    assert refused.value.video_may_exist is False


def test_a_failed_lookup_or_an_unreadable_file_says_no_video_exists(tmp_path):
    yt, _ = publisher(error(401, "authError"))
    with pytest.raises(PublishError) as lookup:
        yt.upload(tmp_path / "unused.mp4", PACKAGE)
    assert lookup.value.video_may_exist is False
    yt, _ = publisher(ok(CHANNEL), ok({"items": []}))
    with pytest.raises(PublishError, match="cannot read") as unreadable:
        yt.upload(tmp_path / "missing.mp4", PACKAGE)
    assert unreadable.value.video_may_exist is False


def test_an_error_mid_upload_may_have_left_a_video(tmp_path):
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\0" * 1024)
    yt, _ = publisher(ok(CHANNEL), ok({"items": []}),
                      ({"status": "200", "location": "https://upload.example/session"}, ""),
                      error(400, "badRequest"))
    with pytest.raises(PublishError) as broken:
        yt.upload(clip, PACKAGE)
    assert broken.value.video_may_exist is True


class DroppedAfter(HttpMockSequence):
    """Replays the scripted responses, then fails like a dropped connection."""

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        if not self._iterable:
            raise TimeoutError("timed out")
        return super().request(uri, method, body, headers, **kwargs)


def test_a_network_failure_before_the_upload_session_says_no_video_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("googleapiclient.http.time.sleep", lambda s: None)
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\0" * 1024)
    yt = YouTubePublisher(service=build_service(http=DroppedAfter([ok(CHANNEL), ok({"items": []})])))
    with pytest.raises(PublishError, match="timed out") as dropped:
        yt.upload(clip, PACKAGE)
    assert dropped.value.video_may_exist is False
