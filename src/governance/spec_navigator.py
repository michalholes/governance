from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from .type_aliases import JsonDict, JsonList
else:
    try:
        from .type_aliases import JsonDict, JsonList
    except ImportError:
        JsonDict: TypeAlias = dict[str, Any]
        JsonList: TypeAlias = list[JsonDict]

SEPARATOR = "-" * 72


def _load_jsonl(path: Path) -> JsonList:
    objects: JsonList = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                objects.append(json.loads(line))
    return objects


def _parse_applies_to(raw: str) -> set[str]:
    return {t.strip().upper() for t in raw.split("|") if t.strip()}


def _index(objects: JsonList) -> tuple[
    JsonDict | None,
    list[JsonDict],
    dict[str, JsonDict],
]:
    meta: JsonDict | None = None
    caps: list[JsonDict] = []
    rules: dict[str, JsonDict] = {}
    for obj in objects:
        t = obj.get("type")
        if t == "meta":
            meta = obj
        elif t == "capability":
            caps.append(obj)
        elif t == "rule":
            rules[str(obj.get("id", ""))] = obj
    return meta, caps, rules


def _all_tags(caps: list[JsonDict]) -> dict[str, list[str]]:
    """Return {tag: [cap_id, ...]} sorted."""
    tag_map: dict[str, list[str]] = {}
    for cap in caps:
        for tag in _parse_applies_to(cap.get("applies_to", "")):
            tag_map.setdefault(tag, []).append(str(cap.get("id", "")))
    return dict(sorted(tag_map.items()))


def cmd_list_tags(
    meta: JsonDict | None,
    caps: list[JsonDict],
    rules: dict[str, JsonDict],
) -> str:
    out: list[str] = []
    if meta:
        spec_id = meta.get("id", "")
        version = meta.get("version", "")
        out.append(f"spec: {spec_id}  version: {version}")
        out.append("")
    out.append(f"{'TAG':<20}  {'CAPS':>4}  {'RULES':>5}  CAPABILITY IDS")
    out.append(SEPARATOR)
    tag_map = _all_tags(caps)
    cap_by_id = {str(c.get("id", "")): c for c in caps}
    for tag, cap_ids in tag_map.items():
        rule_count = sum(
            len(cap_by_id[cid].get("triggers_rules", []))
            for cid in cap_ids
            if cid in cap_by_id
        )
        out.append(f"{tag:<20}  {len(cap_ids):>4}  {rule_count:>5}  {', '.join(cap_ids)}")
    out.append("")
    out.append(f"total capabilities: {len(caps)}  total rules: {len(rules)}")
    return "\n".join(out)


def cmd_query_tags(
    tags: list[str],
    caps: list[JsonDict],
    rules: dict[str, JsonDict],
) -> str:
    query = {t.upper() for t in tags}
    matched: list[JsonDict] = []
    for cap in caps:
        if _parse_applies_to(cap.get("applies_to", "")) & query:
            matched.append(cap)

    if not matched:
        return f"No capabilities found for tags: {sorted(query)}\n"

    out: list[str] = []
    out.append(f"query tags: {sorted(query)}")
    out.append("")

    seen_rule_ids: set[str] = set()
    total_rules = 0

    for cap in matched:
        cap_id = str(cap.get("id", ""))
        applies = cap.get("applies_to", "")
        rule_ids = [str(r) for r in cap.get("triggers_rules", [])]
        out.append(f"[{cap_id}]  applies_to: {applies}  rules: {len(rule_ids)}")
        out.append(SEPARATOR)
        for rid in rule_ids:
            rule = rules.get(rid)
            if rule is None:
                continue
            stmt = str(rule.get("statement", "")).strip()
            hp = rule.get("heading_path", "")
            section = hp.split(" > ")[-1] if " > " in hp else hp
            normativity = rule.get("normativity", "")
            prefix = f"[{normativity}] " if normativity else ""
            out.append(f"  {rid}")
            if section:
                out.append(f"    section: {section}")
            out.append(f"    {prefix}{stmt}")
            out.append("")
            if rid not in seen_rule_ids:
                seen_rule_ids.add(rid)
                total_rules += 1
        out.append("")

    out.append(SEPARATOR)
    out.append(
        f"matched {len(matched)} capability/capabilities  "
        f"unique rules: {total_rules}"
    )
    return "\n".join(out)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query a specification.jsonl by capability tags.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  spec_navigator.py governance/specification.jsonl --list-tags\n"
            "  spec_navigator.py governance/specification.jsonl --tags PLUGIN REGISTRY\n"
            "  spec_navigator.py governance/specification.jsonl --tags FILE_IO\n"
        ),
    )
    parser.add_argument("spec", help="Path to specification.jsonl")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list-tags",
        action="store_true",
        help="List all available capability tags with rule counts",
    )
    group.add_argument(
        "--tags",
        nargs="+",
        metavar="TAG",
        help="Return rules from capabilities matching any of the given tags",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args((argv or sys.argv)[1:])
    path = Path(args.spec)
    if not path.is_file():
        sys.stderr.write(f"error: file not found: {path}\n")
        return 1
    objects = _load_jsonl(path)
    meta, caps, rules = _index(objects)
    if not caps:
        sys.stderr.write("error: no capability objects found in spec\n")
        return 1
    if args.list_tags:
        sys.stdout.write(cmd_list_tags(meta, caps, rules) + "\n")
    else:
        sys.stdout.write(cmd_query_tags(args.tags, caps, rules) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
