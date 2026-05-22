#!/usr/bin/env python3
"""
ORBYT Complex Test Generator Matrix
Generates 7 matrices from requirement CSVs (input/) and release testing CSVs
(release_notes/release_notes_csv/).
"""

from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

CHP_PATTERN = re.compile(r"CHP-\d+", re.IGNORECASE)
REQ_BACKLOG_KEYWORDS = ("backlog", "feature", "story")
SKIP_REQ_FILES = ("running notes", "action items", "view ")

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# (category, subcategory, keywords) — first match wins after API/UI checks
SITEMAP_RULES: list[tuple[str, str | None, list[str]]] = [
    ("View Settings", None, ["view settings", "view setting", "column config", "user preference", "saved view"]),
    ("Notification", None, ["notification", "push alert", "in-app alert", "toast message"]),
    ("Campaign", None, ["campaign", "marketing outreach"]),
    ("Tasks", None, ["task list", "task management", "create a task", "assignee task", "my tasks"]),
    ("Contacts", None, ["contact list", "contact-lead", "contact tab", "contacts component", " lead tab"]),
    ("Dashboards", None, ["dashboard", "kpi widget", "summary dashboard", "home dashboard"]),
    ("Accounts", "Visits", ["visit log", "field visit", "account visit"]),
    ("Accounts", "Search Accounts", ["search account", "account search", "find account"]),
    ("Accounts", "Open Accounts", ["open account", "open accounts"]),
    ("Accounts", "My Accounts", ["my account", "my accounts"]),
    ("Accounts", None, ["account", "billing address", "company profile", "account list", "account detail"]),
    ("Parts", "Part Health", ["part health", "health score"]),
    ("Parts", "Account Parts", ["account part", "account parts"]),
    ("Parts", "By Category", ["by category", "part category"]),
    ("Parts", "By MPN", ["by mpn", "mpn search", "search mpn"]),
    ("Parts", None, ["part", "mpn", "alternative part", "part detail", "component part"]),
    ("Projects", "Excess", ["excess", "upload excess", "excess list"]),
    ("Projects", "Projects", ["project list", "project detail", "projects tab"]),
    ("Sales", "Invoices", ["sales invoice", "invoice line", "invoice tab", "export pdf", "invoice lines"]),
    ("Sales", "Opportunities", ["opportunity", "sales opportunity"]),
    ("Sales", "Sales Orders", ["sales order", " sales order", "so sync", "so line", "order shipment"]),
    ("Sales", "Quotes", ["quote", "active quote", "standalone quote"]),
    ("Sales", "RFQs", ["rfq", "request for quote", "multiline rfq", "rfq line"]),
    ("Sales", None, ["sales pipeline", "sales flow"]),
    ("Purchasing", "Invoices", ["purchase invoice", "supplier invoice", "payable invoice"]),
    ("Purchasing", "Purchase Orders", ["purchase order", " purchase order", " po ", "po line"]),
    ("Purchasing", "Sourcing Requests", ["sourcing request", "purchase request", "sourcing plan"]),
    ("Purchasing", "Offers", ["market offer", "sourcing offer", " offer ", "offers management"]),
    ("Purchasing", None, ["purchasing", "buyer assign", "procurement"]),
    ("Warehouse", "Stock", ["warehouse stock", "stock list", "inventory stock", "export stock"]),
    ("Warehouse", "Shipments", ["shipment", "shipments workflow"]),
    ("Warehouse", "Sales Orders", ["warehouse sales order", "wms sales order"]),
    ("Warehouse", "Receiving", ["receiving", "goods receipt", "receive stock"]),
    ("Warehouse", None, ["warehouse", "wms"]),
    ("Sourcing", None, ["sourcing", "supplier", "handshake", "sourcing plan"]),
]

API_KEYWORDS = [
    "backend", "api", "endpoint", "microservice", "mongodb", "opensearch",
    "chip1-transaction", "chip1-part", "fn-connect", "graphql", "rest api",
    "service layer", "post /", "patch /", "get /", "kafka", "migration",
    "indexing", "webhook", "api-hub", "api hub",
]

UI_KEYWORDS = [
    "figma", "ui change", "ui only", "filter design", "layout", "button",
    "dropdown", "modal", "tooltip", "css", "styling", "render 2.0",
    "webui", "frontend", "screen design", "top filter bar", "info pane",
    "list view", "tab ", "tabs ", "3 dots", "fab option",
]

ARTIFACT_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Accounts", ["account", "crm"]),
    ("Contacts", ["contact", "lead"]),
    ("Parts", ["part", "mpn"]),
    ("Sales", ["sales", "quote", "rfq", "invoice", "transaction"]),
    ("Purchasing", ["purchase", "po", "sourcing", "offer", "transaction"]),
    ("Warehouse", ["warehouse", "stock", "shipment", "wms", "transaction"]),
    ("API", ["connect", "api", "backend", "service", "transaction"]),
    ("UI", ["webui", "web ui", "frontend", "crm webui"]),
]


def _req_text_blob(row: pd.Series | dict) -> str:
    if isinstance(row, dict):
        row = pd.Series(row)
    parts = [
        row.get("Task Name", ""),
        str(row.get("Task Content", ""))[:2000],
        row.get("tags", ""),
        row.get("Component (drop down)", ""),
        row.get("Feature (drop down)", ""),
        row.get("Hierarchy 1 (drop down)", ""),
        row.get("Capability (drop down)", ""),
    ]
    return " ".join(str(p) for p in parts).lower()


def classify_sitemap_category(row: pd.Series | dict) -> tuple[str, str]:
    """Return (Site_Category, Site_Subcategory) from Chip1 sitemap + API/UI rules."""
    blob = _req_text_blob(row)
    tags = str(row.get("tags", "") if isinstance(row, dict) else row.get("tags", "")).lower()

    name = str(row.get("Task Name", "") if isinstance(row, dict) else row.get("Task Name", "")).lower()
    api_score = sum(1 for k in API_KEYWORDS if k in blob) + (2 if "backend" in tags or "api" in tags else 0)
    ui_score = sum(1 for k in UI_KEYWORDS if k in blob) + (2 if "ui" in tags else 0)
    has_backend_tag = "backend" in tags or "api" in tags
    name_is_api = " api" in name or name.endswith(" api") or "api " in name or "endpoint" in name

    if name_is_api or (has_backend_tag and api_score >= 2) or (api_score >= 3 and api_score > ui_score):
        return "API", ""
    if ui_score >= 2 and not has_backend_tag and ui_score > api_score:
        return "UI", ""
    if "ui" in tags and not has_backend_tag and api_score <= 1:
        return "UI", ""

    for category, subcategory, keywords in SITEMAP_RULES:
        if any(kw in blob for kw in keywords):
            return category, subcategory or ""

    return "General", ""


def get_full_sitemap_taxonomy() -> list[tuple[str, str]]:
    """Complete Chip1 sitemap taxonomy (category, subcategory)."""
    entries: list[tuple[str, str]] = [
        ("Dashboards", ""),
        ("Accounts", "My Accounts"),
        ("Accounts", "Open Accounts"),
        ("Accounts", "Search Accounts"),
        ("Accounts", "Visits"),
        ("Accounts", ""),
        ("Parts", "By MPN"),
        ("Parts", "By Category"),
        ("Parts", "Account Parts"),
        ("Parts", "Part Health"),
        ("Parts", ""),
        ("Projects", "Projects"),
        ("Projects", "Excess"),
        ("Sales", "RFQs"),
        ("Sales", "Quotes"),
        ("Sales", "Sales Orders"),
        ("Sales", "Opportunities"),
        ("Sales", "Invoices"),
        ("Purchasing", "Offers"),
        ("Purchasing", "Sourcing Requests"),
        ("Purchasing", "Purchase Orders"),
        ("Purchasing", "Invoices"),
        ("Warehouse", "Receiving"),
        ("Warehouse", "Sales Orders"),
        ("Warehouse", "Shipments"),
        ("Warehouse", "Stock"),
        ("Warehouse", ""),
        ("Sourcing", ""),
        ("Contacts", ""),
        ("Tasks", ""),
        ("Campaign", ""),
        ("Notification", ""),
        ("View Settings", ""),
        ("API", ""),
        ("UI", ""),
        ("General", ""),
    ]
    return entries


def _classify_deploy_text(category: str, description: str) -> tuple[str, str]:
    return classify_sitemap_category(
        {"Task Name": description, "Task Content": category, "tags": "", "Component (drop down)": category}
    )


def _is_verified_passed(status: str, description: str, category: str = "") -> bool:
    blob = f"{status} {description} {category}".lower()
    if any(
        neg in blob
        for neg in (
            "not verified",
            "unverified",
            "failed",
            "failure",
            "broken",
            "error on",
            "500 error",
            "open issues on",
        )
    ):
        if "verified" not in blob and " passed" not in blob:
            return False
    if any(
        p in blob
        for p in (
            "verified",
            "passed",
            "pass on",
            "sanity test",
            "smoke test",
            "what's tested",
            "whats tested",
            "qe status",
            "prod yes",
            "stage yes",
            " yes yes",
        )
    ):
        return True
    if re.search(r"\byes\b", blob) and any(w in blob for w in ("stage", "prod", "sanity", "smoke")):
        return True
    st = status.lower().strip()
    return st in ("verified", "verified.", "passed", "pass", "good")


def _is_bug_issue(status: str, description: str, category: str = "") -> bool:
    blob = f"{category} {description} {status}".lower()
    return any(
        k in blob
        for k in (
            "bug",
            "bugs in build",
            "bugs in production",
            "issue",
            "issues on stage",
            "issues on prod",
            "defect",
            "broken",
            " fail",
            "failed",
            "npe",
            "oom",
            "gateway timeout",
            "500 error",
            "regression",
            "hotfix",
            "raised one issue",
            "open issues",
            "error",
            "fixes in build",
        )
    )


def _parse_release_date(value: str, filename: str = "") -> datetime | None:
    value = str(value).strip()
    if value:
        for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.split()[0], fmt)
            except (ValueError, IndexError):
                continue
    m = re.search(r"(\d{1,2})[-\s]([A-Za-z]+)[-\s]?(\d{2,4})?", filename)
    if m:
        day = int(m.group(1))
        mon = MONTH_MAP.get(m.group(2).lower()[:4], MONTH_MAP.get(m.group(2).lower()[:3], 0))
        yr = m.group(3)
        year = int(yr) + 2000 if yr and len(yr) == 2 else (int(yr) if yr else 2026)
        if mon:
            try:
                return datetime(year, mon, day)
            except ValueError:
                pass
    return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _read_csv_safe(path: Path) -> pd.DataFrame | None:
    try:
        return _normalize_columns(pd.read_csv(path, dtype=str, keep_default_na=False))
    except Exception:
        return None


def _is_requirement_backlog(path: Path) -> bool:
    name = path.name.lower()
    if any(skip in name for skip in SKIP_REQ_FILES):
        return False
    return any(k in name for k in REQ_BACKLOG_KEYWORDS)


def _release_text_path_for_csv(csv_path: Path) -> Path:
    return csv_path.parent.parent / "release_notes_text" / f"{csv_path.stem}.txt"


def _extract_release_status_from_text(csv_path: Path) -> str:
    text_path = _release_text_path_for_csv(csv_path)
    if not text_path.exists():
        return ""
    try:
        content = text_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    match = re.search(r"(?im)^\s*Status\s*:\s*(.+?)\s*$", content)
    return match.group(1).strip() if match else ""


def _artifact_categories(artifact_name: str, version: str = "") -> list[str]:
    blob = f"{artifact_name} {version}".lower()
    if not artifact_name.strip() or not version.strip():
        return []
    categories = [
        category
        for category, keywords in ARTIFACT_CATEGORY_RULES
        if any(keyword in blob for keyword in keywords)
    ]
    return categories or ["General"]


