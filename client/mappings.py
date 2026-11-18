# mappings.py
from __future__ import annotations
import json
import re
from copy import deepcopy
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple


MACHINE_MAP: Dict[str, str] = {
    "M00001": "IMM 301",
    "M00002": "IMM 302",
    "M00003": "IMM 303",
    "M00004": "IMM 304",
    "M00005": "IMM 305",
    "M00006": "IMM 306",
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
    "M00411": "IMM 411",
    "M00412": "IMM 412",
    "M00413": "IMM 413",
    "M00414": "IMM 414",
    "M00415": "IMM 415",
    "M00416": "IMM 416",
    "M00417": "IMM 417",
    "M00418": "IMM 418",
    "M00421": "IMM 421",
    "M00422": "IMM 422",
    "M00423": "IMM 423",
    "M00424": "IMM 424",
    "M00425": "IMM 425",
    "M00426": "IMM 426",
    "M00441": "IMM 441",
    "M00442": "IMM 442",
    "M00443": "IMM 443",
    "M00444": "IMM 444",
}

# Job display names are now sourced from the live Job API response in client.py.
JOB_MAP: Dict[str, str] = {}

REJECT_REASON_MAP: Dict[str, str] = {
    "BM01": "BURN MARK",
    "CS02": "COLOR STREAK",
    "CO03": "CONTAMINATION",
    "CR04": "CRACK/BRITTLE",
    "DI05": "DISCOLORATION",
    "EM06": "EJECTOR MARK",
    "FL07": "FLASHES",
    "F08": "FLOW MARK/ WRINKLE",
    "FM08": "FLOW MARK/ WRINKLE",
    "NO": "NO SHOT",
    "OC09": "OVER-CUT",
    "SC10": "SCRATCH",
    "SS11": "SHORT SHOT",
    "SI12": "SILICONE MARK",
    "SK13": "SILVER STREAK",
    "ST14": "STUCK",
    "VO15": "VOID",
    "WA": "WARP",
    "WM": "WATER MARK",
    "WL": "WELD LINE",
}
REJECT_REASON_CANONICAL_MAP: Dict[str, str] = {
    key: re.sub(r"\d{2}$", "", key) if key != "F08" else "FM"
    for key in REJECT_REASON_MAP
}


