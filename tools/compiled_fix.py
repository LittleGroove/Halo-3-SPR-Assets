# Our fixes on items copied compiled (the fallback items, no source yet), in the shipped map (2026-11-23). The source-built
# items take their fixes in the source (values\fixes.json, sprapply.py); a fallback item comes from HugeGrass SPR as it is,
# so a fix it needs is made here, after importtags (and after split_variants.py, so its copies can be edited too).
# Each fixes file maps a tag spec ("name.group") to a list of ops:
#   drop_last_named: remove the LAST element of a top-level block if its name field is <value> (a count change only;
#                    refused if that element isn't the last one)
#   set: write one field by its plugin path ("/Seats[1]/Seat Animation", "/Variants[0]/Objects[1]/Child Object") with
#        value [kind, value]: sid (text), ref ("name.group"), num (numbers, packed by the field's type). "expect" (the same
#        form) is checked first, so a fix never lands on a field that isn't what it was written for.
#   flags: add / remove flags by their plugin names ({"path": "/Seats[1]/Flags", "add": ["Allow AI Noncombatants"]})
#   append: a new element at the end of a top-level block, a raw copy of element "copy" with references set
#           ({"block": "Vehicle Properties", "copy": 4, "set": {"Unit": ["ref", "objects\\vehicles\\warthog\\warthog_spr.vehi"]}});
#           only for blocks whose elements hold no blocks of their own
# Every fix is read back. usage: python -I compiled_fix.py <map, edited in place> <fixes.json> [<fixes.json> ...]
import html, json, os, re, struct, sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tagkit import Editor
import sprdiff, tagfields
from tagfields import fields, FMT
def block_of(group, name):
    el = tagfields.plugin(group)
    c = next(c for c in el if c.tag == 'tagblock' and html.unescape(c.get('name', '')) == name)
    return int(c.get('offset'), 16)
def locate(m, addr, path, el):
    """(field address, plugin element) of a plugin path in a compiled tag; "<name> #2" picks a name's second use"""
    def pick(el, seg, want_block):
        mt = re.match(r'^(.*?)(?: #(\d+))?$', seg); nm, k = mt.group(1), int(mt.group(2) or 1)
        hits = [c for c in el if c.get('offset') is not None and html.unescape(c.get('name', '')) == nm and (c.tag == 'tagblock') == want_block]
        assert len(hits) >= k, f'{path}: no {seg}'
        return hits[k - 1]
    parts = path.strip('/').split('/')
    for seg in parts[:-1]:
        mt = re.match(r'^(.+)\[(\d+)\]$', seg); c = pick(el, mt.group(1), True); i = int(mt.group(2))
        cnt, p = struct.unpack('<II', m.mem(addr + int(c.get('offset'), 16), 8)); assert i < cnt, f'{path}: {seg} of {cnt}'
        addr, el = p * 4 + int(c.get('elementSize'), 16) * i, c
    c = pick(el, parts[-1], False)
    return addr + int(c.get('offset'), 16), c
