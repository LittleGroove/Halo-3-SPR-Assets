# Deep parity (2026-11-23, host: "close the two gaps ... the first is something thatll be useful to be able to do for
# anything else"): every tag under every source-built SPR item, the shipped SPR Assets map against HugeGrass SPR.
# parity.py looks only at the tags an item owns (its _spr copies). A change HugeGrass makes to a SHARED tag (stock or RJ's,
# under its own name: one of our LG fixes, or RJ's own change to a stock tag inside his map) sits deeper, in tags the item
# only uses. This walks each item's whole reference tree in HugeGrass SPR and compares every tag with the shipped map's
# tag of that name, field for field (floats within 1e-4 relative, so compiler noise doesn't count).
#
#   report (default): per item, which tags differ and how; tags missing from the shipped map
#   --write <out.json>: makes the source carry those differences, as a walk file sprapply.py takes (the item walk plus):
#       - an OWNED tag (one of the walk's _spr copies) that differs: the differences become values on it (marked "deep")
#       - a SHARED tag that differs: an _spr copy of it is made (copy_from = the shared tag, its differences as values),
#         and every tag between it and the nearest owned tag on the reference chain gets an _spr copy too, each pointing at
#         the next copy, the owned tag pointing at the first. Copies are shared between items that reach the same tag.
#     A difference in a block's element count, or under an element one side lacks, can't be written as a value: listed as
#     "structure" for a decision (the Lich's removed H5 variant is one, decided).
# Map-specific fields (indices into a map's own tables: the sound gestalt, string-id sets, runtime caches) are skipped
# by name pattern, see SKIP.
# usage: python -I deepparity.py <shipped map> <hugegrass_spr.map> <inventory.json> <walk.json> [--write <out.json>] [-v]
#        [--fallback: report on the fallback items instead]
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff, sprwalk
from tagfields import fields
STOP = {'scnr', 'matg', 'sbsp', 'char', 'mulg', 'sLdT', 'play', 'zone', 'pixl', 'vtsh', 'rmt2', 'gpix', 'glps', 'glvs',
        'rasg', 'ugh!', 'cfxs', 'rmdf', 'rmop', 'sncl', 'snmx', 'spk!', 'adlg', 'mdlg', 'udlg', 'unic', 'jmrq', 'cmoe', 'wezr'}
SKIP = re.compile(r'(?i)(^|/)(runtime|cached|.*\bindex\b(?!.*name)|.*\bgestalt\b|.*\bunknown\b)')
# What Bungie's compiler works out rather than what an author sets (round 1 on 2026-11-23 showed each of these differing
# between RJ's build and ours from the same source): skipped, as no source value can carry them.
DERIVED_GROUPS = {'mode', 'jmad', 'coll', 'bitm'}       # render geometry and flags, animation tables, collision BSPs, pixels
SKIP_GROUP_FIELDS = {
    'snd!': re.compile(r'(?i)(index|count|permutation|chunk|codec|playback|scale|promotion|custom|extra|language)'),
    'phmo': re.compile(r'.'),                           # masses, inertia, shapes: computed (masses: see phmo_scales)
    'hlmt': re.compile(r'(?i)^/(Collision Regions|Model Object Data|Render-Only Node Flags|Nodes)\b'),
    'weap': re.compile(r'(?i)Private Use Font Icon'),   # the newer kit's HUD font icons; RJ's older build has 0
}
POSTPROCESS = re.compile(r'(?i)/Postprocess\[|/Options\[')   # compiled shader data of shaders, particles, beams, contrails
def correlation(v):                                     # an effect's particle-correlation slot: numbered by the compiler
    return v is not None and v[0] == 'enum' and (isinstance(v[1], int) or 'Correlation' in str(v[1]))
def close(a, b):
    if a == b: return True
    if a is None or b is None or a[0] != b[0] or a[0] != 'num' or len(a[1]) != len(b[1]): return False
    return all(abs(x - y) <= 1e-5 + 1e-4 * abs(y) for x, y in zip(a[1], b[1]))
def skip(group, p, va=None, vb=None):
    leaf = p.rsplit('/', 1)[-1]
    if group in DERIVED_GROUPS or SKIP.search(leaf) or POSTPROCESS.search(p) or correlation(va) or correlation(vb): return True
    g = SKIP_GROUP_FIELDS.get(group); return bool(g and g.search(p))
