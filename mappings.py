# mappings.py
from __future__ import annotations
import json
import re
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any


MACHINE_MAP: Dict[str, str] = {
    "M00001": "IMM 301",
    "M00002": "IMM 302",
    "M00004": "IMM 303",
    "M00005": "IMM 304",
    "M00006": "IMM 305",
    "M00007": "IMM 307",
    "M00008": "IMM 308",
    "M00009": "IMM 309",
    "M00010": "IMM 310",
    "M00011": "IMM 311",
    "M00012": "IMM 312",
    "M00013": "IMM 313",
    "M00014": "IMM 314",
    "M00015": "IMM 315",
    "M00016": "IMM 316",
    "M00017": "IMM 317",
    "M00018": "IMM 318",
    "M00019": "IMM 319",
    "M00020": "IMM 320",
    "M00021": "IMM 321",
}

# Job display names are now sourced from the live Job API response in client.py.
JOB_MAP: Dict[str, str] = {}

REJECT_REASON_MAP: Dict[str, str] = {
    "BM01": "BURN MARK",
    "CS02": "COLOR STREAK",
    "CO03": "CONTAMINATION",
    "CR04": "CRACK/BRITTLE",
    "DI05": "DISCOLORATION",
}

OPERATOR_MAP: Dict[str, str] = {
    "1000001": "Snoopy Von Peanuts",
    "1000002": "Charlie Brown",
    "1000003": "Lucy Van Pelt",
}


