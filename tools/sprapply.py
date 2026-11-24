# Applies an SPR item's values (sprwalk.py's JSON) to Editing Kit source tags with H3EK's tool.exe, and reads them back.
# For each tag: copy the base's source file to the SPR file's name (re-copied every run, so a run always starts clean),
# apply our fixes from values\fixes.json (fixes first), then for each changed field find its tool path, convert the
# value, patch it, and check it in an XML export.
# Finding a field's tool path (plugin names from Assembly vs the kit's own names; structs exist only in the kit):
#   - the block chain must match level for level (same element index, names alike after dropping non-letters)
#   - the leaf name must match after the same normalisation; ties broken by the base's value (compiled vs source);
#   - with no name match, a field in the same block whose source value equals the base's compiled value, if unique
# Units: a value is converted when the base's compiled value x 57.29578 equals its source value (radians -> degrees).
# Tag references are written "path,group" (tool.exe ignores other forms silently). A value the read-back doesn't confirm
# is written again through mbtool.exe (ManagedBlam, typed field paths), which reaches fields tool.exe can't: a field whose
# name appears twice in the layout. Fields not mapped or not confirmed by the read-back are listed; nothing is guessed.
# usage: python -I sprapply.py <walk.json> <hugegrass_spr.map> [--dry]
import json, os, re, subprocess, sys, shutil, math, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
sys.stdout.reconfigure(encoding='utf-8')
import tagxml, sprdiff, sprwalk, tagfields
from tagfields import fields
EK = r'C:\Program Files (x86)\Steam\steamapps\common\H3EK'
TMP = r'S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\values\xml'
DRY = '--dry' in sys.argv
os.makedirs(TMP, exist_ok=True)
def tool(*a):
    r = subprocess.run([os.path.join(EK, 'tool.exe'), *a], cwd=EK, capture_output=True, text=True, errors='replace')
    return (r.stdout + r.stderr).replace('\r', '')
ROOTS = {}
def root_of(kit_file):
    ext = kit_file.rsplit('.', 1)[1]
    if ext not in ROOTS:
        out = tool('get-tag-field-value', kit_file, 'nope')
        first = next(l for l in out.splitlines() if re.match(r'^[a-z_]+\[0\]', l.strip()))
        ROOTS[ext] = first.strip().split('.')[0]
    return ROOTS[ext]
def export(kit_file):
    dst = os.path.join(TMP, kit_file.replace('\\', '__') + '.xml')
    tool('export-tag-to-xml', os.path.join(EK, 'tags', kit_file), dst)
    rows = tagxml.read(dst); r = root_of(kit_file)
    # tagxml names the root "<group>_group[0]"; the tool's own root differs for some groups (model_block_struct[0])
    fixed = []
    for p, t, v, x in rows:
        parts = p.split('.', 1)
        fixed.append((r + ('.' + parts[1] if len(parts) > 1 else ''), t, v, x))
    return fixed
def clean(s):
    s = re.sub(r'\(.*?\)|#\d+$', '', s.lower())
    return re.sub(r'\bmax\b', 'maximum', re.sub(r'\bmin\b', 'minimum', s))     # "engine max angular velocity"
def dup_index(leaf):
    """0 for a plugin name's first use in its struct, 1 for "<name> #2" (tagfields.EXACT), ..."""
    m = re.search(r'#(\d+)$', leaf); return int(m.group(1)) - 1 if m else 0
def raw_words(s): return frozenset(re.findall(r'[a-z0-9]+', re.sub(r'#\d+$', '', s.lower())))
norm = lambda s: re.sub(r'[^a-z0-9]', '', clean(s))
def tokens(s): return frozenset(t for t in re.findall(r'[a-z0-9]+', clean(s)) if t not in ('the', 'of', 'a', 'type'))
def plugin_parts(p):
    segs = [s for s in p.split('/') if s]
    chain = []
    for s in segs[:-1]:
        m = re.match(r'^(.*)\[(\d+)\]$', s); chain.append((m.group(1), int(m.group(2))) if m else (s, None))
    return chain, segs[-1]
def tool_parts(p, structs):
    """the block levels (name, index) with structs left out, and the leaf name. A path is split only after an element
    index ("...[0].leaf"): field names may hold a period themselves ("Max. transfer scale (minor)", 2026-11-23)"""
    segs = re.split(r'(?<=\])\.', p); chain = []; prefix = segs[0]
    for s in segs[1:-1]:
        prefix += '.' + s
        if prefix in structs: continue
        m = re.match(r'^(.*)\[(\d+)\]$', s); chain.append((m.group(1), int(m.group(2))) if m else (s, None))
    return chain, segs[-1]