BODIES = re.compile(r'^/Rigid Bodies\[\d+\]/Mass$')
SHAPES = re.compile(r'^/(Polyhedra|Spheres|Pills|Boxes|Triangles|Capsules)\[(\d+)\]/Mass$')
def phmo_scales(a, b):
    """a physics model's masses (HugeGrass a, shipped b) -> source values. Two ways Bungie's compiler makes masses (rounds
    1-2, 2026-11-23):
      - a source without "mopp codes dirty" keeps its authored masses (Hornet SPR: total 3700 and its bodies came out as
        written)
      - a source with it (Ghost SPR, as Bungie left it) has the physics recomputed: each shape = volume x material density x
        its Relative Mass Scale, and authored masses are ignored (written 364 + 195, came out 703 + 376 both times)
    So: the total Mass = HugeGrass's bodies' sum, and for every shape whose mass still differs a Relative Mass Scale =
    HugeGrass's mass over the compiled one (times the compiled scale, 1 by default). A shape that already matches gets no
    scale, so a model that keeps authored masses is never scaled twice."""
    if all(close(va, b.get(p)) for p, va in a.items() if BODIES.match(p)): return []
    rows = [('/Mass', ('num', (sum(va[1][0] for p, va in a.items() if BODIES.match(p)),)), b.get('/Mass'))]
    for p, va in a.items():
        vb = b.get(p)
        if not SHAPES.match(p) or vb is None or close(va, vb) or not vb[1][0]: continue
        rp = p[:-len('Mass')] + 'Relative Mass Scale'
        cur = (b.get(rp) or ('num', (1.0,)))[1][0] or 1.0
        rows.append((rp, ('num', (cur * va[1][0] / vb[1][0],)), b.get(rp)))
    return rows
def refs(fl):
    return [(p, v[1]) for p, v in fl.items() if v[0] == 'ref' and v[1] not in ('-', None, '')]
