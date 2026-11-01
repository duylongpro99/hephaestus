---
title: Vòng sửa script sau reject đã chạy, có giới hạn 2 vòng
date: 2026-11-01
summary: A3 sửa script theo ghi chú reviewer qua RevisionRequest, đếm chung panel và gate 1, tối đa 2 vòng rồi ESCALATED; review tìm ra lỗi con trỏ artifact khi script quay lại bản cũ và đã sửa
---

# Vòng sửa script sau reject

## Đã làm
- Thực thi `plans/261101-1124-review-notes-revision-loop/` (5 phase, chế độ `--auto`).
- State machine: `MAX_REJECTS = 1` đổi thành `MAX_REWRITES = 2`, dùng chung cho review panel và
  gate 1. Số vòng đếm từ bảng `job` (`repo.count_rewrites`), nên vẫn đúng qua nhiều lần
  `factory run`. Reject ở gate 2 vẫn escalate và không bị tính.
- Contract mới `RevisionRequest` / `ReviewerNote`. Mỗi vòng sửa tạo một artifact
  `revision_request` và artifact đó nằm trong input của A3, nên chạy lại sau crash sẽ dùng lại
  output đã lưu.
- A3 có chế độ sửa: luôn chạy ít nhất một turn dù script đã pass gate. Prompt có mục
  "Revising after review". Bản sửa không đổi gì sẽ escalate với lý do `NO_CHANGES`.
- `factory decide --gate 1 --decision reject` bắt buộc có `--notes`.
- Fake LLM hỗ trợ fixture `{station}.{n}.json` theo lượt gọi. Thêm test e2e cho bốn đường:
  panel reject rồi sửa, chạm giới hạn, người duyệt reject ở gate 1 (chạy trong một process và
  qua hai lần chạy CLI), và script quay lại một bản cũ.
- Việc còn mở trong `2026-10-22-walking-skeleton-implemented.md` (reject quay về DRAFTED nhưng
  không ai đưa ghi chú cho A3) nay đã đóng.
- Kết quả: ruff sạch, `pytest` 287 passed / 3 skipped, `scripts/ci.sh` pass.

## Bất ngờ
- Code review tìm ra lỗi con trỏ "artifact mới nhất" bị lệch. Store dùng content-addressing và
  `ON CONFLICT DO NOTHING`, nên khi A3 sửa script quay lại đúng một bản panel đã chấm
  (A → B → A), review của A được dùng lại mà không thêm dòng mới. Lúc đó `latest_artifact`
  vẫn trỏ vào review của B. Đã sửa: `revision_request` đọc review theo đúng input
  `[spec, script]` từ store. Test mới fail với code cũ, pass với code mới.
  Con trỏ mới nhất của `c2_enrichment` và QAReport của panel cũng có thể lệch theo cách này.
  Hiện chưa station nào đọc lại `c2_enrichment`, nên phần này chưa sửa.
- Bộ đếm của fixture đánh số nằm trong process. Test gate 1 chạy trong một process đã che mất
  việc hai lần `factory run` bắt đầu đếm lại từ 1. Đã thêm fixture `xx-A2-revise-gate` và test
  qua CLI thật.
- Thuộc tính `calls` của `FakeLLMProvider` trùng tên với `CountingLLM.calls` trong test cũ, làm
  số lần đếm bị nhân đôi. Đã đổi tên thành `_served`.

## Quyết định
- Giới hạn vòng sửa vẫn là hằng số trong code. Khi chuyển sang Channel Bible thì phải đổi
  `config_hash`, nên để sau.
- Chỉ bắt buộc `--notes` khi reject ở gate 1: reject ở gate 2 không chạy A3.
- Truy vấn quyết định gate 1 chỉ lấy reject, để một approve ghi muộn không bị dùng làm ghi chú.
- Khi gate vẫn fail, lý do gate được ưu tiên hơn `NO_CHANGES`.

## Việc tiếp theo
- Episode cũ từng bị reject ở gate 1 không kèm notes sẽ escalate với "cannot build the revision
  request". Người vận hành cần ghi lại quyết định có notes.
- Câu hỏi sản phẩm: có cho A3 thêm turn khi turn sửa đầu tiên không đổi gì không? Có đưa
  `suggested_fix` của persona chọn `edit-and-approve` vào RevisionRequest khi persona khác reject
  không?
- Cân nhắc cho `c2_enrichment` và QAReport ở gate 1 đọc theo input thay vì con trỏ mới nhất.