def same_name(a, b, need=0.75):
    if norm(a) == norm(b): return True
    ta, tb = tokens(a), tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= need
def chain_match(tc, pc):
    """plugin block levels in order inside the tool's; a tool level the plugin doesn't have must be element 0 (a wrapper
    such as 'physics types[0]')"""
    i = 0
    for tn, ti in tc:
        if i < len(pc) and ti == pc[i][1] and same_name(tn, pc[i][0], 0.5): i += 1
        elif ti not in (0, None): return False
    return i == len(pc)
# Known renames (plugin leaf -> source leaf or leaves), each checked by hand against the field's meaning; a plugin pair
# split over two source fields takes one number each.
ALIAS = {
    'damage_effect': {'Area Of Effect Spike Damage Bump': ['aoe spike damage bump'],
                      'Area Of Effect Spike Radius': ['aoe spike radius']},
    'collision_damage': {'Apply Damage Scale': ['Apply collision damage scale'],
                         'Apply Recoil Damage Scale': ['Friendly apply collision damage scale'],
                         'Damage Acceleration': ['min game acc (default)', 'max game acc (default)'],
                         'Damage Scale': ['min game scale (default)', 'max game scale (default)'],
                         'Recoil Damage Acceleration': ['min abs acc (default)', 'max abs acc (default)'],
                         'Recoil Damage Scale': ['min abs scale (default)', 'max abs scale (default)']},
    'vehicle': {'Rise Target Lag': ['minimum rise target lag', 'maximum rise target lag'],
                'Up Acceleration': ['minimum up acceleration', 'maximum up acceleration'],
                'Yaw': ['yaw minimum', 'yaw maximum']},          # a seat's yaw: plugin radian range, source two angles
}
def nums(v):
    try: return [float(x) for x in str(v).split(',') if x.strip() != '']
    except ValueError: return None
def close(a, b, tol=2e-3): return a is not None and b is not None and len(a) == len(b) and all(abs(x - y) <= tol * max(1, abs(y)) for x, y in zip(a, b))
def convert(pv, srcv):
    """factor that takes a compiled value to the source's (1 or degrees), or None if they don't agree"""
    if pv is None or pv[0] != 'num': return 1.0
    a, b = list(pv[1]), nums(srcv)
    if close(a, b): return 1.0
    if close([x * 180 / math.pi for x in a], b, 5e-3): return 180 / math.pi
    return None
ANGLE = ('angle', 'angle bounds', 'real euler angles 2d', 'real euler angles 3d')
def factor(pv, srcv, ty, ptype=None):
    """(factor, note): the source's angle fields hold degrees. The compiled value is in degrees when the plugin field is
    a degree type (tagfields converts those) and in radians otherwise (a 'ranged' Yaw, say): known from the plugin's own
    type, never guessed (2026-11-23). Without the plugin type, the values decide (compiled x 57.29578 = source: radians).
    A base whose compiled value isn't the source's (RJ's variant against a release's original, say) is noted: the SPR
    value is written all the same, as HugeGrass SPR has it."""
    if ty in ANGLE and ptype:
        k = 1.0 if ptype.lower().startswith('degree') else 180 / math.pi
        same = pv is None or pv[0] != 'num' or close([x * k for x in pv[1]], nums(srcv), 5e-3)
        return k, ('' if k == 1 else 'radians -> degrees') + ('' if same else f'; base differs: compiled {fmtv(pv[1])} vs source {srcv}')
    k = convert(pv, srcv)
    if k is not None: return k, '' if k == 1 else 'radians -> degrees'
    if ty in ANGLE: return None, f'angle with units unknown (compiled {pv[1]} vs source {srcv})'
    return 1.0, f'base differs: compiled {fmtv(pv[1])} vs source {srcv}'
def plugin_type(group, ppath):
    """the plugin's element type of a field (tagfields path), e.g. 'degree', 'ranged', 'float32'; None if not found"""
    el = tagfields.plugin(group)
    for seg in [s for s in ppath.split('/') if s]:
        nm = re.sub(r'\[\d+\]$', '', re.sub(r' #\d+$', '', seg))
        el = next((c for c in el if c.get('offset') is not None and html.unescape(c.get('name', '')) == nm), None)
        if el is None: return None
    return el.tag
