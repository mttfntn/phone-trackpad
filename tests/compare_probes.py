"""Compares two probe_behaviour.py results and lists every difference.

    python tests/compare_probes.py old.json new.json

Exits 0 when they are identical, 1 otherwise.
"""
import json
import sys


def diff(a, b, path="", out=None):
    out = [] if out is None else out
    if type(a) is not type(b):
        out.append(f"{path}: {a!r} -> {b!r}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}/{k}: added {b[k]!r}")
            elif k not in b:
                out.append(f"{path}/{k}: removed {a[k]!r}")
            else:
                diff(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: {a!r} -> {b!r}")
    return out


def main():
    old, new = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:3])
    found = diff(old, new)
    for line in found:
        print(line[:400])
    print(f"{len(found)} differences")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