def _feature_label_from_item_description(category: str, description: str) -> str:
    text = re.sub(r"\s+", " ", str(description or "")).strip()
    text = re.sub(r"\(\s*#?\d*\s*\)", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip(" -:()")
    if not text or text in {"(", ")", "-", "—"}:
        return ""

    cat = re.sub(r"\s+", " ", str(category or "")).strip()
    cat = re.sub(r"\(\s*#?\d*\s*\)", "", cat).strip()
    cat = cat.replace("(", " ").replace(")", " ")
    cat = re.sub(r"\s+", " ", cat).strip()
    cat = cat.strip(" -:()")
    low_cat = cat.lower()
    low_text = text.lower()
    noisy_categories = {
        "qe remarks",
        "remarks",
        "please try this user",
        "testing done",
        "note",
        "open issues on stage",
    }
    noisy_text_prefixes = (
        "it has permissions",
        "there's export button",
        "not able to test",
        "tested ",
        "verified ",
        "did sanity",
    )
    if low_cat in noisy_categories or low_text.startswith(noisy_text_prefixes):
        return ""

    if cat and not cat.upper().startswith("CHP-") and cat.lower() not in {
        "qe remarks",
        "remarks",
        "list of deployed items",
    }:
        label = f"{cat}: {text}"
    else:
        label = text
    label = re.sub(r"\s+", " ", label).strip(" -:()")
    return f"{label[:110].rstrip()}..." if len(label) > 110 else label


def _feature_labels_from_deployed_items(deployed_items: pd.DataFrame) -> list[str]:
    labels: list[str] = []
    grouped: dict[str, list[str]] = {}
    group_order: list[str] = []
    generic_categories = {
        "",
        "general",
        "qe remarks",
        "remarks",
        "list of deployed items",
        "new added fields",
        "testing done",
    }

    for idx, d in deployed_items.iterrows():
        category = str(d.get("Category", "")).strip()
        description = str(d.get("Item_Description", "")).strip()
        clean_category = re.sub(r"\s+", " ", category).strip().lower()
        if clean_category in generic_categories or category.upper().startswith("CHP-"):
            label = _feature_label_from_item_description(category, description)
            if label:
                labels.append(label)
            continue
        key = category
        if key not in grouped:
            grouped[key] = []
            group_order.append(key)
        grouped[key].append(description)

    for category in group_order:
        combined = " ".join(part for part in grouped[category] if part).strip()
        label = _feature_label_from_item_description(category, combined)
        if label:
            labels.append(label)

    return labels


def _join_limited(values: list[str], limit: int = 8) -> str:
    unique = list(dict.fromkeys(v for v in values if v))
    shown = unique[:limit]
    suffix = f" +{len(unique) - limit} more" if len(unique) > limit else ""
    return " | ".join(shown) + suffix if shown else ""


def _split_limited_values(value: str, limit: int = 8) -> tuple[list[str], int]:
    text = str(value or "").strip()
    if not text:
        return [], 0
    more = 0
    more_match = re.search(r"\s\+(\d+)\s+more$", text)
    if more_match:
        more = int(more_match.group(1))
        text = text[: more_match.start()].strip()
    values = [part.strip() for part in text.split("|") if part.strip()]
    return values[:limit], more


def _features_touched_bullets(value: str) -> str:
    values, more = _split_limited_values(value, limit=8)
    if not values:
        return "<span class=\"muted\">No deployed item descriptions</span>"
    items = "".join(f"<li>{escape(v)}</li>" for v in values)
    if more:
        items += f"<li class=\"muted\">+{more} more</li>"
    return f"<ul class=\"feature-bullets\">{items}</ul>"


def _safe_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    existing = [c for c in cols if c in df.columns]
    return df[existing].copy() if existing else df.copy()


MATRIX_PAGE_CONFIG: dict[str, dict[str, Any]] = {
    "01_Requirement_Testing_Traceability_Matrix": {
        "title": "Item Traceability",
        "fields": [
            "Req_ID", "Req_Name", "Site_Category", "Traceability_Status",
            "QE_Verified", "Last_Release_Date", "Release_Count", "Test_Evidence",
        ],
    },
    "01b_Feature_Level_Traceability_Matrix": {
        "title": "Feature Traceability",
        "fields": [
            "Feature_ID", "Feature_Name", "Site_Category", "Site_Subcategory",
            "Traceability_Status", "QE_Verified", "Story_Coverage_%",
            "Last_Release_Date", "Release_Count", "Coverage_Gap",
        ],
    },
    "02_Impact_Analysis_Matrix": {
        "title": "Impact Analysis",
        "fields": [
            "Req_ID", "Req_Name", "Component", "Impact_Score", "Risk_Level",
            "Severity", "Release_Count", "Hotfix_Count", "Last_Release_Date",
        ],
    },
    "03_AI_Powered_Validation_Matrix": {
        "title": "AI Validation",
        "fields": [
            "Req_ID", "Req_Name", "AI_Confidence", "Validation_Recommendation",
            "Traceability_Status", "Release_Count", "Potential_False_Positive",
            "AI_Rationale",
        ],
    },
    "04_Automation_Stability_Matrix": {
        "title": "Automation Stability",
        "fields": [
            "Release_File", "Release_Label", "Release_Date", "Automation_Health",
            "Verified_Count", "Bug_Issue_Count", "Hotfix_Risk", "Stability_Score",
        ],
    },
    "05_Release_Readiness_Matrix": {
        "title": "Release Readiness",
        "fields": [
            "Release_File", "Release_Label", "Release_Date", "Environment",
            "Release_Status", "Readiness_Score", "Go_No_Go", "Open_Gaps",
        ],
    },
    "06_Cross_Platform_Sync_Validation_Matrix": {
        "title": "Cross-Platform Sync",
        "fields": [
            "Release_File", "Chip1 Account", "Chip1 Part", "Chip1 Transaction",
            "Chip1 CRM WebUI", "Chip1 WebUI", "fn-connect", "Sync_Status",
            "Manifest_Status", "Drift_Notes",
        ],
    },
    "08_Strategy_Traceability_Matrix": {
        "title": "Strategy Traceability",
        "fields": [
            "Scenario_ID", "Scenario_Title", "Traceability_Status",
            "Release_Match_Count", "Req_Match_Count", "Linked_Releases",
            "Release_Evidence", "Automatable_%",
        ],
    },
    "09_Architecture_Coverage_Matrix": {
        "title": "Architecture Coverage",
        "fields": [
            "Node_ID", "Node_Label", "Architecture_Layer", "Node_Type",
            "Scenario_Coverage", "Scenarios_Testing_Node", "Impact_if_Fails",
        ],
    },
}


def _matrix_page_name(matrix_name: str) -> str:
    return f"{matrix_name}.html"


def load_requirements(req_folder: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for f in sorted(req_folder.glob("*.csv")):
        if not _is_requirement_backlog(f):
            continue
        df = _read_csv_safe(f)
        if df is None or df.empty:
            continue
        df["Source_File"] = f.name
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    req = pd.concat(frames, ignore_index=True)
    id_col = "Task Custom ID" if "Task Custom ID" in req.columns else None
    if id_col:
        req["Req_ID"] = req[id_col].astype(str).str.strip().str.upper()
        req = req[req["Req_ID"].str.match(r"^CHP-\d+$", na=False)]
    req = req.drop_duplicates(subset=["Req_ID"], keep="first")
    return req


def _extract_chp_ids(text: str) -> list[str]:
    return [m.upper() for m in CHP_PATTERN.findall(str(text) if text else "")]


def load_release_notes(release_folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (all_rows, chp_deployments)."""
    rows: list[dict[str, Any]] = []
    chp_rows: list[dict[str, Any]] = []

    for f in sorted(release_folder.glob("*.csv")):
        df = _read_csv_safe(f)
        if df is None or df.empty:
            continue

        release_label = f.stem.split("-2026")[0] if "-2026" in f.stem else f.stem
        meta: dict[str, str] = {
            "Release_File": f.name,
            "Release_Label": release_label,
            "Environment": "",
            "Release_Status": _extract_release_status_from_text(f),
            "Release_Date": "",
            "DB_Changes": "",
            "Platform_Branch": "",
            "Prod_Owner": "",
        }
        artefacts: dict[str, str] = {}

        for _, row in df.iterrows():
            section = str(row.get("Section", "")).strip()
            category = str(row.get("Category", "")).strip()
            desc = str(row.get("Item_Description", "")).strip()
            status = str(row.get("Status_Value", "")).strip()
            owner = str(row.get("Owner", "")).strip()

            if section == "Metadata" and category == "Release Info":
                key = desc.lower()
                if key == "environment":
                    meta["Environment"] = status
                elif key == "status":
                    meta["Release_Status"] = status or meta["Release_Status"]
                elif key == "release date":
                    meta["Release_Date"] = status
                elif key == "db changes":
                    meta["DB_Changes"] = status
                elif key in ("platform", "branch"):
                    meta["Platform_Branch"] = status or meta["Platform_Branch"]
                elif key == "prod release owner":
                    meta["Prod_Owner"] = status

            if section == "Artefacts" and category == "Artefacts" and desc:
                artefacts[desc] = status

            chp_in_cat = _extract_chp_ids(category)
            chp_in_desc = _extract_chp_ids(desc)
            chp_ids = list(dict.fromkeys(chp_in_cat + chp_in_desc))
            is_deployed = section == "Deployed Items"
            verified = (
                _is_verified_passed(status, desc, category) if is_deployed else False
            )
            is_bug = _is_bug_issue(status, desc, category) if is_deployed else False
            site_cat, site_sub = (
                _classify_deploy_text(category, desc) if is_deployed else ("", "")
            )

            record = {
                **meta,
                "Section": section,
                "Category": category,
                "Item_Description": desc,
                "Status_Value": status,
                "Owner": owner,
                "CHP_IDs_Found": "|".join(chp_ids),
                "Is_Hotfix": "hotfix" in f.name.lower(),
                "Is_Verified_Passed": verified,
                "Is_Bug_Issue": is_bug,
                "Deploy_Site_Category": site_cat,
                "Deploy_Site_Subcategory": site_sub,
            }
            rows.append(record)

            for chp in chp_ids:
                chp_rows.append(
                    {
                        **meta,
                        "CHP_ID": chp,
                        "Deploy_Category": category,
                        "Deploy_Description": desc,
                        "Deploy_Status": status,
                        "Deploy_Owner": owner,
                        "Is_Hotfix": record["Is_Hotfix"],
                        "Is_Verified_Passed": verified,
                        "Is_Bug_Issue": is_bug,
                        "Deploy_Site_Category": site_cat,
                        "Deploy_Site_Subcategory": site_sub,
                    }
                )

        for r in rows[-len(df) :]:
            r["Artefacts_JSON"] = str(artefacts)

    all_df = pd.DataFrame(rows)
    chp_df = pd.DataFrame(chp_rows)
    if not chp_df.empty:
        chp_df = chp_df.drop_duplicates(
            subset=["CHP_ID", "Release_File", "Deploy_Description"], keep="first"
        )
    return all_df, chp_df


def _text_similarity(a: str, b: str) -> float:
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio() * 100, 1)


def _col(req: pd.DataFrame, name: str, default: str = "") -> pd.Series:
    return req[name].fillna(default).astype(str) if name in req.columns else pd.Series(default, index=req.index)


def _release_dates_lookup(release_rows: pd.DataFrame) -> dict[str, datetime | None]:
    if release_rows.empty:
        return {}
    meta = release_rows.drop_duplicates(subset=["Release_File"], keep="first")
    return {
        str(r["Release_File"]): _parse_release_date(
            r.get("Release_Date", ""), r.get("Release_File", "")
        )
        for _, r in meta.iterrows()
    }


def _max_date_from_release_files(files: str, lookup: dict[str, datetime | None]) -> str:
    dates = []
    for f in str(files).split("|"):
        f = f.strip()
        if f and lookup.get(f):
            dates.append(lookup[f])
    if not dates:
        return ""
    return max(dates).strftime("%Y-%m-%d")


def _merge_verified_deploy_evidence(
    matrix: pd.DataFrame,
    req: pd.DataFrame,
    release_rows: pd.DataFrame,
    chp_deploy: pd.DataFrame,
) -> pd.DataFrame:
    """Treat deployed items marked verified/passed as tested."""
    if matrix.empty:
        return matrix

    matrix = matrix.copy()

    if not chp_deploy.empty and "Is_Verified_Passed" in chp_deploy.columns:
        v_chp = chp_deploy[chp_deploy["Is_Verified_Passed"].astype(bool)]
        if not v_chp.empty:
            v_agg = (
                v_chp.groupby("CHP_ID")
                .agg(
                    Verified_Pass_Count=("Release_File", "nunique"),
                    Verified_Releases=("Release_File", lambda x: "|".join(sorted(set(x)))),
                    Verified_Evidence=("Deploy_Description", lambda x: " // ".join(x.head(2).astype(str))),
                )
                .reset_index()
                .rename(columns={"CHP_ID": "Req_ID"})
            )
            matrix = matrix.merge(v_agg, on="Req_ID", how="left")

    deployed = (
        release_rows[release_rows["Section"] == "Deployed Items"]
        if not release_rows.empty and "Section" in release_rows.columns
        else pd.DataFrame()
    )
    if "Verified_Pass_Count" not in matrix.columns:
        matrix["Verified_Pass_Count"] = 0
    matrix["Verified_Pass_Count"] = matrix["Verified_Pass_Count"].fillna(0).astype(int)

    if deployed.empty or "Is_Verified_Passed" not in deployed.columns:
        matrix["QE_Verified"] = matrix["Verified_Pass_Count"].apply(lambda c: "YES" if c > 0 else "NO")
        return matrix

    verified = deployed[deployed["Is_Verified_Passed"].astype(bool)]
    lookup = _release_dates_lookup(release_rows)
    matrix.loc[matrix["Verified_Pass_Count"] > 0, "QE_Verified"] = "YES"

    pending = matrix[
        (matrix["Verified_Pass_Count"] == 0) & (matrix["Release_Count"] == 0)
    ]
    if not pending.empty and not verified.empty:
        verified_records = [
            (
                v["Release_File"],
                f"{v.get('Category', '')} {v.get('Item_Description', '')}",
                set(_extract_chp_ids(f"{v.get('Category', '')} {v.get('Item_Description', '')}")),
            )
            for _, v in verified.iterrows()
        ]
        for idx, row in pending.iterrows():
            rname = str(row.get("Req_Name", ""))
            releases: set[str] = set()
            evidence: list[str] = []
            for rf, blob, chps in verified_records:
                if row["Req_ID"] in chps or _text_similarity(rname, blob) >= 48:
                    releases.add(rf)
                    evidence.append(blob[:80])
            if not releases:
                continue
            matrix.at[idx, "Verified_Pass_Count"] = len(releases)
            matrix.at[idx, "QE_Verified"] = "YES"
            matrix.at[idx, "Matched_Releases"] = "|".join(sorted(releases))
            matrix.at[idx, "Release_Count"] = len(releases)
            matrix.at[idx, "Test_Evidence"] = " // ".join(evidence[:2])
            matrix.at[idx, "Last_Release_Date"] = _max_date_from_release_files(
                matrix.at[idx, "Matched_Releases"], lookup
            )

    if "QE_Verified" not in matrix.columns:
        matrix["QE_Verified"] = "NO"
    matrix.loc[matrix["Verified_Pass_Count"] > 0, "QE_Verified"] = "YES"
    matrix["QE_Verified"] = matrix["QE_Verified"].fillna("NO")
    if "Verified_Pass_Count" not in matrix.columns:
        matrix["Verified_Pass_Count"] = 0
    matrix["Verified_Pass_Count"] = matrix["Verified_Pass_Count"].fillna(0).astype(int)
    return matrix


def build_traceability_matrix(
    req: pd.DataFrame, chp_deploy: pd.DataFrame, release_rows: pd.DataFrame
) -> pd.DataFrame:
    if req.empty:
        return pd.DataFrame()

    categories = req.apply(classify_sitemap_category, axis=1, result_type="expand")
    categories.columns = ["Site_Category", "Site_Subcategory"]

    base = pd.DataFrame(
        {
            "Req_ID": req["Req_ID"],
            "Req_Name": _col(req, "Task Name"),
            "Req_Type": _col(req, "Task Type"),
            "Req_Status": _col(req, "Status"),
            "Site_Category": categories["Site_Category"],
            "Site_Subcategory": categories["Site_Subcategory"],
            "Component": _col(req, "Component (drop down)"),
            "Priority": _col(req, "Priority"),
            "TestCase_ID": _col(req, "TestCase ID (text)"),
            "Type_Of_Test": _col(req, "Type Of Test Performed (drop down)"),
            "Source_File": _col(req, "Source_File"),
        }
    )

    lookup = _release_dates_lookup(release_rows)

    if chp_deploy.empty:
        matrix = base.copy()
        matrix["Matched_Releases"] = ""
        matrix["Release_Count"] = 0
        matrix["Test_Evidence"] = ""
        matrix["Last_Release_Date"] = ""
        matrix["Hotfix_Count"] = 0
    else:
        agg = (
            chp_deploy.groupby("CHP_ID")
            .agg(
                Matched_Releases=("Release_File", lambda x: "|".join(sorted(set(x)))),
                Release_Count=("Release_File", "nunique"),
                Test_Evidence=("Deploy_Description", lambda x: " // ".join(x.head(3).astype(str))),
                Last_Release_Date=("Release_Date", lambda x: max([d for d in x if d], default="")),
                Hotfix_Count=("Is_Hotfix", "sum"),
            )
            .reset_index()
            .rename(columns={"CHP_ID": "Req_ID"})
        )
        matrix = base.merge(agg, on="Req_ID", how="left")
        matrix["Release_Count"] = matrix["Release_Count"].fillna(0).astype(int)
        matrix["Hotfix_Count"] = matrix.get("Hotfix_Count", pd.Series(0, index=matrix.index)).fillna(0).astype(int)

    matrix = _merge_verified_deploy_evidence(matrix, req, release_rows, chp_deploy)
    matrix["Matched_Releases"] = matrix.get("Matched_Releases", "").fillna("")
    matrix["Test_Evidence"] = matrix.get("Test_Evidence", "").fillna("")
    matrix["Last_Release_Date"] = matrix.apply(
        lambda r: r.get("Last_Release_Date", "")
        or _max_date_from_release_files(r.get("Matched_Releases", ""), lookup),
        axis=1,
    )

    def trace_status(row: pd.Series) -> str:
        qe_ver = str(row.get("QE_Verified", "")) == "YES" or int(row.get("Verified_Pass_Count", 0) or 0) > 0
        if row["Release_Count"] == 0 and not qe_ver:
            return "UNTESTED"
        if qe_ver or row.get("TestCase_ID", ""):
            return "VERIFIED"
        if row["Release_Count"] >= 2:
            return "REGRESSION_COVERED"
        return "DEPLOYED_TESTED"

    matrix["Traceability_Status"] = matrix.apply(trace_status, axis=1)
    matrix["Coverage_Gap"] = matrix.apply(
        lambda r: "None"
        if r["Traceability_Status"] in ("VERIFIED", "REGRESSION_COVERED")
        else ("Missing test case ID" if r["Release_Count"] > 0 else "Not found in any release notes"),
        axis=1,
    )
    return matrix.sort_values(
        ["Last_Release_Date", "Release_Count", "Req_ID"],
        ascending=[False, False, True],
        na_position="last",
    )


def build_story_to_feature_map(req: pd.DataFrame) -> dict[str, str]:
    """Map story Req_ID -> parent feature Req_ID."""
    features = req[req["Task Type"].str.lower() == "feature"]
    stories = req[req["Task Type"].str.lower() == "story"]
    if features.empty or stories.empty:
        return {}

    tid_to_feat = features.set_index("Task ID")["Req_ID"].to_dict()
    feat_ids = set(features["Req_ID"])
    mapping: dict[str, str] = {}

    for _, row in stories.iterrows():
        sid = row["Req_ID"]
        pf = str(row.get("Primary Feature (tasks)", ""))
        for tid in re.findall(r"[a-z0-9]{8,}", pf.lower()):
            if tid in tid_to_feat:
                mapping[sid] = tid_to_feat[tid]
                break
        if sid in mapping:
            continue

        blob = f"{row.get('Task Content', '')} {row.get('Task Name', '')}"
        for chp in _extract_chp_ids(blob):
            if chp in feat_ids and chp != sid:
                mapping[sid] = chp
                break

    # Fuzzy fallback: link orphan stories to best-matching feature by title
    feat_names = features.set_index("Req_ID")["Task Name"].to_dict()
    for _, row in stories.iterrows():
        sid = row["Req_ID"]
        if sid in mapping:
            continue
        sname = str(row.get("Task Name", ""))
        best_fid, best_score = "", 0.0
        for fid, fname in feat_names.items():
            score = _text_similarity(sname, str(fname))
            if score > best_score:
                best_fid, best_score = fid, score
        if best_score >= 35:
            mapping[sid] = best_fid
            continue
        story_tokens = {w for w in re.findall(r"[a-z]{5,}", sname.lower())}
        for fid, fname in feat_names.items():
            feat_tokens = {w for w in re.findall(r"[a-z]{5,}", str(fname).lower())}
            if len(story_tokens & feat_tokens) >= 2:
                mapping[sid] = fid
                break

    return mapping


def build_feature_traceability_matrix(
    req: pd.DataFrame,
    chp_deploy: pd.DataFrame,
    item_trace: pd.DataFrame,
    release_rows: pd.DataFrame,
) -> pd.DataFrame:
    """Roll up requirement→testing traceability to Feature (parent) level."""
    features = req[req["Task Type"].str.lower() == "feature"].copy()
    if features.empty:
        return pd.DataFrame()

    story_map = build_story_to_feature_map(req)
    feat_to_stories: dict[str, list[str]] = {}
    for story_id, feat_id in story_map.items():
        feat_to_stories.setdefault(feat_id, []).append(story_id)

    trace_idx = item_trace.set_index("Req_ID") if not item_trace.empty else pd.DataFrame()
    lookup = _release_dates_lookup(release_rows)

    rows: list[dict[str, Any]] = []
    for _, feat in features.iterrows():
        fid = feat["Req_ID"]
        fname = str(feat.get("Task Name", ""))
        child_ids = sorted(set(feat_to_stories.get(fid, [])))

        releases: set[str] = set()
        evidence: list[str] = []
        tested_stories: list[str] = []
        verified_stories: list[str] = []

        verified_pass_count = 0
        if not chp_deploy.empty:
            direct = chp_deploy[chp_deploy["CHP_ID"] == fid]
            for _, d in direct.iterrows():
                releases.add(d["Release_File"])
                evidence.append(f"[direct] {str(d.get('Deploy_Description', ''))[:100]}")
                if d.get("Is_Verified_Passed"):
                    verified_pass_count += 1

            for _, d in chp_deploy.iterrows():
                blob = f"{d.get('Deploy_Category', '')} {d.get('Deploy_Description', '')}"
                if _text_similarity(fname, blob) >= 45:
                    releases.add(d["Release_File"])
                    evidence.append(f"[name-match] {str(d.get('Deploy_Description', ''))[:80]}")
                    if d.get("Is_Verified_Passed"):
                        verified_pass_count += 1

        if (
            not releases
            and release_rows is not None
            and not release_rows.empty
        ):
            deployed = release_rows[release_rows["Section"] == "Deployed Items"]
            verified = deployed[deployed["Is_Verified_Passed"].astype(bool)]
            for _, v in verified.iterrows():
                blob = f"{v.get('Category', '')} {v.get('Item_Description', '')}"
                if fid in _extract_chp_ids(blob) or _text_similarity(fname, blob) >= 48:
                    releases.add(v["Release_File"])
                    verified_pass_count += 1
                    evidence.append(f"[qe-verified] {str(v.get('Item_Description', ''))[:80]}")

        for sid in child_ids:
            if trace_idx.empty or sid not in trace_idx.index:
                continue
            ct = trace_idx.loc[sid]
            rc = int(ct.get("Release_Count", 0) or 0)
            if rc > 0:
                tested_stories.append(sid)
                for r in str(ct.get("Matched_Releases", "")).split("|"):
                    if r.strip():
                        releases.add(r.strip())
                ev = str(ct.get("Test_Evidence", ""))[:100]
                if ev:
                    evidence.append(f"[{sid}] {ev}")
            if str(ct.get("Traceability_Status", "")) == "VERIFIED":
                verified_stories.append(sid)

        story_count = len(child_ids)
        tested_count = len(tested_stories)
        if story_count:
            story_coverage_pct = round(100 * tested_count / story_count, 1)
        else:
            story_coverage_pct = 100.0 if releases else 0.0

        direct_deploy = bool(not chp_deploy.empty and (chp_deploy["CHP_ID"] == fid).any())
        qe_verified = verified_pass_count > 0 or any(
            str(trace_idx.loc[sid].get("QE_Verified", "")) == "YES"
            for sid in child_ids
            if not trace_idx.empty and sid in trace_idx.index
        )

        if direct_deploy or qe_verified or (story_count and tested_count == story_count):
            status = "FULLY_TRACED"
            gap = "None"
        elif tested_count > 0 or releases:
            status = "PARTIALLY_TRACED"
            gap = f"{story_count - tested_count} linked stories without release evidence" if story_count else "Indirect/name-match only"
        elif story_count == 0 and releases:
            status = "INDIRECT_TRACED"
            gap = "No child stories linked; matched via feature ID or name"
        else:
            status = "UNTESTED"
            gap = "No release linkage at feature or story level"

        site_cat, site_sub = classify_sitemap_category(feat)
        last_release = _max_date_from_release_files("|".join(sorted(releases)), lookup)

        rows.append(
            {
                "Feature_ID": fid,
                "Feature_Name": fname,
                "Site_Category": site_cat,
                "Site_Subcategory": site_sub,
                "Feature_Status": str(feat.get("Status", "")),
                "Component": str(feat.get("Component (drop down)", "")),
                "Priority": str(feat.get("Priority", "")),
                "Source_File": str(feat.get("Source_File", "")),
                "Child_Story_Count": story_count,
                "Child_Story_IDs": "|".join(child_ids),
                "Stories_Tested_Count": tested_count,
                "Stories_Verified_Count": len(verified_stories),
                "Story_Coverage_%": story_coverage_pct,
                "Verified_Pass_Count": verified_pass_count,
                "QE_Verified": "YES" if qe_verified else "NO",
                "Direct_Feature_In_Release": "YES" if direct_deploy else "NO",
                "Matched_Releases": "|".join(sorted(releases)),
                "Release_Count": len(releases),
                "Last_Release_Date": last_release,
                "Test_Evidence": " // ".join(evidence[:4]),
                "Traceability_Status": status,
                "Coverage_Gap": gap,
            }
        )

    result = pd.DataFrame(rows)
    col_order = [
        "Feature_ID", "Feature_Name", "Site_Category", "Site_Subcategory",
        "Feature_Status", "Component", "Priority", "Source_File",
        "Child_Story_Count", "Child_Story_IDs", "Stories_Tested_Count", "Stories_Verified_Count",
        "Story_Coverage_%", "Verified_Pass_Count", "QE_Verified",
        "Direct_Feature_In_Release", "Matched_Releases", "Release_Count", "Last_Release_Date",
        "Test_Evidence", "Traceability_Status", "Coverage_Gap",
    ]
    return result[[c for c in col_order if c in result.columns]].sort_values(
        ["Last_Release_Date", "Release_Count", "Site_Category", "Feature_ID"],
        ascending=[False, False, True, True],
        na_position="last",
    )


def build_sitemap_category_coverage(
    feature_trace: pd.DataFrame,
    release_rows: pd.DataFrame,
    item_trace: pd.DataFrame,
) -> pd.DataFrame:
    """Full sitemap taxonomy with feature coverage, verified deploys, and bug/issue counts."""
    stats: dict[tuple[str, str], dict[str, Any]] = {
        (cat, sub): {
            "Site_Category": cat,
            "Site_Subcategory": sub,
            "Feature_Count": 0,
            "Traced_Features": 0,
            "Fully_Traced": 0,
            "QE_Verified_Features": 0,
            "Items_Tested": 0,
            "Verified_Deployed_Items": 0,
            "Bugs_Issues_Count": 0,
        }
        for cat, sub in get_full_sitemap_taxonomy()
    }

    if not feature_trace.empty:
        for _, f in feature_trace.iterrows():
            cat = str(f.get("Site_Category", "General"))
            sub = str(f.get("Site_Subcategory", "") or "")
            key = (cat, sub)
            if key not in stats:
                stats[key] = {
                    "Site_Category": cat,
                    "Site_Subcategory": sub,
                    "Feature_Count": 0,
                    "Traced_Features": 0,
                    "Fully_Traced": 0,
                    "QE_Verified_Features": 0,
                    "Items_Tested": 0,
                    "Verified_Deployed_Items": 0,
                    "Bugs_Issues_Count": 0,
                }
            stats[key]["Feature_Count"] += 1
            if f.get("Traceability_Status") != "UNTESTED":
                stats[key]["Traced_Features"] += 1
            if f.get("Traceability_Status") == "FULLY_TRACED":
                stats[key]["Fully_Traced"] += 1
            if str(f.get("QE_Verified", "")) == "YES":
                stats[key]["QE_Verified_Features"] += 1

    if not item_trace.empty:
        tested = item_trace[item_trace["Traceability_Status"] != "UNTESTED"]
        for _, t in tested.iterrows():
            key = (str(t.get("Site_Category", "General")), str(t.get("Site_Subcategory", "") or ""))
            if key not in stats:
                stats[key] = {
                    "Site_Category": key[0],
                    "Site_Subcategory": key[1],
                    "Feature_Count": 0,
                    "Traced_Features": 0,
                    "Fully_Traced": 0,
                    "QE_Verified_Features": 0,
                    "Items_Tested": 0,
                    "Verified_Deployed_Items": 0,
                    "Bugs_Issues_Count": 0,
                }
            stats[key]["Items_Tested"] += 1

    if not release_rows.empty and "Section" in release_rows.columns:
        deployed = release_rows[release_rows["Section"] == "Deployed Items"]
        for _, d in deployed.iterrows():
            cat = str(d.get("Deploy_Site_Category", "") or "")
            sub = str(d.get("Deploy_Site_Subcategory", "") or "")
            if not cat:
                cat, sub = _classify_deploy_text(
                    str(d.get("Category", "")), str(d.get("Item_Description", ""))
                )
            key = (cat, sub)
            if key not in stats:
                stats[key] = {
                    "Site_Category": cat,
                    "Site_Subcategory": sub,
                    "Feature_Count": 0,
                    "Traced_Features": 0,
                    "Fully_Traced": 0,
                    "QE_Verified_Features": 0,
                    "Items_Tested": 0,
                    "Verified_Deployed_Items": 0,
                    "Bugs_Issues_Count": 0,
                }
            if d.get("Is_Verified_Passed"):
                stats[key]["Verified_Deployed_Items"] += 1
            if d.get("Is_Bug_Issue"):
                stats[key]["Bugs_Issues_Count"] += 1

    rows = []
    for data in stats.values():
        fc = data["Feature_Count"]
        traced = data["Traced_Features"]
        verified_items = data["Verified_Deployed_Items"]
        item_evidence = max(data["Items_Tested"], verified_items)
        evidence_bonus = min(max(fc - traced, 0), item_evidence)
        coverage_numerator = traced + evidence_bonus
        if fc:
            coverage_pct = round(100 * coverage_numerator / fc, 1)
            evidence_status = "COVERED" if coverage_pct >= 100 else ("PARTIAL" if coverage_numerator else "GAP")
        elif item_evidence:
            coverage_pct = 100.0
            evidence_status = "DEPLOY_EVIDENCE"
        else:
            coverage_pct = 0.0
            evidence_status = "NO_FEATURES_MAPPED"
        denom = max(fc, 1)
        rows.append(
            {
                **data,
                "Coverage_Evidence_Items": item_evidence,
                "Coverage_Status": evidence_status,
                "Coverage_%": coverage_pct,
                "Verified_Coverage_%": round(
                    100 * coverage_numerator / denom if fc else (100 if item_evidence else 0),
                    1,
                ),
            }
        )

    result = pd.DataFrame(rows)
    result["Label"] = result.apply(
        lambda r: f"{r['Site_Category']}"
        + (f" › {r['Site_Subcategory']}" if r["Site_Subcategory"] else ""),
        axis=1,
    )
    return result.sort_values(
        ["Verified_Deployed_Items", "Bugs_Issues_Count", "Coverage_%", "Site_Category"],
        ascending=[False, False, False, True],
    )


def build_last_n_releases_traceability(
    release_rows: pd.DataFrame,
    chp_deploy: pd.DataFrame,
    feature_trace: pd.DataFrame,
    readiness: pd.DataFrame,
    story_map: dict[str, str],
    n: int = 10,
) -> pd.DataFrame:
    if release_rows.empty:
        return pd.DataFrame()

    meta = release_rows.drop_duplicates(subset=["Release_File"], keep="first").copy()
    meta["_sort_date"] = meta.apply(
        lambda r: _parse_release_date(r.get("Release_Date", ""), r.get("Release_File", "")),
        axis=1,
    )
    meta = meta.sort_values(
        by="_sort_date",
        ascending=False,
        na_position="last",
    ).head(n)

    readiness_idx = (
        readiness.set_index("Release_File") if not readiness.empty else pd.DataFrame()
    )

    rows = []
    for _, rel in meta.iterrows():
        rf = rel["Release_File"]
        deploys = chp_deploy[chp_deploy["Release_File"] == rf] if not chp_deploy.empty else pd.DataFrame()
        chp_ids = deploys["CHP_ID"].unique().tolist() if not deploys.empty else []
        release_slice = release_rows[release_rows["Release_File"] == rf]
        deployed_items = release_slice[release_slice["Section"] == "Deployed Items"]
        artefacts = release_slice[release_slice["Section"] == "Artefacts"]

        feature_labels = _feature_labels_from_deployed_items(deployed_items)

        categories: set[str] = set()
        for _, artifact in artefacts.iterrows():
            categories.update(
                _artifact_categories(
                    str(artifact.get("Item_Description", "")),
                    str(artifact.get("Status_Value", "")),
                )
            )

        if not categories and not deployed_items.empty:
            for _, d in deployed_items.iterrows():
                site_cat, _ = _classify_deploy_text(
                    str(d.get("Category", "")),
                    str(d.get("Item_Description", "")),
                )
                if site_cat:
                    categories.add(site_cat)

        rrow = readiness_idx.loc[rf] if not readiness_idx.empty and rf in readiness_idx.index else None
        sort_dt = rel.get("_sort_date")
        display_date = rel.get("Release_Date", "") or (
            sort_dt.strftime("%Y-%m-%d") if sort_dt is not None else ""
        )
        feature_labels = list(dict.fromkeys(label for label in feature_labels if label))
        rows.append(
            {
                "Release_File": rf,
                "Release_Label": rel.get("Release_Label", ""),
                "Release_Date": display_date,
                "Environment": rel.get("Environment", ""),
                "Release_Status": rel.get("Release_Status", ""),
                "CHP_Items_Deployed": len(chp_ids),
                "Features_Touched_Count": len(feature_labels),
                "Features_Touched": _join_limited(feature_labels),
                "Categories_Affected": "|".join(sorted(categories)) if categories else "—",
                "Readiness_Score": rrow["Readiness_Score"] if rrow is not None else "",
                "Go_No_Go": rrow["Go_No_Go"] if rrow is not None else "",
                "Is_Hotfix": "YES" if rel.get("Is_Hotfix") else "NO",
                "Top_Evidence": " // ".join(
                    deploys["Deploy_Description"].astype(str).head(2).tolist()
                )
                if not deploys.empty
                else "",
            }
        )

    return pd.DataFrame(rows)


def build_impact_matrix(req: pd.DataFrame, chp_deploy: pd.DataFrame, trace: pd.DataFrame) -> pd.DataFrame:
    if req.empty:
        return pd.DataFrame()

    impact = trace[
        [
            "Req_ID",
            "Req_Name",
            "Component",
            "Release_Count",
            "Hotfix_Count",
            "Traceability_Status",
        ]
    ].copy()

    impact["Related_Components"] = _col(req, "Related Components Impacted (short text)").reindex(impact.index, fill_value="")
    impact["Tags"] = _col(req, "tags").reindex(impact.index, fill_value="")
    impact["Severity"] = _col(req, "Severity (drop down)").reindex(impact.index, fill_value="")

    deploy_by_req = (
        chp_deploy.groupby("CHP_ID")["Deploy_Description"].apply(lambda x: len(set(x))).to_dict()
        if not chp_deploy.empty
        else {}
    )
    impact["Deploy_Touch_Count"] = impact["Req_ID"].map(deploy_by_req).fillna(0).astype(int)
    if not trace.empty and "Last_Release_Date" in trace.columns:
        impact = impact.merge(
            trace[["Req_ID", "Last_Release_Date"]], on="Req_ID", how="left"
        )

    def impact_score(row: pd.Series) -> int:
        score = 0
        if row["Release_Count"] >= 3:
            score += 30
        elif row["Release_Count"] >= 1:
            score += 15
        if row["Hotfix_Count"] >= 1:
            score += 25
        if row["Deploy_Touch_Count"] >= 3:
            score += 20
        if str(row["Severity"]).upper() in ("CRITICAL", "HIGH", "URGENT"):
            score += 20
        if row["Component"]:
            score += 10
        return min(score, 100)

    impact["Impact_Score"] = impact.apply(impact_score, axis=1)

    def risk_level(score: int) -> str:
        if score >= 70:
            return "CRITICAL"
        if score >= 45:
            return "HIGH"
        if score >= 25:
            return "MEDIUM"
        return "LOW"

    impact["Risk_Level"] = impact["Impact_Score"].apply(risk_level)
    impact["Blast_Radius"] = impact.apply(
        lambda r: f"{r['Component'] or 'General'} | {r['Tags'] or 'untagged'} | {r['Deploy_Touch_Count']} deploy touches",
        axis=1,
    )
    sort_cols = ["Impact_Score"]
    if "Last_Release_Date" in impact.columns:
        sort_cols.append("Last_Release_Date")
    return impact.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")


def build_ai_validation_matrix(req: pd.DataFrame, chp_deploy: pd.DataFrame, trace: pd.DataFrame) -> pd.DataFrame:
    if req.empty:
        return pd.DataFrame()

    ai = trace[["Req_ID", "Req_Name", "Test_Evidence", "Release_Count"]].copy()
    ai["Req_Content_Snippet"] = _col(req, "Task Content").str[:500].reindex(ai.index, fill_value="")

    deploy_text: dict[str, str] = {}
    if not chp_deploy.empty:
        deploy_text = (
            chp_deploy.groupby("CHP_ID")
            .apply(lambda g: " ".join(g["Deploy_Description"].astype(str).head(5)))
            .to_dict()
        )

    ai["Semantic_Match_Score"] = ai.apply(
        lambda r: _text_similarity(r["Req_Name"], deploy_text.get(r["Req_ID"], "")),
        axis=1,
    )
    ai["Description_Completeness"] = ai["Req_Content_Snippet"].apply(
        lambda t: min(100, 20 + len(t.split()) * 2) if t.strip() else 10
    )
    ai["Test_Note_Alignment"] = ai.apply(
        lambda r: min(100, r["Semantic_Match_Score"] + (15 if r["Release_Count"] > 0 else 0)),
        axis=1,
    )
    ai["AI_Confidence"] = (
        ai["Semantic_Match_Score"] * 0.4
        + ai["Description_Completeness"] * 0.25
        + ai["Test_Note_Alignment"] * 0.35
    ).round(1)

    def recommendation(row: pd.Series) -> str:
        if row["AI_Confidence"] >= 75:
            return "AUTO_APPROVE"
        if row["AI_Confidence"] >= 50:
            return "HUMAN_REVIEW"
        return "REQUIRES_MANUAL_VALIDATION"

    ai["Validation_Recommendation"] = ai.apply(recommendation, axis=1)
    ai["Anomaly_Flags"] = ai.apply(
        lambda r: "; ".join(
            f
            for f in [
                "LOW_SEMANTIC_MATCH" if r["Semantic_Match_Score"] < 25 and r["Release_Count"] > 0 else "",
                "SPARSE_REQUIREMENT" if r["Description_Completeness"] < 30 else "",
                "NO_DEPLOY_EVIDENCE" if r["Release_Count"] == 0 else "",
            ]
            if f
        )
        or "NONE",
        axis=1,
    )
    return ai.sort_values("AI_Confidence", ascending=False)


def build_automation_stability_matrix(release_rows: pd.DataFrame) -> pd.DataFrame:
    if release_rows.empty:
        return pd.DataFrame()

    rel = release_rows.drop_duplicates(subset=["Release_File"], keep="first").copy()
    deployed = release_rows[release_rows["Section"] == "Deployed Items"]

    deploy_counts = deployed.groupby("Release_File").size().to_dict()
    qe_notes = deployed[deployed["Category"].str.contains("note|qe|sanity|validation", case=False, na=False)]
    qe_counts = qe_notes.groupby("Release_File").size().to_dict()
    regression_hits = (
        deployed[deployed["Item_Description"].str.contains("bug|regression|fix|sync", case=False, na=False)]
        .groupby("Release_File")
        .size()
        .to_dict()
    )

    rows = []
    for _, r in rel.iterrows():
        rf = r["Release_File"]
        dcount = deploy_counts.get(rf, 0)
        qcount = qe_counts.get(rf, 0)
        rcount = regression_hits.get(rf, 0)
        hotfix = r.get("Is_Hotfix", False)

        flaky = min(100, int(hotfix) * 30 + rcount * 8 + max(0, 5 - qcount) * 5)
        pass_rate = max(0, 100 - flaky - (10 if str(r.get("Release_Status", "")).lower() not in ("good", "pass", "ok", "") else 0))

        rows.append(
            {
                "Release_File": rf,
                "Release_Label": r.get("Release_Label", ""),
                "Release_Date": r.get("Release_Date", ""),
                "Environment": r.get("Environment", ""),
                "Release_Status": r.get("Release_Status", ""),
                "Is_Hotfix": hotfix,
                "Deployed_Item_Count": dcount,
                "QE_Validation_Notes": qcount,
                "Regression_Mentions": rcount,
                "Automation_Pass_Rate_%": pass_rate,
                "Flaky_Score": flaky,
                "Stability_Trend": "DECLINING" if flaky >= 50 else ("STABLE" if flaky < 25 else "WATCH"),
                "Automation_Health": "HEALTHY" if pass_rate >= 80 else ("AT_RISK" if pass_rate >= 60 else "CRITICAL"),
            }
        )

    return pd.DataFrame(rows).sort_values("Flaky_Score", ascending=False)


def build_release_readiness_matrix(
    release_rows: pd.DataFrame, trace: pd.DataFrame, chp_deploy: pd.DataFrame
) -> pd.DataFrame:
    if release_rows.empty:
        return pd.DataFrame()

    rel = release_rows.drop_duplicates(subset=["Release_File"], keep="first")
    total_reqs = len(trace) if not trace.empty else 1
    covered_reqs = set(trace.loc[trace["Release_Count"] > 0, "Req_ID"]) if not trace.empty else set()

    chp_per_release = (
        chp_deploy.groupby("Release_File")["CHP_ID"].nunique().to_dict() if not chp_deploy.empty else {}
    )

    rows = []
    for _, r in rel.iterrows():
        rf = r["Release_File"]
        chp_count = chp_per_release.get(rf, 0)
        env = str(r.get("Environment", "")).lower()
        status = str(r.get("Release_Status", "")).lower()
        db = str(r.get("DB_Changes", ""))

        coverage_pct = round((chp_count / max(total_reqs, 1)) * 100, 1) if total_reqs else 0
        gaps = []
        if not status or status in ("", "nan"):
            gaps.append("Missing release status")
        if "change" in db.lower() and "no change" not in db.lower():
            gaps.append("DB migration review required")
        if chp_count == 0:
            gaps.append("No CHP traceability in release notes")
        if env not in ("stage", "prod", "production", "uat"):
            gaps.append("Environment not confirmed")

        score = 100
        score -= len(gaps) * 15
        score -= 20 if "hotfix" in rf.lower() else 0
        score = max(0, min(100, score))

        rows.append(
            {
                "Release_File": rf,
                "Release_Label": r.get("Release_Label", ""),
                "Release_Date": r.get("Release_Date", ""),
                "Environment": r.get("Environment", ""),
                "Release_Status": r.get("Release_Status", ""),
                "DB_Changes": r.get("DB_Changes", ""),
                "Platform_Branch": r.get("Platform_Branch", ""),
                "CHP_Items_In_Release": chp_count,
                "Req_Backlog_Coverage_%": coverage_pct,
                "Open_Gaps": "; ".join(gaps) or "None",
                "Readiness_Score": score,
                "Go_No_Go": "GO" if score >= 75 and not gaps else ("CONDITIONAL" if score >= 50 else "NO_GO"),
            }
        )

    result = pd.DataFrame(rows)
    lookup = _release_dates_lookup(release_rows)
    result["_sort_date"] = result["Release_File"].map(lookup)
    def _fmt_release_date(r: pd.Series) -> str:
        if str(r.get("Release_Date", "")).strip():
            return str(r["Release_Date"])
        sd = r.get("_sort_date")
        if sd is not None and pd.notna(sd):
            return sd.strftime("%Y-%m-%d")
        return ""

    result["Release_Date"] = result.apply(_fmt_release_date, axis=1)
    return result.sort_values(
        ["_sort_date", "Readiness_Score"],
        ascending=[False, False],
        na_position="last",
    ).drop(columns=["_sort_date"], errors="ignore")


ARTEFACT_KEYS = [
    "Chip1 Part",
    "Chip1 Transaction",
    "Chip1 CRM WebUI",
    "Chip1 WebUI",
    "fn-connect",
]


def build_cross_platform_matrix(release_rows: pd.DataFrame) -> pd.DataFrame:
    if release_rows.empty:
        return pd.DataFrame()

    arte_rows = release_rows[
        (release_rows["Section"] == "Artefacts") & (release_rows["Category"] == "Artefacts")
    ]
    rel_meta = release_rows.drop_duplicates(subset=["Release_File"], keep="first")

    rows = []
    for _, meta in rel_meta.iterrows():
        rf = meta["Release_File"]
        subset = arte_rows[arte_rows["Release_File"] == rf]
        versions = {k: "" for k in ARTEFACT_KEYS}
        for _, a in subset.iterrows():
            desc = str(a.get("Item_Description", ""))
            for key in ARTEFACT_KEYS:
                if key.lower() in desc.lower():
                    versions[key] = str(a.get("Status_Value", ""))

        present = [v for v in versions.values() if v]
        prefixes = set()
        for v in present:
            parts = re.split(r"[.\s]", v)
            if parts:
                prefixes.add(parts[0][:8])

        aligned = len(prefixes) <= 1 and len(present) >= 2
        drift = []
        if len(present) < 3:
            drift.append("Incomplete artefact manifest")
        if len(prefixes) > 1:
            drift.append("Version prefix mismatch across services")

        rows.append(
            {
                "Release_File": rf,
                "Release_Date": meta.get("Release_Date", ""),
                **{k.replace(" ", "_"): versions[k] for k in ARTEFACT_KEYS},
                "Services_Reported": len(present),
                "Version_Alignment": "ALIGNED" if aligned else "MISALIGNED",
                "Sync_Status": "SYNCED" if aligned and len(present) >= 4 else "PARTIAL",
                "Drift_Detected": "; ".join(drift) if drift else "None",
            }
        )

    return pd.DataFrame(rows)


STRATEGY_KEYWORDS: dict[str, list[str]] = {
    "DIS-01": ["sync", "flow", "end-to-end", "e2e", "pipeline", "ingest", "data store"],
    "DIS-02": ["schema", "validation", "quality", "mandatory", "field", "format"],
    "DIS-03": ["transform", "mapping", "business", "logic", "calculation", "rule"],
    "DIS-04": ["error", "logging", "handler", "exception", "fail"],
    "DIS-05": ["performance", "volume", "load", "latency", "concurrent", "throughput"],
    "DIS-06": ["security", "permission", "access", "rbac", "auth"],
    "DIS-07": ["regression", "re-run", "sanity", "smoke"],
}


def load_test_strategy(req_folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    strategy_path = req_folder / "Data_Integration_Testing_Strategy.csv"
    arch_path = req_folder / "Data_Integration_Architecture.csv"
    strategy = _read_csv_safe(strategy_path) if strategy_path.exists() else pd.DataFrame()
    arch = _read_csv_safe(arch_path) if arch_path.exists() else pd.DataFrame()
    return strategy, arch


def _keyword_hits(text: str, keywords: list[str]) -> int:
    t = (text or "").lower()
    return sum(1 for k in keywords if k in t)


def build_strategy_traceability_matrix(
    strategy: pd.DataFrame,
    req: pd.DataFrame,
    release_rows: pd.DataFrame,
) -> pd.DataFrame:
    if strategy.empty:
        return pd.DataFrame()

    deployed = release_rows[release_rows["Section"] == "Deployed Items"] if not release_rows.empty else pd.DataFrame()
    req_names = (
        req[["Req_ID", "Task Name"]].rename(columns={"Task Name": "Req_Name"})
        if not req.empty and "Task Name" in req.columns
        else pd.DataFrame()
    )

    rows = []
    for sid in strategy["Scenario_ID"].unique():
        subset = strategy[strategy["Scenario_ID"] == sid]
        title = subset["Scenario_Title"].iloc[0]
        components = "|".join(subset["Architecture_Component"].unique())
        keywords = STRATEGY_KEYWORDS.get(sid, [])

        matched_reqs = []
        if not req_names.empty:
            for _, r in req_names.iterrows():
                if _keyword_hits(r["Req_Name"], keywords) >= 1:
                    matched_reqs.append(r["Req_ID"])

        matched_releases = []
        evidence = []
        if not deployed.empty:
            for _, d in deployed.iterrows():
                blob = f"{d.get('Category', '')} {d.get('Item_Description', '')}"
                if _keyword_hits(blob, keywords) >= 1:
                    matched_releases.append(d["Release_File"])
                    evidence.append(str(d.get("Item_Description", ""))[:120])

        auto_pct = round(
            100 * subset["Automatable"].str.lower().eq("yes").mean(), 1
        ) if "Automatable" in subset.columns else 0

        rows.append(
            {
                "Scenario_ID": sid,
                "Scenario_Title": title,
                "Architecture_Components": components,
                "Test_Level": "|".join(subset["Test_Level"].unique()),
                "Priority": subset["Priority"].iloc[0] if "Priority" in subset.columns else "",
                "Linked_Requirements": "|".join(sorted(set(matched_reqs))[:8]),
                "Req_Match_Count": len(set(matched_reqs)),
                "Linked_Releases": "|".join(sorted(set(matched_releases))[:6]),
                "Release_Match_Count": len(set(matched_releases)),
                "Release_Evidence": " // ".join(evidence[:3]),
                "Automatable_%": auto_pct,
                "Traceability_Status": (
                    "COVERED"
                    if matched_releases
                    else ("REQ_ONLY" if matched_reqs else "GAP")
                ),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["Release_Match_Count", "Req_Match_Count"],
        ascending=[False, False],
    )


def build_strategy_architecture_coverage(strategy: pd.DataFrame, arch: pd.DataFrame) -> pd.DataFrame:
    if arch.empty:
        return pd.DataFrame()

    covered = set(strategy["Architecture_Component"]) if not strategy.empty else set()
    rows = []
    for _, node in arch.iterrows():
        label = node.get("Node_Label", "")
        rows.append(
            {
                "Node_ID": node.get("Node_ID", ""),
                "Node_Label": label,
                "Architecture_Layer": node.get("Architecture_Layer", ""),
                "Node_Type": node.get("Node_Type", ""),
                "Upstream_Nodes": node.get("Upstream_Nodes", ""),
                "Scenario_Coverage": "YES" if label in covered else "NO",
                "Scenarios_Testing_Node": "|".join(
                    strategy.loc[strategy["Architecture_Component"] == label, "Scenario_ID"].unique()
                )
                if not strategy.empty
                else "",
                "Impact_if_Fails": "HIGH" if node.get("Architecture_Layer") == "Processing" else "MEDIUM",
            }
        )
    return pd.DataFrame(rows)


def build_dashboard_summary(
    trace: pd.DataFrame,
    impact: pd.DataFrame,
    ai: pd.DataFrame,
    automation: pd.DataFrame,
    readiness: pd.DataFrame,
    cross_platform: pd.DataFrame,
    strategy_trace: pd.DataFrame | None = None,
    feature_trace: pd.DataFrame | None = None,
) -> pd.DataFrame:
    def pct(series: pd.Series, good_values: set[str]) -> float:
        if series.empty:
            return 0.0
        return round(100 * series.isin(good_values).mean(), 1)

    kpis = [
        ("Total Requirements", len(trace)),
        ("Tested / Deployed", int((trace["Release_Count"] > 0).sum()) if not trace.empty else 0),
        ("Verified (with TestCase)", int((trace["Traceability_Status"] == "VERIFIED").sum()) if not trace.empty else 0),
        ("Untested Gaps", int((trace["Traceability_Status"] == "UNTESTED").sum()) if not trace.empty else 0),
        ("High/Critical Impact", int(impact["Risk_Level"].isin(["HIGH", "CRITICAL"]).sum()) if not impact.empty else 0),
        ("AI Auto-Approve", int((ai["Validation_Recommendation"] == "AUTO_APPROVE").sum()) if not ai.empty else 0),
        ("Automation At Risk", int((automation["Automation_Health"] != "HEALTHY").sum()) if not automation.empty else 0),
        ("Releases GO", int((readiness["Go_No_Go"] == "GO").sum()) if not readiness.empty else 0),
        ("Cross-Platform SYNCED", int((cross_platform["Sync_Status"] == "SYNCED").sum()) if not cross_platform.empty else 0),
        ("Avg Readiness Score", round(readiness["Readiness_Score"].mean(), 1) if not readiness.empty else 0),
    ]
    if feature_trace is not None and not feature_trace.empty:
        feat_traced = feature_trace["Traceability_Status"] != "UNTESTED"
        kpis.extend(
            [
                ("Total Features", len(feature_trace)),
                ("Features Traced", int(feat_traced.sum())),
                (
                    "Feature Coverage %",
                    round(100 * feat_traced.mean(), 1),
                ),
            ]
        )
    if strategy_trace is not None and not strategy_trace.empty:
        kpis.extend(
            [
                ("Strategy Scenarios", len(strategy_trace)),
                ("Strategy COVERED", int((strategy_trace["Traceability_Status"] == "COVERED").sum())),
                ("Strategy GAPs", int((strategy_trace["Traceability_Status"] == "GAP").sum())),
            ]
        )
    return pd.DataFrame(kpis, columns=["KPI", "Value"])


def _inline_bar_chart(title: str, pairs: list[tuple[str, float]], suffix: str = "") -> str:
    pairs = [(str(label), float(value or 0)) for label, value in pairs if str(label)]
    if not pairs:
        return ""
    max_value = max((value for _, value in pairs), default=1) or 1
    rows = ""
    for label, value in pairs[:12]:
        width = round(100 * value / max_value, 1)
        display_value = int(value) if float(value).is_integer() else round(value, 1)
        rows += f"""
        <div class="chart-row">
          <span class="chart-label">{escape(label)}</span>
          <div class="chart-track"><div class="chart-fill" style="width:{width}%"></div></div>
          <span class="chart-value">{display_value}{escape(suffix)}</span>
        </div>"""
    return f"""
    <div class="chart-card">
      <h2>{escape(title)}</h2>
      {rows}
    </div>"""


def _status_donut(title: str, pairs: list[tuple[str, float]]) -> str:
    pairs = [(str(label), float(value or 0)) for label, value in pairs if value]
    if not pairs:
        return ""
    total = sum(value for _, value in pairs) or 1
    colors = ["#43f6c8", "#7aa7ff", "#ff4fd8", "#ffc857", "#ff5c7a", "#8ad7ff"]
    offset = 25
    circles = ""
    legend = ""
    for idx, (label, value) in enumerate(pairs[:6]):
        pct = value / total * 100
        color = colors[idx % len(colors)]
        circles += (
            f'<circle class="donut-segment" r="16" cx="20" cy="20" '
            f'stroke="{color}" stroke-dasharray="{pct:.2f} {100 - pct:.2f}" '
            f'stroke-dashoffset="-{offset:.2f}" />'
        )
        offset += pct
        legend += f"""
        <span><i style="background:{color}"></i>{escape(label)}: {int(value)}</span>"""
    return f"""
    <div class="chart-card">
      <h2>{escape(title)}</h2>
      <div class="donut-wrap">
        <svg viewBox="0 0 40 40" class="donut">
          <circle class="donut-base" r="16" cx="20" cy="20" />
          {circles}
        </svg>
        <div class="donut-total">{int(total)}<small>total</small></div>
      </div>
      <div class="chart-legend">{legend}</div>
    </div>"""


def write_orbyt_html_dashboard(
    output_path: Path,
    summary: pd.DataFrame,
    trace: pd.DataFrame,
    impact: pd.DataFrame,
    readiness: pd.DataFrame,
    feature_trace: pd.DataFrame | None = None,
    category_coverage: pd.DataFrame | None = None,
    last_releases: pd.DataFrame | None = None,
    strategy_trace: pd.DataFrame | None = None,
    arch_coverage: pd.DataFrame | None = None,
) -> None:
    def table_html(df: pd.DataFrame, limit: int = 12, cols: list[str] | None = None) -> str:
        if df.empty:
            return "<p>No data</p>"
        view = df[cols] if cols and all(c in df.columns for c in cols) else df
        return view.head(limit).to_html(index=False, classes="data-table")

    def coverage_bars_html(df: pd.DataFrame, label_col: str, pct_col: str) -> str:
        if df.empty:
            return "<p>No data</p>"
        bars = ""
        for _, r in df.iterrows():
            pct = float(r[pct_col])
            bugs = int(r.get("Bugs_Issues_Count", 0) or 0)
            verified = int(r.get("Verified_Deployed_Items", 0) or 0)
            bars += f"""
            <div class="cat-row">
              <span class="cat-label">{r[label_col]}<br><small style="color:var(--muted)">verified:{verified} · bugs:{bugs}</small></span>
              <div class="cat-bar"><div class="cat-fill" style="width:{min(pct, 100)}%"></div></div>
              <span class="cat-pct">{pct}%</span>
            </div>"""
        return bars

    def last_releases_table_html(df: pd.DataFrame) -> str:
        if df.empty:
            return "<p>No data</p>"
        rows = ""
        for _, r in df.head(10).iterrows():
            rows += f"""
            <tr>
              <td>{escape(str(r.get("Release_Label", "")))}</td>
              <td>{escape(str(r.get("Release_Date", "")))}</td>
              <td>{escape(str(r.get("Environment", "")))}</td>
              <td>{escape(str(r.get("Release_Status", "")))}</td>
              <td>{escape(str(r.get("CHP_Items_Deployed", "")))}</td>
              <td>{escape(str(r.get("Features_Touched_Count", "")))}</td>
              <td>{_features_touched_bullets(str(r.get("Features_Touched", "")))}</td>
              <td>{escape(str(r.get("Categories_Affected", "")))}</td>
              <td>{escape(str(r.get("Go_No_Go", "")))}</td>
            </tr>"""
        return f"""
        <table class="data-table release-table">
          <thead>
            <tr>
              <th>Release</th>
              <th>Date</th>
              <th>Environment</th>
              <th>Status</th>
              <th>CHP Items</th>
              <th>Features Count</th>
              <th>Features Touched</th>
              <th>Categories Affected</th>
              <th>Go/No-Go</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    kpi_cards = ""
    for _, row in summary.iterrows():
        kpi_cards += f"""
        <div class="kpi-card">
          <div class="kpi-label">{row['KPI']}</div>
          <div class="kpi-value">{row['Value']}</div>
        </div>"""

    untested = int((trace["Traceability_Status"] == "UNTESTED").sum()) if not trace.empty else 0
    tested = (
        int((trace["Traceability_Status"] != "UNTESTED").sum())
        if not trace.empty
        else 0
    )
    coverage = round(100 * tested / max(len(trace), 1), 1) if not trace.empty else 0
    trace_recent = (
        trace.sort_values(
            ["Last_Release_Date", "Release_Count", "Verified_Pass_Count"],
            ascending=[False, False, False],
            na_position="last",
        )
        if not trace.empty
        else trace
    )
    impact_recent = impact
    readiness_recent = readiness

    feat_total = len(feature_trace) if feature_trace is not None and not feature_trace.empty else 0
    feat_traced = (
        int((feature_trace["Traceability_Status"] != "UNTESTED").sum())
        if feat_total
        else 0
    )
    feat_coverage = round(100 * feat_traced / max(feat_total, 1), 1) if feat_total else 0

    trace_status_pairs = []
    if not trace.empty and "Traceability_Status" in trace.columns:
        trace_status_pairs = list(trace["Traceability_Status"].value_counts().items())
    readiness_pairs = []
    if not readiness.empty and "Go_No_Go" in readiness.columns:
        readiness_pairs = list(readiness["Go_No_Go"].value_counts().items())
    risk_pairs = []
    if not impact.empty and "Risk_Level" in impact.columns:
        risk_pairs = list(impact["Risk_Level"].value_counts().items())
    category_pairs = []
    if category_coverage is not None and not category_coverage.empty:
        category_pairs = [
            (str(r["Label"]), float(r["Coverage_%"]))
            for _, r in category_coverage.sort_values("Coverage_%", ascending=False).head(10).iterrows()
        ]
    charts_section = f"""
  <section class="charts-grid">
    {_status_donut("Traceability Status", trace_status_pairs)}
    {_status_donut("Release Readiness", readiness_pairs)}
    {_status_donut("Impact Risk", risk_pairs)}
    {_inline_bar_chart("Top Sitemap Coverage", category_pairs, "%")}
  </section>"""

    category_section = ""
    if category_coverage is not None and not category_coverage.empty:
        cat_display = category_coverage.copy()
        if "Label" not in cat_display.columns:
            cat_display["Label"] = cat_display.apply(
                lambda r: f"{r['Site_Category']}"
                + (f" › {r['Site_Subcategory']}" if r.get("Site_Subcategory") else ""),
                axis=1,
            )
        cat_display = cat_display.sort_values(
            ["Verified_Deployed_Items", "Bugs_Issues_Count", "Coverage_%", "Feature_Count"],
            ascending=[False, False, False, False],
        )
        cat_limit = len(cat_display)
        category_section = f"""
  <section class="panels">
    <div class="panel" style="grid-column: 1 / -1;">
      <h2>Overall Test Coverage by Sitemap Category</h2>
      <p>Full Chip1 sitemap ({cat_limit} areas) · verified/passed deployed items count as tested · bug/issue counts per area</p>
      {coverage_bars_html(cat_display, "Label", "Coverage_%")}
      {table_html(cat_display, cat_limit, ["Site_Category", "Site_Subcategory", "Feature_Count", "Traced_Features", "Items_Tested", "Verified_Deployed_Items", "Coverage_Evidence_Items", "Bugs_Issues_Count", "QE_Verified_Features", "Coverage_Status", "Coverage_%"])}
    </div>
  </section>"""

    feature_section = ""
    if feature_trace is not None and not feature_trace.empty:
        feat_view = feature_trace.sort_values(
            ["Last_Release_Date", "Release_Count", "Verified_Pass_Count"],
            ascending=[False, False, False],
            na_position="last",
        )
        feature_section = f"""
  <section class="panels">
    <div class="panel" style="grid-column: 1 / -1;">
      <h2>Feature Traceability (Sitemap Categories)</h2>
      <p>{feat_coverage}% feature coverage ({feat_traced} of {feat_total}) · sorted by most recent release activity</p>
      <div class="coverage-bar"><div class="coverage-fill feature-fill"></div></div>
      {table_html(feat_view, 30, ["Feature_ID", "Feature_Name", "Site_Category", "Site_Subcategory", "Traceability_Status", "QE_Verified", "Last_Release_Date", "Release_Count", "Verified_Pass_Count"])}
    </div>
  </section>"""

    releases_section = ""
    if last_releases is not None and not last_releases.empty:
        releases_section = f"""
  <section class="panels">
    <div class="panel" style="grid-column: 1 / -1;">
      <h2>Last 10 Releases Traceability</h2>
      {last_releases_table_html(last_releases)}
    </div>
  </section>"""

    strategy_section = ""
    if strategy_trace is not None and not strategy_trace.empty:
        strat_cov = int((strategy_trace["Traceability_Status"] == "COVERED").sum())
        strategy_section = f"""
  <section style="padding: 0 2.5rem 1.5rem;">
    <div class="panel">
      <h2>Data Integration Testing Strategy</h2>
      <p class="flow-caption">DB Tables · External API · Flat Files → Validation → Transformation → Error Handling → Target Store</p>
      <div class="flow-diagram">
        <div class="flow-node source">DB Tables</div>
        <div class="flow-node source">External API</div>
        <div class="flow-node source">Flat Files</div>
        <div class="flow-arrow">↓</div>
        <div class="flow-node process">Validation Engine</div>
        <div class="flow-node process">Transformation Logic</div>
        <div class="flow-node process">Error Handling</div>
        <div class="flow-arrow">↓</div>
        <div class="flow-node target">Target Data Store</div>
      </div>
      <p>{strat_cov} of {len(strategy_trace)} strategy scenarios linked to release evidence</p>
      <div class="matrix-links">
        <a href="{_matrix_page_name("08_Strategy_Traceability_Matrix")}">Strategy Traceability</a>
        <a href="{_matrix_page_name("09_Architecture_Coverage_Matrix")}">Architecture Coverage</a>
      </div>
    </div>
  </section>
  <section class="panels">
    <div class="panel" style="grid-column: 1 / -1;">
      <h2>Strategy Scenario Traceability</h2>
      {table_html(strategy_trace.sort_values(["Release_Match_Count", "Req_Match_Count"], ascending=[False, False])[["Scenario_ID", "Scenario_Title", "Traceability_Status", "Release_Match_Count", "Req_Match_Count"]], 10)}
    </div>
  </section>"""

    arch_panel = ""
    if arch_coverage is not None and not arch_coverage.empty:
        arch_panel = f"""
    <div class="panel">
      <h2>Architecture Node Coverage</h2>
      {table_html(arch_coverage[["Node_Label", "Scenario_Coverage", "Scenarios_Testing_Node", "Impact_if_Fails"]])}
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ORBYT Test Matrix Dashboard</title>
  <style>
    :root {{
      --bg: #050914;
      --panel: rgba(9, 18, 34, 0.88);
      --panel-strong: rgba(12, 27, 48, 0.96);
      --line: rgba(123, 252, 255, 0.18);
      --accent: #43f6c8;
      --accent2: #7aa7ff;
      --accent3: #ff4fd8;
      --text: #eef7ff;
      --muted: #9db1c8;
      --warn: #ffc857;
      --danger: #ff5c7a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background-color: var(--bg);
      background-image:
        linear-gradient(115deg, rgba(5,9,20,0.96), rgba(6,16,31,0.9) 46%, rgba(13,11,29,0.94)),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1600' height='900' viewBox='0 0 1600 900'%3E%3Crect width='1600' height='900' fill='%23030a14'/%3E%3Cg fill='none' stroke='%2335f2d0' stroke-opacity='.26' stroke-width='1.2'%3E%3Cpath d='M0 180h220l70 70h260l80-80h330l70 70h570'/%3E%3Cpath d='M0 540h360l70-70h210l90 90h310l60-60h500'/%3E%3Cpath d='M230 0v220m420-220v170m530-170v250M980 900V630M410 900V650m850 250V610'/%3E%3C/g%3E%3Cg fill='%237aa7ff' fill-opacity='.72'%3E%3Ccircle cx='220' cy='180' r='5'/%3E%3Ccircle cx='550' cy='250' r='4'/%3E%3Ccircle cx='960' cy='170' r='5'/%3E%3Ccircle cx='430' cy='470' r='5'/%3E%3Ccircle cx='730' cy='560' r='4'/%3E%3Ccircle cx='1100' cy='500' r='5'/%3E%3C/g%3E%3Cg fill='%23ff4fd8' fill-opacity='.45'%3E%3Ccircle cx='1280' cy='240' r='3'/%3E%3Ccircle cx='650' cy='170' r='3'/%3E%3Ccircle cx='1260' cy='610' r='3'/%3E%3C/g%3E%3C/svg%3E");
      background-attachment: fixed;
      background-size: cover;
      color: var(--text);
      min-height: 100vh;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: center;
      padding: 1.5rem 2.5rem 1rem;
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(18px);
    }}
    .brand {{ display: flex; align-items: center; gap: 0.9rem; }}
    .orbyt-logo {{
      width: 46px;
      height: 46px;
      border: 1px solid rgba(67,246,200,0.65);
      border-radius: 50%;
      display: grid;
      place-items: center;
      color: var(--accent);
      font-weight: 800;
      letter-spacing: 0;
      box-shadow: 0 0 22px rgba(67,246,200,0.26), inset 0 0 20px rgba(122,167,255,0.16);
      position: relative;
      background: rgba(5, 13, 27, 0.7);
    }}
    .orbyt-logo::before {{
      content: "";
      position: absolute;
      width: 60px;
      height: 18px;
      border: 1px solid rgba(255,79,216,0.62);
      border-radius: 50%;
      transform: rotate(-24deg);
    }}
    h1 {{
      margin: 0;
      font-size: 1.75rem;
      background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent3));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .subtitle {{ color: var(--muted); margin-top: 0.35rem; }}
    .download-hub {{
      color: #03111b;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      text-decoration: none;
      padding: 0.55rem 0.85rem;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 700;
      white-space: nowrap;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 1rem;
      padding: 1.5rem 2.5rem;
    }}
    .kpi-card {{
      background: var(--panel);
      border-radius: 8px;
      padding: 1rem 1.25rem;
      border: 1px solid var(--line);
      box-shadow: 0 14px 32px rgba(0,0,0,0.28);
    }}
    .kpi-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
    .kpi-value {{ font-size: 1.6rem; font-weight: 700; margin-top: 0.35rem; color: var(--accent); }}
    .panels {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; padding: 0 2.5rem 2.5rem; }}
    @media (max-width: 1100px) {{ .panels {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 760px) {{
      header {{ align-items: flex-start; flex-direction: column; padding-left: 1rem; padding-right: 1rem; }}
      .kpi-grid, .charts-grid, .panels, section[style] {{ padding-left: 1rem !important; padding-right: 1rem !important; }}
    }}
    .panel {{
      background: var(--panel);
      border-radius: 8px;
      padding: 1.25rem;
      border: 1px solid var(--line);
      box-shadow: 0 18px 46px rgba(0,0,0,0.24);
      backdrop-filter: blur(16px);
      overflow-x: auto;
    }}
    .panel h2 {{ margin: 0 0 1rem; font-size: 1rem; color: var(--accent); }}
    .coverage-bar {{
      height: 10px;
      background: rgba(255,255,255,0.08);
      border-radius: 6px;
      overflow: hidden;
      margin: 0.5rem 0 1rem;
    }}
    .coverage-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
    }}
    .item-fill {{ width: {coverage}%; }}
    .feature-fill {{ width: {feat_coverage}%; }}
    .cat-row {{
      display: grid;
      grid-template-columns: 200px 1fr 48px;
      gap: 0.75rem;
      align-items: center;
      margin-bottom: 0.5rem;
      font-size: 0.8rem;
    }}
    .cat-label {{ color: var(--text); }}
    .cat-bar {{
      height: 8px;
      background: rgba(255,255,255,0.08);
      border-radius: 4px;
      overflow: hidden;
    }}
    .cat-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent2), var(--accent));
    }}
    .cat-pct {{ color: var(--muted); text-align: right; }}
    .status-pill {{
      display: inline-block;
      padding: 0.15rem 0.45rem;
      border-radius: 4px;
      font-size: 0.7rem;
      font-weight: 600;
    }}
    .data-table {{
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
      font-size: 0.8rem;
    }}
    .data-table th, .data-table td {{
      padding: 0.5rem 0.6rem;
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }}
    .data-table th {{ color: var(--muted); font-weight: 600; }}
    .release-table td:nth-child(7) {{ min-width: 360px; }}
    .feature-bullets {{
      margin: 0;
      padding-left: 1rem;
      color: var(--text);
    }}
    .feature-bullets li {{ margin: 0.18rem 0; }}
    .muted {{ color: var(--muted); }}
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
      padding: 0 2.5rem 1.5rem;
    }}
    .chart-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 1rem;
      box-shadow: 0 18px 46px rgba(0,0,0,0.24);
      backdrop-filter: blur(16px);
      min-height: 180px;
    }}
    .chart-card h2 {{ margin: 0 0 0.9rem; color: var(--accent); font-size: 0.95rem; }}
    .chart-row {{
      display: grid;
      grid-template-columns: minmax(96px, 150px) 1fr 48px;
      gap: 0.65rem;
      align-items: center;
      margin: 0.5rem 0;
      font-size: 0.78rem;
    }}
    .chart-label {{
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .chart-track {{
      height: 8px;
      border-radius: 5px;
      background: rgba(255,255,255,0.08);
      overflow: hidden;
    }}
    .chart-fill {{ height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent3)); }}
    .chart-value {{ text-align: right; color: var(--text); }}
    .donut-wrap {{ display: grid; place-items: center; position: relative; min-height: 96px; }}
    .donut {{ width: 104px; height: 104px; transform: rotate(-90deg); }}
    .donut-base {{ fill: transparent; stroke: rgba(255,255,255,0.08); stroke-width: 6; }}
    .donut-segment {{ fill: transparent; stroke-width: 6; }}
    .donut-total {{
      position: absolute;
      display: grid;
      place-items: center;
      font-size: 1.25rem;
      font-weight: 800;
      color: var(--accent);
    }}
    .donut-total small {{ display: block; color: var(--muted); font-size: 0.62rem; font-weight: 600; }}
    .chart-legend {{ display: flex; flex-wrap: wrap; gap: 0.45rem 0.75rem; margin-top: 0.75rem; font-size: 0.75rem; color: var(--muted); }}
    .chart-legend span {{ display: inline-flex; align-items: center; gap: 0.28rem; }}
    .chart-legend i {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
    .matrix-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 1rem;
    }}
    .matrix-links a {{
      color: #03111b;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      text-decoration: none;
      padding: 0.35rem 0.75rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .flow-caption {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 1rem; }}
    .flow-diagram {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem;
      margin-bottom: 1rem;
    }}
    .flow-node {{
      padding: 0.4rem 0.7rem; border-radius: 8px; font-size: 0.75rem; font-weight: 600;
    }}
    .flow-node.source {{ background: rgba(108,92,231,0.25); border: 1px solid var(--accent2); }}
    .flow-node.process {{ background: rgba(0,212,170,0.15); border: 1px solid var(--accent); }}
    .flow-node.target {{ background: rgba(243,156,18,0.2); border: 1px solid var(--warn); }}
    .flow-arrow {{ color: var(--muted); font-size: 1.1rem; width: 100%; text-align: center; }}
    footer {{ text-align: center; color: var(--muted); font-size: 0.75rem; padding: 1rem; }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="orbyt-logo" aria-label="ORBYT logo">O</div>
      <div>
        <h1>ORBYT Test Matrix Dashboard</h1>
        <p class="subtitle">Complex Test Generator Matrix · Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
      </div>
    </div>
    <a class="download-hub" href="ORBYT_Downloads.html">Download Hub</a>
  </header>
  <section class="kpi-grid">{kpi_cards}</section>
  {charts_section}
  <section style="padding: 0 2.5rem 1rem;">
    <div class="panel">
      <h2>Overall Test Coverage</h2>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;">
        <div>
          <p><strong>All requirements</strong> — {coverage}% ({tested} / {len(trace)})</p>
          <div class="coverage-bar"><div class="coverage-fill item-fill"></div></div>
        </div>
        <div>
          <p><strong>Features (sitemap)</strong> — {feat_coverage}% ({feat_traced} / {feat_total})</p>
          <div class="coverage-bar"><div class="coverage-fill feature-fill"></div></div>
        </div>
      </div>
      <p style="color: var(--warn); margin-top:0.75rem;">{untested} item-level untested gaps</p>
    </div>
  </section>
  {category_section}
  {feature_section}
  {releases_section}
  {strategy_section}
  <section style="padding: 0 2.5rem;">
    <div class="panel">
      <h2>Item-Level Coverage</h2>
      <p>{coverage}% traced to releases ({tested} of {len(trace)} requirements)</p>
      <div class="coverage-bar"><div class="coverage-fill item-fill"></div></div>
      <div class="matrix-links">
        <a href="{_matrix_page_name("01_Requirement_Testing_Traceability_Matrix")}">Item Traceability</a>
        <a href="{_matrix_page_name("01b_Feature_Level_Traceability_Matrix")}">Feature Traceability</a>
        <a href="{_matrix_page_name("02_Impact_Analysis_Matrix")}">Impact</a>
        <a href="{_matrix_page_name("03_AI_Powered_Validation_Matrix")}">AI Validation</a>
        <a href="{_matrix_page_name("04_Automation_Stability_Matrix")}">Automation</a>
        <a href="{_matrix_page_name("05_Release_Readiness_Matrix")}">Readiness</a>
        <a href="{_matrix_page_name("06_Cross_Platform_Sync_Validation_Matrix")}">Cross-Platform</a>
        <a href="ORBYT_Complete_Matrices.html">Full Excel</a>
      </div>
    </div>
  </section>
  <section class="panels">
    <div class="panel">
      <h2>Top Impact Risks</h2>
      <p class="flow-caption">Sorted by impact score and recent release activity</p>
      {table_html(impact_recent[["Req_ID", "Req_Name", "Impact_Score", "Risk_Level", "Last_Release_Date"]] if not impact_recent.empty and "Last_Release_Date" in impact_recent.columns else (impact_recent[["Req_ID", "Req_Name", "Impact_Score", "Risk_Level"]] if not impact_recent.empty else impact_recent), 15)}
    </div>
    <div class="panel">
      <h2>Release Readiness</h2>
      <p class="flow-caption">Most recent releases first</p>
      {table_html(readiness_recent[["Release_Label", "Release_Date", "Readiness_Score", "Go_No_Go", "Open_Gaps"]] if not readiness_recent.empty else readiness_recent, 15)}
    </div>
    {arch_panel}
    <div class="panel" style="grid-column: 1 / -1;">
      <h2>Traceability Snapshot</h2>
      <p class="flow-caption">Latest verified/deployed requirements first</p>
      {table_html(trace_recent[["Req_ID", "Req_Name", "Site_Category", "Traceability_Status", "QE_Verified", "Last_Release_Date", "Release_Count"]] if not trace_recent.empty else trace_recent, 20)}
    </div>
  </section>
  <footer>ORBYT · Altir Hackathon Test Matrix Generator</footer>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


def write_downloads_html_page(output_path: Path, matrices: dict[str, pd.DataFrame]) -> None:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = [
        """
        <article class="download-card" id="ORBYT_Complete_Matrices">
          <div>
            <h2>ORBYT Complete Matrices</h2>
            <p>All generated matrices in one workbook.</p>
          </div>
          <div class="actions">
            <a href="ORBYT_Complete_Matrices.html">View</a>
            <a download href="ORBYT_Complete_Matrices.xlsx">Download Excel</a>
          </div>
        </article>"""
    ]
    for name, df in matrices.items():
        label = escape(name.replace("_", " "))
        detail_href = _matrix_page_name(name) if name in MATRIX_PAGE_CONFIG else "ORBYT_Downloads.html"
        rows.append(
            f"""
        <article class="download-card" id="{escape(name)}">
          <div>
            <h2>{label}</h2>
            <p>{len(df)} rows · Excel and CSV available.</p>
          </div>
          <div class="actions">
            <a href="{escape(detail_href)}">View</a>
            <a download href="{escape(name)}.xlsx">Excel</a>
            <a download href="{escape(name)}.csv">CSV</a>
          </div>
        </article>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ORBYT Matrix Downloads</title>
  <style>
    :root {{
      --bg: #050914;
      --panel: rgba(9, 18, 34, 0.9);
      --line: rgba(123, 252, 255, 0.18);
      --accent: #43f6c8;
      --accent2: #7aa7ff;
      --accent3: #ff4fd8;
      --text: #eef7ff;
      --muted: #9db1c8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      background-color: var(--bg);
      background-image:
        linear-gradient(115deg, rgba(5,9,20,0.96), rgba(6,16,31,0.9) 46%, rgba(13,11,29,0.94)),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1600' height='900' viewBox='0 0 1600 900'%3E%3Crect width='1600' height='900' fill='%23030a14'/%3E%3Cg fill='none' stroke='%2335f2d0' stroke-opacity='.26' stroke-width='1.2'%3E%3Cpath d='M0 180h220l70 70h260l80-80h330l70 70h570'/%3E%3Cpath d='M0 540h360l70-70h210l90 90h310l60-60h500'/%3E%3Cpath d='M230 0v220m420-220v170m530-170v250M980 900V630M410 900V650m850 250V610'/%3E%3C/g%3E%3Cg fill='%237aa7ff' fill-opacity='.72'%3E%3Ccircle cx='220' cy='180' r='5'/%3E%3Ccircle cx='550' cy='250' r='4'/%3E%3Ccircle cx='960' cy='170' r='5'/%3E%3Ccircle cx='430' cy='470' r='5'/%3E%3Ccircle cx='730' cy='560' r='4'/%3E%3Ccircle cx='1100' cy='500' r='5'/%3E%3C/g%3E%3Cg fill='%23ff4fd8' fill-opacity='.45'%3E%3Ccircle cx='1280' cy='240' r='3'/%3E%3Ccircle cx='650' cy='170' r='3'/%3E%3Ccircle cx='1260' cy='610' r='3'/%3E%3C/g%3E%3C/svg%3E");
      background-size: cover;
      background-attachment: fixed;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 1.5rem 2.5rem 1rem;
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(18px);
    }}
    .brand {{ display: flex; align-items: center; gap: 0.9rem; }}
    .orbyt-logo {{
      width: 46px;
      height: 46px;
      border: 1px solid rgba(67,246,200,0.65);
      border-radius: 50%;
      display: grid;
      place-items: center;
      color: var(--accent);
      font-weight: 800;
      box-shadow: 0 0 22px rgba(67,246,200,0.26), inset 0 0 20px rgba(122,167,255,0.16);
      position: relative;
      background: rgba(5, 13, 27, 0.7);
    }}
    .orbyt-logo::before {{
      content: "";
      position: absolute;
      width: 60px;
      height: 18px;
      border: 1px solid rgba(255,79,216,0.62);
      border-radius: 50%;
      transform: rotate(-24deg);
    }}
    h1 {{
      margin: 0;
      font-size: 1.7rem;
      background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent3));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .subtitle {{ color: var(--muted); margin: 0.35rem 0 0; }}
    .back-link, .download-card a {{
      color: #03111b;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      text-decoration: none;
      padding: 0.55rem 0.85rem;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 700;
      white-space: nowrap;
    }}
    main {{
      display: grid;
      gap: 1rem;
      padding: 1.5rem 2.5rem 2.5rem;
    }}
    .download-card {{
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 1rem 1.1rem;
      box-shadow: 0 18px 46px rgba(0,0,0,0.24);
      backdrop-filter: blur(16px);
    }}
    .download-card h2 {{ margin: 0; font-size: 1rem; color: var(--accent); }}
    .download-card p {{ margin: 0.35rem 0 0; color: var(--muted); font-size: 0.85rem; }}
    .actions {{ display: flex; gap: 0.5rem; flex-wrap: wrap; justify-content: flex-end; }}
    @media (max-width: 760px) {{
      header, .download-card {{ align-items: flex-start; flex-direction: column; }}
      main, header {{ padding-left: 1rem; padding-right: 1rem; }}
      .actions {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="orbyt-logo" aria-label="ORBYT logo">O</div>
      <div>
        <h1>ORBYT Matrix Downloads</h1>
        <p class="subtitle">Generated {generated}</p>
      </div>
    </div>
    <a class="back-link" href="ORBYT_Test_Matrix_Dashboard.html">Back to Dashboard</a>
  </header>
  <main>
    {''.join(rows)}
  </main>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")


def write_matrix_detail_pages(output_dir: Path, matrices: dict[str, pd.DataFrame]) -> None:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    def render_page(title: str, body: str, actions: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escape(title)} · ORBYT</title>
  <style>
    :root {{
      --bg: #050914;
      --panel: rgba(9, 18, 34, 0.9);
      --line: rgba(123, 252, 255, 0.18);
      --accent: #43f6c8;
      --accent2: #7aa7ff;
      --accent3: #ff4fd8;
      --text: #eef7ff;
      --muted: #9db1c8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      background-color: var(--bg);
      background-image:
        linear-gradient(115deg, rgba(5,9,20,0.96), rgba(6,16,31,0.9) 46%, rgba(13,11,29,0.94)),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1600' height='900' viewBox='0 0 1600 900'%3E%3Crect width='1600' height='900' fill='%23030a14'/%3E%3Cg fill='none' stroke='%2335f2d0' stroke-opacity='.26' stroke-width='1.2'%3E%3Cpath d='M0 180h220l70 70h260l80-80h330l70 70h570'/%3E%3Cpath d='M0 540h360l70-70h210l90 90h310l60-60h500'/%3E%3C/g%3E%3Cg fill='%237aa7ff' fill-opacity='.72'%3E%3Ccircle cx='220' cy='180' r='5'/%3E%3Ccircle cx='550' cy='250' r='4'/%3E%3Ccircle cx='960' cy='170' r='5'/%3E%3Ccircle cx='430' cy='470' r='5'/%3E%3Ccircle cx='730' cy='560' r='4'/%3E%3Ccircle cx='1100' cy='500' r='5'/%3E%3C/g%3E%3C/svg%3E");
      background-size: cover;
      background-attachment: fixed;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: center;
      padding: 1.5rem 2.5rem 1rem;
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(18px);
    }}
    h1 {{
      margin: 0;
      font-size: 1.65rem;
      background: linear-gradient(90deg, var(--accent), var(--accent2), var(--accent3));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .subtitle {{ color: var(--muted); margin: 0.35rem 0 0; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: flex-end; }}
    a.button {{
      color: #03111b;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      text-decoration: none;
      padding: 0.55rem 0.85rem;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 700;
      white-space: nowrap;
    }}
    main {{ padding: 1.5rem 2.5rem 2.5rem; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 1rem;
      box-shadow: 0 18px 46px rgba(0,0,0,0.24);
      backdrop-filter: blur(16px);
      overflow-x: auto;
    }}
    .data-table {{
      width: 100%;
      min-width: 900px;
      border-collapse: collapse;
      font-size: 0.82rem;
    }}
    .data-table th, .data-table td {{
      padding: 0.58rem 0.65rem;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid rgba(255,255,255,0.07);
    }}
    .data-table th {{
      color: var(--accent);
      font-weight: 700;
      background: rgba(67,246,200,0.06);
      position: sticky;
      top: 0;
    }}
    .data-table td {{ color: var(--text); }}
    .empty {{ color: var(--muted); }}
    .matrix-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }}
    .matrix-card {{
      background: rgba(255,255,255,0.035);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 1rem;
    }}
    .matrix-card h2 {{ margin: 0 0 0.35rem; font-size: 1rem; color: var(--accent); }}
    .matrix-card p {{ color: var(--muted); margin: 0 0 0.75rem; font-size: 0.85rem; }}
    @media (max-width: 760px) {{
      header {{ align-items: flex-start; flex-direction: column; padding-left: 1rem; padding-right: 1rem; }}
      main {{ padding-left: 1rem; padding-right: 1rem; }}
      .actions {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>{escape(title)}</h1>
      <p class="subtitle">ORBYT matrix view · Generated {generated}</p>
    </div>
    <div class="actions">
      <a class="button" href="ORBYT_Test_Matrix_Dashboard.html">Dashboard</a>
      <a class="button" href="ORBYT_Downloads.html">Download Hub</a>
      {actions}
    </div>
  </header>
  <main>
    <div class="panel">
      {body}
    </div>
  </main>
</body>
</html>"""

    for name, config in MATRIX_PAGE_CONFIG.items():
        if name not in matrices:
            continue
        df = matrices[name]
        fields = config["fields"]
        view = _safe_cols(df, fields)
        if view.empty:
            table = "<p class=\"empty\">No data available for this matrix.</p>"
        else:
            table = view.to_html(index=False, classes="data-table", escape=True)
        actions = f"""
      <a class="button" download href="{escape(name)}.xlsx">Download Excel</a>
      <a class="button" download href="{escape(name)}.csv">Download CSV</a>"""
        (output_dir / _matrix_page_name(name)).write_text(
            render_page(str(config["title"]), table, actions),
            encoding="utf-8",
        )

    cards = ""
    for name, df in matrices.items():
        title = MATRIX_PAGE_CONFIG.get(name, {}).get("title", name.replace("_", " "))
        view_link = _matrix_page_name(name) if name in MATRIX_PAGE_CONFIG else "ORBYT_Downloads.html"
        cards += f"""
        <article class="matrix-card">
          <h2>{escape(str(title))}</h2>
          <p>{len(df)} rows</p>
          <div class="actions">
            <a class="button" href="{escape(view_link)}">View</a>
            <a class="button" download href="{escape(name)}.xlsx">Excel</a>
            <a class="button" download href="{escape(name)}.csv">CSV</a>
          </div>
        </article>"""
    complete_actions = '<a class="button" download href="ORBYT_Complete_Matrices.xlsx">Download Workbook</a>'
    complete_body = f"<div class=\"matrix-grid\">{cards}</div>"
    (output_dir / "ORBYT_Complete_Matrices.html").write_text(
        render_page("ORBYT Complete Matrices", complete_body, complete_actions),
        encoding="utf-8",
    )


def generate_all_matrices(
    req_folder: str | Path = "input",
    release_csv_folder: str | Path = "release_notes/release_notes_csv",
    output_dir: str | Path = "output",
) -> dict[str, pd.DataFrame]:
    req_folder = Path(req_folder)
    release_csv_folder = Path(release_csv_folder)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading requirements...")
    req = load_requirements(req_folder)
    print(f"  → {len(req)} unique CHP requirements")

    print("Loading release notes...")
    release_rows, chp_deploy = load_release_notes(release_csv_folder)
    print(f"  → {release_rows['Release_File'].nunique() if not release_rows.empty else 0} releases, {len(chp_deploy)} CHP deployments")

    print("Loading test strategy (if present)...")
    strategy, arch = load_test_strategy(req_folder)
    if not strategy.empty:
        print(f"  → {strategy['Scenario_ID'].nunique()} data-integration scenarios")

    print("Building matrices...")
    trace = build_traceability_matrix(req, chp_deploy, release_rows)
    feature_trace = build_feature_traceability_matrix(req, chp_deploy, trace, release_rows)
    print(f"  → {len(feature_trace)} features in feature-level traceability")
    story_map = build_story_to_feature_map(req)
    category_coverage = build_sitemap_category_coverage(feature_trace, release_rows, trace)
    impact = build_impact_matrix(req, chp_deploy, trace)
    ai = build_ai_validation_matrix(req, chp_deploy, trace)
    automation = build_automation_stability_matrix(release_rows)
    readiness = build_release_readiness_matrix(release_rows, trace, chp_deploy)
    last_releases = build_last_n_releases_traceability(
        release_rows, chp_deploy, feature_trace, readiness, story_map, n=10
    )
    cross_platform = build_cross_platform_matrix(release_rows)
    strategy_trace = build_strategy_traceability_matrix(strategy, req, release_rows)
    arch_coverage = build_strategy_architecture_coverage(strategy, arch)
    dashboard = build_dashboard_summary(
        trace, impact, ai, automation, readiness, cross_platform, strategy_trace, feature_trace
    )

    matrices = {
        "01_Requirement_Testing_Traceability_Matrix": trace,
        "01b_Feature_Level_Traceability_Matrix": feature_trace,
        "10_Sitemap_Category_Coverage": category_coverage,
        "11_Last_10_Releases_Traceability": last_releases,
        "02_Impact_Analysis_Matrix": impact,
        "03_AI_Powered_Validation_Matrix": ai,
        "04_Automation_Stability_Matrix": automation,
        "05_Release_Readiness_Matrix": readiness,
        "06_Cross_Platform_Sync_Validation_Matrix": cross_platform,
        "07_Dashboard_Summary_Matrix": dashboard,
    }
    if not strategy_trace.empty:
        matrices["08_Strategy_Traceability_Matrix"] = strategy_trace
        matrices["09_Architecture_Coverage_Matrix"] = arch_coverage

    for name, df in matrices.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"  ✓ {path.name} ({len(df)} rows)")
        item_excel_path = output_dir / f"{name}.xlsx"
        with pd.ExcelWriter(item_excel_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=name[:31], index=False)
        print(f"  ✓ {item_excel_path.name}")

    excel_path = output_dir / "ORBYT_Complete_Matrices.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        for name, df in matrices.items():
            sheet = name[:31]
            df.to_excel(writer, sheet_name=sheet, index=False)
    print(f"  ✓ {excel_path.name}")

    html_path = output_dir / "ORBYT_Test_Matrix_Dashboard.html"
    write_orbyt_html_dashboard(
        html_path,
        dashboard,
        trace,
        impact,
        readiness,
        feature_trace,
        category_coverage,
        last_releases,
        strategy_trace,
        arch_coverage,
    )
    print(f"  ✓ {html_path.name}")

    downloads_path = output_dir / "ORBYT_Downloads.html"
    write_downloads_html_page(downloads_path, matrices)
    print(f"  ✓ {downloads_path.name}")

    write_matrix_detail_pages(output_dir, matrices)
    print("  ✓ matrix detail HTML pages")

    return matrices


if __name__ == "__main__":
    generate_all_matrices()