_COMMAND_DEFAULTS: List[Dict[str, Any]] = [
    {"id": "test_machine", "label": "Test Machine", "handler_token": "testmachine~1", "kind": "MACHINE", "value": "TEST MACHINE", "aliases": ["testmachine~1"]},
    {"id": "finish_job", "label": "Finish Job", "handler_token": "finishjob", "kind": "FINISH_JOB", "value": "Finish current job session", "aliases": ["finishjob", "finishjob~1", "jobfinish"]},
    {"id": "operator_shift", "label": "Finish Operator Shift", "handler_token": "finishshift", "kind": "OPERATOR_SHIFT_TRIGGER", "value": "Finish shift", "aliases": ["finishshift", "operatorshift", "operatorshift~1", "operator_shift~1", "shiftchange~1"]},
    {"id": "change_operator", "label": "Change Operator", "handler_token": "changeoperator", "kind": "CHANGE_OPERATOR_TRIGGER", "value": "Change operator or helper", "aliases": ["changeoperator", "changeoperator~1", "change_operator~1", "operatorchange~1", "operator_change~1"]},
    {"id": "refresh_job", "label": "Refresh Job Details", "handler_token": "refreshjob", "kind": "JOB_API_REFRESH_TRIGGER", "value": "Refresh all running job details", "aliases": ["refreshjob", "refreshjobapi~1", "refresh_job_api~1", "refreshjobs~1", "jobrefresh~1"]},
    {"id": "void", "label": "Void Mode", "handler_token": "void", "kind": "VOID_TRIGGER", "value": "Void mode", "aliases": ["void", "void~1", "voidscan~1", "voidqr~1", "voidpack~1", "void_pack~1", "packvoid~1", "voidbutal~1", "void_butal~1", "butalvoid~1", "voidreject~1", "void_reject~1", "rejectvoid~1"]},
    {"id": "counter_overwrite", "label": "Machine Counter Overwrite", "handler_token": "machinecounteroverwrite", "kind": "MACHINE_COUNTER_OVERWRITE_TRIGGER", "value": "Supervisor machine counter overwrite", "aliases": ["machinecounteroverwrite", "machinecounteroverwrite~1", "machine_counter_overwrite~1", "changemachinecounter~1", "change_machine_counter~1", "counteroverwrite~1"]},
    {"id": "supervisor_review", "label": "Supervisor Review", "handler_token": "svisorreview", "kind": "SUPERVISOR_REVIEW_TRIGGER", "value": "Open Supervisor Review", "aliases": ["svisorreview", "svisorreview~1"]},
    {"id": "pdrstart", "label": "Start PDR", "handler_token": "pdrstart", "kind": "PRODUCTION_DAILY_REPORT_TRIGGER", "value": "Production daily report mode", "aliases": ["pdrstart"]},
    {"id": "job_linkage", "label": "Job Linkage", "handler_token": "joblinkage", "kind": "JOB_LINKAGE_TRIGGER", "value": "Linkage mode", "aliases": ["joblinkage", "joblinkage~1"]},
    {"id": "change_work_order", "label": "Change Work Order", "handler_token": "changeworkorder", "kind": "CHANGE_WORK_ORDER_TRIGGER", "value": "Change work order mode", "aliases": ["changeworkorder", "changeworkorder~1", "change_work_order~1", "workorderchange~1", "changejob~1"]},
    {"id": "virtual_pack", "label": "Virtual Pack QR", "handler_token": "virtualpackqr", "kind": "VIRTUAL_PACK_QR_TRIGGER", "value": "Show virtual pack QR", "aliases": ["virtualpackqr", "virtualqr~1", "virtualpackqr~1", "virtual_pack_qr~1", "autopackqr~1", "auto_pack_qr~1", "autoqr~1"]},
    {"id": "print_qr", "label": "Print QR", "handler_token": "printqr", "kind": "PRINT_NEXT_PACK_QR_TRIGGER", "value": "Print next PACK QR", "aliases": ["printqr", "printqr~1", "print_qr~1", "printpackqr~1", "print_pack_qr~1"]},
    {"id": "change_color_mold", "label": "Change Color / Mold", "handler_token": "changecolormold", "kind": "COLOR_CHANGE_TRIGGER", "value": "Change color or mold", "aliases": ["changecolormold", "changecolormold~1", "change_color_mold", "change_color_mold~1"]},
    {"id": "reject", "label": "Reject Mode", "handler_token": "reject", "kind": "REJECT_TRIGGER", "value": "Reject mode", "aliases": ["reject", "reject~1"]},
    {"id": "reject_summary", "label": "Reject Summary", "handler_token": "rejectsummary", "kind": "REJECT_SUMMARY", "value": "Reject summary", "aliases": ["rejectsummary"]},
    {"id": "no_shot", "label": "No Shot", "handler_token": "NO", "kind": "REJECT_REASON", "value": "NO", "aliases": ["NO"]},
    {"id": "startup_reject", "label": "Start-up Reject", "handler_token": "startupreject", "kind": "STARTUP_REJECT", "value": "Start Up Reject", "qty": 1, "aliases": ["sur", "startupreject"]},
    {"id": "butal", "label": "Butal", "handler_token": "butal", "kind": "BUTAL", "value": "Butal", "qty": 1, "aliases": ["butal", "butal~1", "btl~1"]},
    {"id": "show_raw_materials", "label": "Raw Material Summary", "handler_token": "showrawmats", "kind": "RAW_COMMAND", "aliases": ["showrawmats", "rawmatsummary~1"]},
    {"id": "production_history", "label": "Production History", "handler_token": "prodhistory", "kind": "RAW_COMMAND", "aliases": ["prodhistory", "prodhistory~1"]},
    {"id": "crew_list", "label": "Crew List", "handler_token": "crewlist", "kind": "RAW_COMMAND", "aliases": ["crewlist", "crewlist~1"]},
    {"id": "crew_add_remove", "label": "Add / Remove Helper", "handler_token": "crewaddremove", "kind": "RAW_COMMAND", "aliases": ["crewaddremove"]},
    {"id": "reliever", "label": "Reliever", "handler_token": "relieverqr", "kind": "RAW_COMMAND", "aliases": ["relieverqr", "reliever~1", "relief~1", "relieveradd~1"]},
    {"id": "cancel", "label": "Cancel", "handler_token": "cancel", "kind": "RAW_COMMAND", "aliases": ["cancel", "cancel~1"]},
    {"id": "clear", "label": "Clear Input", "handler_token": "clear", "kind": "RAW_COMMAND", "aliases": ["clear"]},
    {"id": "backspace", "label": "Backspace", "handler_token": "backspace", "kind": "RAW_COMMAND", "aliases": ["backspace"]},
    {"id": "confirm", "label": "Confirm", "handler_token": "confirm", "kind": "RAW_COMMAND", "aliases": ["confirm"]},
    {"id": "next", "label": "Next Page", "handler_token": "next", "kind": "RAW_COMMAND", "aliases": ["next"]},
    {"id": "previous", "label": "Previous Page", "handler_token": "prev", "kind": "RAW_COMMAND", "aliases": ["prev", "previous", "preview"]},
]

