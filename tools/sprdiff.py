# What an SPR copy changes: every field of the copy's tag that differs from its base tag in the same map (plugin paths),
# and every tag reference that points somewhere else (a tag of its own, which then needs its own diff against what the
# base references there). usage: python -I sprdiff.py <map> "objects\vehicles\banshee\banshee_spr.vehi" "objects\vehicles\banshee\banshee.vehi"
import sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
sys.stdout.reconfigure(encoding='utf-8')
from h3map import Map
import tagfields
tagfields.EXACT = True          # the stored floats, unrounded: values files must rebuild HugeGrass SPR's numbers exactly
from tagfields import fields, strings
def load(path):
    m = Map(path); return m, strings(m)
def find(m, spec):
    name, group = spec.lower().rsplit('.', 1)
    return next(k for k in range(m.ntags) if (m.names[k] or '').lower() == name and 0 <= m.tag_group[k] < len(m.groups) and m.groups[m.tag_group[k]] == group)
def find_group(m, spec):
    """the 4-letter group of a tag spec ('...banshee.vehi' -> 'vehi')"""
    return m.groups[m.tag_group[find(m, spec)]]
def diff(m, S, a, b):
    fa, fb = fields(m, S, find(m, a)), fields(m, S, find(m, b))
    out = []
    for p in list(dict.fromkeys(list(fb) + list(fa))):
        va, vb = fa.get(p), fb.get(p)
        if va != vb: out.append((p, vb, va))
    return out
if __name__ == '__main__':
    m, S = load(sys.argv[1])
    rows = diff(m, S, sys.argv[2], sys.argv[3])
    print(f'{len(rows)} fields differ ({sys.argv[2]} vs base {sys.argv[3]})')
    for p, base, spr in rows:
        print(f'{p}\n    base {base}\n    spr  {spr}')
