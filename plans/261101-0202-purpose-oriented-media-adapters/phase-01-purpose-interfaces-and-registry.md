---
phase: 1
title: "Interface theo mục đích, media config, registry"
status: completed
priority: P1
effort: "2d"
dependencies: []
---

# Phase 1: Interface theo mục đích, media config, registry

## Goal

Station và worker chỉ phụ thuộc vào bốn interface theo mục đích; provider được chọn từ
`config/media.yaml`; các fake hiện có trở thành provider `fake`/`export` của interface mới; CI
vẫn xanh, không gọi mạng.

## Interface

Viết trong `base.py` của từng package. Không có thuộc tính `vendor`; `identity` là thứ duy nhất
đi vào `station_version`.

```python
# factory/adapters/speech/base.py
@dataclass(frozen=True)
class SpeechRequest:
    text: str
    language: str      # BCP-47 của pack, ví dụ "en"
    voice: str         # key giọng trừu tượng của pack, ví dụ "en-gb-female-1"
    rate: float        # tỉ lệ so với tốc độ nói tự nhiên của pack; 1.0 = native

@dataclass
class SpeechResult:
    duration_s: float
    words: list[WordTiming] | None   # None khi provider không trả word timing
    costs: list[CostEntry]

class SpeechSynthesizer(Protocol):
    identity: str
    def synthesize(self, request: SpeechRequest, out_path: Path) -> SpeechResult:
        """Ghi WAV mono PCM 16-bit ở `sample_rate` của config vào out_path."""

# factory/adapters/image/base.py
@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    width: int
    height: int
    seed: int          # suy ra từ prompt, để cùng input thì cùng request

class ImageGenerator(Protocol):
    identity: str
    def generate(self, request: ImageRequest, out_path: Path) -> list[CostEntry]:
        """Ghi PNG đúng width x height; provider sinh kích thước khác thì gọi fit_image."""

# factory/adapters/video/base.py
class VideoRenderer(Protocol):
    identity: str
    def render(self, props: RenderProps, resolve: Callable[[str], Path], media_dir: Path) -> Path: ...

# factory/adapters/publishing/base.py
class VideoPublisher(Protocol):
    platform: str      # nền tảng đích ghi vào PublishReceipt, ví dụ "youtube", "export"
    identity: str
    def upload(self, video: Path, package: PublishPackage) -> Upload: ...
    def schedule(self, external_id: str, publish_at: datetime) -> int: ...  # trả quota units
```

`platform` là nền tảng đích chứ không phải vendor: episode được lên lịch ở đâu là dữ liệu của
receipt.

## Giọng trừu tượng

- `factory/tools/language_pack.py`: thay `VoiceRef(vendor, id, tags)` bằng
  `VoiceSpec(key, locale, gender, tags)`.
- `packs/en/pack.py`: khai báo `en-gb-female-1`, `en-gb-male-1` (locale `en-GB`).
  `packs/xx_fixture/pack.py`: `xx-a`, `xx-b`.
- Channel Bible: `cast[].voice` tùy chọn, là key giọng của pack. `en-podcast-spike.yaml`:
  anna → `en-gb-female-1`, ben → `en-gb-male-1`. Không ghi thì giữ cách gán theo thứ tự.
  Config loader báo lỗi khi key không có trong pack.
- `LineDirective`: bỏ `vendor`, `voice_id`; thêm `voice` (key). Tăng `schema_version` lên `2.0.0`
  và tạo lại JSON schema trong `factory/contracts/schemas/`.
- `voice.direct` giữ `rate` theo đơn vị pack (contract không đổi ý nghĩa); `voice.voice` chia cho
  `pack.native_rate` khi dựng `SpeechRequest`.

## `config/media.yaml`

```yaml
# Which provider serves each media purpose (docs/decisions/0004-purpose-oriented-media-adapters.md).
# Secrets never live here; providers name the environment variables that hold them.
providers:
  fake-speech: {type: fake_speech}
  fake-image: {type: fake_image}
  ffmpeg-pillow: {type: ffmpeg_pillow}
  export: {type: export, dir: artifacts/_export}
  # Real providers are added by later phases.

prices: {}       # provider -> model -> USD per unit, như llm.yaml

profiles:
  fake:
    speech: {provider: fake-speech, voices: {en-gb-female-1: fake-a, en-gb-male-1: fake-b, xx-a: fake-a, xx-b: fake-b}}
    image: {provider: fake-image}
    video: {provider: ffmpeg-pillow}
    publishing: {provider: export}
  live:
    # filled by phases 2-5
```

