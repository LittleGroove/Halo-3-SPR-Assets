# Field-by-field reading of tags through the Assembly plugins, for comparing two maps (Trapa's builds vs OG).
# fields(m, S, i) -> {path: (kind, value)}; diff(a, b) -> [(path, a, b)]; strings(m) -> the string table.
import os, struct, html
import xml.etree.ElementTree as ET
here = os.path.dirname(os.path.abspath(__file__)); B = chr(92)
def strings(m):
    u = lambda o: struct.unpack_from('<I', m.h, o)[0]
    cnt, buf, size, idx = u(0x30), u(0x34), u(0x38), u(0x3c)
    dm = m.masks[0]; buf, idx = (buf + dm) % (1 << 32), (idx + dm) % (1 << 32)    # debug section addresses -> file
    offs = struct.unpack_from('<%di' % cnt, bytes(m.mm[idx:idx + 4 * cnt])); blob = bytes(m.mm[buf:buf + size])
    return [blob[o:blob.find(b'\0', o)].decode('latin1') if 0 <= o < size else None for o in offs]
# Halo 3's string id sets (the same table in every map, stock ones included: header 0x40 count, 0x44 sizes). An id is
# set << 19 | index (19-bit index; checked 2026-10-27: every id above 0x7FFFF in LG HugeGrass fits its set, e.g. 0x00080292
# = set 1 'empty', 0x00200001 = set 4 'frag_grenade'). The string table holds set 0's first 1,177, then sets 1-9 (2,187),
# then the rest of set 0 (the map's own strings). Until 2026-10-27 the tools read every id as set 0 (index < 1200 ->
# table[index], else +2187), which misread the few ids from sets 1-9; no writing tool used those.
NS = (1177, 1658, 146, 86, 16, 76, 57, 20, 13, 115)
def sid_index(v):
    st, i = (v >> 19) & 0x1F, v & 0x7FFFF
    if st == 0: return i if i < NS[0] else i + sum(NS[1:])
    return NS[0] + sum(NS[1:st]) + i
def sid_value(t):
    """the string id for string table index t"""
    if t < NS[0]: return t
    if t < sum(NS): k = t - NS[0]; st = 1
    else: return t - sum(NS[1:])
    while k >= NS[st]: k -= NS[st]; st += 1
    return st << 19 | k
SIZE = {'int8': 1, 'uint8': 1, 'int16': 2, 'uint16': 2, 'int32': 4, 'uint32': 4, 'float32': 4, 'degree': 4, 'enum8': 1,
        'enum16': 2, 'enum32': 4, 'flags8': 1, 'flags16': 2, 'flags32': 4, 'stringid': 4, 'stringId': 4, 'rangef': 8,
        'rangeF': 8, 'ranged': 8, 'range16': 4, 'point2': 8, 'point3': 12, 'vector2': 8, 'vector3': 12, 'degree2': 8,
        'degree3': 12, 'tagRef': 16, 'tagref': 16, 'colorf': 12}
FMT = {'int8': '<b', 'uint8': '<B', 'int16': '<h', 'uint16': '<H', 'int32': '<i', 'uint32': '<I', 'float32': '<f',
       'degree': '<f', 'enum8': '<B', 'enum16': '<H', 'enum32': '<I', 'flags8': '<B', 'flags16': '<H', 'flags32': '<I',
       'rangef': '<2f', 'rangeF': '<2f', 'ranged': '<2f', 'range16': '<2h', 'point2': '<2f', 'point3': '<3f', 'vector2': '<2f',
       'vector3': '<3f', 'degree2': '<2f', 'degree3': '<3f', 'colorf': '<3f'}
PLUG = {}
EXACT = False   # True: numbers unrounded (SPR Assets values files); False (default): rounded to 4 places, as every tool had.
                # True also names a field the plugin uses twice in one struct "<name> #2" (2026-11-23); False keeps the old
                # behaviour, where the second silently replaced the first (no other tool changes)
def plugin(g):
    if g not in PLUG:
        f = g.strip() + '.xml'                          # 'rmd ' / 'rmw ': the plugin files have no trailing space
        p = next((q for q in (os.path.join(here, 'assembly', 'plugins-h3mcc', f), os.path.join(here, 'assembly', 'plugins-h3', f)) if os.path.exists(q)), None)
        PLUG[g] = ET.parse(p).getroot() if p else None
    return PLUG[g]
