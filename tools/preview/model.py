# Loads Halo 3 objects from the H3EK tags for the Workshop preview render (2026-11-23). Everything comes from tool.exe's
# own exports, nothing from a cache map:
#   object (.vehicle ...) -> its model (.model): default variant, the variant's region permutations, child objects at
#   markers (a Warthog's turret) -> render model (.render_model, export-tag-to-xml): per mesh temporary = the source
#   vertices and triangle-strip indices; parts = index ranges with a material; nodes posed by their default transforms
#   (rigid meshes are in their node's space, skinned ones in model space); markers -> material -> shader's base_map bitmap
#   (export-bitmap-tga).
# Halo axes throughout: x forward, y left, z up, in world units.
import os, re, subprocess, hashlib, pickle
import numpy as np
EK = r'C:\Program Files (x86)\Steam\steamapps\common\H3EK'
TOOL = os.path.join(EK, 'tool.exe')
EXT = {'vehi': 'vehicle', 'hlmt': 'model', 'mode': 'render_model', 'rmsh': 'shader', 'rmcs': 'shader_custom',
       'rmhg': 'shader_halogram', 'rmd ': 'shader_decal', 'rmd': 'shader_decal', 'rmfl': 'shader_foliage', 'bitm': 'bitmap',
       'weap': 'weapon', 'scen': 'scenery', 'bloc': 'crate', 'eqip': 'equipment', 'bipd': 'biped', 'mach': 'device_machine'}
CACHE = os.environ.get('PREVIEW_CACHE') or os.path.join(os.environ['TEMP'], 'spr_preview_cache')
os.makedirs(CACHE, exist_ok=True)
import tagxml

def _key(s): return re.sub(r'[^\w.-]+', '_', s)[-120:]

def rows(tag, group):
    """tagxml rows of an H3EK tag (path without extension, group or extension)"""
    ext = EXT.get(group, group)
    out = os.path.join(CACHE, _key(tag + '.' + ext) + '.xml')
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        subprocess.run([TOOL, 'export-tag-to-xml', os.path.join(EK, 'tags', tag + '.' + ext), out], cwd=EK,
                       capture_output=True)
    if not os.path.exists(out) or os.path.getsize(out) == 0: raise FileNotFoundError(tag + '.' + ext)
    return tagxml.read(out)

def ref(v):
    if not v or ',' not in v: return None, None
    p, g = v.rsplit(',', 1); return (p, g.strip()) if p else (None, None)

def quat(q):
    i, j, k, w = q
    n = (i * i + j * j + k * k + w * w) ** 0.5 or 1.0; i, j, k, w = i / n, j / n, k / n, w / n
    return np.array([[1 - 2 * (j * j + k * k), 2 * (i * j - k * w), 2 * (i * k + j * w)],
                     [2 * (i * j + k * w), 1 - 2 * (i * i + k * k), 2 * (j * k - i * w)],
                     [2 * (i * k - j * w), 2 * (j * k + i * w), 1 - 2 * (i * i + j * j)]])

def nums(v): return [float(x) for x in v.split(',')] if v else []
def bidx(v):
    try: return int(v.rsplit(',', 1)[-1])
    except ValueError: return -1

