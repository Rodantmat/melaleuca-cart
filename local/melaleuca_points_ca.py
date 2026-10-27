"""Canadian points table: compares the points of every product / pack in the US store with the Canadian store (saved catalogs family_map_us.json /
family_map_ca.json, written by the scan / fill) and writes feed\\points_ca.tsv   (item no. <TAB> name <TAB> US points <TAB> Canadian points).
The workbook's sheet 'MelaleucaCA' (used by the Canadian = orange / yellow tabs) takes these points instead of the US ones.
usage: python melaleuca_points_ca.py [feed_dir]"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def cards(path):
    d = json.load(open(path, encoding="utf-8")).get("cards", {}).get("v", {})
    o = {}
    for v in d.values():
        for s in v.get("skus") or []:
            o[str(s)] = v
    return o


ACC = ("bottle", "sprayer", "pump", "brush", "mop", "refill cap", "dispenser")


def pack_audit(feed):
    """A pack of the store that holds FIXED products next to its free choices ('mixed' pack) cannot be the pack of a sheet group that says 'any of the products'
    (e.g. the Canadian Cleaning Wipes 5-Pack: Sol-U-Guard + MelaMagic + Tough & Tender are fixed, only 2 are free). Such a pack is written to
    feed\\pack_audit_ca.tsv (pack <TAB> reason); the workbook switches the sheet group that uses it off (every product then uses its own pack / price)."""
    out = []
    try:
        d = json.load(open(os.path.join(feed, "info_ca.json"), encoding="utf-8"))
    except Exception:
        d = {}
    for sku, e in d.items():
        v = e.get("v") if isinstance(e, dict) else None
        conf = (v or {}).get("conf") or []
        free = sum(int(c.get("req") or 0) for c in conf if c.get("type") == "FSKU")
        fixed = [c.get("title") or "" for c in conf if c.get("type") == "Static" and c.get("title") and not any(a in c["title"].lower() for a in ACC)]
        if free and fixed:
            out.append((str(sku), "fixed contents (%s) + only %d free choice(s)" % ("; ".join(fixed), free)))
    # sets of the sheet (feed\\mel_groups_in.tsv = key, pack item no., units) whose pack the Canadian store does not sell, or sells with another unit count
    try:
        ca = cards(os.path.join(feed, "family_map_ca.json"))
        for ln in open(os.path.join(feed, "mel_groups_in.tsv"), encoding="utf-8-sig").read().splitlines()[1:]:
            p = ln.split("\t")
            if len(p) < 3 or not p[1].strip().isdigit():
                continue
            key, pk, n = p[0], p[1].strip(), int(float(p[2] or 0))
            if ca and pk not in ca and not re.match(r"^F\d+$", key):      # F#### sets come from the store's own offers: their pack is not always a catalog card
                out.append((pk, "set %s: this item number is not in the Canadian store's catalog" % key))
            elif pk in ca:
                m = re.search(r"(\d+)\s*[-\u2013]\s*pack", ca[pk].get("title") or "", re.I)
                if m and n and int(m.group(1)) != n and key != "CLEAN":
                    out.append((pk, "set %s: the store calls it '%s' but the sheet set has %d units" % (key, ca[pk].get("title"), n)))
    except Exception as e:
        print("pack audit of the sheet sets skipped:", e)
    with open(os.path.join(feed, "pack_audit_ca.tsv"), "w", encoding="utf-8", newline="") as f:
        f.write("pack\treason\r\n")
        for r in out:
            f.write("%s\t%s\r\n" % r)
    print("Pack audit: %d Canadian pack(s) that cannot be used as 'any of' sets -> pack_audit_ca.tsv" % len(out))
    for r in out:
        print("   %s : %s" % r)


def main(feed):
    us, ca = cards(os.path.join(feed, "family_map_us.json")), cards(os.path.join(feed, "family_map_ca.json"))
    rows = []
    for s in sorted(set(us) & set(ca), key=lambda x: int(x) if x.isdigit() else 0):
        a, b = us[s].get("pts"), ca[s].get("pts")
        if a is not None and b is not None and abs(float(a) - float(b)) > 0.01:
            rows.append((s, (ca[s].get("title") or "")[:60], float(a), float(b)))
    with open(os.path.join(feed, "points_ca.tsv"), "w", encoding="utf-8", newline="") as f:
        f.write("item\tname\tus_points\tca_points\r\n")
        for r in rows:
            f.write("%s\t%s\t%g\t%g\r\n" % r)
    print("Canadian points table: %d products with other points than in the US store -> points_ca.tsv" % len(rows))
    for r in rows:
        print("   %s  %s : US %g -> CA %g" % r)
    only_us = sorted(set(us) - set(ca))
    print("(%d items of the US store are not sold in Canada)" % len(only_us))
    pack_audit(feed)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "feed"))
