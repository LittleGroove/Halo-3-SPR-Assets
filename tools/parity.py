# Parity check (2026-11-23): an SPR item built from source vs the same item in HugeGrass SPR, field for field (unrounded).
# For every tag the item owns (sprwalk.py's JSON): the fields that differ between the two maps, each one explained where
# it can be against a reference map holding the bases as their author compiled them (a stock map such as sandbox.map
# for stock bases; RJ's own HugeGrass from the Workshop for his):
#   SPR    - one of the fields the walk changed (our SPR values): these must match, so any difference here is a fault
#   map    - HugeGrass's base tag differs from the reference there and the build has the reference's value: a change made
#            in the map (RJ's to a stock tag, or one of our LG fixes from build_lg.py) that the source doesn't carry yet
#   source - HugeGrass has the reference's value and the build doesn't: the source tag, or how it was compiled, differs
#            from what the author compiled (the Reclaimer Kit compile of 0.10.9 lands here; so does RJ's published source
#            where it isn't his compiled map)
#   other  - none of these (or no reference given): listed for a look
# usage: python -I parity.py <built map> <hugegrass_spr.map> <walk.json> [<reference map>] [-v: list the 'map' rows too]
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff
from tagfields import fields
def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    new, hg, walk = args[0], args[1], json.load(open(args[2], encoding='utf-8'))
    mn, Sn = sprdiff.load(new); mh, Sh = sprdiff.load(hg)
    ms = sprdiff.load(args[3]) if len(args) > 3 else None
    totals = {'SPR': 0, 'map': 0, 'source': 0, 'other': 0}
    for t in walk['tags']:
        try: fn = fields(mn, Sn, sprdiff.find(mn, t['tag']))
        except StopIteration: print(f"MISSING in built map: {t['tag']}"); totals['SPR'] += 1; continue
        fh = fields(mh, Sh, sprdiff.find(mh, t['tag']))
        spr_paths = {f['path'] for f in t['fields']}
        bh = fields(mh, Sh, sprdiff.find(mh, t['copy_from']))
        bs = None
        if ms:
            try: bs = fields(ms[0], ms[1], sprdiff.find(ms[0], t['copy_from']))
            except StopIteration: bs = None
        rows = [(p, fh.get(p), fn.get(p)) for p in dict.fromkeys(list(fh) + list(fn)) if fh.get(p) != fn.get(p)]
        print(f"{t['tag']}: {len(rows)} fields differ")
        for p, a, b in rows:
            if p in spr_paths: why = 'SPR'
            elif bs is not None and bh.get(p) != bs.get(p) and b == bs.get(p): why = 'map'
            elif bs is not None and a == bs.get(p): why = 'source'
            else: why = 'other'
            totals[why] += 1
            if why != 'map' or '-v' in sys.argv:
                print(f'   {why:6s} {p}\n          hugegrass {a}\n          built     {b}' + (f'\n          reference {bs.get(p)}' if bs is not None else ''))
    print(f"differences: {totals['SPR']} in SPR fields (must be 0), {totals['map']} made in the map (not in source yet), "
          f"{totals['source']} where source or its compile differs from the reference, {totals['other']} other")
main()
