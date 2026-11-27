from dataclasses import asdict, dataclass


RELEASE = "放行"
CONDITIONAL = "条件放行"
DEFER = "延期"
DECISIONS = (RELEASE, CONDITIONAL, DEFER)

FOLLOW_UP = "后续复核"
SUPPLY = "补件"
OBLIGATION_KINDS = (FOLLOW_UP, SUPPLY)

COLUMN_LABELS = {
    "credential": "凭据号",
    "batch": "批次号",
    "permit": "许可单号",
    "decision": "放行结论",
    "planned": "施工计划开工分",
    "issued": "签发分钟",
    "reasons": "裁决依据",
    "obligations": "后续凭据",
    "basis": "关联记录",
}


@dataclass(frozen=True, slots=True)
class Obligation:
    kind: str
    detail: str
    due: int | None

    def __post_init__(self):
        if self.kind not in OBLIGATION_KINDS:
            raise ValueError("后续凭据种类无效")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("后续凭据说明缺失")
        if self.due is not None and (type(self.due) is not int or not 0 <= self.due <= 50000):
            raise ValueError("后续凭据时限越界")

    def as_record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Clearance:
    credential: str
    batch: str
    permit: str
    decision: str
    planned: int
    issued: int
    reasons: tuple
    obligations: tuple
    basis: tuple

    def __post_init__(self):
        if not isinstance(self.credential, str) or not self.credential.strip():
            raise ValueError("凭据号缺失")
        if not isinstance(self.batch, str) or not self.batch.strip():
            raise ValueError("批次号缺失")
        if not isinstance(self.permit, str) or not self.permit.strip():
            raise ValueError("许可单号缺失")
        if self.decision not in DECISIONS:
            raise ValueError("放行结论无效")
        if type(self.planned) is not int or not 0 <= self.planned <= 50000:
            raise ValueError("施工计划开工分越界")
        if type(self.issued) is not int or not 0 <= self.issued <= 50000:
            raise ValueError("签发分钟越界")
        if not isinstance(self.reasons, tuple) or any(not isinstance(item, str) or not item.strip() for item in self.reasons):
            raise ValueError("裁决依据须为非空文字序列")
        if not isinstance(self.obligations, tuple) or any(not isinstance(item, Obligation) for item in self.obligations):
            raise ValueError("后续凭据须为凭据序列")
        if not isinstance(self.basis, tuple) or any(not isinstance(item, str) or not item.strip() for item in self.basis):
            raise ValueError("关联记录须为非空文字序列")
        if self.decision == RELEASE and self.obligations:
            raise ValueError("放行不得附带后续凭据")
        if self.decision == CONDITIONAL and not self.obligations:
            raise ValueError("条件放行须留后续复核或补件凭据")
        if self.decision == DEFER and not self.reasons:
            raise ValueError("延期须说明裁决依据")

    def as_record(self) -> dict:
        return asdict(self)