_REJECT_CONTEXT_DEFAULTS = [
    (1, "BM", "BURN MARK", ["BM", "BM01"]), (2, "CS", "COLOR STREAK", ["CS", "CS02"]),
    (3, "CO", "CONTAMINATION", ["CO", "CO03"]), (4, "CR", "CRACK/BRITTLE", ["CR", "CR04"]),
    (5, "DI", "DISCOLORATION", ["DI", "DI05"]), (6, "EM", "EJECTOR MARK", ["EM", "EM06"]),
    (7, "FL", "FLASHES", ["FL", "FL07"]), (8, "FM", "FLOW MARK/ WRINKLE", ["FM", "FM08", "F08"]),
    (9, "NO", "NO SHOT", ["NO"]), (10, "OC", "OVER-CUT", ["OC", "OC09"]),
    (11, "SC", "SCRATCH", ["SC", "SC10"]), (12, "SS", "SHORT SHOT", ["SS", "SS11"]),
    (13, "SI", "SILICONE MARK", ["SI", "SI12"]), (14, "SK", "SILVER STREAK", ["SK", "SK13"]),
    (15, "SM", "SINK MARK", ["SM"]), (16, "ST", "STUCK", ["ST", "ST14"]),
    (17, "VO", "VOID", ["VO", "VO15"]), (18, "WA", "WARP", ["WA"]),
    (19, "WM", "WATER MARK", ["WM"]), (20, "WL", "WELD LINE", ["WL"]),
    (21, "SUR", "START UP REJECT", ["SUR", "STARTUPREJECT"]),
]

_PDR_CONTEXT_DEFAULTS = [
    (1, "01", "Machine Issue/Breakdown/Repair"), (2, "02", "Machine Adjustment - Parameters"),
    (3, "03", "Material Issue/Delay/Drying"), (4, "04", "Mold Issue/Repair/Cleaning"),
    (5, "05", "No Manpower/Operator"), (6, "06", "Material Color Change"),
    (7, "07", "Mold Change"), (8, "08", "Preventive Maintenance"),
    (9, "09", "No production schedule"), (10, "10", "Start-up/Shutdown (1st&Last Day)"),
    (11, "11", "Shift Meeting/Shift Turn-over"), (12, "12", "Mold / Color Testing"),
    (13, "13", "Power interruption"), (14, "14", "Robot Set-up/Adjustment"), (15, "15", "Others"),
]

