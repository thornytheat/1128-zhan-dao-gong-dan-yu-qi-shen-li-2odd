import json
import pytest
from permitdesk.pipeline import run

def test_permit_full_result():
    packet=run()
    assert packet==run()
    assert len(packet["rows"])>=15 and len(packet["series"])==5 and len(packet["stages"])==7
    assert packet["stages"][-2]["records"][0]["passed"]
    json.dumps(packet,allow_nan=False)

def test_queue_capacity_and_material_decisions():
    smallest=run(1)
    ample=run(15)
    assert smallest["metrics"]["已安排复核"]==1
    assert ample["metrics"]["已安排复核"]>1
    assert smallest["stages"][-2]["records"][0]["digest"]!=ample["stages"][-2]["records"][0]["digest"]
    assert any(row["state"]=="通知补件" for row in ample["rows"])

def test_invalid_form_disposition_visible():
    entries=run()["stages"][0]["records"]
    assert {"同版冲突","已撤回","隔离","迟到更新"}<={record.get("state") for record in entries}

def test_bucket_sizes_match_observed_closure_volume():
    packet=run()
    audit=packet["stages"][-2]["records"][0]
    assert sum(point["value"] for point in packet["series"])==audit["observed"]
    assert audit["observed"]>0

def test_invalid_capacity_never_enters_scoring():
    for option in (0,101,False,"2"):
        with pytest.raises(ValueError,match="配额"): run(option)

def test_clearance_list_matches_business_rules():
    packet=run()
    stage=packet["stages"][-1]
    assert stage["title"]=="开工放行"
    summary,*rows=stage["records"]
    assert (summary["放行"],summary["条件放行"],summary["延期"])==(6,5,8)
    assert summary["本批凭据"]==len(rows)==19
    assert packet["metrics"]["准予开工"]==11 and packet["metrics"]["延期开工"]==8
    decisions={row["permit"]:row["decision"] for row in rows}
    assert decisions["SC-207"]=="放行" and decisions["SC-209"]=="延期"
    assert decisions["SC-222"]=="条件放行" and decisions["SC-223"]=="延期"
    urgent=next(row for row in rows if row["permit"]=="SC-222")
    assert any("后续复核" in item for item in urgent["obligations"])
    assert any("补件" in item for item in urgent["obligations"])
    overdue=next(row for row in rows if row["permit"]=="SC-218")
    assert overdue["decision"]=="延期" and any("不得借放行绕过原结论" in text for text in overdue["reasons"])
    table={row["permit"]:row for row in packet["rows"]}
    assert table["SC-222"]["clearance"]=="条件放行" and table["SC-222"]["credential"].startswith("TJ-")

def test_clearance_rerun_keeps_journal_without_duplicates():
    from permitdesk.start_clearance.journal import ClearanceJournal
    journal=ClearanceJournal()
    first=run(journal=journal)["stages"][-1]["records"]
    second=run(journal=journal)["stages"][-1]["records"]
    assert [row["credential"] for row in first[1:]]==[row["credential"] for row in second[1:]]
    assert first[0]["库内凭据"]==second[0]["库内凭据"]==19
    assert len(journal.credentials)==19 and len(journal.batches)==1