- `factory/adapters/media.py`: model pydantic `extra="forbid"` cho file trên;
  `load_media_config()`, `speech_for(profile, pack)`, `image_for(profile)`, `video_for(profile)`,
  `publisher_for(profile)`. Dựng implementation theo `type` với import lười, như `router.py`.
- `identity` của speech gồm type, model, sample rate và hash của bảng `voices`, để đổi giọng thì
  `station_version` đổi.
- Kiểm tra lúc load: mọi key giọng mà pack của channel dùng phải có trong `voices` của profile.
- Profile chọn bằng `--media-profile` của `factory run`, mặc định đọc `FACTORY_MEDIA_PROFILE`,
  không có thì `fake`. `scripts/ci.sh` export `FACTORY_MEDIA_PROFILE=fake`.

## Files to Create / Modify

- Create: `factory/adapters/speech/{__init__,base,fake}.py` (chuyển từ `tts/`), xóa `factory/adapters/tts/`.
- Modify: `factory/adapters/image/{base,fake}.py`; thêm `fit_image` vào `image/base.py`.
- Create: `factory/adapters/video/{__init__,base,ffmpeg_pillow}.py` (code từ `workers/render.py`, xem phase 4).
- Create: `factory/adapters/publishing/{__init__,base,export}.py` (chuyển từ `publish/`; `FakePublisher` thành `ExportPublisher` vì nó chính là gói export để upload tay), xóa `factory/adapters/publish/`.
- Create: `factory/adapters/media.py`, `config/media.yaml`.
- Modify: `factory/tools/language_pack.py`, `packs/en/pack.py`, `packs/xx_fixture/pack.py`, `factory/config.py` (cast voice), `config/channels/*.yaml`.
- Modify: `factory/contracts/voice_directives.py`, `factory/contracts/schemas/`.
- Modify: `factory/workers/voice.py`, `visuals.py`, `publisher.py`, `render.py` (gọi qua interface; gom `costs` vào `Built`).
- Modify: `factory/orchestrator/stations.py` (`Vendors` nhận 4 interface; `station_version` lấy `identity`).
- Modify: `factory/cli.py` (`--media-profile`), `scripts/ci.sh`.
- Create: `tests/adapters/conformance.py` (bộ test chung theo mục đích), `tests/adapters/test_fake_providers.py`, `tests/test_media_config.py`.
- Modify: `tests/test_fake_adapters.py` (gộp vào file mới hoặc xóa), `tests/test_workers.py`, `tests/test_e2e.py`, pack conformance test nếu kiểm `voices`.

## Tasks & Steps

1. Viết bốn `base.py` và `fit_image` (Pillow, crop giữa rồi scale, giữ tỉ lệ).
2. Viết bộ conformance cho từng mục đích:
   - speech: WAV mono 16-bit, `duration_s` khớp số frame, `words` nếu có thì tăng dần và nằm trong `duration_s`, `identity` không rỗng;
   - image: PNG đúng kích thước;
   - video: MP4 có một stream video H.264 và một stream AAC, thời lượng khớp props;
   - publishing: `upload` rồi `schedule` hai lần không lỗi.
3. Chuyển các fake sang interface mới, chạy conformance trên chúng.
4. Đổi `VoiceRef` thành `VoiceSpec`, thêm `cast[].voice`, đổi `LineDirective`, tạo lại schema.
5. Viết `media.py` + `config/media.yaml` + test load config (key thiếu, provider không tồn tại, secret thiếu báo tên biến).
6. Nối `stations.py`, `cli.py`, `ci.sh`.
7. Xóa `tts/`, `publish/` và mọi import cũ.

## Verification

- `uv run ruff check .`
- `uv run pytest -m "not db and not e2e"`
- `scripts/ci.sh` pass.
- `grep -rn "vendor" factory/adapters/*/base.py factory/contracts/voice_directives.py` không còn kết quả.