def fmtv(v): return ','.join(f'{x:.9g}' if isinstance(x, float) else str(x) for x in v)
def plugin_bits(group, ppath):
    """{flag name: bit} of a plugin field (path as tagfields writes it), from the Assembly plugin"""
    el = tagfields.plugin(group)
    for seg in [s for s in ppath.split('/') if s]:
        nm = re.sub(r'\[\d+\]$', '', seg)
        el = next((c for c in el if c.get('offset') is not None and html.unescape(c.get('name', '')) == nm), None)
        if el is None: return {}
    return {html.unescape(b.get('name')): int(b.get('index')) for b in el if b.tag == 'bit'}
# Bungie's compiler reorders some blocks (material effects by global material, a model's damage responses), so element n
# of a compiled block isn't always element n of the source's (deep parity round 2, 2026-11-23: a repoint for
# energy_shield_thick landed on energy_holo's element). Where the compiled element has a name key, the source element with
# the same key is the one meant.
PKEY = ('name', 'global material name', 'material name', 'region name', 'region', 'label', 'permutation name', 'variant name')
SKEY = ('name', 'material name', 'global material name', 'region name', 'region', 'label', 'permutation name', 'variant name')
def remap(ppath, base_f, leaves, structs):
    """the plugin path with each block index replaced by the source's index of the element holding the same name key"""
    chain, leaf = plugin_parts(ppath)
    if not chain or base_f is None: return ppath
    srows = []
    for p, ty, v, x in leaves:
        if ty not in ('string id', 'old string id') or not v: continue
        tc, tl = tool_parts(p, structs)
        if re.sub(r'#\d+$', '', tl.lower()).strip() in SKEY: srows.append((tc, v))
    new = []; orig = ''
    for lvl, (name, i) in enumerate(chain):
        orig += f'/{name}' + (f'[{i}]' if i is not None else '')
        j = i
        if i is not None:
            key = next((v[1] for k, v in base_f.items() if k.startswith(orig + '/') and k.count('/') == orig.count('/') + 1 and v[0] == 'sid'
                        and re.sub(r'#\d+$', '', k.rsplit('/', 1)[1].lower()).strip() in PKEY and v[1]), None)
            if key:
                hits = {tc[lvl][1] for tc, v in srows if v == key and len(tc) == lvl + 1
                        and all(same_name(tc[q][0], chain[q][0], 0.5) for q in range(lvl + 1))
                        and all(tc[q][1] == new[q][1] for q in range(lvl))}
                if len(hits) == 1: j = hits.pop()
        new.append((name, j))
    return ''.join(f'/{n}' + (f'[{i}]' if i is not None else '') for n, i in new) + '/' + leaf
def agrees(got, value):
    if got is not None and value == '': return got.split(',', 1)[0] == ''      # a reference set to nothing
    return got is not None and (got.lower() == value.lower() or close(nums(got), nums(value), 2e-3))
# ManagedBlam through mbtool.exe (a native .NET program; ManagedBlam crashes inside Python). Its typed paths name each
# field's type, so a field whose name appears twice in a layout (a barrel's "projectile" label before its "projectile"
# reference, which tool.exe resolves to the label) is reachable. Labels and custom fields hold no value and are skipped.
MB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mbtool', 'mbtool.exe')
def mbtool(*a):
    r = subprocess.run([MB, EK, *a], capture_output=True, text=True, errors='replace', timeout=300)
    return r.returncode, (r.stdout + r.stderr).replace('\r', '')
def mb_paths(kit_file):
    """tool path without its root ('unit[0].seats[0].label') -> typed path ('Struct:unit[0]/Block:seats[0]/OldStringId:label')"""
    name, ext = kit_file.rsplit('.', 1)
    code, out = mbtool('paths', name, ext); found = {}
    for line in out.splitlines():
        tp = line.split(' = ', 1)[0]
        segs = tp.split('/')
        if segs[-1].split(':', 1)[0] in ('Explanation', 'Custom', 'Block', 'Struct'): continue
        plain = '.'.join(s.split(':', 1)[1] for s in segs)
        found.setdefault(plain, []).append(tp)
    return {k: v[0] for k, v in found.items() if len(v) == 1}
def mb_value(value):
    """tool.exe's reference form 'path,proj' -> ManagedBlam's 'path,projectile' (other values pass through)"""
    if ',' in value and nums(value) is None:
        path, g = value.rsplit(',', 1)
        return f'{path},{sprwalk.EXT.get(g, g)}'
    return value
