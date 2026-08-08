#!/usr/bin/env python3
"""
Import sector FAQ seeds from Kaggle datasets into data/kaggle_faqs.json.

Requires Kaggle API credentials (one of):
  - KAGGLE_USERNAME + KAGGLE_KEY env vars
  - ~/.kaggle/kaggle.json

Usage:
  python scripts/kaggle_import.py
  python scripts/kaggle_import.py --vertical industrial
  python scripts/kaggle_import.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCES_PATH = ROOT / "data" / "kaggle_sources.json"
OUTPUT_PATH = ROOT / "data" / "kaggle_faqs.json"

VERTICALS = ("industrial", "construction", "logistics", "financial", "property")

# Dutch templates per dataset type — keeps answers sector-appropriate
TEMPLATES: dict[str, tuple[str, str]] = {
    "maintenance_orders": (
        "We hebben een melding voor {asset} — hoe snel kunnen jullie langskomen?",
        "Storingsdienst werkdagen meestal binnen 4 uur. Stuur serienummer, symptoom ({issue}) "
        "en foto — dan plannen we een monteur met de juiste onderdelen.",
    ),
    "fleet_maintenance": (
        "Ons voertuig heeft onderhoud nodig ({issue}) — wat is de planning?",
        "We plannen onderhoud op basis van km-stand en urgentie. Stuur kenteken of voertuig-ID — "
        "dispatch bevestigt het eerstvolgende venster.",
    ),
    "logistics_delivery": (
        "Status van zending {ref} — wanneer wordt geleverd?",
        "Zending {ref} staat gepland voor levering op {eta}. Stuur je referentienummer voor track & trace.",
    ),
    "support_tickets": (
        "Ik heb een vraag over {category}: {issue}",
        "We nemen dit op in je dossier. Stuur relevante gegevens via WhatsApp — "
        "we bevestigen de volgende stap binnen één werkdag.",
    ),
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())[:200]


def _pick(row: dict, *keys: str) -> str:
    lower = {k.lower(): v for k, v in row.items()}
    for key in keys:
        val = lower.get(key.lower())
        if val:
            return _norm(str(val))
    return ""


def _keywords(*parts: str) -> list[str]:
    out: list[str] = []
    for part in parts:
        for token in re.split(r"[^a-zA-Z0-9]+", part.lower()):
            if len(token) >= 4 and token not in out:
                out.append(token)
            if len(out) >= 6:
                return out
    return out or ["info", "vraag"]


def _entry(question: str, answer: str, keywords: list[str], source: str) -> dict:
    return {
        "keywords": keywords,
        "question": question,
        "answer": answer,
        "source": source,
    }


def rows_to_faqs(rows: list[dict], *, dtype: str, source: str, category_filter: list[str] | None) -> list[dict]:
    faqs: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if dtype == "maintenance_orders":
            asset = _pick(row, "machine_name", "machine", "asset", "equipment", "Machine_Name") or "machine"
            issue = _pick(row, "failure_description", "issue", "description", "Failure_Description") or "storing"
            q_tpl, a_tpl = TEMPLATES["maintenance_orders"]
            q = q_tpl.format(asset=asset, issue=issue)
            a = a_tpl.format(asset=asset, issue=issue)
            kw = _keywords(asset, issue, "storings", "onderhoud")
        elif dtype == "fleet_maintenance":
            issue = _pick(row, "maintenance_type", "issue", "description", "component") or "onderhoud"
            q_tpl, a_tpl = TEMPLATES["fleet_maintenance"]
            q = q_tpl.format(issue=issue)
            a = a_tpl.format(issue=issue)
            kw = _keywords(issue, "voertuig", "onderhoud")
        elif dtype == "logistics_delivery":
            ref = _pick(row, "shipment_id", "reference", "order_id", "tracking_number") or "onbekend"
            eta = _pick(row, "delivery_date", "eta", "scheduled_date") or "binnenkort"
            q_tpl, a_tpl = TEMPLATES["logistics_delivery"]
            q = q_tpl.format(ref=ref)
            a = a_tpl.format(ref=ref, eta=eta)
            kw = _keywords(ref, "zending", "levering", "track")
        else:
            category = _pick(row, "Category", "category", "Product", "Department") or "support"
            if category_filter and category.lower() not in {c.lower() for c in category_filter}:
                continue
            issue = _pick(row, "Subject", "subject", "Description", "description", "Ticket Subject") or category
            q_tpl, a_tpl = TEMPLATES["support_tickets"]
            q = q_tpl.format(category=category, issue=issue[:80])
            a = a_tpl.format(category=category, issue=issue[:80])
            kw = _keywords(category, issue)

        key = q.lower()
        if key in seen or len(q) < 15:
            continue
        seen.add(key)
        faqs.append(_entry(q, a, kw, source))
    return faqs


def download_dataset(slug: str, dest: Path) -> Path:
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:
        raise SystemExit(
            "Install kaggle: pip install kaggle\n"
            "Then set KAGGLE_USERNAME and KAGGLE_KEY or ~/.kaggle/kaggle.json"
        ) from exc

    api = KaggleApi()
    api.authenticate()
    owner, name = slug.split("/", 1)
    api.dataset_download_files(f"{owner}/{name}", path=str(dest), unzip=True, quiet=False)
    return dest


def find_csv_files(root: Path, glob_pattern: str) -> list[Path]:
    if glob_pattern == "*.csv":
        return sorted(root.rglob("*.csv"))
    pattern = glob_pattern.replace("*", "")
    return sorted(p for p in root.rglob("*.csv") if pattern.lower() in p.name.lower())


def read_csv_rows(path: Path, max_rows: int) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            rows.append(dict(row))
    return rows


def import_vertical(vertical: str, config: dict, *, dry_run: bool) -> list[dict]:
    datasets = config.get("datasets") or []
    merged: list[dict] = []
    for spec in datasets:
        slug = spec["slug"]
        target = spec.get("vertical_map") or vertical
        if target != vertical:
            continue
        dtype = spec.get("type", "support_tickets")
        max_rows = int(spec.get("max_rows", 100))
        glob_pattern = spec.get("file_glob", "*.csv")
        category_filter = spec.get("category_filter")
        source = f"kaggle:{slug.split('/')[-1]}"

        if dry_run:
            print(f"  [dry-run] would fetch {slug} -> {dtype} (max {max_rows} rows)")
            continue

        tmp = Path(tempfile.mkdtemp(prefix="kaggle_import_"))
        try:
            download_dataset(slug, tmp)
            csv_files = find_csv_files(tmp, glob_pattern)
            if not csv_files:
                print(f"  warning: no CSV for {slug} ({glob_pattern})", file=sys.stderr)
                continue
            rows: list[dict] = []
            for csv_path in csv_files[:3]:
                rows.extend(read_csv_rows(csv_path, max_rows - len(rows)))
                if len(rows) >= max_rows:
                    break
            faqs = rows_to_faqs(rows, dtype=dtype, source=source, category_filter=category_filter)
            print(f"  {slug}: {len(faqs)} FAQ entries")
            merged.extend(faqs)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return merged


def dedupe_entries(entries: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for entry in entries:
        q = str(entry.get("question", "")).strip().lower()
        if q and q not in seen:
            seen.add(q)
            out.append(entry)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Kaggle datasets into sector FAQs")
    parser.add_argument("--vertical", choices=VERTICALS, help="Import one vertical only")
    parser.add_argument("--dry-run", action="store_true", help="Show planned imports without downloading")
    parser.add_argument("--merge", action="store_true", default=True, help="Merge with existing kaggle_faqs.json")
    args = parser.parse_args()

    if not SOURCES_PATH.is_file():
        raise SystemExit(f"Missing {SOURCES_PATH}")

    sources = _load_json(SOURCES_PATH)
    existing = _load_json(OUTPUT_PATH) if OUTPUT_PATH.is_file() else {}
    targets = [args.vertical] if args.vertical else list(VERTICALS)

    if not args.dry_run and not (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")):
        kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
        if not kaggle_json.is_file():
            print(
                "No Kaggle credentials found. Ship data/kaggle_faqs.json as-is or set "
                "KAGGLE_USERNAME + KAGGLE_KEY.",
                file=sys.stderr,
            )
            sys.exit(1)

    out: dict[str, list[dict]] = {k: list(v) for k, v in existing.items()} if args.merge else {}

    for vertical in targets:
        cfg = sources.get(vertical)
        if not cfg:
            continue
        print(f"=== {vertical} ===")
        fresh = import_vertical(vertical, cfg, dry_run=args.dry_run)
        if args.dry_run:
            continue
        if fresh:
            combined = dedupe_entries((out.get(vertical) or []) + fresh)
            out[vertical] = combined[:12]
        elif vertical not in out:
            out[vertical] = []

    if args.dry_run:
        return

    OUTPUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({sum(len(v) for v in out.values())} entries total)")


if __name__ == "__main__":
    main()
