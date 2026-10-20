"""
Parse NIST OSCAL catalogs and baseline profiles into plain records.

Works with the official NIST SP 800-53 Rev 5 OSCAL JSON published at
https://github.com/usnistgov/oscal-content. The parser is deliberately
small: it extracts what ICARIS tracks (identifier, label, title, family,
parent, statement text, withdrawn status, baseline membership) and renders
parameter insertions as readable "[Assignment: ...]" / "[Selection: ...]"
text the way the published SP 800-53 PDF does.
"""
from __future__ import annotations

import gzip
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

BUNDLED_CATALOG = Path(__file__).resolve().parent / "data" / "nist_800_53_rev5.json.gz"

_PARAM_RE = re.compile(r"\{\{\s*insert:\s*param,\s*([\w.\-]+)\s*\}\}")


@dataclass
class ControlRecord:
    control_id: str          # OSCAL id, e.g. "ac-2.1"
    label: str               # display label, e.g. "AC-2(1)"
    title: str
    family: str              # "AC"
    parent_id: str | None    # "ac-2" for enhancements
    sort_key: str
    statement: str
    withdrawn: bool
    baselines: list[str] = field(default_factory=list)  # subset of low/moderate/high


@dataclass
class CatalogData:
    title: str
    version: str
    families: dict[str, str]           # "AC" -> "Access Control"
    controls: list[ControlRecord]

    def to_json(self) -> dict:
        return {
            "title": self.title,
            "version": self.version,
            "families": self.families,
            "controls": [asdict(c) for c in self.controls],
        }

    @classmethod
    def from_json(cls, data: dict) -> CatalogData:
        return cls(
            title=data["title"],
            version=data["version"],
            families=data["families"],
            controls=[ControlRecord(**c) for c in data["controls"]],
        )


def _prop(obj: dict, name: str, *, no_class: bool = False) -> str | None:
    for prop in obj.get("props", []):
        if prop.get("name") == name and (not no_class or "class" not in prop):
            return prop.get("value")
    return None


def _param_text(param: dict | None) -> str:
    if param is None:
        return "[Assignment: organization-defined value]"
    select = param.get("select")
    if select:
        choices = []
        for choice in select.get("choice", []):
            choices.append(_PARAM_RE.sub("[organization-defined value]", choice))
        prefix = "one or more" if select.get("how-many") == "one-or-more" else ""
        joined = "; ".join(choices)
        return f"[Selection ({prefix}): {joined}]" if prefix else f"[Selection: {joined}]"
    label = (param.get("label") or "value").strip()
    # NIST's Rev 5 parameter labels sometimes already begin with the phrase.
    if not label.lower().startswith("organization-defined"):
        label = f"organization-defined {label}"
    return f"[Assignment: {label}]"


def _render_parts(parts: list[dict], params: dict[str, dict], depth: int = 0) -> list[str]:
    lines: list[str] = []
    for part in parts:
        if part.get("name") not in ("statement", "item"):
            continue
        label = _prop(part, "label")
        prose = part.get("prose", "")
        prose = _PARAM_RE.sub(lambda m: _param_text(params.get(m.group(1))), prose)
        text = " ".join(x for x in (label, prose) if x).strip()
        if text:
            lines.append("  " * depth + text)
        lines.extend(_render_parts(part.get("parts", []), params, depth + (1 if text else 0)))
    return lines


def _walk(controls: list[dict], family: str, parent: str | None, out: list[ControlRecord]) -> None:
    for ctl in controls:
        params: dict[str, dict] = {}
        for param in ctl.get("params", []):
            params[param["id"]] = param
            alt = _prop(param, "alt-identifier")
            if alt:
                params[alt] = param
        statement_parts = [p for p in ctl.get("parts", []) if p.get("name") == "statement"]
        statement = "\n".join(_render_parts(statement_parts, params))
        out.append(
            ControlRecord(
                control_id=ctl["id"],
                label=_prop(ctl, "label", no_class=True) or ctl["id"].upper(),
                title=ctl.get("title", ""),
                family=family,
                parent_id=parent,
                sort_key=_prop(ctl, "sort-id") or ctl["id"],
                statement=statement,
                withdrawn=_prop(ctl, "status") == "withdrawn",
            )
        )
        _walk(ctl.get("controls", []), family, ctl["id"], out)


def parse_catalog(catalog_doc: dict) -> CatalogData:
    catalog = catalog_doc["catalog"]
    families: dict[str, str] = {}
    controls: list[ControlRecord] = []
    for group in catalog.get("groups", []):
        code = group["id"].upper()
        families[code] = group.get("title", code)
        _walk(group.get("controls", []), code, None, controls)
    meta = catalog.get("metadata", {})
    return CatalogData(
        title=meta.get("title", "OSCAL catalog"),
        version=str(meta.get("version", "")),
        families=families,
        controls=controls,
    )


def parse_profile_ids(profile_doc: dict) -> set[str]:
    """Return the control ids a baseline profile selects (include-controls/with-ids)."""
    ids: set[str] = set()
    for imp in profile_doc["profile"].get("imports", []):
        for include in imp.get("include-controls", []):
            ids.update(include.get("with-ids", []))
    return ids


def apply_baselines(data: CatalogData, baselines: dict[str, set[str]]) -> None:
    for record in data.controls:
        record.baselines = [name for name in ("low", "moderate", "high") if record.control_id in baselines.get(name, set())]


def load_json(path: Path) -> dict:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def load_bundled() -> CatalogData:
    return CatalogData.from_json(load_json(BUNDLED_CATALOG))


def write_bundle(data: CatalogData, path: Path = BUNDLED_CATALOG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as handle:
        json.dump(data.to_json(), handle, separators=(",", ":"))