DEFAULT_QR_MAPPING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "commands": [{**row, "enabled": True} for row in _COMMAND_DEFAULTS],
    "reject_reasons": [
        {"number": number, "code": code, "label": label, "aliases": aliases, "enabled": True}
        for number, code, label, aliases in _REJECT_CONTEXT_DEFAULTS
    ],
    "pdr_reasons": [
        {"number": number, "code": code, "label": label, "enabled": True}
        for number, code, label in _PDR_CONTEXT_DEFAULTS
    ],
}

_DEFAULT_MANAGED_ALIASES = {
    str(alias).strip().lower()
    for row in _COMMAND_DEFAULTS
    for alias in row.get("aliases", [])
    if str(alias).strip()
}
_RETIRED_COMMAND_ALIASES = {
    "joblinkageremove~1", "job_linkage_remove~1", "removejoblinkage~1", "remove_job_linkage~1", "unlinkjob~1",
    "multicolorprepack~1", "multi_color_prepack~1", "prepacklinkage~1", "prepack_linkage~1",
    "productiondailyreport~0", "pdr_cancel", "pdrcancel",
    "productiondailyreport~2", "pdr_done", "pdrdone",
    "butalpack~1", "butalcomplete~1", "butalcompletion~1",
}
_ACTIVE_QR_MAPPING_CONFIG: Dict[str, Any] = deepcopy(DEFAULT_QR_MAPPING_CONFIG)
_ACTIVE_COMMAND_ALIASES: Dict[str, Dict[str, Any]] = {}
_ACTIVE_HANDLER_TOKENS: set[str] = set()


def validate_qr_mapping_config(config: Any) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(config, dict):
        return False, ["Mapping configuration must be a JSON object."]
    commands = config.get("commands")
    if not isinstance(commands, list):
        errors.append("commands must be a list.")
    else:
        seen_aliases: Dict[str, str] = {}
        for index, row in enumerate(commands):
            if not isinstance(row, dict):
                errors.append(f"commands[{index}] must be an object.")
                continue
            command_id = str(row.get("id") or "").strip()
            aliases = row.get("aliases")
            if not command_id:
                errors.append(f"commands[{index}].id is required.")
            if not isinstance(aliases, list) or not any(str(x or "").strip() for x in aliases):
                errors.append(f"commands[{index}].aliases must contain at least one QR value.")
                continue
            for alias in aliases:
                key = str(alias or "").strip().lower()
                if not key:
                    continue
                if key in seen_aliases and seen_aliases[key] != command_id:
                    errors.append(f"Duplicate command alias '{key}' is used by {seen_aliases[key]} and {command_id}.")
                seen_aliases[key] = command_id
    for section in ("reject_reasons", "pdr_reasons"):
        rows = config.get(section)
        if not isinstance(rows, list):
            errors.append(f"{section} must be a list.")
            continue
        seen_numbers = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"{section}[{index}] must be an object.")
                continue
            try:
                number = int(row.get("number"))
            except Exception:
                number = -1
            if number < 0 or number > 22:
                errors.append(f"{section}[{index}].number must be from 0 to 22.")
            if number in seen_numbers:
                errors.append(f"{section} has duplicate num_{number}.")
            seen_numbers.add(number)
            if not str(row.get("code") or "").strip() or not str(row.get("label") or "").strip():
                errors.append(f"{section}[{index}] requires code and label.")
    return not errors, errors


