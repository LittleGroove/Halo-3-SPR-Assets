# One Forge entry per configuration (2026-11-23, host on the Falcons). Project Reclaimer offers every model variant of a
# Forge object as its own entry; a vehicle whose model holds one variant is one entry. For each "split" in the data file:
#   - a copy of the "from" vehicle's model (every block its own: tagkit deep_copy) whose Variants block holds only
#     "variant", as <tag>.hlmt; refused if any model target names a variant by index
#   - a copy of the "from" vehicle as <tag>.vehi, its Model pointing at that model and its Default Model Variant "variant"
#   - both new tags take their original's zone bits (add_tag like=), so the game loads them
#   - a Forge vehicle palette entry named "label" (limits copied from the "from" vehicle's entry) and a scenario Vehicle
#     Palette entry
# The "retire" vehicles come off the Forge palette (they stay in the map: the copies' sub-tags are theirs).
# Read back: each new vehicle's model, default variant, the model's one variant, the palette by name.
# For fallback items (copied compiled); a source-built item would get its configurations in source instead.
# usage: python -I split_variants.py <map, edited in place> <splits.json>
import html, json, os, struct, sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tagkit import Editor
import sprdiff, tagfields
from tagfields import fields, strings, sid_index
FORGE_VEHI = 0x1E0
def field(group, name):
    c = next(c for c in tagfields.plugin(group) if c.get('offset') is not None and html.unescape(c.get('name', '')) == name)
    return int(c.get('offset'), 16), c
