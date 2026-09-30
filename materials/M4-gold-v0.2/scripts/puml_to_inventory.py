#!/usr/bin/env python3
"""puml_to_inventory.py — v0 (written with M4 so the gold CSVs come from an extractor).

Flattens a PlantUML class or activity diagram into the element CSV schema of
materials checklist §5.3. The SAME script must be used on gold and on agent
output. M8 still needs to harden it on the pilot outputs (see NOTES in
GOLD-NOTES.md, section "Extractor").

Usage:
  puml_to_inventory.py class    IN.puml OUT.csv [--tier-map MAP.csv]
  puml_to_inventory.py activity IN.puml OUT.csv [--tier-map MAP.csv]

Without --tier-map the `tier` column is left empty (agent output).
With --tier-map every element must have a tier, otherwise the script fails,
so no gold element can silently end up untiered.

Schemas
  class:    element_id, element_type, canonical_name, owner_class, detail, tier
            element_type in {class, attribute, relationship}
            class        detail = "" or "stereotype=enum"
            attribute    detail = "type=<T>"  |  "literal" (enum value)
            relationship canonical_name = "<From>-<To>"
                         detail = "<from>|<kind>|<to>|<mult_from>:<mult_to>"
  activity: element_id, element_type, verb, object, swimlane, detail, tier
            element_type in {action, branch, swimlane, start, end}
            action   verb = first token, object = remaining text (both lowercased);
                     a trailing "to <x>" is moved to detail = "to=<x>"
                     (target state, destination or recipient)
            branch   detail = "<guard question> [<then label> | <else label>]"
            swimlane only declares the lane (the swimlane column holds its name)
"""
import csv, re, sys

CLASS_COLS = ["element_id", "element_type", "canonical_name", "owner_class", "detail", "tier"]
ACT_COLS = ["element_id", "element_type", "verb", "object", "swimlane", "detail", "tier"]

REL_KINDS = [  # (arrow, kind, reversed)  reversed=True means the "whole/parent" is on the right
    ("<|--", "generalization", False), ("--|>", "generalization", True),
    ("*--", "composition", False), ("--*", "composition", True),
    ("o--", "aggregation", False), ("--o", "aggregation", True),
    ("..>", "dependency", False), ("<..", "dependency", True),
    ("-->", "association", False), ("<--", "association", True),
    ("--", "association", False),
]
REL_RE = re.compile(
    r'^(?P<a>\w+)\s*(?:"(?P<ma>[^"]*)")?\s*(?P<arrow><\|--|--\|>|\*--|--\*|o--|--o|\.\.>|<\.\.|-->|<--|--)'
    r'\s*(?:"(?P<mb>[^"]*)")?\s*(?P<b>\w+)\s*(?::\s*(?P<label>.*))?$')
BLOCK_RE = re.compile(r'^(?:(abstract)\s+)?(class|enum|interface)\s+"?(\w+)"?.*?(\{)?\s*$')
ATTR_RE = re.compile(r'^[+\-#~]?\s*(\w+)\s*:\s*(.+)$')


def strip(lines):
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("'") or line.startswith("skinparam") or line.startswith("hide") \
                or line.startswith("@startuml") or line.startswith("@enduml") or line.startswith("title"):
            continue
        yield line


def parse_class(text):
    rows, owner, is_enum = [], None, False
    n = {"class": 0, "attribute": 0, "relationship": 0}
    pre = {"class": "CL", "attribute": "AT", "relationship": "RL"}

    def add(t, name, own, detail):
        n[t] += 1
        rows.append({"element_id": f"{pre[t]}-{n[t]:02d}", "element_type": t,
                     "canonical_name": name, "owner_class": own, "detail": detail, "tier": ""})

    for line in strip(text.splitlines()):
        if owner is not None:
            if line.startswith("}"):
                owner = None
                continue
            m = ATTR_RE.match(line)
            if m:
                add("attribute", m.group(1), owner, f"type={m.group(2).strip()}")
            elif is_enum and re.match(r'^\w+$', line):
                add("attribute", line, owner, "literal")
            continue
        m = BLOCK_RE.match(line)
        if m:
            kind, name = m.group(2), m.group(3)
            add("class", name, "", "stereotype=enum" if kind == "enum" else
                ("stereotype=interface" if kind == "interface" else ""))
            if m.group(4):
                owner, is_enum = name, kind == "enum"
            continue
        m = REL_RE.match(line)
        if m:
            a, b, ma, mb = m.group("a"), m.group("b"), m.group("ma") or "", m.group("mb") or ""
            kind, rev = next((k, r) for arrow, k, r in REL_KINDS if arrow == m.group("arrow"))
            if rev:  # normalise so the whole/parent/source is always "from"
                a, b, ma, mb = b, a, mb, ma
            add("relationship", f"{a}-{b}", "", f"{a}|{kind}|{b}|{ma}:{mb}")
    return rows