def render_model(tag, perms=None):
    """{'pos','nrm','uv','tris','mat','shaders','markers'}: the chosen permutation of every region (perms: region ->
    permutation name; otherwise 'base'/'default' or the first)"""
    ck = os.path.join(CACHE, _key(tag) + '.' + hashlib.md5(repr(sorted((perms or {}).items())).encode()).hexdigest()[:8] + '.pkl')
    if os.path.exists(ck): return pickle.load(open(ck, 'rb'))
    R = rows(tag, 'mode')
    regions, nodes, markers, shaders, meshes, temp, comp = {}, {}, {}, {}, {}, {}, {}
    rx = re.compile(r'\[(\d+)\]')
    for p, t, v, x in R:
        q = p.split('_group[0].', 1)[-1]
        if q.startswith('regions['):
            ix = [int(n) for n in rx.findall(q)]; f = q.rsplit('.', 1)[-1]
            reg = regions.setdefault(ix[0], {'perms': {}})
            if len(ix) == 1 and f == 'name': reg['name'] = v
            elif len(ix) == 2: reg['perms'].setdefault(ix[1], {})[f] = v
        elif q.startswith('nodes['):
            ix = int(rx.findall(q)[0]); f = q.rsplit('.', 1)[-1]; nodes.setdefault(ix, {})[f] = v
        elif q.startswith('marker groups['):
            ix = [int(n) for n in rx.findall(q)]; f = q.rsplit('.', 1)[-1]
            g = markers.setdefault(ix[0], {'list': {}})
            if len(ix) == 1 and f == 'name': g['name'] = v
            elif len(ix) == 2: g['list'].setdefault(ix[1], {})[f] = v
        elif q.startswith('render geometry[0].compression info[0].') and t != 'block':
            comp[q.rsplit('.', 1)[-1]] = v
        elif q.startswith('materials[') and q.endswith('render method'):
            shaders[int(rx.findall(q)[0])] = ref(v)
        elif q.startswith('render geometry[0].meshes['):
            ix = [int(n) for n in rx.findall(q)]; f = q.rsplit('.', 1)[-1]; m = meshes.setdefault(ix[1], {'parts': {}})
            if '.parts[' in q: m['parts'].setdefault(ix[2], {})[f] = v
            elif len(ix) == 2 and t != 'block': m[f] = v
        elif q.startswith('render geometry[0].per mesh temporary['):
            ix = [int(n) for n in rx.findall(q)]; f = q.rsplit('.', 1)[-1]; m = temp.setdefault(ix[1], {'v': {}, 'i': []})
            if '.raw vertices[' in q:
                vv = m['v'].setdefault(ix[2], {})
                if f in ('node index', 'node weight'): vv.setdefault(f, []).append(float(v))
                else: vv[f] = v
            elif '.raw indices[' in q: m['i'].append(int(v) & 0xFFFF)
    # nodes: absolute transforms
    nabs = []
    for k in range(len(nodes)):
        n = nodes[k]; Rl = quat(nums(n['default rotation'])); tl = np.array(nums(n['default translation']))
        par = bidx(n.get('parent node', ',-1'))
        if par >= 0: Rp, tp = nabs[par]; nabs.append((Rp @ Rl, Rp @ tl + tp))
        else: nabs.append((Rl, tl))
    # which meshes: one permutation per region
    use = []
    for r in regions.values():
        ps = [r['perms'][k] for k in sorted(r['perms'])]
        if not ps: continue
        want = (perms or {}).get(r.get('name'))
        if want == '': continue                          # the variant hides this region
        pick = next((p for p in ps if p.get('name') == want), None) if want else None
        pick = pick or next((p for p in ps if p.get('name') in ('base', 'default')), ps[0])
        mi, mc = int(pick.get('mesh index', -1)), int(pick.get('mesh count', 1))
        if mi >= 0: use += list(range(mi, mi + mc))
    P, N, U, T, M = [], [], [], [], []; base = 0
    for mi in use:
        if mi not in temp or mi not in meshes: continue
        tm, me = temp[mi], meshes[mi]
        vs = [tm['v'][k] for k in sorted(tm['v'])]
        if not vs: continue
        pos = np.array([nums(v['position']) for v in vs]); nrm = np.array([nums(v['normal']) for v in vs])
        uv = np.array([nums(v.get('texcoord', '0,0'))[:2] for v in vs])
        # the source vertices are compressed to 0..1 inside the model's bounds (compression info: bounds 0 = x min, x max,
        # y min; bounds 1 = y max, z min, z max; texcoords u min, u max / v min, v max), in model space for every vertex type
        if comp.get('position bounds 0'):
            b0, b1 = nums(comp['position bounds 0']), nums(comp['position bounds 1'])
            lo, hi = np.array([b0[0], b0[2], b1[1]]), np.array([b0[1], b1[0], b1[2]])
            pos = lo + pos * (hi - lo)
        if comp.get('texcoord bounds 0'):
            u0, v0 = nums(comp['texcoord bounds 0']), nums(comp['texcoord bounds 1'])
            uv = np.array([u0[0], v0[0]]) + uv * np.array([u0[1] - u0[0], v0[1] - v0[0]])
        idx = tm['i']; strip = me.get('index buffer type', 'triangle strip') == 'triangle strip'
        for pk in sorted(me['parts']):
            pt = me['parts'][pk]; s0 = int(pt.get('index start', 0)) & 0xFFFF; c = int(pt.get('index count', 0)) & 0xFFFF
            mat = bidx(pt.get('render method index', ',-1')); seg = idx[s0:s0 + c]
            if strip:
                for k in range(len(seg) - 2):
                    a, b, cc = seg[k], seg[k + 1], seg[k + 2]
                    if 0xFFFF in (a, b, cc) or a == b or b == cc or a == cc: continue
                    T.append((a + base, b + base, cc + base) if k % 2 == 0 else (b + base, a + base, cc + base)); M.append(mat)
            else:
                for k in range(0, len(seg) - 2, 3):
                    T.append((seg[k] + base, seg[k + 1] + base, seg[k + 2] + base)); M.append(mat)
        P.append(pos); N.append(nrm); U.append(uv); base += len(pos)
    mk = {}
    for g in markers.values():
        for m in g['list'].values():
            ni = int(m.get('node index', 0)); Rn, tn = nabs[ni] if 0 <= ni < len(nabs) else (np.eye(3), np.zeros(3))
            Rm = quat(nums(m['rotation'])) if m.get('rotation') else np.eye(3); tm_ = np.array(nums(m['translation']))
            mk.setdefault(g.get('name', ''), (Rn @ Rm, Rn @ tm_ + tn))
    out = {'pos': np.concatenate(P) if P else np.zeros((0, 3)), 'nrm': np.concatenate(N) if N else np.zeros((0, 3)),
           'uv': np.concatenate(U) if U else np.zeros((0, 2)), 'tris': np.array(T, np.int64).reshape(-1, 3),
           'mat': np.array(M, np.int64), 'shaders': [shaders.get(k, (None, None)) for k in range(len(shaders))], 'markers': mk}
    pickle.dump(out, open(ck, 'wb'))
    return out

