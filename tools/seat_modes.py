# Which seat animations a body can use (2026-11-23, Falcon AI seats): Halo 3 lets a character take a seat only if its
# animation graph has an "enter" (or enter_a..enter_d) animation in the mode the seat's label names (halo3.dll 0x3512dc,
# research (2026-11-23 falcon AI)\code findings.md). For each graph (and its parents), the modes that have one.
# usage: python -I seat_modes.py <map> <graph name> [...]      e.g. objects\characters\marine\marine
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff
from tagfields import fields
ENTER = re.compile(r'^enter(_[a-d])?$')
def modes(m, S, name, seen):
    if name.lower() in seen: return {}
    seen.add(name.lower())
    try: f = fields(m, S, sprdiff.find(m, name + '.jmad'))
    except StopIteration: return {}
    out = {}
    labels = {int(k.split('[')[1].split(']')[0]): v[1] for k, v in f.items() if re.match(r'^/Modes\[\d+\]/Label$', k)}
    for i, lab in labels.items():
        has = any(v[0] == 'sid' and ENTER.match(str(v[1])) for k, v in f.items() if k.startswith(f'/Modes[{i}]/') and k.endswith('/Label') and '/Actions[' in k)
        out[lab] = out.get(lab, False) or has
    parent = f.get('/Parent Animation Graph', ('ref', '-'))[1]
    if parent and parent != '-':
        for lab, has in modes(m, S, parent.rsplit('.', 1)[0], seen).items(): out.setdefault(lab, has)
    return out
def main():
    m, S = sprdiff.load(sys.argv[1])
    for g in sys.argv[2:]:
        md = modes(m, S, g, set())
        seat = sorted(k for k, v in md.items() if v and re.search(r'_(d|g|p|e)(_|$|\d)|_g_|_p_|turret_g', k))
        print(f'{g}: {len(md)} modes, seat modes with enter: {" ".join(seat)}')
main()