# Our fixes to base tags (values\fixes.json), applied right after the copy and before the SPR values (fixes first).
FIXES = json.load(open(os.path.join(os.path.dirname(TMP), 'fixes.json'), encoding='utf-8'))
def apply_fix(kit, fx):
    """one fix; returns a report row"""
    name, ext = kit.rsplit('.', 1)
    if fx['op'] == 'remove_named':
        code, out = mbtool('paths', name, ext)
        hit = [l for l in out.splitlines() if re.match(re.escape(fx['block']) + r'\[\d+\]/' + re.escape(fx['field']) + ' = ' + re.escape(fx['value']) + '$', l)]
        if len(hit) != 1: return (kit, 'fix: ' + fx['op'], fx['block'], fx['value'], False, f'{len(hit)} elements named so', fx['why'])
        idx = re.search(r'\[(\d+)\]/', hit[0][len(fx['block']):]).group(1)
        code, out = mbtool('remove', name, ext, fx['block'], idx)
        return (kit, 'fix: remove ' + fx['value'], f"{fx['block']}[{idx}]", fx['value'], code == 0, out.strip().splitlines()[-1] if out.strip() else '', fx['why'])
    return (kit, 'fix: ' + fx['op'], '', '', False, 'unknown op', fx.get('why', ''))
