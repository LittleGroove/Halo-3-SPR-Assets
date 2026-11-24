# Whose change is it (2026-11-23)? For tags where HugeGrass SPR differs from the source build, the same tag in stock maps
# (Bungie's compiled originals) and in RJ's own HugeGrass (the Workshop map our LG line starts from):
#   bungie - stock has HugeGrass SPR's value: H3EK's source isn't what Bungie shipped (nothing of ours or RJ's)
#   rj     - RJ's map has it and stock doesn't: RJ changed it in his map
#   lg     - neither has it: one of our LG fixes (build_lg.py and friends)
# usage: python -I provenance.py <hugegrass_spr.map> <shipped map> <tag spec> [...]
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff
from tagfields import fields
STOCK = r'H:\SteamLibrary\steamapps\common\Halo The Master Chief Collection\halo3\maps'
RJ = r'H:\SteamLibrary\steamapps\workshop\content\976730\2984061723\maps\hugeass_remastered_mcc.map'
def get(m, S, spec):
    try: return fields(m, S, sprdiff.find(m, spec))
    except StopIteration: return None
def main():
    hg, sh = sprdiff.load(sys.argv[1]), sprdiff.load(sys.argv[2]); rj = sprdiff.load(RJ)
    stock = [sprdiff.load(f) for f in sorted(glob.glob(os.path.join(STOCK, '*.map'))) if os.path.basename(f) in ('sandbox.map', 'guardian.map', 'construct.map', 'salvation.map', 'riverworld.map', 'deadlock.map', 'snowbound.map')]
    for spec in sys.argv[3:]:
        a, b, r = get(*hg, spec), get(*sh, spec), get(*rj, spec)
        st = next((f for f in (get(*s, spec) for s in stock) if f is not None), None)
        print(f'{spec}  (stock copy: {"found" if st is not None else "none"}, RJ map: {"found" if r is not None else "none"})')
        for p in dict.fromkeys(list(a) + list(b)):
            if a.get(p) == b.get(p) or 'Runtime' in p: continue
            who = 'bungie' if st is not None and st.get(p) == a.get(p) else 'rj' if r is not None and r.get(p) == a.get(p) else 'lg'
            print(f'   {who:6s} {p}: hugegrass {a.get(p)} / shipped {b.get(p)}' + (f' / stock {st.get(p)}' if st is not None else '') + (f' / rj {r.get(p)}' if r is not None else ''))
main()