def apply_qr_mapping_config(config: Any) -> Tuple[bool, List[str]]:
    global _ACTIVE_QR_MAPPING_CONFIG, _ACTIVE_COMMAND_ALIASES, _ACTIVE_HANDLER_TOKENS
    ok, errors = validate_qr_mapping_config(config)
    if not ok:
        return False, errors
    normalized = deepcopy(config)
    _ACTIVE_QR_MAPPING_CONFIG = normalized
    alias_map: Dict[str, Dict[str, Any]] = {}
    defaults_by_id = {str(row.get("id")): row for row in _COMMAND_DEFAULTS}
    for row in normalized.get("commands") or []:
        if not isinstance(row, dict) or not bool(row.get("enabled", True)):
            continue
        default = defaults_by_id.get(str(row.get("id") or ""), {})
        runtime_row = {**default, **row}
        runtime_row["handler_token"] = str(default.get("handler_token") or row.get("handler_token") or "").strip().lower()
        runtime_row["kind"] = str(default.get("kind") or row.get("kind") or "RAW_COMMAND").strip().upper()
        for alias in row.get("aliases") or []:
            key = str(alias or "").strip().lower()
            if key:
                alias_map[key] = runtime_row
    _ACTIVE_COMMAND_ALIASES = alias_map
    _ACTIVE_HANDLER_TOKENS = {
        str(row.get("handler_token") or "").strip().lower()
        for row in alias_map.values()
        if str(row.get("handler_token") or "").strip()
    }
    REJECT_REASON_MAP.clear()
    REJECT_REASON_CANONICAL_MAP.clear()
    for row in normalized.get("reject_reasons") or []:
        if not isinstance(row, dict) or not bool(row.get("enabled", True)):
            continue
        label = str(row.get("label") or "").strip()
        code = str(row.get("code") or "").strip().upper()
        for alias in [code, *(row.get("aliases") or [])]:
            key = str(alias or "").strip().upper()
            if key:
                REJECT_REASON_MAP[key] = label
                REJECT_REASON_CANONICAL_MAP[key] = code
    return True, []


def active_qr_mapping_config() -> Dict[str, Any]:
    return deepcopy(_ACTIVE_QR_MAPPING_CONFIG)


def qr_mapping_config_to_text(config: Any) -> str:
    """Render the mapping registry as a compact one-QR-per-line text file."""
    source = config if isinstance(config, dict) else DEFAULT_QR_MAPPING_CONFIG
    lines = [
        "# QR MAPPINGS - edit only the payload after =",
        "# One row equals one QR. Lines beginning with # are ignored.",
        "",
        "[COMMANDS]",
    ]
    for row in source.get("commands") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or row.get("id") or "Unnamed command").strip()
        aliases = [str(value or "").strip() for value in (row.get("aliases") or [])]
        payload = next((value for value in aliases if value), "")
        lines.append(f"{label} = {payload}")
    lines.extend(["", "[REJECT]"])
    for row in source.get("reject_reasons") or []:
        if not isinstance(row, dict):
            continue
        number = int(row.get("number") or 0)
        label = str(row.get("label") or row.get("code") or "Reject").strip()
        aliases = [str(value or "").strip() for value in (row.get("aliases") or [])]
        payload = next((value for value in aliases if value), str(row.get("code") or "").strip())
        lines.append(f"num_{number} | {label} = {payload}")
    lines.extend(["", "[PDR]"])
    for row in source.get("pdr_reasons") or []:
        if not isinstance(row, dict):
            continue
        number = int(row.get("number") or 0)
        label = str(row.get("label") or row.get("code") or "PDR reason").strip()
        aliases = [str(value or "").strip() for value in (row.get("aliases") or [])]
        payload = next((value for value in aliases if value), str(row.get("code") or "").strip())
        lines.append(f"num_{number} | {label} = {payload}")
    return "\n".join(lines).rstrip() + "\n"