def model_of(obj, group):
    """(model tag, default model variant) of an object tag"""
    hl, dv = None, None
    for p, t, v, x in rows(obj, group):
        if p.endswith('.model') and t == 'tag reference' and hl is None: hl = ref(v)[0]
        elif p.endswith('default model variant') and dv is None: dv = v
    return hl, dv

def model_variant(hlmt, variant):
    """(render model tag, {region: permutation}, [(parent marker, child marker, child variant, (tag, group))])"""
    rm, vars_ = None, {}
    rx = re.compile(r'\[(\d+)\]')
    for p, t, v, x in rows(hlmt, 'hlmt'):
        q = p.split('_group[0].', 1)[-1]
        if q == 'render model': rm = ref(v)[0]
        elif q.startswith('variants['):
            ix = [int(n) for n in rx.findall(q)]; f = q.rsplit('.', 1)[-1]; var = vars_.setdefault(ix[0], {'regions': {}, 'objects': {}})
            if len(ix) == 1 and f == 'name': var['name'] = v
            elif '.regions[' in q and '.permutations[' not in q: var['regions'].setdefault(ix[1], {'perms': []})[f] = v
            elif '.regions[' in q and '.permutations[' in q and f == 'permutation name': var['regions'][ix[1]]['perms'].append(v)
            elif '.objects[' in q: var['objects'].setdefault(ix[1], {})[f] = v
    chosen = next((v for v in vars_.values() if v.get('name') == (variant or 'default')), None) or (vars_.get(0) if vars_ else None)
    perms, kids = {}, []
    if chosen:
        for r in chosen['regions'].values():
            if r.get('region name') and r['perms']: perms[r['region name']] = r['perms'][0]
        for o in chosen['objects'].values():
            kids.append((o.get('parent marker', ''), o.get('child marker', ''), o.get('child variant name', ''), ref(o.get('child object', ''))))
    return rm, perms, kids

_bitmaps = {}
def base_map(shader):
    """the shader's base_map bitmap as an RGB float array (h, w, 3) in 0..1, or None"""
    if shader is None or shader[0] is None: return None
    if shader in _bitmaps: return _bitmaps[shader]
    img = None
    try:
        bm = None; scale = None
        for p, t, v, x in rows(shader[0], shader[1]):
            if p.endswith('parameter name'): cur = v
            elif p.endswith('.bitmap') and t == 'tag reference' and cur == 'base_map' and bm is None: bm = ref(v)[0]
        if bm:
            from PIL import Image
            prefix = os.path.join(CACHE, 'bm_' + _key(bm) + '_')
            out = prefix + bm.rsplit('\\', 1)[-1] + '_00_00.tga'
            if not os.path.exists(out):
                subprocess.run([TOOL, 'export-bitmap-tga', bm, prefix], cwd=EK, capture_output=True)
            if os.path.exists(out):
                img = np.asarray(Image.open(out).convert('RGB'), np.float32) / 255.0
    except FileNotFoundError:
        img = None
    _bitmaps[shader] = img
    return img

def load(obj, group, variant=None, depth=0):
    """[(render model dict, R, t)] for an object and its child objects, placed at their markers"""
    hl, dv = model_of(obj, group)
    if not hl: return []
    rm, perms, kids = model_variant(hl, variant or dv)
    if not rm: return []
    m = render_model(rm, perms)
    out = [(m, np.eye(3), np.zeros(3))]
    if depth < 3:
        for pm, cm, cv, (ct, cg) in kids:
            if not ct or pm not in m['markers']: continue
            Rp, tp = m['markers'][pm]
            for (cm_, Rc, tc) in load(ct, cg, cv or None, depth + 1):
                if cm:
                    pass                                   # child markers: not needed for the vehicles drawn
                out.append((cm_, Rp @ Rc, Rp @ tc + tp))
    return out
