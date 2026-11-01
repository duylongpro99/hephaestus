---
title: "Vòng sửa script sau reject: đưa ghi chú reviewer cho A3"
description: "Reject ở review panel hoặc gate 1 sẽ đưa ghi chú reviewer cho A3 sửa script, tối đa MAX_REWRITES vòng, quá thì ESCALATED."
status: completed
priority: P1
effort: 7h
branch: main
tags: [bugfix, backend, orchestrator, agents]
blockedBy: []
blocks: []
created: 2026-11-01
---

# Vòng sửa script sau reject

## Outcome

Khi review panel hoặc người duyệt ở gate 1 reject một script, A3 (Level Editor) nhận ghi chú của
reviewer và sửa script theo từng dòng. Script mới khác script cũ, panel chấm lại, rồi episode quay
về gate 1. Mỗi episode được sửa tối đa `MAX_REWRITES = 2` vòng (đếm chung panel và gate 1). Lần
reject tiếp theo chuyển episode sang `ESCALATED` để người sửa tay.

## Nguyên nhân gốc (đã kiểm chứng trong code)

- `PIPELINE` trong `factory/orchestrator/states.py` cho reject quay về `DRAFTED`. Step của `DRAFTED`
  là `a3_level_editor`, nên A2 không chạy lại.
- `level_script` trong `factory/orchestrator/stations.py` produce với input
  `[draft, spec, config_hash, wordlist_hash, max_turns]`. Input không đổi, nên store
  content-addressed trả lại đúng script cũ, không gọi LLM.
- Kể cả khi không có cache, `level_loop` chỉ gọi LLM khi level gate fail (`while not reports[-1].passed`).
- Hệ quả: panel reject lần hai thì escalate (`MAX_REJECTS = 1`) mà không hề sửa gì. Gate 1 đưa lại
  đúng script cũ cho người duyệt và không có giới hạn số vòng. Test
  `test_human_reject_at_gate_one_sends_the_script_back` đang khẳng định hành vi no-op này
  (`toys.builds["a3_level_editor"] == 1`).
- Ghi chú trong yêu cầu ban đầu nói "tốn tiền LLM vô ích" là chưa đúng: lần chạy lại tốn $0 vì
  dùng cache. Cái mất là công người duyệt và vòng sửa không có tác dụng.

## Constraints

- Orchestrator vẫn là state machine tất định. Số vòng đếm từ bảng `job`, không giữ trong bộ nhớ.
- Không hard-code ngôn ngữ, tuổi hay level trong `factory/`. Ghi chú reviewer đi vào prompt nguyên văn.
- Artifact mới (`RevisionRequest`) có Pydantic contract và JSON schema, validate tại ranh giới station.
- Idempotent theo episode và station: `RevisionRequest` và script đã sửa được hash theo input, nên
  chạy lại sau crash dùng lại output đã lưu và không tính tiền hai lần.
- Không đổi schema DB, không cần migration. Không đổi `config_hash` của channel nào.
- `scripts/ci.sh` vẫn chạy không cần mạng, không cần secret.
- Lệnh `factory script` và `factory review` dùng chung `level_script` vẫn chạy như cũ khi không có revision.
- Không đưa mã plan hoặc phase vào code, test hay commit. Không commit khi người dùng chưa yêu cầu.

## Non-goals

- A2 viết lại toàn bộ script (người dùng chọn A3 sửa từng dòng).
- Phân loại reject (level hay nội dung) để chọn đường xử lý.
- Ghi chú có cấu trúc ở gate 1, đổi `GateDecision` hoặc migration DB.
- Đưa giới hạn vòng vào Channel Bible (để sau, khi có console).
- Áp dụng `diff` của `edit-and-approve` vào script (hiện runner coi như approve; việc riêng).
- Gỡ trạng thái `ESCALATED` hoặc cho episode chạy tiếp sau escalate.

## Acceptance criteria

1. Panel reject rồi A3 sửa: episode đi tiếp tới `SCHEDULED` (với `--auto-approve`), script của A3 sau
   vòng sửa khác script trước, và có một artifact `revision_request` chứa ghi chú của reviewer đã reject.
2. Người duyệt reject ở gate 1 với notes: lần `factory run` tiếp theo tạo script mới (hash khác),
   panel chấm lại, episode dừng lại ở `QA_OK` chờ quyết định mới.
3. Reject lần thứ `MAX_REWRITES + 1` (panel hoặc gate 1, đếm chung) chuyển episode sang `ESCALATED`;
   job cuối có `status = escalated` và error nói rõ đã hết số vòng sửa.
4. A3 ở chế độ sửa luôn chạy ít nhất một turn kể cả khi level gate đã pass; nếu sau các turn script
   không đổi thì station escalate, không gửi lại cho panel.
5. `factory decide --decision reject` không có `--notes` bị từ chối với thông báo rõ.
6. Test với `--fake-llm` cho (1) và (3) chạy trong `uv run pytest`, không cần mạng.
7. `uv run ruff check .`, `uv run pytest` và `scripts/ci.sh` đều pass.

## Phases

