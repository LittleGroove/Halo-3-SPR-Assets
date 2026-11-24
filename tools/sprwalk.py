# Every tag an SPR item owns and what each one changes, from the built HugeGrass SPR map (our values, frozen as data).
# Start: (SPR tag, its base). For each pair: the fields that differ (sprdiff.diff). A field that is a tag reference and
# points at another tag than the base's does: if that tag is one the source build must make (it isn't stock Halo 3 in
# H3EK's archive or in RJ's repository), it is made from what the base references there (or, with nothing there, left
# for a decision) and walked the same way.
# Output: JSON {"tags": [{"tag", "group", "copy_from", "fields": [{"path", "base", "spr"}]}], "unresolved": [...]}
# usage: python -I sprwalk.py <hugegrass_spr.map> <out.json> "spr.group=base.group" ...  |  <inventory.json> (every item
#        with source). A tag reached from two items with different bases is listed under "conflicts".
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff
HERE = r'S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\research (2026-11-22)'
EXT = {'vehi': 'vehicle', 'weap': 'weapon', 'proj': 'projectile', 'jpt!': 'damage_effect', 'hlmt': 'model', 'phmo': 'physics_model',
       'coll': 'collision_model', 'mode': 'render_model', 'cddf': 'collision_damage', 'effe': 'effect', 'eqip': 'equipment',
       'bloc': 'crate', 'scen': 'scenery', 'jmad': 'model_animation_graph', 'snd!': 'sound', 'lsnd': 'sound_looping',
       'chdt': 'chud_definition', 'cntl': 'contrail_system', 'bitm': 'bitmap', 'rmsh': 'shader', 'foot': 'material_effects',
       'drdf': 'damage_response_definition', 'trak': 'camera_track', 'ligh': 'light', 'lens': 'lens_flare', 'prt3': 'particle'}
def source_files():
    have = set()
    for l in open(os.path.join(HERE, 'kit listings', 'H3EK.tsv'), encoding='utf-8', errors='replace'):
        if '\t' in l:
            p = l.rstrip('\n').split('\t', 1)[1].lower()
            if p.startswith('tags\\'): have.add(p[5:])
    for l in open(os.path.join(HERE, 'rj_tree.tsv'), encoding='utf-8'):
        p = l.split('\t')[1].strip()
        if p.startswith('Halo3/tags/'): have.add(p[len('Halo3/tags/'):].replace('/', '\\').lower())
    return have | release_files()
VARIANT_SUFFIXES = ('_fast', '_tracking', '_pf')   # RJ's variants of a release's tags
OVERLAYS = r'S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\overlays'
def release_files():
    """tags the downloaded releases put into H3EK (overlay manifests nexus-*: Sparrowhawk, Vulture, Kestrel, R3ACH);
    never our own _spr files (p1-spr), which the walk has to make"""
    have = set()
    for f in os.listdir(OVERLAYS):
        if f.startswith('nexus-') and f.endswith('.json'):
            for k in json.load(open(os.path.join(OVERLAYS, f), encoding='utf-8'))['added']:
                if k.lower().startswith('tags\\'): have.add(k[5:].lower())
    return have
def kitfile(spec):
    name, g = spec.rsplit('.', 1); return f'{name}.{EXT.get(g, g)}'
if __name__ == '__main__':
    mp, out = sys.argv[1], sys.argv[2]
    m, S = sprdiff.load(mp); have = source_files()
    args = sys.argv[3:]
    if len(args) == 1 and args[0].endswith('.json'):   # an inventory (inventory.py): every item with source
        args = [f"{r['tag']}={r['base']}" + (f"={r['source_base']}" if r.get('source_base') else '')
                for r in json.load(open(args[0], encoding='utf-8'))['items'] if r['source'] in ('stock', 'rj', 'release')]
    # "spr=base" or "spr=base=source base": the values are diffed against base (in HugeGrass SPR); the source copy starts
    # from source base when HugeGrass has only RJ's variant (kestrel_railgun_fast) and a release has the original
    todo = [(a.split('=')[0], a.split('=')[1], a.split('=')[0], a.split('=')[2] if a.count('=') > 1 else None) for a in args]
    done = {}; unresolved = []; conflicts = []
    while todo:
        spr, base, item, src_base = todo.pop(0)
        if spr.lower() in done:                        # one SPR tag reached from two items: it must have one base
            if done[spr.lower()]['copy_from'].lower() != base.lower():
                conflicts.append({'tag': spr, 'item': item, 'kept': done[spr.lower()]['copy_from'], 'also': base})
            continue
        rows = sprdiff.diff(m, S, spr, base); fields = []
        for p, bv, sv in rows:
            fields.append({'path': p, 'base': list(bv) if bv else None, 'spr': list(sv) if sv else None})
            if sv and sv[0] == 'ref' and sv[1] not in ('-', None):
                target = sv[1]; btarget = bv[1] if bv and bv[0] == 'ref' else None
                if kitfile(target).lower() in have: continue          # a stock or RJ tag: nothing to make
                sb = None                                              # RJ's variant of a release tag (focus_rifle_beam_pf):
                if btarget and btarget != '-' and kitfile(btarget).lower() not in have:   # copy the release's original
                    for suf in VARIANT_SUFFIXES:
                        nm, g = btarget.rsplit('.', 1)
                        if nm.lower().endswith(suf) and kitfile(f'{nm[:-len(suf)]}.{g}').lower() in have: sb = f'{nm[:-len(suf)]}.{g}'; break
                if btarget and btarget != '-': todo.append((target, btarget, item, sb))
                else: unresolved.append({'tag': target, 'item': item, 'referenced_by': spr, 'field': p, 'why': 'the base references nothing here'})
        cf = kitfile(src_base or base)
        done[spr.lower()] = {'tag': spr, 'item': item, 'kit_file': kitfile(spr), 'copy_from': base, 'copy_from_kit_file': cf,
                             'source_of_base': 'source' if cf.lower() in have else 'NOT IN SOURCE', 'fields': fields}
        if src_base: done[spr.lower()]['source_base'] = src_base
    json.dump({'map': mp, 'tags': list(done.values()), 'unresolved': unresolved, 'conflicts': conflicts}, open(out, 'w', encoding='utf-8'), indent=1)
    for t in done.values():
        print(f"{t['kit_file']}  <- copy of {t['copy_from_kit_file']} ({t['source_of_base']}): {len(t['fields'])} fields")
    for u in unresolved: print('UNRESOLVED', u)
    for c in conflicts: print('CONFLICT', c)
