# The SPR Assets inventory (2026-11-23): every SPR item in HugeGrass SPR's Forge palettes (a tag whose name ends in _spr),
# its base (the same name without _spr, in the same map), and where the base's source is:
#   stock  - H3EK ships it (the kit's archive listing)
#   rj     - RJ's repository has it (Halo3/tags)
#   none   - neither: the item is copied compiled from HugeGrass SPR (the fallback, host's decision 12) until source comes
# Items that need map scripts are left out (host's decision: no spawner crates, no Scarab or Mantis assets).
# usage: python -I inventory.py <hugegrass_spr.map> <out.json>
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
import sprdiff, sprwalk
from tagfields import strings, sid_index
FORGE = {0x1E0: 'vehicles', 0x1EC: 'weapons', 0x1F8: 'equipment', 0x204: 'scenery', 0x210: 'teleporters', 0x21C: 'goals', 0x228: 'spawners'}
SCRIPTED = ('scarab', 'mantis', 'spawner', 'crate')
# items whose base has source but which stay copied compiled until a gap has source (values\fallback.json, with why)
FALLBACK = {k: v for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'values', 'fallback.json'), encoding='utf-8')).items() if k != 'about'}
def main():
    m, S = sprdiff.load(sys.argv[1]); have = sprwalk.source_files(); releases = sprwalk.release_files()
    rj = set()
    for l in open(os.path.join(sprwalk.HERE, 'rj_tree.tsv'), encoding='utf-8'):
        p = l.split('\t')[1].strip()
        if p.startswith('Halo3/tags/'): rj.add(p[len('Halo3/tags/'):].replace('/', '\\').lower())
    grp = lambda i: m.groups[m.tag_group[i]] if 0 <= m.tag_group[i] < len(m.groups) else None
    index = {(m.names[i].lower(), grp(i)): i for i in range(m.ntags) if m.names[i] and grp(i)}
    A = int(m.tag_addr[next(i for i in range(m.ntags) if grp(i) == 'scnr')])
    items, left_out, seen = [], [], set()
    for off, shelf in FORGE.items():
        c, p = struct.unpack('<II', m.mem(A + off, 8))
        for k in range(c):
            e = m.mem(p * 4 + 0x1C * k, 0x1C)
            d = struct.unpack_from('<I', e, 12)[0]
            if d == 0xFFFFFFFF or (d & 0xFFFF) >= m.ntags: continue
            i = d & 0xFFFF; name, g = m.names[i], grp(i)
            if not name or not name.lower().endswith('_spr') or (name.lower(), g) in seen: continue
            seen.add((name.lower(), g))
            label = S[sid_index(struct.unpack_from('<I', e, 0x10)[0])]
            base = name[:-4]
            row = {'tag': f'{name}.{g}', 'label': label, 'shelf': shelf}
            if any(w in name.lower() for w in SCRIPTED): row['why'] = 'needs map scripts (host: no spawners, Scarab or Mantis)'; left_out.append(row); continue
            for suffix in ('_fast', '_pilot'):          # mongoose_fast_spr has no mongoose_fast: it was made from the mongoose
                if (base.lower(), g) not in index and base.lower().endswith(suffix) and (base[:-len(suffix)].lower(), g) in index:
                    base = base[:-len(suffix)]; row['note'] = f'no {name[:-4]} in the map: based on {base}'
            if (base.lower(), g) not in index: row['why'] = f'no base {base}.{g} in the map'; left_out.append(row); continue
            kf = sprwalk.kitfile(f'{base}.{g}').lower()
            for suffix in ('_fast', '_tracking'):      # RJ's variant (kestrel_railgun_fast, plasma_launcher_tracking) has no
                if kf not in have and base.lower().endswith(suffix):   # source, but the release's original does
                    b2 = base[:-len(suffix)]; k2 = sprwalk.kitfile(f'{b2}.{g}').lower()
                    if k2 in have:
                        if (b2.lower(), g) in index:   # HugeGrass has the original too: walk from it, RJ's changes come
                            row['note'] = f"{base} (RJ's variant) has no source: based on {b2}"; base = b2; kf = k2   # out as values
                        else:                          # HugeGrass has only RJ's variant: the values are diffed against it,
                            row['source_base'] = f'{b2}.{g}'; kf = k2   # the source copy starts from the original, and
                            row['note'] = f"{base} (RJ's variant) has no source: source copied from {b2}, RJ's changes via deep parity"
            row.update(base=f'{base}.{g}', source='rj' if kf in rj else 'release' if kf in releases else 'stock' if kf in have else 'none')
            if row['source'] != 'none' and row['tag'] in FALLBACK:
                row.update(base_source=row['source'], source='none', fallback_why=FALLBACK[row['tag']])
            items.append(row)
    json.dump({'map': sys.argv[1], 'items': items, 'left_out': left_out}, open(sys.argv[2], 'w', encoding='utf-8'), indent=1)
    from collections import Counter
    print(f"{len(items)} items: {dict(Counter(r['source'] for r in items))}; {len(left_out)} left out")
    for r in items: print(f"  {r['source']:5s} {r['shelf']:9s} {r['tag']:70s} {r['label']}")
    for r in left_out: print(f"  OUT   {r['tag']}: {r['why']}")
main()