def main():
    path, spec = sys.argv[1], json.load(open(sys.argv[2], encoding='utf-8'))
    E = Editor(path); m = E.m; TS = strings(m)
    grp = lambda i: m.groups[m.tag_group[i]] if 0 <= m.tag_group[i] < len(m.groups) else None
    idx = lambda s: sprdiff.find(m, s)
    datum = lambda i: (int(m.tag_salt[i]) << 16) | i
    VAR_OFF, VAR_C = field('hlmt', 'Variants'); VAR_ES = int(VAR_C.get('elementSize'), 16)
    VNAME = next(int(c.get('offset'), 16) for c in VAR_C if html.unescape(c.get('name', '')) == 'Name')
    MODEL_OFF, _ = field('vehi', 'Model'); DMV_OFF, _ = field('vehi', 'Default Model Variant')
    SEATS_OFF, SEATS_C = field('vehi', 'Seats'); SEAT_ES = int(SEATS_C.get('elementSize'), 16)
    SEAT_FLAGS2 = [int(c.get('offset'), 16) for c in SEATS_C if html.unescape(c.get('name', '')) == 'Flags'][1]   # the seat's second "Flags" (flags16)
    A = int(m.tag_addr[E.scn]); fc, fp = struct.unpack('<II', m.mem(A + FORGE_VEHI, 8))
    forge = [bytearray(m.mem(fp * 4 + 0x1C * k, 0x1C)) for k in range(fc)]
    entry_of = {struct.unpack_from('<I', e, 12)[0] & 0xFFFF: e for e in forge}
    copied = []
    for c in spec.get('copies', []):                   # plain copies of any tag under a new name (e.g. a side gun a test
        ci = idx(c['from']); g = c['from'].rsplit('.', 1)[1]   # Falcon points at; compiled_fix.py then edits it)
        el = tagfields.plugin(g); raw = E.deep_copy(int(m.tag_addr[ci]), el, int(el.get('baseSize'), 16))
        na = E.alloc(len(raw)); E.write(na, raw); E.add_tag(c['tag'], g, na, like=ci); copied.append((c['tag'], g))
    made = []
    for s in spec.get('split', []):
        vi = idx(s['from']); va = int(m.tag_addr[vi])
        mref = m.mem(va + MODEL_OFF, 16); mi = struct.unpack_from('<I', mref, 12)[0] & 0xFFFF; ma = int(m.tag_addr[mi])
        mf = fields(m, TS, mi)
        assert all(v[1] == (-1,) for k, v in mf.items() if k.endswith('/Variant Index')), f"{s['from']}: a model target names a variant"
        n, vp = struct.unpack('<II', m.mem(ma + VAR_OFF, 8))
        names = [TS[sid_index(struct.unpack('<I', m.mem(vp * 4 + VAR_ES * k + VNAME, 4))[0])] for k in range(n)]
        assert s['variant'] in names, f"{s['from']}: no variant {s['variant']} (has {names})"
        k = names.index(s['variant'])
        # the model: a deep copy, its Variants block = that one element
        mraw = bytearray(E.deep_copy(ma, tagfields.plugin('hlmt'), int(tagfields.plugin('hlmt').get('baseSize'), 16)))
        cnt, p = struct.unpack_from('<II', mraw, VAR_OFF)
        struct.pack_into('<II', mraw, VAR_OFF, 1, (p * 4 + VAR_ES * k) // 4)
        nma = E.alloc(len(mraw)); E.write(nma, bytes(mraw))
        nmi, nmd = E.add_tag(s['tag'], 'hlmt', nma, like=mi)
        # the vehicle: a deep copy pointing at it, defaulting to that variant
        vraw = bytearray(E.deep_copy(va, tagfields.plugin('vehi'), int(tagfields.plugin('vehi').get('baseSize'), 16)))
        vraw[MODEL_OFF:MODEL_OFF + 4] = b'hlmt'[::-1]; struct.pack_into('<I', vraw, MODEL_OFF + 12, nmd)
        sid = E.sid_of(s['variant']); struct.pack_into('<I', vraw, DMV_OFF, sid if sid is not None else E.add_string(s['variant']))
        sf = s.get('seats_from') or (s['from'] if s.get('pilot_from') else None)
        if sf:                                         # a Seats block of its own: another vehicle's (seats_from), each seat copied
            sa_ = int(m.tag_addr[idx(sf)]); sc, sp = struct.unpack('<II', m.mem(sa_ + SEATS_OFF, 8))
            seats = [bytearray(E.deep_copy(sp * 4 + SEAT_ES * j, SEATS_C, SEAT_ES)) for j in range(sc)]
            if s.get('pilot_from'):                    # another vehicle's pilot-seat flags (seat 0: Flags, Flags #2)
                pa_ = int(m.tag_addr[idx(s['pilot_from'])]); _, pp = struct.unpack('<II', m.mem(pa_ + SEATS_OFF, 8))
                src0 = m.mem(pp * 4, SEAT_ES)
                seats[0][0:4] = src0[0:4]; seats[0][SEAT_FLAGS2:SEAT_FLAGS2 + 2] = src0[SEAT_FLAGS2:SEAT_FLAGS2 + 2]
            nsa = E.alloc(SEAT_ES * sc); E.write(nsa, b''.join(bytes(x) for x in seats)); struct.pack_into('<II', vraw, SEATS_OFF, sc, nsa // 4)
        nva = E.alloc(len(vraw)); E.write(nva, bytes(vraw))
        nvi, nvd = E.add_tag(s['tag'], 'vehi', nva, like=vi)
        # its Forge entry (the "from" vehicle's limits) and scenario palette entry
        like = entry_of.get(vi) or next(e for e in forge if e[0:4][::-1] == b'vehi')
        e = bytearray(like); e[0:4] = b'vehi'[::-1]; e[4:12] = bytes(8); struct.pack_into('<I', e, 12, nvd)
        lsid = E.sid_of(s['label']); struct.pack_into('<I', e, 0x10, lsid if lsid is not None else E.add_string(s['label']))
        forge.append(e); E.scenario_palette_add(0xF0, nvd, 'vehi')
        made.append((s, k, names))
    retire = {idx(r) for r in spec.get('retire', [])}
    kept = [e for e in forge if (struct.unpack_from('<I', e, 12)[0] & 0xFFFF) not in retire]
    # trim_all (2026-11-23, host: "do the trim"): every vehicle still on the Forge palette whose model holds more than one
    # variant gets a model of its own holding only its default variant, so it is one Forge entry. Project Reclaimer offers
    # a model's variants once per model, the ones no vehicle defaults to under the first vehicle using it: trimming only
    # that vehicle would move them to the next one, so every vehicle on such a model is trimmed. The vehicle keeps its tag
    # (saved layouts name it); only its Model reference changes.
    trimmed = []
    if spec.get('trim_all'):
        names_taken = {(m.names[i] or '').lower() + '.' + (grp(i) or '') for i in range(m.ntags)}
        names_taken |= {(s['tag'] + '.hlmt').lower() for s in spec.get('split', [])}
        for e in kept:
            vi = struct.unpack_from('<I', e, 12)[0] & 0xFFFF
            if vi >= m.ntags or grp(vi) != 'vehi': continue    # new vehicles made above hold one variant already
            va = int(m.tag_addr[vi]); mi = struct.unpack_from('<I', m.mem(va + MODEL_OFF, 16), 12)[0] & 0xFFFF
            if mi >= m.ntags: continue
            ma = int(m.tag_addr[mi]); n, vp = struct.unpack('<II', m.mem(ma + VAR_OFF, 8))
            if n <= 1: continue
            names = [TS[sid_index(struct.unpack('<I', m.mem(vp * 4 + VAR_ES * k + VNAME, 4))[0])] for k in range(n)]
            dv = TS[sid_index(struct.unpack('<I', m.mem(va + DMV_OFF, 4))[0])] or 'default'
            k = names.index(dv) if dv in names else 0
            base = m.names[vi]; mname = base if (base + '.hlmt').lower() not in names_taken else base + '_own'
            assert (mname + '.hlmt').lower() not in names_taken, mname
            names_taken.add((mname + '.hlmt').lower())
            mraw = bytearray(E.deep_copy(ma, tagfields.plugin('hlmt'), int(tagfields.plugin('hlmt').get('baseSize'), 16)))
            cnt, p = struct.unpack_from('<II', mraw, VAR_OFF); struct.pack_into('<II', mraw, VAR_OFF, 1, (p * 4 + VAR_ES * k) // 4)
            nma = E.alloc(len(mraw)); E.write(nma, bytes(mraw)); nmi, nmd = E.add_tag(mname, 'hlmt', nma, like=mi)
            E.write(va + MODEL_OFF, b'hlmt'[::-1] + bytes(8) + struct.pack('<I', nmd))
            trimmed.append((m.names[vi], mname, names[k], n))
    na = E.alloc(0x1C * len(kept)); E.write(na, b''.join(bytes(e) for e in kept)); E.write(A + FORGE_VEHI, struct.pack('<II', len(kept), na // 4))
    E.commit()
    # read back
    n2, S2 = sprdiff.load(path); A2 = int(n2.tag_addr[next(i for i in range(n2.ntags) if n2.groups[n2.tag_group[i]] == 'scnr')])
    c, p = struct.unpack('<II', n2.mem(A2 + FORGE_VEHI, 8))
    pal = {n2.tagname(struct.unpack('<I', n2.mem(p * 4 + 0x1C * k + 12, 4))[0] & 0xFFFF).lower(): S2[sid_index(struct.unpack('<I', n2.mem(p * 4 + 0x1C * k + 0x10, 4))[0])] for k in range(c)}
    for s, k, names in made:
        vf = fields(n2, S2, sprdiff.find(n2, s['tag'] + '.vehi')); mf = fields(n2, S2, sprdiff.find(n2, s['tag'] + '.hlmt'))
        assert vf['/Model'][1].lower() == (s['tag'] + '.hlmt').lower(), vf['/Model']
        assert vf['/Default Model Variant'][1] == s['variant'] and mf['/Variants (count)'][1] == 1 and mf['/Variants[0]/Name'][1] == s['variant']
        assert pal.get((s['tag'] + '.vehi').lower()) == s['label'], (s['tag'], pal.get((s['tag'] + '.vehi').lower()))
        objs = [mf.get(f'/Variants[0]/Objects[{j}]/Child Object', ('', '?'))[1].rsplit(chr(92), 1)[-1] for j in range(mf.get('/Variants[0]/Objects (count)', ('count', 0))[1])]
        if s.get('seats_from'):
            want = fields(n2, S2, sprdiff.find(n2, s['seats_from']))['/Seats (count)'][1]
            assert vf['/Seats (count)'][1] == want, (s['tag'], vf['/Seats (count)'], want)
        if s.get('pilot_from'):
            want = fields(n2, S2, sprdiff.find(n2, s['pilot_from']))['/Seats[0]/Flags'][1]
            assert vf['/Seats[0]/Flags'][1] == want, (s['tag'], vf['/Seats[0]/Flags'], want)
        print(f"  {s['label']:30s} {s['tag'].rsplit(chr(92), 1)[-1]}: {s['variant']} of {s['from'].rsplit(chr(92), 1)[-1]} ({', '.join(objs)}); "
              f"{vf['/Seats (count)'][1]} seats, pilot {', '.join(vf.get('/Seats[0]/Flags', ('', []))[1]) or '-'}")
    for r in spec.get('retire', []): assert r.lower() not in pal, f'{r} still on the Forge palette'
    for t, g in copied: sprdiff.find(n2, f'{t}.{g}')     # each copy is in the map
    for v, mname, keep, n in trimmed:                       # each trimmed vehicle: its own model, one variant
        vf = fields(n2, S2, sprdiff.find(n2, v + '.vehi')); mf = fields(n2, S2, sprdiff.find(n2, mname + '.hlmt'))
        assert vf['/Model'][1].lower() == (mname + '.hlmt').lower() and mf['/Variants (count)'][1] == 1 and mf['/Variants[0]/Name'][1] == keep, (v, vf['/Model'], mf.get('/Variants (count)'))
        print(f"  trimmed {v.rsplit(chr(92), 1)[-1]}: {n} variants -> '{keep}' ({mname.rsplit(chr(92), 1)[-1]}.hlmt)")
    print(f"{len(copied)} tags copied; {len(trimmed)} vehicles trimmed to one variant; {len(made)} configurations made and read back; {len(spec.get('retire', []))} vehicles off the Forge palette ({len(forge) - len(kept)} entries)")
main()