def main():
    path = sys.argv[1]; fixes = {}
    for f in sys.argv[2:]:
        for k, v in json.load(open(f, encoding='utf-8')).items():
            if k != 'about': fixes.setdefault(k, []).extend(v)
    E = Editor(path); m = E.m; S = tagfields.strings(m); done = []; appended = {}
    for spec, ops in fixes.items():
        try: i = sprdiff.find(m, spec)
        except StopIteration: print(f'  {spec}: not in the map, skipped'); continue
        group = spec.rsplit('.', 1)[1]; a = int(m.tag_addr[i]); f = fields(m, S, i)
        for op in ops:
            if op['op'] == 'drop_last_named':
                n = f.get(f"/{op['block']} (count)", ('count', 0))[1]
                last = f.get(f"/{op['block']}[{n - 1}]/{op['field']}")
                assert n and last and last[1] == op['value'], f"{spec}: the last {op['block']} element is {last}, not {op['value']}"
                E.write(a + block_of(group, op['block']), struct.pack('<I', n - 1))
                done.append((spec, op, n))
            elif op['op'] == 'set':
                if 'expect' in op:
                    have = f.get(op['path'])
                    assert have is not None and have[0] == op['expect'][0] and (str(have[1]).lower() == str(op['expect'][1]).lower() if op['expect'][0] != 'num' else tuple(have[1]) == tuple(op['expect'][1])), f"{spec} {op['path']}: is {have}, expected {op['expect']}"
                fa, c = locate(m, a, op['path'], tagfields.plugin(group)); kind, val = op['value']
                if kind == 'sid':
                    sid = E.sid_of(val); raw = struct.pack('<I', sid if sid is not None else E.add_string(val))
                elif kind == 'ref':
                    if val in ('-', '', None): raw = struct.pack('<4sIII', b'\xff\xff\xff\xff', 0, 0, 0xFFFFFFFF)
                    else:
                        ti = sprdiff.find(m, val); g = val.rsplit('.', 1)[1]
                        raw = g[::-1].encode('latin1') + bytes(8) + struct.pack('<I', (int(m.tag_salt[ti]) << 16) | ti)
                elif kind == 'num':
                    raw = struct.pack(FMT[c.tag], *(val if isinstance(val, (list, tuple)) else [val]))
                else: raise SystemExit(f'{spec}: unknown value kind {kind}')
                E.write(fa, raw); done.append((spec, op, None))
            elif op['op'] == 'flags':                  # add / remove flags by their plugin names
                fa, c = locate(m, a, op['path'], tagfields.plugin(group))
                bits = {html.unescape(b.get('name')): int(b.get('index')) for b in c if b.tag == 'bit'}
                for n_ in op.get('add', []) + op.get('remove', []): assert n_ in bits, f"{spec} {op['path']}: no flag {n_}"
                cur = struct.unpack(FMT[c.tag], m.mem(fa, struct.calcsize(FMT[c.tag])))[0]
                for n_ in op.get('add', []): cur |= 1 << bits[n_]
                for n_ in op.get('remove', []): cur &= ~(1 << bits[n_])
                E.write(fa, struct.pack(FMT[c.tag], cur)); done.append((spec, op, None))
            elif op['op'] == 'append':                 # new elements of a top-level block, each a raw copy of element
                c = next(x for x in tagfields.plugin(group) if x.tag == 'tagblock' and html.unescape(x.get('name', '')) == op['block'])
                es = int(c.get('elementSize'), 16); bo = a + int(c.get('offset'), 16)
                key = (spec, op['block'])
                if key not in appended:                # (copy) with fields set; elements holding blocks of their own refused
                    assert not any(x.tag == 'tagblock' for x in c), f"{spec} {op['block']}: elements hold blocks"
                    cnt, p = struct.unpack('<II', m.mem(bo, 8))
                    appended[key] = (bo, es, c, [bytearray(m.mem(p * 4 + es * k, es)) for k in range(cnt)])
                for fname, (kind, val) in op.get('expect', {}).items():   # the element copied must be the one meant
                    have = f.get(f"/{op['block']}[{op['copy']}]/{fname}")
                    assert have is not None and str(have[1]).lower() == str(val).lower(), f"{spec} {op['block']}[{op['copy']}] {fname}: is {have}, expected {val}"
                el = bytearray(appended[key][3][op['copy']])
                for fname, (kind, val) in op.get('set', {}).items():
                    fc = next(x for x in c if x.get('offset') is not None and html.unescape(x.get('name', '')) == fname); fo = int(fc.get('offset'), 16)
                    assert kind == 'ref', 'append sets references only'
                    ti = sprdiff.find(m, val); g = val.rsplit('.', 1)[1]
                    el[fo:fo + 16] = g[::-1].encode('latin1') + bytes(8) + struct.pack('<I', (int(m.tag_salt[ti]) << 16) | ti)
                appended[key][3].append(el); done.append((spec, op, None))
            else: raise SystemExit(f"{spec}: unknown op {op['op']}")
    for (spec, block), (bo, es, c, els) in appended.items():
        na = E.alloc(es * len(els)); E.write(na, b''.join(bytes(e) for e in els)); E.write(bo, struct.pack('<II', len(els), na // 4))
    E.commit()
    m2, S2 = sprdiff.load(path); cache = {}
    for spec, op, n in done:
        if spec not in cache: cache[spec] = fields(m2, S2, sprdiff.find(m2, spec))
        f = cache[spec]
        if op['op'] == 'drop_last_named':
            got = f.get(f"/{op['block']} (count)")[1]; assert got == n - 1, f'{spec}: read back {got}'
            print(f"  {spec}: {op['block']} {n} -> {got} (dropped {op['value']}: {op['why'][:90]})")
        elif op['op'] == 'append':
            units = [v[1].lower() for k, v in f.items() if re.match(rf"^/{re.escape(op['block'])}\[\d+\]/{re.escape(next(iter(op['set'])))}$", k)]
            want = next(iter(op['set'].values()))[1].lower()
            assert want in units, f"{spec} {op['block']}: no element with {want}"
            print(f"  {spec.rsplit(chr(92), 1)[-1]} {op['block']}: + a copy of [{op['copy']}] for {want.rsplit(chr(92), 1)[-1]}")
        elif op['op'] == 'flags':
            got = set(f.get(op['path'], ('flags', ()))[1])
            assert all(x in got for x in op.get('add', [])) and not any(x in got for x in op.get('remove', [])), f"{spec} {op['path']}: read back {sorted(got)}"
            print(f"  {spec.rsplit(chr(92), 1)[-1]} {op['path']}: " + ', '.join(['+' + x for x in op.get('add', [])] + ['-' + x for x in op.get('remove', [])]))
        else:
            got = f.get(op['path']); kind, val = op['value']
            ok = got is not None and (str(got[1]).lower() == str(val).lower() if kind in ('sid', 'ref') else all(abs(x - y) < 1e-4 for x, y in zip(got[1], val if isinstance(val, (list, tuple)) else [val])))
            assert ok, f"{spec} {op['path']}: read back {got}, wanted {op['value']}"
            print(f"  {spec.rsplit(chr(92), 1)[-1]} {op['path']} = {val}")
    print(f'{len(done)} compiled fixes made and read back')
main()
