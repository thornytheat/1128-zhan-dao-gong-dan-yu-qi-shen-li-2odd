import json

import pytest
from types import SimpleNamespace as O

from permitdesk.start_clearance.adjudicate import decide
from permitdesk.start_clearance.contracts import Clearance, Obligation
from permitdesk.start_clearance.journal import ClearanceJournal
from permitdesk.start_clearance.service import prepare_clearance, visible_closures
from permitdesk.review_roster.contracts import Appointment


def permit(key="P1", planned=1000, urgent=False):
    return O(permit=key, planned=planned, urgent=urgent, work="开挖修复", district="政西")


def closure(key="P1", recorded=900, late=False, ticket="C-1"):
    return {"permit": key, "submitted": 800, "recorded": recorded, "late": late,
            "signature": "督办科复核", "disposition": "已会签", "primary": "政西 主管", "ticket": ticket}


def hearing(key="P1", state="安排复核", reviewer="政西 主管"):
    return Appointment(key, state, reviewer if state == "安排复核" else None, None,
                       8100 if state == "安排复核" else None, 8155 if state == "安排复核" else None, "资质及班内时段可用")


def clock(key="P1", overdue=False, due=950):
    return O(overdue=overdue, remaining=10, due=due)


def adjudicate(**overrides):
    payload = dict(urgent=False, planned=1000, missing=(), overdue=False,
                   closure=O(recorded=900, disposition="已会签", ticket="C-1"),
                   hearing=hearing(), due=950)
    payload.update(overrides)
    return decide(**payload)


def test_normal_unreviewed_defers_and_never_starts_as_planned():
    decision, reasons, obligations, _ = adjudicate(closure=None, hearing=hearing(state="保留待审"))
    assert decision == "延期" and not obligations
    assert any("复核未完成" in text and "不得按计划开工" in text for text in reasons)


def test_normal_reviewed_clean_releases():
    decision, reasons, obligations, basis = adjudicate()
    assert decision == "放行" and not obligations
    assert any("结案流水 C-1" in text for text in basis)


def test_overdue_cannot_bypass_original_conclusion():
    decision, reasons, _, basis = adjudicate(overdue=True, closure=O(recorded=900, disposition="已会签", ticket="C-9"))
    assert decision == "延期"
    assert any("逾期" in text and "不得借放行绕过原结论" in text for text in reasons)
    assert any("已逾期" in text for text in basis)


def test_missing_documents_cannot_release():
    decision, reasons, _, _ = adjudicate(missing=("恢复承诺书",), hearing=hearing(state="通知补件"))
    assert decision == "延期"
    assert any("恢复承诺书" in text and "不得借放行绕过原结论" in text for text in reasons)


def test_urgent_conditional_release_keeps_followup_credentials():
    decision, reasons, obligations, _ = adjudicate(urgent=True, closure=None, missing=("恢复承诺书",), overdue=True)
    assert decision == "条件放行"
    kinds = {entry.kind for entry in obligations}
    assert kinds == {"后续复核", "补件"}
    follow = next(entry for entry in obligations if entry.kind == "后续复核")
    assert "开工后补办完整复核" in follow.detail and "逾期在案" in follow.detail
    assert any("原结论在案" in text for text in reasons)


def test_urgent_reviewed_clean_releases_without_conditions():
    decision, _, obligations, _ = adjudicate(urgent=True)
    assert decision == "放行" and not obligations


def test_closure_recorded_after_plan_is_not_reviewed():
    decision, reasons, _, _ = adjudicate(closure=O(recorded=1001, disposition="已会签", ticket="C-2"))
    assert decision == "延期"
    assert any("晚于计划开工" in text for text in reasons)


def test_clearance_contract_guards():
    with pytest.raises(ValueError, match="不得附带"):
        Clearance("FX-1", "B-1", "P1", "放行", 1000, 900, ("依据",), (Obligation("补件", "补交图纸", 950),), ("关联",))
    with pytest.raises(ValueError, match="须留后续"):
        Clearance("TJ-1", "B-1", "P1", "条件放行", 1000, 900, ("依据",), (), ("关联",))
    with pytest.raises(ValueError, match="结论无效"):
        Clearance("XX-1", "B-1", "P1", "默许", 1000, 900, ("依据",), (), ("关联",))


def prepare(journal, receipts=None, hearings=None, missing=None, clocks=None, cutoff=1000):
    permits = [permit("P1"), permit("P2", planned=1010, urgent=True)]
    hearings = hearings if hearings is not None else [hearing("P1"), hearing("P2")]
    clocks = clocks if clocks is not None else {key: clock(key) for key in ("P1", "P2")}
    missing = missing if missing is not None else {key: () for key in ("P1", "P2")}
    receipts = receipts if receipts is not None else [closure("P1"), closure("P2", ticket="C-2")]
    return prepare_clearance(permits, hearings, clocks, missing, receipts, cutoff, journal)


def test_receipts_beyond_cutoff_are_not_reviewed():
    batch, clearances, _ = prepare(ClearanceJournal(), receipts=[closure("P1", recorded=1001), closure("P2", ticket="C-2")])
    states = {row.permit: row.decision for row in clearances}
    assert states["P1"] == "延期" and states["P2"] == "放行"


def test_conflicting_visible_closures_are_rejected():
    with pytest.raises(ValueError, match="相互矛盾"):
        prepare(ClearanceJournal(), receipts=[closure("P1"), closure("P1", ticket="C-9", recorded=901)])


def test_same_batch_rerun_never_duplicates_credentials():
    journal = ClearanceJournal()
    batch, first, stats = prepare(journal)
    batch2, second, stats2 = prepare(journal)
    assert batch == batch2
    assert [row.credential for row in first] == [row.credential for row in second]
    assert stats["added"] == 2 and stats2["added"] == 0 and stats2["kept"] == 2
    assert stats2["credentials"] == 2


def test_journal_keeps_original_records_when_batch_changes():
    journal = ClearanceJournal()
    prepare(journal)
    _, _, stats = prepare(journal, hearings=[hearing("P1"), hearing("P2", state="保留待审")])
    assert stats["batches"] == 2 and stats["credentials"] == 4


def test_tampered_credential_and_batch_conflict_are_rejected():
    journal = ClearanceJournal()
    batch, clearances, _ = prepare(journal)
    stored = journal.credentials[clearances[0].credential]
    journal.credentials[clearances[0].credential] = stored | {"planned": stored["planned"] + 7}
    with pytest.raises(ValueError, match="冲突"):
        prepare(journal)
    with pytest.raises(ValueError, match="批次指纹"):
        journal.merge(batch, 1000, ["P1", "P2", "P3"], [])


def test_journal_roundtrip_and_corrupt_file(tmp_path):
    path = tmp_path / "journal.json"
    journal = ClearanceJournal()
    prepare(journal)
    journal.save(path)
    loaded = ClearanceJournal.load(path)
    _, _, stats = prepare(loaded)
    assert stats["added"] == 0 and stats["credentials"] == 2
    path.write_text("{损坏", encoding="utf-8")
    with pytest.raises(ValueError, match="无法读取"):
        ClearanceJournal.load(path)


def test_visible_closures_reject_inverted_clock():
    with pytest.raises(ValueError, match="早于收件"):
        visible_closures([closure("P1", recorded=700)], 1000)