def parse_activity(text):
    rows, lane, seen = [], "", set()
    n = {"action": 0, "branch": 0, "swimlane": 0, "start": 0, "end": 0}
    pre = {"action": "AC", "branch": "BR", "swimlane": "SL", "start": "ST", "end": "EN"}
    stack = []  # open branches: row dicts awaiting their else label

    def add(t, verb="", obj="", detail=""):
        n[t] += 1
        r = {"element_id": f"{pre[t]}-{n[t]:02d}", "element_type": t, "verb": verb,
             "object": obj, "swimlane": lane, "detail": detail, "tier": ""}
        rows.append(r)
        return r

    buf = None
    for line in strip(text.splitlines()):
        if buf is not None:                      # multi-line action
            buf += " " + line
            if buf.endswith(";"):
                line, buf = buf, None
            else:
                continue
        m = re.match(r'^\|(?:[^|]*\|)?([^|]+)\|$', line)
        if m:
            lane = m.group(1).strip()
            if lane not in seen:
                seen.add(lane)
                add("swimlane")
            continue
        if line == "start":
            add("start"); continue
        if line in ("stop", "end", "kill", "detach"):
            add("end"); continue
        if line.startswith(":"):
            if not line.endswith(";") and not line.endswith("]") and not line.endswith(">"):
                buf = line
                continue
            label = re.sub(r'[;\]<>|/}]+$', "", line[1:]).strip().lower()
            label = re.sub(r"\s+", " ", label)
            verb, _, obj = label.partition(" ")
            obj, sep, target = obj.rpartition(" to ") if " to " in obj else (obj, "", "")
            add("action", verb, obj, f"to={target}" if sep else "")
            continue
        m = re.match(r'^if\s*\((.*)\)\s*then\s*(?:\((.*?)\))?\s*$', line)
        if m:
            r = add("branch", detail=m.group(1).strip())
            r["_then"], r["_else"] = (m.group(2) or "").strip(), ""
            stack.append(r)
            continue
        m = re.match(r'^elseif\s*\((.*)\)\s*then\s*(?:\((.*?)\))?\s*$', line)
        if m and stack:
            stack[-1]["_else"] = f"elseif {m.group(1).strip()}"
            continue
        m = re.match(r'^else\s*(?:\((.*?)\))?\s*$', line)
        if m and stack:
            stack[-1]["_else"] = (m.group(1) or "").strip()
            continue
        if line.startswith("endif") and stack:
            r = stack.pop()
            r["detail"] = f'{r["detail"]} [{r.pop("_then")} | {r.pop("_else")}]'
            continue
    for r in stack:  # unclosed if (only in broken output) — keep what we have
        r["detail"] = f'{r["detail"]} [{r.pop("_then")} | {r.pop("_else")}]'
    return rows


def tier_key(kind, r):
    t = r["element_type"]
    if kind == "class":
        if t == "attribute":
            return f"attribute:{r['owner_class']}.{r['canonical_name']}"
        if t == "relationship":
            return f"relationship:{r['detail']}"
        return f"class:{r['canonical_name']}"
    if t == "action":
        return f"action:{r['swimlane']}:{r['verb']} {r['object']}" + (f" {r['detail']}" if r['detail'] else "")
    if t == "branch":
        return f"branch:{r['detail']}"
    if t == "swimlane":
        return f"swimlane:{r['swimlane']}"
    return t  # start / end share one key each


def main(argv):
    if len(argv) < 4 or argv[1] not in ("class", "activity"):
        sys.exit(__doc__)
    kind, src, out = argv[1], argv[2], argv[3]
    text = open(src, encoding="utf-8").read()
    rows = parse_class(text) if kind == "class" else parse_activity(text)
    if "--tier-map" in argv:
        tmap = {}
        with open(argv[argv.index("--tier-map") + 1], encoding="utf-8") as f:
            for r in csv.DictReader(f):
                tmap[r["key"]] = r["tier"]
        missing = [tier_key(kind, r) for r in rows if tier_key(kind, r) not in tmap]
        if missing:
            sys.exit("untiered gold elements:\n  " + "\n  ".join(missing))
        for r in rows:
            r["tier"] = tmap[tier_key(kind, r)]
    cols = CLASS_COLS if kind == "class" else ACT_COLS
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["element_type"]] = counts.get(r["element_type"], 0) + 1
    print(f"{out}: {len(rows)} elements {counts}")


if __name__ == "__main__":
    main(sys.argv)
