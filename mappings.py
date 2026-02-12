# mappings.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple


MACHINE_MAP: Dict[str, str] = {
    "M00001": "Machine 01",
    "M00002": "Machine 02",
    "M00003": "Machine 03",
}

JOB_MAP: Dict[str, str] = {
    "101245": "J024-0305",
    "250424": "JO22-0100",
    "56675":  "J023-1122",
}

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


@dataclass
class ScanResult:
    kind: str
    raw: str
    value: str
    qty: Optional[int] = None


def parse_scan(raw: str) -> Optional[ScanResult]:
    s = raw.strip()

    # Reject trigger
    if s.lower() == "reject~1":
        return ScanResult(kind="REJECT_TRIGGER", raw=raw, value="Reject mode")

    # Reject reason code
    if s in REJECT_REASON_MAP:
        return ScanResult(kind="REJECT_REASON", raw=raw, value=REJECT_REASON_MAP[s])

    # Machine
    if s in MACHINE_MAP:
        return ScanResult(kind="MACHINE", raw=raw, value=MACHINE_MAP[s])

    # Job
    if s in JOB_MAP:
        return ScanResult(kind="JOB", raw=raw, value=JOB_MAP[s])

    # Operator
    if is_operator_badge(s):
        return ScanResult(kind="OPERATOR", raw=raw, value=f"{s} - {OPERATOR_MAP[s]}")

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
