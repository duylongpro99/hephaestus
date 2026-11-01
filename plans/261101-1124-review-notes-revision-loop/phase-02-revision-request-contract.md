---
phase: 2
title: "Contract RevisionRequest"
status: completed
effort: 1h
---

# Phase 2: Contract RevisionRequest

## Context

- Contract nằm ở `factory/contracts/`, đăng ký trong `CONTRACTS` của `factory/contracts/__init__.py`,
  schema sinh bằng `uv run python -m factory.contracts` vào `factory/contracts/schemas/`.
- `QAIssue` (`qa_report.py`) đã có `line_id`, `category`, `severity`, `description`, `suggested_fix`.
- Quyết định: không đổi `GateDecision` hay `QAReport`; contract mới bắt đầu ở `1.0.0`.

## Yêu cầu

`RevisionRequest` là input của vòng sửa: ghi chú của lần reject gần nhất, đủ để A3 sửa và để người
xem lại sau này hiểu vì sao script đổi.

Phác thảo (tên field có thể chỉnh khi implement, giữ ý nghĩa):

```python
class ReviewerNote(Part):
    reviewer: str            # persona id của panel, hoặc user ở gate ("human")
    gate: Literal[0, 1, 2]
    notes: str = ""          # GateDecision.notes
    issues: list[QAIssue] = []  # từ QAReport của persona; rỗng với người duyệt ở gate

class RevisionRequest(Contract):
    schema_version: str = "1.0.0"
    episode_id: str
    round: int = Field(ge=1)  # vòng sửa thứ mấy
    rejected_by: str          # station hoặc gate đã reject: "review_panel" | "gate_1"
    notes: list[ReviewerNote] = Field(min_length=1)
```

- Validator: ít nhất một note có `notes` không rỗng hoặc `issues` không rỗng. Không có gì để sửa thì
  contract không hợp lệ.

## Files

- Tạo `factory/contracts/revision_request.py`.
- Sửa `factory/contracts/__init__.py`: export và thêm vào `CONTRACTS`.
- Tạo `factory/contracts/schemas/revision_request.schema.json` (sinh bằng lệnh, không viết tay).
- Sửa `tests/test_contracts.py`.

## Test

- Round-trip JSON; schema sinh ra khớp file đã commit (nếu `test_contracts.py` có test này cho mọi
  contract thì contract mới tự được kiểm).
- `RevisionRequest` với note rỗng bị từ chối; `round = 0` bị từ chối.
- Lệnh: `uv run pytest tests/test_contracts.py`.

## Rủi ro và rollback

- Không ảnh hưởng contract khác. Rollback bằng xóa file và dòng đăng ký.
