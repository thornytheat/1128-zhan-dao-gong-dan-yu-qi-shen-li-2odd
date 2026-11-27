"""按业务条件裁决开工放行：放行、条件放行或延期。"""

from .contracts import CONDITIONAL, DEFER, FOLLOW_UP, RELEASE, SUPPLY, Obligation

SHORTAGE = "缺件"
OVERDUE = "逾期"
UNREVIEWED = "复核未完成"


def review_note(closure, hearing, planned):
    if closure is not None and closure.recorded > planned:
        return f"结案录入 {closure.recorded} 晚于计划开工 {planned}"
    if hearing is None:
        return "本班无排班记录"
    notes = {"安排复核": "本班已排复核，截面未见结案回执",
             "通知补件": "本班已通知补件，复核未办结",
             "保留待审": "本班席位不足，保留待审",
             "主管协调": "待主管协调会签"}
    return notes.get(hearing.state, f"本班状态：{hearing.state}")


def decide(*, urgent, planned, missing, overdue, closure, hearing, due):
    """裁决一单。返回 (结论, 裁决依据, 后续凭据, 关联记录)。

    普通工单：复核完成、材料齐全且在法定时限内才放行，否则延期；
    应急抢修：不等完整复核可条件放行，但逾期、缺件、未复核的原结论
    一律写入后续复核或补件凭据，不得借放行绕过。
    """
    reviewed = closure is not None and closure.recorded <= planned
    blocks = []
    if missing:
        blocks.append((SHORTAGE, f"材料仍缺：{'、'.join(missing)}"))
    if overdue:
        blocks.append((OVERDUE, "法定时限已逾期"))
    if not reviewed:
        blocks.append((UNREVIEWED, f"复核未完成（{review_note(closure, hearing, planned)}）"))
    basis = []
    if hearing is not None:
        signer = f"（{hearing.reviewer}）" if hearing.reviewer else ""
        basis.append(f"本班排班：{hearing.state}{signer}")
    if closure is not None:
        basis.append(f"结案流水 {closure.ticket}（{closure.disposition}，录入 {closure.recorded}）")
    if due is not None:
        basis.append(f"法定截止 {due}" + ("，已逾期" if overdue else ""))
    basis = tuple(basis)
    if not blocks:
        return RELEASE, ("复核已完成，材料齐全且在法定时限内",), (), basis
    if not urgent:
        reasons = tuple(text + ("，不得借放行绕过原结论" if kind != UNREVIEWED else "，普通工单不得按计划开工")
                        for kind, text in blocks)
        return DEFER, reasons, (), basis
    follow = []
    if not reviewed:
        follow.append("开工后补办完整复核")
    if overdue:
        follow.append("逾期在案，督办复核销号")
    obligations = []
    if follow:
        obligations.append(Obligation(FOLLOW_UP, "；".join(follow), due))
    if missing:
        obligations.append(Obligation(SUPPLY, "补交" + "、".join(missing), due))
    reasons = ("应急抢修，先予条件放行",) + tuple(text + "，原结论在案" for _, text in blocks)
    return CONDITIONAL, reasons, tuple(obligations), basis
