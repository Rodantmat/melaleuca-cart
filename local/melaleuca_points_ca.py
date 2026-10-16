"""Canadian points table: compares the points of every product / pack in the US store with the Canadian store (saved catalogs family_map_us.json /
family_map_ca.json, written by the scan / fill) and writes feed\\points_ca.tsv   (item no. <TAB> name <TAB> US points <TAB> Canadian points).
The workbook's sheet 'MelaleucaCA' (used by the Canadian = orange / yellow tabs) takes these points instead of the US ones.
usage: python melaleuca_points_ca.py [feed_dir]"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def cards(path):
    d = json.load(open(path, encoding="utf-8")).get("cards", {}).get("v", {})
    o = {}
    for v in d.values():
        for s in v.get("skus") or []:
            o[str(s)] = v
    return o


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


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "feed"))