def tagname(m, d):
    t = d & 0xFFFF
    return m.tagname(t) if d != 0xFFFFFFFF and t < m.ntags else '-'
def flat(m, S, addr, el, size, path, out, depth=0):
    """field path -> (kind, value) for one struct and everything under it"""
    f = m.tagsfile + (addr - m.base)                  # Trapa's builds hold data past the 0x1d0000000 ceiling: read the file
    if f < 0 or f + size > m.size: return out
    raw = bytes(m.mm[f:f + size])
    for c in el:
        if c.get('offset') is None or c.tag in ('comment', 'revisions'): continue
        o = int(c.get('offset'), 16); nm = html.unescape(c.get('name', '')); p = f'{path}/{nm}'
        if EXACT and (p in out or p + ' (count)' in out):   # a name the plugin uses twice in one struct (a gear's loaded and
            k = 2                                     # cruising torque curves): without this the second hid the first
            while f'{p} #{k}' in out or f'{p} #{k} (count)' in out: k += 1
            p = f'{p} #{k}'
        if c.tag == 'tagblock':
            es = int(c.get('elementSize'), 16); cnt, ptr = struct.unpack_from('<II', raw, o)
            out[p + ' (count)'] = ('count', cnt)
            if depth < 4:
                for k in range(min(cnt, 64) if es else 0): flat(m, S, ptr * 4 + es * k, c, es, f'{p}[{k}]', out, depth + 1)
            continue
        k = SIZE.get(c.tag)
        if not k or o + k > size: continue
        x = raw[o:o + k]
        if c.tag in ('tagRef', 'tagref'): out[p] = ('ref', tagname(m, struct.unpack_from('<I', x, 12)[0]))
        elif c.tag in ('stringid', 'stringId'):
            v = struct.unpack('<I', x)[0]; t = sid_index(v)
            out[p] = ('sid', S[t] if v and 0 <= t < len(S) else '')
        elif c.tag.startswith('enum'):
            v = struct.unpack(FMT[c.tag], x)[0]; opts = {int(q.get('value'), 16): q.get('name') for q in c if q.tag == 'option'}
            out[p] = ('enum', opts.get(v, v))
        elif c.tag.startswith('flags'):
            v = struct.unpack(FMT[c.tag], x)[0]; bits = {int(q.get('index')): q.get('name') for q in c if q.tag == 'bit'}
            out[p] = ('flags', tuple(bits.get(b, f'bit {b}') for b in range(8 * k) if v >> b & 1))
        elif c.tag in FMT:
            v = struct.unpack(FMT[c.tag], x)
            if EXACT:                                   # SPR Assets values files (2026-11-23): the stored floats, unrounded
                if c.tag.startswith('degree'): v = tuple(z * 57.29577951308232 for z in v)
                out[p] = ('num', tuple(v)); continue
            if c.tag.startswith('degree'): v = tuple(round(z * 57.29577951308232, 4) for z in v)
            out[p] = ('num', tuple(round(z, 4) if isinstance(z, float) else z for z in v))
    return out
def fields(m, S, i):
    g = m.groups[m.tag_group[i]]; el = plugin(g)
    if el is None: return {}
    return flat(m, S, int(m.tag_addr[i]), el, int(el.get('baseSize'), 16), '', {})
def find(m, name, g):
    return next((i for i in range(m.ntags) if m.names[i] == name and m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == g), None)
def fmt(kind, v):
    if kind == 'num': return ', '.join(f'{z:g}' for z in v)
    if kind == 'flags': return ', '.join(v) if v else '(none)'
    return str(v)
def diff(fo, ft):
    rows = []
    for k in sorted(set(fo) | set(ft)):
        a, b = fo.get(k), ft.get(k)
        if a != b: rows.append((k, fmt(*a) if a else '(absent)', fmt(*b) if b else '(absent)'))
    return rows
def refs(fl, group_suffix):
    return [(k, v[1]) for k, v in fl.items() if v[0] == 'ref' and v[1].endswith('.' + group_suffix)]
def label(name): return name.rsplit(B, 1)[-1]
