"""放行与延期凭据库：只增不减，同批重跑不重复签发。"""

import json
from pathlib import Path


class ClearanceJournal:
    """按批次指纹与凭据号归并放行/延期凭据。

    凭据号由批次指纹和许可单号确定，同一批计划重跑得到同一批凭据号，
    已留存的凭据原样保留；同号不同内容视为冲突，直接拒绝。
    """

    def __init__(self, batches=None, credentials=None, path=None):
        self.batches = dict(batches or {})
        self.credentials = dict(credentials or {})
        self.path = Path(path) if path is not None else None

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls(path=path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"放行凭据库无法读取：{error}") from error
        if not isinstance(raw, dict) or not isinstance(raw.get("batches"), dict) \
                or not isinstance(raw.get("credentials"), dict):
            raise ValueError("放行凭据库结构无效")
        return cls(raw["batches"], raw["credentials"], path)

    def save(self, path=None):
        target = Path(path) if path is not None else self.path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"batches": self.batches, "credentials": self.credentials},
                             ensure_ascii=False, sort_keys=True, indent=1)
        temp = target.with_name(target.name + ".tmp")
        temp.write_text(payload + "\n", encoding="utf-8")
        temp.replace(target)

    def merge(self, batch, cutoff, permits, clearances):
        permits = sorted(permits)
        existing = self.batches.get(batch)
        if existing is not None and (existing["permits"] != permits or existing["cutoff"] != cutoff):
            raise ValueError("批次指纹与库内记录冲突")
        incoming = []
        for item in clearances:
            record = json.loads(json.dumps(item.as_record(), ensure_ascii=False, sort_keys=True))
            stored = self.credentials.get(item.credential)
            if stored is not None and stored != record:
                raise ValueError("放行凭据与库内记录冲突，疑似篡改")
            incoming.append((item.credential, record))
        added = 0
        for credential, record in incoming:
            if credential in self.credentials:
                continue
            self.credentials[credential] = record
            added += 1
        self.batches.setdefault(batch, {"cutoff": cutoff, "permits": permits, "issued": cutoff})
        return {"batch": batch, "added": added, "kept": len(incoming) - added,
                "batches": len(self.batches), "credentials": len(self.credentials)}