def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    out_path = None
    if '--write' in sys.argv: out_path = sys.argv[sys.argv.index('--write') + 1]; args.remove(out_path)
    mb, Sb = sprdiff.load(args[0]); mh, Sh = sprdiff.load(args[1])
    inv = json.load(open(args[2], encoding='utf-8')); walk = json.load(open(args[3], encoding='utf-8'))
    owned = {t['tag'].lower(): t for t in walk['tags']}
    # a walk written by --write earlier carries its _spr copies of shared tags: in the shipped map a source item uses the
    # copy, so the copy is what's compared with HugeGrass's shared tag (references mapped back to the shared names)
    have_copy = {k.lower(): v for k, v in walk.get('copies', {}).items()}
    back = {v.lower(): k for k, v in have_copy.items()}
    orig_name = {}                                      # lower-case name -> HugeGrass's spelling (filled while walking)
    def unmap(v):
        if v is None or v[0] != 'ref': return v
        k = back.get(str(v[1]).lower())
        return v if k is None else ('ref', orig_name.get(k, k))
    def idx(m, spec):
        try: return sprdiff.find(m, spec)
        except StopIteration: return None
    cache_h, cache_b = {}, {}
    def fh(spec):
        if spec not in cache_h: i = idx(mh, spec); cache_h[spec] = fields(mh, Sh, i) if i is not None else None
        return cache_h[spec]
    def fb(spec):
        if spec not in cache_b: i = idx(mb, spec); cache_b[spec] = fields(mb, Sb, i) if i is not None else None
        return cache_b[spec]
    diffs, missing, structure = {}, collections.defaultdict(set), collections.defaultdict(list)
    parents = collections.defaultdict(set)              # tag -> {(parent tag, field path)} in HugeGrass
    item_of = collections.defaultdict(set)
    stats = collections.Counter()
    # --fallback: the fallback items instead (copied compiled; a tag the map already had by name, from the source build or
    # Epitaph, was kept, so this shows where a fallback item ended up using another version of a shared tag)
    pick = (lambda r: r['source'] == 'none') if '--fallback' in sys.argv else (lambda r: r['source'] in ('stock', 'rj', 'release'))
    for r in [r for r in inv['items'] if pick(r)]:
        root = r['tag']; seen = {root.lower()}; todo = [root]
        while todo:
            spec = todo.pop(); item_of[spec.lower()].add(root)
            a = fh(spec)
            if a is None: continue
            group = spec.rsplit('.', 1)[1]
            for p, t in refs(a):
                tg = t.rsplit('.', 1)[-1]
                parents[t.lower()].add((spec, p)); orig_name[t.lower()] = t
                if tg in STOP or t.lower() in seen: continue
                seen.add(t.lower()); todo.append(t)
            if spec.lower() in diffs or spec.lower() in missing: continue
            # the shipped counterpart: the item's own copy if the map has it, else the tag of that name (a copy goes unused
            # when the _spr tag pointing at it was shared with a fallback item, which came first: then it's HugeGrass's)
            b = fb(have_copy[spec.lower()]) if spec.lower() in have_copy else None
            if b is None: b = fb(spec)
            if b is None: missing[spec.lower()].add(root); continue
            b = {p: unmap(v) for p, v in b.items()}
            rows = phmo_scales(a, b) if group == 'phmo' else []
            for p in dict.fromkeys(list(a) + list(b)):
                va, vb = a.get(p), b.get(p)
                if close(va, vb) or skip(group, p, va, vb): continue
                if va is None or vb is None or va[0] == 'count': structure[spec.lower()].append((p, va, vb)); continue
                rows.append((p, va, vb))
            for p, va, vb in rows: stats[(group, re.sub(r'\[\d+\]', '[]', p))] += 1
            if rows: diffs[spec.lower()] = (spec, rows)
    n_owned = sum(1 for k in diffs if k in owned); n_shared = len(diffs) - n_owned
    print(f'{len(diffs)} tags differ ({n_owned} owned, {n_shared} shared), {len(missing)} missing from the shipped map, '
          f'{len(structure)} with structural differences')
    for k, (spec, rows) in sorted(diffs.items()):
        print(f"  {'OWNED ' if k in owned else 'SHARED'} {spec}: {len(rows)} fields (items: {', '.join(sorted(x.rsplit(chr(92), 1)[-1] for x in item_of[k]))[:120]})")
        if '-v' in sys.argv:
            for p, va, vb in rows[:12]: print(f'        {p}: hugegrass {va} / shipped {vb}')
    for k, its in sorted(missing.items()): print(f'  MISSING {k} (items: {", ".join(sorted(x.rsplit(chr(92), 1)[-1] for x in its))[:120]})')
    for k, rows in sorted(structure.items()): print(f'  STRUCTURE {k}: {len(rows)} fields, e.g. {rows[0][0]}')
    if '-v' in sys.argv:
        print('most common differing fields:')
        for (g, p), n in stats.most_common(int(os.environ.get("TOP", "40"))): print(f'   {n:4d} {g} {p}')
    if not out_path: return
    # ---- the walk file that makes the source carry these differences
    out = {k: dict(t, fields=list(t['fields'])) for k, t in owned.items()}
    def spr_name(spec):
        name, g = spec.rsplit('.', 1); return f'{name}_spr.{g}'
    copies = dict(have_copy)                           # shared tag (lower) -> its _spr copy's spec (earlier rounds kept)
    def own(spec, item):
        """make the shared tag spec an _spr copy, and its parents up to an owned tag point at copies"""
        k = spec.lower()
        if k in owned or k in copies: return out[k if k in owned else copies[k].lower()]
        new = spr_name(spec); copies[k] = new
        out[new.lower()] = {'tag': new, 'item': item, 'kit_file': sprwalk.kitfile(new), 'copy_from': spec,
                            'copy_from_kit_file': sprwalk.kitfile(spec), 'source_of_base': 'source', 'fields': [], 'deep': True}
        for par, p in sorted(parents[k]):
            if not item_of[par.lower()]: continue
            t = own(par, item)                         # owned already, or made a copy now (recursively)
            t['fields'].append({'path': p, 'base': ['ref', spec], 'spr': ['ref', new], 'deep': 'points at the copy of a changed shared tag'})
        return out[new.lower()]
    for k, (spec, rows) in sorted(diffs.items()):
        before = len(copies)
        t = out[k] if k in owned else own(spec, sorted(item_of[k])[0])
        if k not in owned: print(f'  copies for {spec}: {len(copies) - before} ({", ".join(sorted(v.rsplit(chr(92), 1)[-1] for v in list(copies.values())[before:]))[:200]})')
        for p, va, vb in rows:
            t['fields'] = [f for f in t['fields'] if f['path'] != p]     # a deep value replaces the walk's on that field
            t['fields'].append({'path': p, 'base': list(vb) if vb else None, 'spr': list(va), 'deep': 'HugeGrass SPR has it; the source build did not'})
    json.dump({'map': args[1], 'tags': list(out.values()), 'copies': copies, 'missing': {k: sorted(v) for k, v in missing.items()},
               'structure': {k: [r[0] for r in v] for k, v in structure.items()}}, open(out_path, 'w', encoding='utf-8'), indent=1)
    print(f'wrote {out_path}: {len(out)} tags ({len(copies)} new _spr copies of shared tags)')
main()