def qr_mapping_config_from_text(text: Any, base_config: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Apply compact mapping text to a structured registry without losing metadata."""
    if not isinstance(base_config, dict):
        return None, ["No base QR mapping configuration is available."]
    result = deepcopy(base_config)
    section = ""
    values: Dict[str, List[Tuple[int, str, str]]] = {"COMMANDS": [], "REJECT": [], "PDR": []}
    errors: List[str] = []
    for line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        section_match = re.fullmatch(r"\[\s*(COMMANDS|REJECT|PDR)\s*\]", line, flags=re.IGNORECASE)
        if section_match:
            section = section_match.group(1).upper()
            continue
        if not section:
            errors.append(f"Line {line_number}: add a [COMMANDS], [REJECT], or [PDR] heading first.")
            continue
        if "=" not in line:
            errors.append(f"Line {line_number}: expected QR Name = QR Payload.")
            continue
        name, payload = (part.strip() for part in line.split("=", 1))
        if not name or not payload:
            errors.append(f"Line {line_number}: both QR name and payload are required.")
            continue
        values[section].append((line_number, name, payload))

    command_rows = [row for row in (result.get("commands") or []) if isinstance(row, dict)]
    command_lookup: Dict[str, Dict[str, Any]] = {}
    for row in command_rows:
        for key in (row.get("label"), row.get("id")):
            normalized = re.sub(r"\s+", " ", str(key or "").strip()).casefold()
            if normalized:
                command_lookup[normalized] = row
    seen_commands = set()
    for line_number, name, payload in values["COMMANDS"]:
        key = re.sub(r"\s+", " ", name).casefold()
        row = command_lookup.get(key)
        if row is None:
            errors.append(f"Line {line_number}: unknown command name '{name}'.")
            continue
        command_id = str(row.get("id") or key)
        if command_id in seen_commands:
            errors.append(f"Line {line_number}: command '{name}' is listed more than once.")
            continue
        seen_commands.add(command_id)
        row["aliases"] = [payload]

    def apply_numbered(section_name: str, config_key: str) -> None:
        rows = {
            int(row.get("number")): row
            for row in (result.get(config_key) or [])
            if isinstance(row, dict) and str(row.get("number", "")).isdigit()
        }
        seen_numbers = set()
        for line_number, name, payload in values[section_name]:
            match = re.match(r"num_(\d{1,2})(?:\s*\||\s|$)", name, flags=re.IGNORECASE)
            if not match:
                errors.append(f"Line {line_number}: '{name}' must start with num_0 through num_22.")
                continue
            number = int(match.group(1))
            row = rows.get(number)
            if row is None:
                errors.append(f"Line {line_number}: num_{number} is not configured in [{section_name}].")
                continue
            if number in seen_numbers:
                errors.append(f"Line {line_number}: num_{number} is listed more than once in [{section_name}].")
                continue
            seen_numbers.add(number)
            row["aliases"] = [payload]

    apply_numbered("REJECT", "reject_reasons")
    apply_numbered("PDR", "pdr_reasons")
    if errors:
        return None, errors
    ok, validation_errors = validate_qr_mapping_config(result)
    return (result, []) if ok else (None, validation_errors)


def resolve_mapped_scan(raw: str) -> Optional[str]:
    value = str(raw or "").strip()
    key = value.lower()
    row = _ACTIVE_COMMAND_ALIASES.get(key)
    if isinstance(row, dict):
        return str(row.get("handler_token") or value).strip()
    if key in _DEFAULT_MANAGED_ALIASES or key in _RETIRED_COMMAND_ALIASES:
        return None
    return value


def numeric_context_mapping(context: str) -> Dict[int, Dict[str, Any]]:
    section = "reject_reasons" if str(context or "").strip().lower() == "reject" else "pdr_reasons"
    return {
        int(row.get("number")): dict(row)
        for row in (_ACTIVE_QR_MAPPING_CONFIG.get(section) or [])
        if isinstance(row, dict) and bool(row.get("enabled", True)) and str(row.get("number", "")).isdigit()
    }


apply_qr_mapping_config(DEFAULT_QR_MAPPING_CONFIG)

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


def extract_qty_segment(payload: str, marker: str) -> Optional[float]:
    """
    Extract the 11-character numeric quantity after marker ('Q' or 'QB').
    Example marker='Q':  ...Q00000000006...
    Example marker='QB': ...QB00000000006...
    Decimal quantities are valid for product-part labels.
    """
    idx = payload.find(marker)
    if idx < 0:
        return None

    start = idx + len(marker)
    quantity_text = payload[start:start + 11]
    if len(quantity_text) != 11 or re.fullmatch(r"\d+(?:\.\d+)?", quantity_text) is None:
        return None

    return float(quantity_text)


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
    q_match = re.search(r"QRM(\d+(?:\.\d+)?)I", s)
    tail_match = re.search(r"I(\d{11})T(\d{11})L(\d{14})-(\d+)\s*$", s)
    if not p_match or not q_match or not tail_match:
        return None

    i_digits, t_digits, lot_digits, po_digits = tail_match.groups()
    material_code_digits = p_match.group(1).lstrip("0") or "0"
    qty = float(q_match.group(1))
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
    qty: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None


def parse_scan(raw: str) -> Optional[ScanResult]:
    raw_value = str(raw or "").strip()
    # ClientUI resolves configurable aliases before parsing. Keep active
    # internal handler tokens intact on that second pass.
    mapped = raw_value if raw_value.lower() in _ACTIVE_HANDLER_TOKENS else resolve_mapped_scan(raw_value)
    if mapped is None:
        return None
    s = mapped.strip()
    s_l = s.lower()

    # Isolated server/client sandbox controls. These never map to a physical
    # IMM machine or production work order.
    if s_l == "testmachine~1":
        return ScanResult(
            kind="MACHINE",
            raw=raw,
            value="TEST MACHINE",
            meta={"machine_code": "TEST-MACHINE", "test_machine": True},
        )

    # Operator handoff trigger
    if s_l in ("finishshift", "operatorshift", "operatorshift~1", "operator_shift~1", "shiftchange~1"):
        return ScanResult(kind="OPERATOR_SHIFT_TRIGGER", raw=raw, value="Finish shift")
    if s_l in (
        "changeoperator", "changeoperator~1",
        "change_operator~1",
        "operatorchange~1",
        "operator_change~1",
    ):
        return ScanResult(kind="CHANGE_OPERATOR_TRIGGER", raw=raw, value="Change operator or helper")
    if s_l in (
        "refreshjob", "refreshjobapi~1",
        "refresh_job_api~1",
        "refreshjobs~1",
        "jobrefresh~1",
    ):
        return ScanResult(
            kind="JOB_API_REFRESH_TRIGGER",
            raw=raw,
            value="Refresh all running job details",
        )
    if s_l in ("void", "void~1", "voidscan~1", "voidqr~1", "voidpack~1", "void_pack~1", "packvoid~1", "voidbutal~1", "void_butal~1", "butalvoid~1", "voidreject~1", "void_reject~1", "rejectvoid~1"):
        return ScanResult(kind="VOID_TRIGGER", raw=raw, value="Void mode")
    if s_l in ("butalpack~1", "butalcomplete~1", "butalcompletion~1"):
        return ScanResult(kind="BUTAL_COMPLETION_TRIGGER", raw=raw, value="Butal pack completion mode")
    if s_l in (
        "machinecounteroverwrite", "machinecounteroverwrite~1",
        "machine_counter_overwrite~1",
        "changemachinecounter~1",
        "change_machine_counter~1",
        "counteroverwrite~1",
    ):
        return ScanResult(
            kind="MACHINE_COUNTER_OVERWRITE_TRIGGER",
            raw=raw,
            value="Supervisor machine counter overwrite",
        )
    if s_l in ("svisorreview", "svisorreview~1"):
        return ScanResult(
            kind="SUPERVISOR_REVIEW_TRIGGER",
            raw=raw,
            value="Open Supervisor Review",
        )

    # Production daily report trigger
    if s_l in ("productiondailyreport~1", "pdr_start", "pdrstart"):
        return ScanResult(kind="PRODUCTION_DAILY_REPORT_TRIGGER", raw=raw, value="Production daily report mode")
    if s_l in ("productiondailyreport~0", "pdr_cancel", "pdrcancel"):
        return ScanResult(kind="PRODUCTION_DAILY_REPORT_CANCEL", raw=raw, value="Production daily report cancel")
    if s_l in ("productiondailyreport~2", "pdr_done", "pdrdone"):
        return ScanResult(kind="PRODUCTION_DAILY_REPORT_RESOLVE", raw=raw, value="Production daily report resolve")
    if s.isdigit() and 1 <= int(s) <= 15:
        return ScanResult(kind="PRODUCTION_DAILY_REPORT_REASON", raw=raw, value=f"{int(s):02d}")
    if s_l in ("finishjob", "finishjob~1", "jobfinish"):
        return ScanResult(kind="FINISH_JOB", raw=raw, value="Finish current job session")
    if s_l in ("joblinkage", "joblinkage~1"):
        return ScanResult(kind="JOB_LINKAGE_TRIGGER", raw=raw, value="Linkage mode")
    if s_l in (
        "joblinkageremove~1",
        "job_linkage_remove~1",
        "removejoblinkage~1",
        "remove_job_linkage~1",
        "unlinkjob~1",
    ):
        return ScanResult(kind="JOB_LINKAGE_REMOVE_TRIGGER", raw=raw, value="Remove linked job mode")
    if s_l in (
        "changeworkorder", "changeworkorder~1",
        "change_work_order~1",
        "workorderchange~1",
        "changejob~1",
    ):
        return ScanResult(kind="CHANGE_WORK_ORDER_TRIGGER", raw=raw, value="Change work order mode")
    if s_l in ("multicolorprepack~1", "multi_color_prepack~1", "prepacklinkage~1", "prepack_linkage~1"):
        return ScanResult(kind="PREPACK_LINKAGE_TRIGGER", raw=raw, value="Multi-color prepack mode")
    if s_l in ("virtualpackqr", "virtualqr~1", "virtualpackqr~1", "virtual_pack_qr~1", "autopackqr~1", "auto_pack_qr~1", "autoqr~1"):
        return ScanResult(kind="VIRTUAL_PACK_QR_TRIGGER", raw=raw, value="Show virtual pack QR")
    if s_l in ("printqr", "printqr~1", "print_qr~1", "printpackqr~1", "print_pack_qr~1"):
        return ScanResult(kind="PRINT_NEXT_PACK_QR_TRIGGER", raw=raw, value="Print next PACK QR")
    m_prepack = re.fullmatch(r"(?:prepack|prepackpack|genericprepack|generic_prepack)(?:~(\d+))?", s_l)
    if m_prepack:
        qty = int(m_prepack.group(1) or "0")
        return ScanResult(kind="PREPACK_GENERIC_PACK", raw=raw, value="Generic prepack scan", qty=qty)
    if s_l in ("changecolormold", "changecolormold~1", "change_color_mold", "change_color_mold~1"):
        return ScanResult(kind="COLOR_CHANGE_TRIGGER", raw=raw, value="Change color or mold")

    # Reject summary trigger
    if s_l == "rejectsummary":
        return ScanResult(kind="REJECT_SUMMARY", raw=raw, value="Reject summary")

    # Reject trigger
    if s_l in ("reject", "reject~1"):
        return ScanResult(kind="REJECT_TRIGGER", raw=raw, value="Reject mode")

    # Reject reason code
    if s_l in ("sur", "startupreject"):
        return ScanResult(kind="STARTUP_REJECT", raw=raw, value="Start Up Reject", qty=1)
    reject_key = s.upper()
    if reject_key in REJECT_REASON_MAP:
        return ScanResult(
            kind="REJECT_REASON",
            raw=raw,
            value=REJECT_REASON_CANONICAL_MAP.get(reject_key, reject_key),
            meta={"reason_text": REJECT_REASON_MAP[reject_key]},
        )

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
        qty = 1.0
        if len(parts) > 2:
            try:
                qty = max(0.0, float(parts[2]))
                if qty <= 0:
                    qty = 1.0
            except Exception:
                qty = 1.0
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
