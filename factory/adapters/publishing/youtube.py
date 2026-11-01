"""YouTube Data API v3: private resumable upload, then `publishAt` scheduling.

Quota (docs/architecture.md): `videos.insert` draws on its own upload bucket, so `quota_units`
counts only the 10,000-unit bucket: one unit per lookup, 50 for `videos.update`.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from factory.adapters.publishing.base import PublishError, Upload, episode_tag, upload_tags
from factory.contracts import PublishPackage

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]
RECENT_UPLOADS = 50
UPDATE_UNITS = 50
CHUNK_RETRIES = 5
REAUTH = "run `factory media auth youtube` again"


def description(package: PublishPackage, language: str) -> str:
    """The package description with chapters appended; YouTube needs the first chapter at 0:00."""
    text = package.description.get(language, "")
    if not package.chapters:
        return text
    stamps = [f"{int(c.start_s) // 60}:{int(c.start_s) % 60:02d} {c.title}" for c in package.chapters]
    return f"{text}\n\n" + "\n".join(stamps) if text else "\n".join(stamps)


def video_body(package: PublishPackage, category_id: str) -> dict:
    """The `videos.insert` resource: private, in the title's first language, others as localizations."""
    language, *others = list(package.title)
    tags = upload_tags(package, language)
    body = {
        "snippet": {"title": package.title[language], "description": description(package, language), "tags": tags,
                    "categoryId": category_id, "defaultLanguage": language, "defaultAudioLanguage": language},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": package.made_for_kids,
                   "containsSyntheticMedia": package.contains_synthetic_media},
    }
    if others:
        body["localizations"] = {lang: {"title": package.title[lang], "description": description(package, lang)}
                                 for lang in others}
    return body


def rfc3339(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise PublishError("publishAt needs a timezone-aware time")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def publish_error(exc: Exception) -> PublishError:
    """A clear message for the failures an operator can act on: quota, expired token, anything else."""
    content = getattr(exc, "content", b"")
    text = f"{exc} {content.decode('utf-8', 'replace') if isinstance(content, bytes) else content}".strip()
    try:
        reasons = {e.get("reason") for e in json.loads(content)["error"].get("errors", [])}
    except (ValueError, KeyError, TypeError, AttributeError):
        reasons = set()
    if "quotaExceeded" in reasons or "uploadLimitExceeded" in reasons or "quotaExceeded" in text:
        return PublishError(f"YouTube quota exhausted ({', '.join(sorted(r for r in reasons if r)) or exc}); "
                            "it resets at midnight Pacific time, or publish through the export provider")
    if "invalid_grant" in text or "Token has been expired or revoked" in text:
        return PublishError(f"the YouTube token expired or was revoked; {REAUTH}")
    return PublishError(f"YouTube request failed: {exc}")


def load_credentials(token: Path):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not token.is_file():
        raise PublishError(f"no YouTube token at {token}; {REAUTH}")
    try:
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    except ValueError as exc:  # unreadable, or saved without a refresh token
        raise PublishError(f"the YouTube token at {token} is not usable ({exc}); {REAUTH}") from exc
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            raise publish_error(exc) from exc
    return creds


def build_service(credentials=None, http=None):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=credentials, http=http, cache_discovery=False)


class YouTubePublisher:
    platform = "youtube"

    def __init__(self, *, token: Path | None = None, category_id: str = "27", service=None):
        if service is None and token is None:
            raise PublishError("YouTubePublisher needs a token file or a service")
        self.token, self.category_id, self._service = token, category_id, service
        self.identity = f"youtube/v3#category={category_id}"

    @property
    def service(self):
        if self._service is None:
            self._service = build_service(load_credentials(self.token))
        return self._service

    def call(self, request):
        return self.run(request.execute)

    def find(self, episode_id: str) -> tuple[str | None, int]:
        """The id of this episode's video among the channel's recent uploads, and the units spent looking."""
        from googleapiclient.errors import HttpError

        yt = self.service
        channels = self.call(yt.channels().list(part="contentDetails", mine=True))
        if not channels.get("items"):
            raise PublishError(f"the YouTube token has no channel; {REAUTH}")
        uploads = channels["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        request = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=RECENT_UPLOADS)
        try:
            items = request.execute()
        except HttpError as exc:  # a channel that never uploaded has no uploads playlist yet
            if exc.resp.status == 404 and "playlistNotFound" in str(exc.content):
                return None, 2
            raise publish_error(exc) from exc
        ids = [i["contentDetails"]["videoId"] for i in items.get("items", [])]
        if not ids:
            return None, 2
        videos = self.call(yt.videos().list(part="snippet", id=",".join(ids)))
        tag = episode_tag(episode_id)
        for video in videos.get("items", []):
            if tag in video.get("snippet", {}).get("tags", []):
                return video["id"], 3
        return None, 3

    def video_tags(self, external_id: str) -> list[str] | None:
        yt = self.service
        channels = self.call(yt.channels().list(part="id", mine=True)).get("items", [])
        videos = self.call(yt.videos().list(part="snippet", id=external_id)).get("items", [])
        if not channels or not videos or videos[0]["snippet"].get("channelId") != channels[0]["id"]:
            return None
        return videos[0]["snippet"].get("tags", [])

    def upload(self, video: Path, package: PublishPackage) -> Upload:
        try:
            existing, units = self.find(package.episode_id)
        except PublishError as exc:  # nothing was sent yet
            exc.video_may_exist = False
            raise
        if existing:
            return Upload(external_id=existing, quota_units=units)
        from googleapiclient.http import MediaFileUpload

        try:
            media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 << 20, resumable=True)
        except OSError as exc:
            raise PublishError(f"cannot read {video}: {exc}", video_may_exist=False) from exc
        body = video_body(package, self.category_id)
        request = self.service.videos().insert(part=",".join(body), body=body, media_body=media)
        response = None
        while response is None:
            try:
                # retries a failed chunk with backoff inside the same upload session
                response = self.run(lambda: request.next_chunk(num_retries=CHUNK_RETRIES))[1]
            except PublishError as exc:
                # Without a session URI YouTube refused the upload before it began: no video exists.
                exc.video_may_exist = request.resumable_uri is not None
                raise
        return Upload(external_id=response["id"], quota_units=units)

    def run(self, step):
        """Call one API step, turning HTTP, token-refresh and network failures into a PublishError."""
        from google.auth.exceptions import RefreshError, TransportError
        from googleapiclient.errors import HttpError
        from httplib2 import HttpLib2Error

        try:
            return step()
        except (HttpError, RefreshError, TransportError, HttpLib2Error, OSError) as exc:
            raise publish_error(exc) from exc

    def schedule(self, external_id: str, publish_at: datetime, package: PublishPackage) -> int:
        when = rfc3339(publish_at)
        found = self.call(self.service.videos().list(part="status", id=external_id)).get("items", [])
        if not found:
            raise PublishError(f"no YouTube video {external_id} on this channel")
        # `videos.update(part=status)` replaces the whole status, so the audience and synthetic-media labels
        # come from the package, never from what the API happens to echo back.
        status = {"privacyStatus": "private", "publishAt": when,
                  "selfDeclaredMadeForKids": package.made_for_kids,
                  "containsSyntheticMedia": package.contains_synthetic_media}
        if all(found[0]["status"].get(key) == value for key, value in status.items()):
            return 1
        self.call(self.service.videos().update(part="status", body={"id": external_id, "status": status}))
        return 1 + UPDATE_UNITS
