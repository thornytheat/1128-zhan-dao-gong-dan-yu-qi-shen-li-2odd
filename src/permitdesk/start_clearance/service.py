"""开工放行环节：汇总台账、本班排班与结案记录，签发放行与延期凭据。"""

from dataclasses import asdict
from hashlib import sha256
from json import dumps

from ..permit_journal.contracts import Closure
from .adjudicate import decide
from .contracts import Clearance

PREFIX = {"放行": "FX", "条件放行": "TJ", "延期": "YQ"}


def visible_closures(receipts, cutoff):
    """截面可见的结案回执，一单一结论，冲突直接隔离。"""
    found = {}
    for raw in receipts:
        row = Closure.parse(raw)
        if row.recorded > cutoff:
            continue
        if row.recorded < row.submitted:
            raise ValueError("结案录入时间早于收件")
        if row.permit in found and found[row.permit] != row:
            raise ValueError("同一许可有相互矛盾的结案")
        found[row.permit] = row
    return found


def fingerprint(plans, closures, dispatch, clocks, missing, cutoff):
    """批次指纹：同一批复核安排与计划重算结果不变。"""
    payload = {
        "cutoff": cutoff,
        "plans": [[case.permit, case.planned, case.urgent, case.work, case.district] for case in plans],
        "closures": sorted((asdict(row) for row in closures.values()), key=lambda row: row["permit"]),
        "hearings": sorted((asdict(row) for row in dispatch.values()), key=lambda row: row["permit"]),
        "clocks": sorted([key, clock.overdue, clock.remaining, clock.due] for key, clock in clocks.items()),
        "missing": sorted([key, list(docs)] for key, docs in missing.items()),
    }
    return "B-" + sha256(dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]


def prepare_clearance(permits, hearings, clocks, missing, receipts, cutoff, journal):
    dispatch = {row.permit: row for row in hearings}
    if len(dispatch) != len(tuple(hearings)):
        raise ValueError("排班中有重复工单")
    closures = visible_closures(receipts, cutoff)
    plans = sorted(permits, key=lambda row: (row.planned, row.permit))
    batch = fingerprint(plans, closures, dispatch, clocks, missing, cutoff)
    issued = []
    for case in plans:
        clock = clocks[case.permit]
        closure = closures.get(case.permit)
        overdue = clock.overdue or (closure.late if closure is not None else False)
        decision, reasons, obligations, basis = decide(
            urgent=case.urgent, planned=case.planned, missing=tuple(missing.get(case.permit, ())),
            overdue=overdue, closure=closure, hearing=dispatch.get(case.permit), due=clock.due)
        digest = sha256(f"{batch}|{case.permit}".encode()).hexdigest()[:10]
        issued.append(Clearance(f"{PREFIX[decision]}-{digest}", batch, case.permit, decision,
                                case.planned, cutoff, tuple(reasons), tuple(obligations), tuple(basis)))
    stats = journal.merge(batch, cutoff, [case.permit for case in plans], issued)
    return batch, tuple(issued), stats


def clearance_rows(clearances):
    rows = []
    for item in clearances:
        rows.append({"permit": item.permit, "credential": item.credential, "decision": item.decision,
                     "planned": item.planned, "issued": item.issued, "reasons": list(item.reasons),
                     "obligations": [f"{entry.kind}：{entry.detail}" + (f"（限 {entry.due}）" if entry.due is not None else "")
                                     for entry in item.obligations],
                     "basis": list(item.basis)})
    return rows