def main():
    walk = json.load(open(sys.argv[1], encoding='utf-8')); m, S = sprdiff.load(sys.argv[2])
    report = []
    for t in walk['tags']:
        kit, base_kit = t['kit_file'], t['copy_from_kit_file']
        src, dst = os.path.join(EK, 'tags', base_kit), os.path.join(EK, 'tags', kit)
        if not DRY:
            os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst)
            for fx in FIXES.get(kit, []):
                if fx['op'] != 'value': report.append(apply_fix(kit, fx))   # 'value' fixes go with the values below
        rows = export(base_kit); structs = {p + '[0]' for p, ty, v, x in rows if ty == 'struct'}
        leaves = [(p, ty, v, x) for p, ty, v, x in rows if ty not in ('struct', 'block')]
        base_f = fields(m, S, sprdiff.find(m, t['copy_from']))
        group_ext = kit.rsplit('.', 1)[1]
        plan = []                                       # (field, tool path or None, value or None, note)
        fixed = [{'path': fx['path'], 'base': None, 'spr': fx['value'], 'fix': fx['why']}
                 for fx in FIXES.get(kit, []) if fx['op'] == 'value']
        for f in fixed + t['fields']:
            chain, leaf = plugin_parts(remap(f['path'], base_f, leaves, structs)); sv = f['spr']   # source element order
            # a deep value (deepparity.py) carries the source build's compiled value as its base: that's what tells the
            # units (HugeGrass's base already has the target value there)
            bv = tuple(f['base']) if 'deep' in f and f.get('base') else base_f.get(f['path'])
            targets = ALIAS.get(group_ext, {}).get(leaf, [leaf])
            found = []
            for want in targets:
                cands = [(p, ty, v, x) for p, ty, v, x in leaves
                         if chain_match(tool_parts(p, structs)[0], chain) and same_name(tool_parts(p, structs)[1], want)]
                if len(cands) > 1:                      # exact names first
                    exact = [c for c in cands if norm(tool_parts(c[0], structs)[1]) == norm(want)]; cands = exact or cands
                if len(cands) > 1:                      # then the fewest block levels the plugin path doesn't have
                    depth = min(len(tool_parts(c[0], structs)[0]) for c in cands)
                    cands = [c for c in cands if len(tool_parts(c[0], structs)[0]) == depth]
                if len(cands) > 1:                      # then the words in brackets too ("guided angular velocity (lower)")
                    sc = [len(raw_words(want) & raw_words(tool_parts(c[0], structs)[1])) / len(raw_words(want) | raw_words(tool_parts(c[0], structs)[1])) for c in cands]
                    if sc.count(max(sc)) == 1: cands = [cands[sc.index(max(sc))]]
                if len(cands) > 1 and bv is not None and len(targets) == 1:   # then the base's value agreeing
                    agree = [c for c in cands if convert(tuple(bv), c[2]) is not None]; cands = agree or cands
                if len(cands) > 1 and len({norm(tool_parts(c[0], structs)[1]) for c in cands}) == 1 and dup_index(leaf) < len(cands):
                    cands = [cands[dup_index(leaf)]]    # one name used twice in both layouts (loaded / cruising torque):
                found.append(cands)                     # the plugin's n-th use is the source's n-th, in layout order
            if any(len(c) != 1 for c in found):
                plan.append((f, None, None, 'not mapped: ' + ' | '.join(f'{len(c)} candidates' + (': ' + '; '.join(x[0] for x in c[:2]) if c else '') for c in found)))
                continue
            paths = [c[0] for c in found]
            if sv[0] == 'ref':
                if sv[1] in ('-', '', None):                # a reference set to nothing (HugeGrass's red Plasma Rifle has no LOD)
                    plan.append((f, paths[0][0], '', 'set to none')); continue
                name, g = sv[1].rsplit('.', 1)
                plan.append((f, paths[0][0], f'{name},{g}', '')); continue
            if sv[0] == 'num':
                ptype = plugin_type(sprdiff.find_group(m, t['copy_from']), f['path'])
                if len(paths) == 1:
                    k, note = factor(tuple(bv) if bv else None, paths[0][2], paths[0][1], ptype)
                    if k is None: plan.append((f, paths[0][0], None, note)); continue
                    plan.append((f, paths[0][0], ','.join(f'{x * k:.9g}' for x in sv[1]), note))
                else:                                   # one number per source field (an angle pair in degrees: the
                    for (p, ty, v, x0), x in zip(paths, sv[1]):   # plugin's type says whether it was radians)
                        k = 180 / math.pi if ty in ANGLE and ptype and not ptype.lower().startswith('degree') else 1.0
                        plan.append((f, p, f'{x * k:.9g}', 'split pair' + ('' if k == 1 else ', radians -> degrees')))
                continue
            if sv[0] == 'flags':
                # toggle exactly the bits the SPR copy changed (bit numbers from the plugin: the engine's layout, which the
                # source shares), and only where the source's bits are the compiled base's
                p, ty, v, names = paths[0]; bits = plugin_bits(sprdiff.find_group(m, t['copy_from']), f['path'])
                was, now = set(bv[1]) if bv else set(), set(sv[1])
                if not bits or any(n not in bits for n in was ^ now):
                    plan.append((f, p, None, 'flag names not in the plugin')); continue
                src = int(v); flip = sum(1 << bits[n] for n in was ^ now)
                if any(((src >> bits[n]) & 1) != (n in was) for n in was ^ now):
                    plan.append((f, p, None, f'source flags {names} differ from the compiled base {sorted(was)} on these bits')); continue
                plan.append((f, p, str(src ^ flip), 'flags: ' + ', '.join(('+' if n in now else '-') + n for n in sorted(was ^ now))))
                continue
            if sv[0] in ('sid', 'enum'):
                plan.append((f, paths[0][0], str(sv[1]).lower() if sv[0] == 'enum' else str(sv[1]), '')); continue
            plan.append((f, paths[0][0], None, f'kind {sv[0]} not handled yet'))
        if not DRY:
            for f, p, value, note in plan:
                if p and value is not None: tool('patch-tag-field', kit, p, value)
        after = {r[0]: r[2] for r in export(kit)} if not DRY else {}
        if not DRY:                                     # what tool.exe couldn't reach: ManagedBlam (mbtool) by typed path
            missed = [(f, p, value, note) for f, p, value, note in plan if p and value is not None and not agrees(after.get(p), value)]
            if missed:
                typed = mb_paths(kit)
                for f, p, value, note in missed:
                    tp = typed.get(p.split('.', 1)[1])
                    if tp: mbtool('set', *kit.rsplit('.', 1), tp, mb_value(value))
                after = {r[0]: r[2] for r in export(kit)}
        for f, p, value, note in plan:
            ok = agrees(after.get(p), value) if p and value is not None else None
            report.append((kit, ('fix: ' if 'fix' in f else '') + f['path'], p, value, ok, after.get(p), note))
    bad = 0
    for kit, pp, tp, value, ok, got, note in report:
        mark = 'OK ' if ok else ('-- ' if DRY and value is not None else 'NO ' if value is None else 'BAD'); bad += 0 if ok else 1
        tail = f'  [{note}]' if note else ''
        print(f'{mark} {kit.rsplit(chr(92), 1)[-1]:40s} {pp:50s} -> {tp or "?"} = {value}{tail}' + ('' if ok or DRY or value is None else f'   (read back: {got})'))
    print(f'{len(report) - bad} of {len(report)} written and read back' if not DRY else
          f'{sum(1 for r in report if r[3] is not None)} of {len(report)} mapped')
main()
