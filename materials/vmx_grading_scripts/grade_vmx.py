"""Score VMX.csv on two metrics.

  completeness  US  : Source-Input-ID != "" AND Structural-Elements != ""
                NFR : Source-Input-ID != ""
                = rows passing / total rows

  integrity     a reference = one value after splitting a cell on ";"
                Source      -> must exist in domain_requirements.json
                Structural  -> must exist in THIS submission's structural.puml
                Behavioral  -> must exist in THIS submission's behavioral.puml
                = references found / total references

Integrity is internal consistency (variant A): the vocabularies come from the
submission's own diagrams, never from gold.

usage: python3 -I score_vmx.py <submission_dir> [domain_requirements.json]
"""
import csv, json, os, re, sys

# G3 gold actions, from context section 4. Only used when the submission has no
# behavioral.puml (the gold's activity diagram lives in a GUI tool, not a file).
G3_GOLD_ACTIONS = {
    "Make an Order", "Receive order", "Fill Order", "Ship Order",
    "Close Order", "Send Invoice", "Make Payment", "Accept Payment",
}


def structural_vocab(path):
    """classes, enums and Class.attribute names declared in a class diagram."""
    puml = open(path, encoding="utf-8").read()
    vocab = set(re.findall(r"^\s*class\s+(\w+)", puml, re.M))
    vocab |= set(re.findall(r"^\s*enum\s+(\w+)", puml, re.M))
    for kind, owner, body in re.findall(
        r"^\s*(class|enum)\s+(\w+)\s*\{(.*?)^\s*\}", puml, re.M | re.S
    ):
        if kind == "enum":
            continue
        for line in body.strip().splitlines():
            attr = line.strip().split(" :")[0].split(":")[0].strip()
            attr = attr.lstrip("+-#~ ").strip()
            if attr:
                vocab.add(f"{owner}.{attr}")
    return vocab


def behavioral_vocab(path):
    """action names declared in an activity diagram."""
    puml = open(path, encoding="utf-8").read()
    vocab = set()
    # ":text;" is an activity node. A node tagged <<obj>> is an object node by
    # the convention this study uses, so it is not an action.
    for raw, stereo in re.findall(r":(.*?);[ \t]*(<<\w+>>)?", puml, re.S):
        name = raw.strip()
        if name and "\n" not in name and stereo != "<<obj>>":
            vocab.add(name)
    return vocab


def cells(row):
    return [v.strip() for v in row] + [""] * (4 - len(row))


def score(sub_dir, dom_path):
    dom = json.load(open(dom_path, encoding="utf-8"))
    source_vocab = set(dom["FR_INPUT"]) | set(dom["NFR_INPUT"])

    st_path = os.path.join(sub_dir, "structural.puml")
    if not os.path.exists(st_path):
        st_path = os.path.join(sub_dir, "structural_gold.puml")
    st_vocab = structural_vocab(st_path)

    bh_path = os.path.join(sub_dir, "behavioral.puml")
    if not os.path.exists(bh_path):
        bh_path = os.path.join(sub_dir, "behavioral_gold.puml")
    if os.path.exists(bh_path):
        bh_vocab = behavioral_vocab(bh_path)
        bh_src = os.path.basename(bh_path)
    else:
        bh_vocab = set(G3_GOLD_ACTIONS)
        bh_src = "context section 4 (no behavioral.puml present)"

    rows = list(csv.reader(open(os.path.join(sub_dir, "VMX.csv"), encoding="utf-8")))
    body = [r for r in rows[1:] if any(v.strip() for v in r)]

    complete, incomplete = 0, []
    found, total, broken = 0, 0, []

    for row in body:
        rid, src, st, bh = cells(row)[:4]

        if rid.startswith("NFR-"):
            ok = bool(src)
            need = "Source"
        else:
            ok = bool(src) and bool(st)
            need = "Source + Structural"
        complete += ok
        if not ok:
            incomplete.append(f"{rid} (needs {need})")

        for cell, vocab, label in ((src, source_vocab, "source"),
                                   (st, st_vocab, "structural"),
                                   (bh, bh_vocab, "behavioral")):
            for ref in filter(None, (v.strip() for v in cell.split(";"))):
                total += 1
                if ref in vocab:
                    found += 1
                else:
                    broken.append(f"{rid} [{label}] {ref!r}")

    print(f"submission      : {sub_dir}")
    print(f"structural vocab: {len(st_vocab)} names from {os.path.basename(st_path)}")
    print(f"behavioral vocab: {len(bh_vocab)} names from {bh_src}")
    print(f"rows            : {len(body)}")
    print()
    print(f"VMX Requirement Coverage  : {complete}/{len(body)} = "
          f"{complete / len(body) * 100:.1f}%")
    for m in incomplete:
        print(f"    incomplete: {m}")
    print(f"VMX Referential Integrity : {found}/{total} = "
          f"{found / total * 100:.1f}%")
    for m in broken:
        print(f"    broken: {m}")
    return complete == len(body) and found == total


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    dom = sys.argv[2] if len(sys.argv) > 2 else os.path.join(d, "domain_requirements.json")
    sys.exit(0 if score(d, dom) else 1)