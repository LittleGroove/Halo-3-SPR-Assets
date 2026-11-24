# Gives SPR Assets objects their Forge palette entries, with SPR display names.
# Why: Project Reclaimer 0.10.9 can't join a server whose forge_mods mod is content-only (bug report 2026-11-22), so
# SPR Assets ships as an ordinary mod map, and an ordinary mod map's Forge objects are exactly its Forge palette entries,
# each shown under its display name ("SABRE SPR", host's check on LG Forge 2026-11-22).
# For each "name.group=Display Name":
#   - a Forge palette entry (0x1C: tag reference, display name string id +0x10, maximum allowed +0x14, +0x18) in the
#     palette of the object's kind (scnr +0x1E0 vehicles, +0x1EC weapons, +0x1F8 equipment, +0x204 scenery), copied
#     from that palette's first entry of the same kind (so its limits are a stock object's), pointing at the tag, named
#     by the display name (found among the map's strings, else added)
#   - the scenario's own Vehicle (+0xF0) / Weapon (+0x120) Palette lists it (a weapon not listed there never readies)
# A tag that already has one Forge entry (importtags brings the compile map's, 2026-11-23) gets that entry renamed.
# Refuses a name that isn't in the map. Appends only (layouts name mod objects
# by tag path, so order doesn't matter for them, but appending keeps every existing code the same).
# The map must be in the flat layout with room (relayout.py, then ceiling.py), as for importtags.py.
# usage: python -I forge_palette.py <map, edited in place> "objects\vehicles\banshee\banshee_spr.vehi=Banshee SPR" ...
import struct, sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
from tagkit import Editor
from tagfields import strings, sid_index
B = chr(92)
FORGE = {'vehi': 0x1E0, 'weap': 0x1EC, 'eqip': 0x1F8, 'scen': 0x204, 'bloc': 0x204}
SCEN_PALETTE = {'vehi': 0xF0, 'weap': 0x120}
path, specs = sys.argv[1], sys.argv[2:]
E = Editor(path); m = E.m; TS = strings(m)
grp = lambda i: m.groups[m.tag_group[i]] if 0 <= m.tag_group[i] < len(m.groups) else None
index = {(m.names[i].lower(), grp(i)): i for i in range(m.ntags) if m.names[i] and grp(i)}
datum = lambda i: (int(m.tag_salt[i]) << 16) | i
A = int(m.tag_addr[E.scn])
rows = {}
def palette(off):
    if off not in rows:
        c, p = struct.unpack('<II', m.mem(A + off, 8))
        rows[off] = [bytearray(m.mem(p * 4 + 0x1C * k, 0x1C)) for k in range(c)]
    return rows[off]
for spec in specs:
    target, label = spec.split('=', 1)
    name, group = target.rsplit('.', 1)
    i = index.get((name.lower(), group))
    assert i is not None, f'{target}: not in the map'
    off = FORGE[group]; ents = palette(off); d = datum(i)
    have = [e for e in ents if struct.unpack_from('<I', e, 12)[0] & 0xFFFF == i]
    assert len(have) <= 1, f'{target}: {len(have)} Forge entries already'
    if have:                                           # brought by importtags from the compile map (its name a string id
        sid = E.sid_of(label)                          # like banshee_spr): renamed; its scenario palette entry is there too
        struct.pack_into('<I', have[0], 0x10, sid if sid is not None else E.add_string(label))
        print(f'  {name.rsplit(B, 1)[-1]}.{group}: Forge palette +0x{off:x} entry {ents.index(have[0])} renamed "{label}"'); continue
    like = next((e for e in ents if e[0:4][::-1].decode('latin1') == group), ents[0] if ents else None)
    assert like is not None, f'{target}: the Forge palette +0x{off:x} is empty: nothing to copy the limits from'
    e = bytearray(like); e[0:4] = group[::-1].encode('latin1'); e[4:12] = bytes(8); struct.pack_into('<I', e, 12, d)
    sid = E.sid_of(label)
    struct.pack_into('<I', e, 0x10, sid if sid is not None else E.add_string(label))
    ents.append(e)
    extra = ''
    if group in SCEN_PALETTE: extra = f'; scenario {group} palette entry {E.scenario_palette_add(SCEN_PALETTE[group], d, group)}'
    print(f'  {name.rsplit(B, 1)[-1]}.{group}: Forge palette +0x{off:x} entry {len(ents) - 1} "{label}"{extra}')
for off, ents in rows.items():
    na = E.alloc(0x1C * len(ents)); E.write(na, b''.join(bytes(e) for e in ents)); E.write(A + off, struct.pack('<II', len(ents), na // 4))
E.commit()
# read back
from h3map import Map
n = Map(path); TS2 = strings(n); A2 = int(n.tag_addr[E.scn])
for spec in specs:
    target, label = spec.split('=', 1); name, group = target.rsplit('.', 1)
    c, p = struct.unpack('<II', n.mem(A2 + FORGE[group], 8))
    hit = [struct.unpack('<I', n.mem(p * 4 + 0x1C * k + 0x10, 4))[0] for k in range(c)
           if n.tagname(struct.unpack('<I', n.mem(p * 4 + 0x1C * k + 12, 4))[0] & 0xFFFF).lower() == f'{name}.{group}'.lower()]
    assert len(hit) == 1 and TS2[sid_index(hit[0])] == label, f'{target}: read back {hit} ({[TS2[sid_index(h)] for h in hit]})'
print(f'{len(specs)} Forge entries added and read back by name')
