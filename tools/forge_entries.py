# What Project Reclaimer's Forge offers for a map's vehicles (2026-11-23): one entry per model variant, the variants no
# vehicle defaults to listed under the first vehicle on that model. Lists every Forge vehicle palette entry with its
# label, model and variants, then the entries PR would show, and flags any vehicle whose model holds more than one variant.
# usage: python -I forge_entries.py <map>
import html, struct, sys, os
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff, tagfields
from tagfields import strings, sid_index
FORGE_VEHI = 0x1E0
def field(group, name):
    c = next(c for c in tagfields.plugin(group) if c.get('offset') is not None and html.unescape(c.get('name', '')) == name)
    return int(c.get('offset'), 16), c
def main():
    m, TS = sprdiff.load(sys.argv[1])
    grp = lambda i: m.groups[m.tag_group[i]] if 0 <= m.tag_group[i] < len(m.groups) else None
    VAR_OFF, VAR_C = field('hlmt', 'Variants'); VAR_ES = int(VAR_C.get('elementSize'), 16)
    VNAME = next(int(c.get('offset'), 16) for c in VAR_C if html.unescape(c.get('name', '')) == 'Name')
    MODEL_OFF, _ = field('vehi', 'Model'); DMV_OFF, _ = field('vehi', 'Default Model Variant')
    A = int(m.tag_addr[next(i for i in range(m.ntags) if grp(i) == 'scnr')])
    fc, fp = struct.unpack('<II', m.mem(A + FORGE_VEHI, 8))
    rows = []
    for k in range(fc):
        e = m.mem(fp * 4 + 0x1C * k, 0x1C); vi = struct.unpack_from('<I', e, 12)[0] & 0xFFFF
        label = TS[sid_index(struct.unpack_from('<I', e, 0x10)[0])]
        if vi >= m.ntags or grp(vi) != 'vehi': rows.append((label, m.names[vi] if vi < m.ntags else '?', '', [], '')); continue
        va = int(m.tag_addr[vi]); mi = struct.unpack_from('<I', m.mem(va + MODEL_OFF, 16), 12)[0] & 0xFFFF
        dv = TS[sid_index(struct.unpack('<I', m.mem(va + DMV_OFF, 4))[0])] or 'default'
        names = []
        if mi < m.ntags:
            n, vp = struct.unpack('<II', m.mem(int(m.tag_addr[mi]) + VAR_OFF, 8))
            names = [TS[sid_index(struct.unpack('<I', m.mem(vp * 4 + VAR_ES * j + VNAME, 4))[0])] for j in range(n)]
        rows.append((label, m.names[vi], m.names[mi] if mi < m.ntags else '-', names, dv))
    # PR's offer: each vehicle = its default variant; per model, the variants no vehicle defaults to go to the first one
    by_model, shown = {}, 0
    for label, v, mdl, names, dv in rows: by_model.setdefault(mdl, []).append((label, v, names, dv))
    extra = {}
    for mdl, vs in by_model.items():
        used = {dv for _, _, _, dv in vs}; names = vs[0][2]
        extra[vs[0][1]] = [n for n in names if n not in used]
    multi = 0
    for label, v, mdl, names, dv in rows:
        x = extra.get(v, []); shown += 1 + len(x)
        flag = '  <-- ' + ', '.join('#' + n for n in x) if x else ''
        if len(names) > 1: multi += 1
        print(f"{label:34s} {v.rsplit(chr(92), 1)[-1]:36s} {mdl.rsplit(chr(92), 1)[-1]:34s} {len(names)} '{dv}'{flag}")
    print(f'{fc} vehicles on the Forge palette; {multi} on a model with more than one variant; about {shown} Forge entries')
main()