| # | Phase | Trạng thái | Phụ thuộc |
|---|---|---|---|
| 1 | [Giới hạn vòng sửa chung trong state machine](phase-01-shared-rewrite-cap.md) | completed | — |
| 2 | [Contract RevisionRequest](phase-02-revision-request-contract.md) | completed | — |
| 3 | [A3 chế độ sửa theo ghi chú và nối vào station](phase-03-a3-revision-mode.md) | completed | 1, 2 |
| 4 | [Fake LLM theo lượt gọi, fixture và test end-to-end](phase-04-fake-llm-sequence-and-e2e.md) | completed | 3 |
| 5 | [Cập nhật docs](phase-05-docs.md) | completed | 4 |

Phase 1 và 2 độc lập, có thể làm song song (không chung file).

## Luồng sau khi sửa

```text
ENRICHED --review_panel reject--> DRAFTED          (rewrites < MAX_REWRITES)
QA_OK    --gate_1 reject (notes)-> DRAFTED          (rewrites < MAX_REWRITES)
         --reject---------------> ESCALATED        (rewrites >= MAX_REWRITES)

DRAFTED (a3_level_editor):
  rewrites == 0 -> level_script(draft của A2)                    như hiện nay
  rewrites  > 0 -> RevisionRequest(ghi chú của lần reject gần nhất)
                -> level_script(script A3 mới nhất, revision=…)  ≥1 turn, script phải đổi
```

## Rủi ro

- `a3.version` hash cả `agent.py` và `prompt.md`, nên mọi output A3 đã cache bị vô hiệu sau thay đổi
  này. Lần chạy `en` đầu tiên sau đó sẽ gọi lại A3 nếu level gate fail. Chấp nhận được.
- A3 có thể sửa theo ghi chú nhưng làm fail level gate. Vòng `level_loop` vẫn tiếp tục sửa level tới
  `max_turns`; hết turn thì escalate như hiện nay.
- Ghi chú nội dung lớn ("đổi cả ý tưởng") vượt khả năng sửa từng dòng. Sau `MAX_REWRITES` vòng sẽ
  escalate; đây là đánh đổi người dùng đã chọn.
- Mỗi vòng tốn thêm một lần A3 và hai lần panel. `budget_usd` của episode vẫn chặn vòng lặp tốn tiền.

## Validation Log

### Session 1 (2026-11-01)

Người dùng trả lời trước khi viết phase, để phase phản ánh đúng quyết định.

1. **Chiến lược khi reject?** Chọn: tự viết lại, có giới hạn số vòng, quá thì `ESCALATED`.
   Bỏ: escalate thẳng; tách theo loại reject.
2. **Agent nào nhận ghi chú?** Chọn: A3 sửa từng dòng, giữ `on_reject = DRAFTED`.
   Bỏ: A2 viết lại toàn bộ (`on_reject = SPEC`); A3 trước rồi A2.
3. **Giới hạn vòng đặt ở đâu, đếm thế nào?** Chọn: hằng số `MAX_REWRITES = 2` trong
   `factory/orchestrator/states.py`, đếm chung reject của panel và gate 1 cho mỗi episode.
   Không đổi `config_hash`. Bỏ: field trong Channel Bible; đếm riêng.
4. **Ghi chú có cấu trúc?** Chọn: dùng cái đang có. Panel đã có `QAIssue` trong `QAReport`; gate 1
   giữ notes text tự do. Thêm contract mới `RevisionRequest` (1.0.0) gom cả hai.
   Hệ quả: không bump `GateDecision` hay `QAReport`, không migration DB.

### Verification Results

- Claims checked: 14
- Verified: 14 | Failed: 0 | Unverified: 0
- Tier: Full (5 phase), kiểm bằng đọc code trực tiếp.
- Đã kiểm: `PIPELINE` và `MAX_REJECTS` (`states.py`); `_pass_gate` truyền `rejects=0` và `_run_step`
  đếm `rejected` của riêng station (`runner.py`); input của `level_script` và `review_script`
  (`stations.py`); điều kiện `while not reports[-1].passed` (`a3_level_editor/agent.py`); panel ghi
  `GateDecision` gate 1 với `user = persona` và `diff` là các suggested_fix (`review_panel/agent.py`);
  envelope panel có `gate_decision` (`stations.py`); `FakeLLMProvider` đọc `{station}.json` cố định
  (`adapters/llm/fake.py`); fixture dir là `tests/fixtures/<pack>/<episode_id>` (`cli.py`); spec CI ở
  `evals/xx-fixture/adult/specs/xx-A2-e2e.json` (`scripts/ci.sh`); bảng `job` có `to_status` và
  `status = 'rejected'` (`migrations/0001_init.sql`); `CONTRACTS` export schema qua
  `python -m factory.contracts`.

### Whole-Plan Consistency Sweep

- Không còn nhắc `MAX_REJECTS` ngoài phần mô tả hiện trạng và bước đổi tên ở phase 1.
- Không phase nào đổi `GateDecision`, migration hay Channel Bible, khớp quyết định 3 và 4.
- Không phase nào đổi `on_reject` sang `SPEC`, khớp quyết định 2.
- Không còn mâu thuẫn chưa giải quyết.