def _load_job_stubs() -> Dict[str, Any]:
    p = Path(__file__).resolve().parent / "Database" / "job_data_stubs.json"
    fallback = Path(__file__).resolve().parent / "job_data_stubs.json"
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        if fallback.exists():
            return json.loads(fallback.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


# Disable local job stub lookup by default now that live Job API fetching is used in client.py.
# Keep the loader function for backward compatibility if needed later.
JOB_STUBS: Dict[str, Any] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_operator_badge(s: str) -> bool:
    return s in OPERATOR_MAP


def extract_qty_segment(payload: str, marker: str) -> Optional[int]:
    """
    Extract 11 digits right after marker ('Q' or 'QB').
    Example marker='Q':  ...Q00000000006...
    Example marker='QB': ...QB00000000006...
    Returns int qty (non-zero part).
    """
    idx = payload.find(marker)
    if idx < 0:
        return None

    start = idx + len(marker)
    digits = payload[start:start + 11]
    if len(digits) != 11 or not digits.isdigit():
        return None

    # "digits that is not 0" means numeric value ignoring leading zeros
    return int(digits)


def _parse_structured_raw_material(payload: str) -> Optional[Dict[str, Any]]:
    """
    Parse raw material QR like:
    O...V2P00000001180QRM00000000012I00000000001T00000000003L20260213150028-000000045890

    - P(11 digits)   -> material code/name seed
    - QRM(11 digits) -> quantity
    - I..T..L..-..   -> unique key payload, also carries trailing job id after '-'
    """
    s = str(payload).strip()
    if "V2" not in s or "QRM" not in s or "P" not in s:
        return None

    p_match = re.search(r"P(\d{11})", s)
    q_match = re.search(r"QRM(\d{11})", s)
    tail_match = re.search(r"I(\d{11})T(\d{11})L(\d{14})-(\d+)\s*$", s)
    if not p_match or not q_match or not tail_match:
        return None

    i_digits, t_digits, lot_digits, po_digits = tail_match.groups()
    material_code_digits = p_match.group(1).lstrip("0") or "0"
    qty = int(q_match.group(1))
    unique_key = f"I{i_digits}T{t_digits}L{lot_digits}-{po_digits}"
    job_code = po_digits.lstrip("0") or "0"
    material_name = f"Raw Material {material_code_digits}"
    return {
        "material_code": material_code_digits,
        "material_name": material_name,
        "qty": qty,
        "unique_key": unique_key,
        "job_code": job_code,
        "index": str(int(i_digits)),
        "total_labels": str(int(t_digits)),
        "lot_number": lot_digits,
        "po_number": po_digits,
    }


def _extract_po_from_job_qr(payload: str) -> Optional[str]:
    """
    Parse job QR format like: O000000000240000010237800000000000
    Extract the 11-digit job/PO segment immediately after the literal "24".
    Example:
      O00000000024 00000102378 00000000000
                  ^^^^^^^^^^^
    """
    s = str(payload).strip()
    # Exact parse for the common format:
    # O + (9 digits + "24") + (11-digit job id) + (11 trailing digits)
    # Example: O00000000024 00000034589 00000000000
    m_after_24 = re.fullmatch(r"O\d{9}24(\d{11})\d{11}", s)
    if m_after_24:
        return m_after_24.group(1).lstrip("0") or "0"

    # Fallback (legacy assumption): middle 11-digit segment.
    m = re.fullmatch(r"O(\d{11})(\d{11})(\d{11})", s)
    if m:
        return m.group(2).lstrip("0") or "0"
    return None


@dataclass
class ScanResult:
    kind: str
    raw: str
    value: str
    qty: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


def parse_scan(raw: str) -> Optional[ScanResult]:
    s = raw.strip()
    s_l = s.lower()

    # Operator handoff trigger
    if s_l in ("operatorshift~1", "operator_shift~1", "shiftchange~1"):
        return ScanResult(kind="OPERATOR_SHIFT_TRIGGER", raw=raw, value="Finish shift")

    # Production daily report trigger
    if s_l == "productiondailyreport~1":
        return ScanResult(kind="PRODUCTION_DAILY_REPORT_TRIGGER", raw=raw, value="Production daily report mode")
    if s_l in ("productiondailyreport~2", "pdr_done", "pdrdone"):
        return ScanResult(kind="PRODUCTION_DAILY_REPORT_RESOLVE", raw=raw, value="Production daily report resolve")
    if s_l in ("finishjob", "finishjob~1", "jobfinish"):
        return ScanResult(kind="FINISH_JOB", raw=raw, value="Finish current job session")
    if s_l == "joblinkage~1":
        return ScanResult(kind="JOB_LINKAGE_TRIGGER", raw=raw, value="Linkage mode")

    # Reject summary trigger
    if s_l == "rejectsummary":
        return ScanResult(kind="REJECT_SUMMARY", raw=raw, value="Reject summary")

    # Reject trigger
    if s_l == "reject~1":
        return ScanResult(kind="REJECT_TRIGGER", raw=raw, value="Reject mode")

    # Reject reason code
    if s in REJECT_REASON_MAP:
        return ScanResult(kind="REJECT_REASON", raw=raw, value=REJECT_REASON_MAP[s])
    if s_l == "sur":
        return ScanResult(kind="STARTUP_REJECT", raw=raw, value="Start Up Reject", qty=1)

    # Machine
    if s in MACHINE_MAP:
        return ScanResult(kind="MACHINE", raw=raw, value=MACHINE_MAP[s])

    # Job
    m_job_url = re.search(r"/v1/jobs/(\d+)\s*$", s_l)
    if m_job_url:
        job_id = m_job_url.group(1).lstrip("0") or "0"
        return ScanResult(kind="JOB", raw=raw, value=job_id, meta={"po_number": job_id})
    po_from_structured_job = _extract_po_from_job_qr(s)
    if po_from_structured_job is not None:
        return ScanResult(
            kind="JOB",
            raw=raw,
            value=po_from_structured_job,
            meta={"po_number": po_from_structured_job},
        )

    # Operator
    if is_operator_badge(s):
        return ScanResult(kind="OPERATOR", raw=raw, value=f"{s} - {OPERATOR_MAP[s]}")

    # Raw materials
    structured_raw = _parse_structured_raw_material(s)
    if structured_raw is not None:
        return ScanResult(
            kind="RAW_MATERIAL",
            raw=raw,
            value=structured_raw["material_name"],
            qty=structured_raw["qty"],
            meta=structured_raw,
        )

    if s_l.startswith("rawmat~") or s_l.startswith("rawmaterial~") or s_l.startswith("rm~"):
        parts = [p.strip() for p in s.split("~")]
        material = parts[1] if len(parts) > 1 and parts[1] else "Sack"
        qty = 1
        if len(parts) > 2:
            try:
                qty = max(1, int(parts[2]))
            except Exception:
                qty = 1
        return ScanResult(kind="RAW_MATERIAL", raw=raw, value=material, qty=qty)
    if s_l in ("rawmat", "rawmaterial", "rm"):
        return ScanResult(kind="RAW_MATERIAL", raw=raw, value="Sack", qty=1)

    # Butal simple trigger
    if s_l in ("butal~1", "butal", "btl~1"):
        return ScanResult(kind="BUTAL", raw=raw, value="Butal", qty=1)

    # Butal (QB first, because it contains Q)
    if "V2" in s and "QB" in s:
        qty = extract_qty_segment(s, "QB")
        if qty is not None:
            return ScanResult(kind="BUTAL", raw=raw, value="Butal", qty=qty)

    # Pack (Q)
    if "V2" in s and "Q" in s:
        # ensure not QB (already handled)
        if "QB" not in s:
            qty = extract_qty_segment(s, "Q")
            if qty is not None:
                return ScanResult(kind="PACK", raw=raw, value="Pack", qty=qty)

    return None
