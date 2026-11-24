# Brings tags from another map into this one (SPR Map Pack, 2026-10-27; host: bring the HugeGrass items 2Fort lacks, "they
# go hard and having options helps"; "building our own is worth it in the long run, but learning from assembly goes a long
# way"). For each root ("name.group=like name"): the root and every tag under it that this map lacks (by name) are copied
# whole from the source: every block and data reference gets its own copy, tag references point at this map's tags of the
# same name (or the new ones), and string ids from the source's own strings are found or added here by text (Halo 3's
# engine string sets are the same in every map, so those ids stay as they are).
#   - each new tag borrows the zone bits of its counterpart here (the tag the "like" root references at the same field:
#     hornet_fast.vehi's model <-> hornet.vehi's model), else the like root itself. Salts come from tagkit (a sequence the
#     network lookup finds; checked on commit).
#   - weapons go into the scenario Weapon Palette, vehicles into its Vehicle Palette (a weapon not listed there never
#     readies: LG 1.0.2-1.0.5), and each root gets the source's Forge entry (its name string found or added here).
#   - RESOURCES (render models, bitmaps, animations: data in the map's resource section). Learned from Assembly's
#     TagContainerInjector (fd14ef3) and from what it left in Wize's 2Fort, done our way (appends only; Assembly rewrites
#     whole tables and has bugs there):
#       1. the raw pages the new resources use are copied byte for byte (still compressed) to the end of the resource
#          section, each 0x1000-aligned; the locale, debug and tag sections after it move down in the file, and every
#          address into them moves with them (header 0x10, the debug tables 0x24-0x44, the 12 language packs' index and
#          data offsets in the globals). Page Block Offsets are absolute file offsets (checked: pages inflate in place).
#       2. zone tag: new File Locations (pages; CRC and SHA-1s stay valid, the bytes are identical), Default Locations,
#          Resources (owner = the new tag, type matched by GUID: the maps order them differently, the map's own salt
#          sequence, control data appended to the control buffer at its alignment, optional-control slots after the last
#          one and the total raised: Assembly never raises it, so Wize's map has 13.5 KB of slots past its buffer),
#          Control Fixups and Interop Locations copied (relative to the resource's own data).
#       3. each manifest's Required / Deferred / Optional / Streamed resource bits grow to the new count and the new ones
#          mirror the source map's (global <- global, every zone set <- any zone set; Assembly sets the global Required
#          bit only), and the zone's and manifests' size fields are recomputed by the rules read from a map Bungie's tools
#          built (checked on the source first: if they don't reproduce its values exactly, they're left alone).
#       4. the copied tags' resource fields ("[zone] Asset Datum") point at the new resources.
#     No predictions are written for these tags (about 8% of HugeGrass's prediction quanta don't follow the encoding
#     Assembly assumes); they're loading hints, and the resources are marked required as in the source.
#   - SOUNDS: a sound tag's indices into the map's sound gestalt (ugh!) are remapped, appending what it uses: codec,
#     playback and scale (reused when an identical one is there), its pitch ranges with their import names, parameters,
#     runtime permutation flags, permutations and chunks (FMOD bank suffix strings by text; the FMOD banks themselves are the
#     mod's files, the same in both maps here), and its extra info (copied whole). Appends only (Assembly rewrites the whole
#     gestalt, with bugs that rename permutations and orphan custom playbacks). Sounds that use promotions, custom
#     playbacks, language durations or language permutations are refused (none of HugeGrass's new ones do).
#   - after writing, every new tag is read back and compared with the source field by field (references by name, strings
#     by text), every new resource's control data and every copied page with the source's; any difference stops the build.
# usage: importtags.py <map, edited in place> <source map> name.group=like_name [...]   (names with / or \)
import sys, os, re, struct, html, zlib, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tagkit import Editor
from h3map import Map
from tagfields import fields, strings, plugin, sid_index, NS
B = chr(92)
target, source = sys.argv[1], sys.argv[2]
ROOTS = []
for a in sys.argv[3:]:
    left, like = a.split('=', 1); name, group = left.rsplit('.', 1)
    ROOTS.append((name.replace('/', B), group, like.replace('/', B)))
FORGE = (0x1E0, 0x1EC, 0x1F8, 0x204, 0x210, 0x21C, 0x228)       # Forge palettes: vehicles, weapons, equipment, scenery, teleporters, goals, spawners
PALETTE = {'vehi': 0xF0, 'weap': 0x120}
RESNAME = re.compile(r'(asset|resource) (index|datum)', re.I)      # Assembly's rule for resource fields (DataBlockBuilder)
NOT_YET = {'sbsp', 'Lbsp'}
MANIFESTS = [(0x70, 0x78), (0x7C, 0x78), (0x88, 0x78), (0x94, 0x78), (0xA0, 0x78), (0xAC, 0x78), (0xB8, 0x78), (0xC4, 0x78),
             (0xD0, 0x78), (0xDC, 0x78), (0xE8, 0x78), (0xF4, 0x78), (0x100, 0x78), (0x194, 0x90)]
BITS = (0x0, 0xC, 0x18, 0x24)                                     # Required, Deferred, Optional, Streamed resource bits
S = Map(source); SS = strings(S)
m0 = Map(target); TS0 = strings(m0)
sgrp = lambda i: S.groups[S.tag_group[i]] if S.tag_group[i] >= 0 else None
SI = {(S.names[i], sgrp(i)): i for i in range(S.ntags) if S.names[i]}
def index_of(m): return {(m.names[i], m.groups[m.tag_group[i]]): i for i in range(m.ntags) if m.names[i] and m.tag_group[i] >= 0}
TI0 = index_of(m0)
FIXED = sum(NS)
assert SS[:FIXED] == TS0[:FIXED], 'the engine string sets differ between the maps'
# ---- which tags come over
def refs_of(i):
    """every tag reference under a tag, at any depth (tagfields.fields stops at 4 block levels and 64 entries; a Wombat HUD
    reference sat deeper), with the field path tagfields would give it"""
    out = []
    def go(addr, el, size, path):
        raw = S.mem(addr, size, strict=False)
        for c in el:
            if c.get('offset') is None: continue
            o, t = int(c.get('offset'), 16), c.tag.lower(); p = f"{path}/{html.unescape(c.get('name', ''))}"
            if t == 'tagblock':
                es = int(c.get('elementSize'), 16); cnt, ptr = struct.unpack_from('<II', raw, o)
                if cnt and es and ptr:
                    for k in range(cnt): go(ptr * 4 + es * k, c, es, f'{p}[{k}]')
            elif t == 'tagref':
                d = struct.unpack_from('<I', raw, o + 12)[0]; j = d & 0xFFFF
                if d != 0xFFFFFFFF and j < S.ntags: out.append((p, j))
    el = plugin(sgrp(i)); go(int(S.tag_addr[i]), el, int(el.get('baseSize'), 16), '')
    return out
new = {}                                                 # source index -> its counterpart here (zone bits)
# Shader code (templates rmt2, compiled pixel and vertex shaders pixl / vtsh): MCC maps are built with "optimized"
# shaders, each map's templates stripped to what that map uses, so a template of the same name here can have other
# passes and parameters (2Fort vs HugeGrass: 43 of the 112 the first import reused, and the render method definitions'
# option lists differ). Reusing them drew HugeGrass's shaders wrong: the Scarabs' broken legs orange, the Gravity Throne a
# bright ball (host, 2026-10-28). Like Assembly's Unique Shaders (_shaderGroups mtsb/mats/pixl/vtsh/rmt2, renamed with a
# suffix), these come over as our own copies, named <name>_hg (reused if an earlier import brought them), unless this
# map's one is the same all the way down (compiled shader code included) and uses no shader code that differs
# (2Fort: 192 of 336 differ, 10.5 MB: every template-pixel pair that differs; all vertex shaders are identical).
SHADER_CODE = {'rmt2', 'pixl', 'vtsh'}
NEWNAME = {}
def deep(mp, st, i):
    """a tag's whole content: numbers and flags byte for byte, references by name, strings by text, data byte for byte"""
    el = plugin(mp.groups[mp.tag_group[i]]); out = []
    def go(addr, el, size):
        raw = mp.mem(addr, size, strict=False); skip = set()
        for c in el:
            if c.get('offset') is None: continue
            o, t = int(c.get('offset'), 16), c.tag.lower()
            if t == 'tagblock':
                es = int(c.get('elementSize'), 16); cnt, p = struct.unpack_from('<II', raw, o); out.append(('n', cnt)); skip.update(range(o, o + 12))
                for k in range(cnt if es and p else 0): go(p * 4 + es * k, c, es)
            elif t == 'dataref':
                n, p = struct.unpack_from('<I', raw, o)[0], struct.unpack_from('<I', raw, o + 12)[0]; skip.update(range(o, o + 20))
                out.append(('d', mp.mem(p * 4, n, strict=False) if n and p else b''))
            elif t == 'tagref':
                d = struct.unpack_from('<I', raw, o + 12)[0]; skip.update(range(o, o + 16)); out.append(('r', mp.tagname(d & 0xFFFF) if d != 0xFFFFFFFF else None))
            elif t == 'stringid':
                v = struct.unpack_from('<I', raw, o)[0]; skip.update(range(o, o + 4)); out.append(('s', st[sid_index(v)] if v else ''))
        out.append(('b', bytes(x for k, x in enumerate(raw) if k not in skip)))
    go(int(mp.tag_addr[i]), el, int(el.get('baseSize'), 16)); return out
SAME = {}
def shader_differs(i):
    """this source shader-code tag can't be this map's of the same name (it differs, or uses shader code that does)"""
    if i not in SAME:
        SAME[i] = True                                   # (cycle guard)
        j = TI0[(S.names[i], sgrp(i))]
        d = deep(S, SS, i) != deep(m0, TS0, j)
        if not d:
            d = any(sgrp(c) in SHADER_CODE and (S.names[c], sgrp(c)) in TI0 and shader_differs(c) for p, c in refs_of(i))
        SAME[i] = not d
    return not SAME[i]
def here_name(i):
    if i in NEWNAME: return NEWNAME[i]
    if sgrp(i) in SHADER_CODE and (S.names[i] + '_hg', sgrp(i)) in TI0: return S.names[i] + '_hg'
    return S.names[i]
def plan(i, like, root_like):
    if i in new: return
    if (S.names[i], sgrp(i)) in TI0:
        if sgrp(i) not in SHADER_CODE: return
        if (S.names[i] + '_hg', sgrp(i)) in TI0: return
        if not shader_differs(i): return                   # this map's is the same all the way down: use it
        NEWNAME[i] = S.names[i] + '_hg'
        if like is None: like = TI0[(S.names[i], sgrp(i))]          # its zone bits: the template of the same name here
    assert plugin(sgrp(i)) is not None, f'{S.tagname(i)}: no plugin for {sgrp(i)}'
    new[i] = like if like is not None else root_like
    fl = fields(m0, TS0, like) if like is not None and m0.groups[m0.tag_group[like]] == sgrp(i) else {}
    for path, j in refs_of(i):
        v = fl.get(path, ('', '-'))[1]; c = TI0.get(tuple(v.rsplit('.', 1))) if '.' in v else None
        plan(j, c if c is not None and m0.groups[m0.tag_group[c]] == sgrp(j) else None, root_like)
for name, group, like in ROOTS:
    assert (name, group) not in TI0, f'{name}.{group} is already in this map'
    li = TI0[(like, group)]; plan(SI[(name, group)], li, li)
todo = sorted(S.tagname(i) for i in new if sgrp(i) in NOT_YET)
assert not todo, f'sounds and structure aren\'t copied yet: {todo[:8]}'
# ---- the source's resources these tags use (their resource fields), and the zone tables
def walk(addr, el, size, cb, m):
    """every resource field under a struct: cb(datum)"""
    raw = m.mem(addr, size, strict=False)
    for c in el:
        if c.get('offset') is None: continue
        o, t = int(c.get('offset'), 16), c.tag.lower(); nm = html.unescape(c.get('name', ''))
        if t == 'tagblock':
            es = int(c.get('elementSize'), 16); cnt, p = struct.unpack_from('<II', raw, o)
            if cnt and es and p:
                for k in range(cnt): walk(p * 4 + es * k, c, es, cb, m)
        elif RESNAME.search(nm):
            assert t == 'datum', f'{nm}: a resource field of type {t}'
            cb(struct.unpack_from('<I', raw, o)[0])
class Zone:
    def __init__(self, m):
        self.m = m; self.i = next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'zone')
        self.a = int(m.tag_addr[self.i])
        # The resource layout table (codec 0x0, shared files 0xC, file locations / raw pages 0x18, streaming sublocations
        # 0x24, patch lookup 0x30, default locations 0x3C) is inline in the zone at +0x1C in tool.exe single-file builds
        # (HugeGrass, 2Fort: their play tag is null), and in the play tag in Bungie's shared builds and Reclaimer Kit maps
        # (SPR Assets P7, 2026-11-22). self.la is its base; for zone-inline maps every offset is the same as before.
        pl = [i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'play']
        pa = int(m.tag_addr[pl[0]]) if pl else 0
        self.la = pa if pa and struct.unpack('<I', m.mem(pa + 0x18, 4))[0] else self.a + 0x1C
    def blk(self, off, a=None):
        c, p = struct.unpack('<II', self.m.mem((self.a if a is None else a) + off, 8)); return c, p * 4
    def rows(self, off, size, a=None):
        c, p = self.blk(off, a); data = self.m.mem(p, size * c) if c else b''
        return [data[size * k:size * (k + 1)] for k in range(c)]
    def control(self):
        sz, p = struct.unpack('<I', self.m.mem(self.a + 0x148, 4))[0], struct.unpack('<I', self.m.mem(self.a + 0x148 + 12, 4))[0]
        return self.m.mem(p * 4, sz) if sz else b''
    def bits(self, off, size, k, bo):
        c, p = self.blk(off); bc, bp = struct.unpack('<II', self.m.mem(p + size * k + bo, 8))
        return struct.unpack(f'<{bc}I', self.m.mem(bp * 4, 4 * bc)) if bc else ()
ZS = Zone(S)
SRES, SLOC, SPAGE = ZS.rows(0x64, 0x40), ZS.rows(0x3C, 0x10, ZS.la), ZS.rows(0x18, 0x58, ZS.la)
used = set()
for i in new:
    def cb(d, i=i):
        if d == 0xFFFFFFFF: return
        r = d & 0xFFFF; assert r < len(SRES) and struct.unpack_from('<H', SRES[r], 0x10)[0] == d >> 16, f'{S.tagname(i)}: bad resource datum {d:#x}'
        used.add(r)
    walk(int(S.tag_addr[i]), plugin(sgrp(i)), int(plugin(sgrp(i)).get('baseSize'), 16), cb, S)
owned = {r for r, e in enumerate(SRES) if struct.unpack_from('<I', e, 12)[0] != 0xFFFFFFFF and struct.unpack_from('<I', e, 12)[0] & 0xFFFF in new}
assert used <= owned, f'resources used by new tags but owned by tags this map has: {sorted(used - owned)[:5]}'
RES = sorted(owned)
def page_ok(p): return struct.unpack_from('<i', SPAGE[p], 8)[0] != -1
PAGES = []
for r in RES:
    li = struct.unpack_from('<h', SRES[r], 0x22)[0]
    if 0 <= li < len(SLOC):
        for w in struct.unpack_from('<hh', SLOC[li], 0):
            if 0 <= w < len(SPAGE) and page_ok(w) and w not in PAGES: PAGES.append(w)
assert all(struct.unpack_from('<h', SPAGE[w], 4)[0] == -1 for w in PAGES), 'pages in shared files are not handled'
print(f'{len(new)} tags to bring in; {len(RES)} resources, {len(PAGES)} raw pages ({sum(struct.unpack_from("<I", SPAGE[w], 0xC)[0] for w in PAGES) / 1e6:.1f} MB)')
# ---- size fields (zone +0x15C..+0x168, each manifest's +0x30..+0x40): sums of the pages' uncompressed sizes, each rounded
# up to 0x1000, over the resources' primary (and secondary) pages. Read off HugeGrass (Bungie's tools built it):
#   Minimum Complete (+0x15C): every resource, primary and secondary pages   Minimum Required / DVD (+0x160/+0x164): primary
#   Global Required (+0x168): primary pages of the global manifest's required resources
#   manifest +0x30 / +0x40: its required resources' primary pages; +0x34: the same, bitmaps only; +0x38: their secondary pages
def zone_sizes(resrows, locrows, pagerows, req_of, is_bitm):
    us = [struct.unpack_from('<I', e, 0x10)[0] for e in pagerows]
    def tot(rs, which):
        ps = set()
        for r in rs:
            li = struct.unpack_from('<h', resrows[r], 0x22)[0]
            if 0 <= li < len(locrows):
                for k in which:
                    w = struct.unpack_from('<h', locrows[li], 2 * k)[0]
                    if 0 <= w < len(pagerows): ps.add(w)
        return sum((us[w] + 0xFFF) // 0x1000 * 0x1000 for w in ps) & 0xFFFFFFFF
    allr = range(len(resrows)); prim = tot(allr, (0,))
    out = {('zone', 0x15C): tot(allr, (0, 1)), ('zone', 0x160): prim, ('zone', 0x164): prim, ('zone', 0x168): tot(req_of(0x7C, 0), (0,))}
    for off, k, req in req_of(None, None):
        p = tot(req, (0,)); out[(off, k, 0x30)] = p; out[(off, k, 0x40)] = p
        out[(off, k, 0x34)] = tot([r for r in req if is_bitm(r)], (0,)); out[(off, k, 0x38)] = tot(req, (1,))
    return out
def stored_sizes(z, keys):
    out = {}
    for key in keys:
        if key[0] == 'zone': out[key] = struct.unpack('<I', z.m.mem(z.a + key[1], 4))[0]
        else:
            off, k, f = key; c, p = z.blk(off); size = dict(MANIFESTS)[off]; out[key] = struct.unpack('<I', z.m.mem(p + size * k + f, 4))[0]
    return out
def req_sets(z, nres):
    def get(off, k):
        if off is None:
            return [(o, kk, get(o, kk)) for o, size in MANIFESTS for kk in range(z.blk(o)[0])]
        w = z.bits(off, dict(MANIFESTS)[off], k, 0x0)
        return {i for i in range(min(nres, 32 * len(w))) if w[i // 32] >> (i % 32) & 1}
    return get
def bitm_of(m, rows):
    def f(r):
        d = struct.unpack_from('<I', rows[r], 12)[0]
        return d != 0xFFFFFFFF and m.tag_group[d & 0xFFFF] >= 0 and m.groups[m.tag_group[d & 0xFFFF]] == 'bitm'
    return f
SIZES_OK = False
if RES:
    want = zone_sizes(SRES, SLOC, SPAGE, req_sets(ZS, len(SRES)), bitm_of(S, SRES)); have = stored_sizes(ZS, want)
    miss = [k for k in want if want[k] != have[k]]
    SIZES_OK = not miss
    print('size fields: the rules reproduce every value in the source' if SIZES_OK else f'size fields: {len(miss)} of {len(want)} not reproduced in the source (e.g. {miss[:3]}): left as they are')
# ---- 1. raw pages into the resource section (the sections after it move down)
NEWOFF = {}
if PAGES:
    h = bytearray(m0.h); u = lambda o: struct.unpack_from('<I', h, o)[0]
    assert m0.masks == [0, 0, 0, 0], 'run normalize.py first'
    res_va, res_size = m0.secs[1]; ins = res_va + res_size
    later = [s for s in (0, 2, 3) if m0.secs[s][1]]
    assert all(m0.secs[s][0] >= ins for s in later), 'a section before the end of the resource section'
    blob = bytearray()
    for w in PAGES:
        off, cs = struct.unpack_from('<II', SPAGE[w], 8)
        NEWOFF[w] = ins + len(blob); blob += bytes(S.mm[off:off + cs]); blob += bytes((-len(blob)) % 0x1000)
    N = len(blob)
    G = int(m0.tag_addr[next(i for i in range(m0.ntags) if m0.tag_group[i] >= 0 and m0.groups[m0.tag_group[i]] == 'matg')])
    packs = [(G + 0x8 + 0x50 * k + 0x10, struct.unpack('<IIII', m0.mem(G + 0x8 + 0x50 * k + 0x10, 16))) for k in range(12)]
    loc_va, loc_size = m0.secs[3]
    for a, (cnt, size, io, do) in packs:
        assert not cnt or (loc_va <= io < loc_va + loc_size and loc_va <= do < loc_va + loc_size), 'a language pack outside the locale section'
    struct.pack_into('<I', h, 0x08, u(0x08) + N)
    struct.pack_into('<I', h, 0x4E8, res_size + N)
    for s in later: struct.pack_into('<I', h, 0x4DC + 8 * s, m0.secs[s][0] + N)
    for o in (0x10, 0x24, 0x2C, 0x34, 0x3C, 0x44):
        if u(o) >= ins: struct.pack_into('<I', h, o, u(o) + N)
    before = (m0.names, m0.tag_addr.tolist(), TS0)
    pack_file = [(m0.file_of(a) + N + 8, struct.pack('<II', io + N if cnt else io, do + N if cnt else do)) for a, (cnt, size, io, do) in packs]
    del m0
    tmp = target + '.tmp'
    with open(target, 'rb') as fi, open(tmp, 'wb') as fo:
        fo.write(bytes(h)); fi.seek(0x4000); left = ins - 0x4000
        while left:
            b = fi.read(min(1 << 26, left)); fo.write(b); left -= len(b)
        fo.write(bytes(blob))
        while True:
            b = fi.read(1 << 26)
            if not b: break
            fo.write(b)
    with open(tmp, 'r+b') as fh:
        for f, d in pack_file: fh.seek(f); fh.write(d)
    import gc; gc.collect()                           # recursive helpers (deep, walk) hold the old map open until collected
    os.replace(tmp, target)
    chk = Map(target)
    assert (chk.names, chk.tag_addr.tolist(), strings(chk)) == before, 'the map reads differently after moving its sections'
    for w in PAGES:
        off, cs, us = struct.unpack_from('<III', SPAGE[w], 8)
        assert bytes(chk.mm[NEWOFF[w]:NEWOFF[w] + cs]) == bytes(S.mm[off:off + cs])
    del chk
    print(f'resource section +{N:#x} ({len(PAGES)} pages at 0x{ins:x}); locale, debug and tags moved down; 12 language packs re-pointed')
# ---- 2. the tags
E = Editor(target); m = E.m; TS = strings(m); TI = index_of(m)
ZT = Zone(m); TRES, TLOC, TPAGE = ZT.rows(0x64, 0x40), ZT.rows(0x3C, 0x10, ZT.la), ZT.rows(0x18, 0x58, ZT.la)
NEWD, ADDR = {}, {}
for i in sorted(new):
    g = sgrp(i); size = int(plugin(g).get('baseSize'), 16)
    a = E.alloc(size); k, d = E.add_tag(here_name(i), g, a, like=new[i]); NEWD[i] = d; ADDR[i] = (a, size)
if RES: E.own_predictions = {NEWD[i] & 0xFFFF for i in new}
# resources: new indices and salts (the map's own sequence)
rc0 = len(TRES); last_salt = struct.unpack_from('<H', TRES[-1], 0x10)[0]
RMAP = {}
for k, r in enumerate(RES):
    s = (last_salt - (rc0 - 1) + rc0 + k) & 0xFFFF
    RMAP[r] = (rc0 + k, s if s != 0xFFFF else 0)
text_index = {}
for t, s in enumerate(TS):
    if s is not None and t >= FIXED and s not in text_index: text_index[s] = t
added = {}
def sid(v):
    if not v: return v
    t = sid_index(v)
    if t < FIXED: return v                               # an engine string: the same id in every map
    s = SS[t]
    if s in text_index: return text_index[s] - sum(NS[1:])
    if s not in added: added[s] = E.add_string(s)
    return added[s]
def ref(d):
    if d == 0xFFFFFFFF: return d
    i = d & 0xFFFF
    if i in NEWD: return NEWD[i]
    j = TI.get((here_name(i), sgrp(i))); assert j is not None, f'{S.tagname(i)} is neither here nor coming'
    return E.datum(j)
def res(d):
    if d == 0xFFFFFFFF: return d
    k, s = RMAP[d & 0xFFFF]; return (s << 16) | k
def copy(addr, el, size):
    raw = bytearray(S.mem(addr, size, strict=False))
    for c in el:
        if c.get('offset') is None: continue
        o, t = int(c.get('offset'), 16), c.tag.lower()
        if t == 'tagblock':
            es = int(c.get('elementSize'), 16); cnt, p = struct.unpack_from('<II', raw, o)
            if cnt and es and p:
                data = b''.join(copy(p * 4 + es * k, c, es) for k in range(cnt))
                na = E.alloc(len(data)); E.write(na, data); struct.pack_into('<II', raw, o, cnt, na // 4)
        elif t == 'dataref':
            sz, dp = struct.unpack_from('<I', raw, o)[0], struct.unpack_from('<I', raw, o + 12)[0]
            if sz and dp:
                na = E.alloc(sz); E.write(na, S.mem(dp * 4, sz, strict=False)); struct.pack_into('<I', raw, o + 12, na // 4)
        elif t == 'tagref': struct.pack_into('<I', raw, o + 12, ref(struct.unpack_from('<I', raw, o + 12)[0]))
        elif t == 'stringid': struct.pack_into('<I', raw, o, sid(struct.unpack_from('<I', raw, o)[0]))
        elif t == 'datum':
            assert RESNAME.search(html.unescape(c.get('name', ''))), f'{c.get("name")}: a datum field, not handled'
            struct.pack_into('<I', raw, o, res(struct.unpack_from('<I', raw, o)[0]))
    return bytes(raw)
# ---- sounds: the sound gestalt
UGH = {}
if any(sgrp(i) == 'snd!' for i in new):
    PU = plugin('ugh!'); ue = {html.unescape(c.get('name', '')): c for c in PU if c.get('offset') is not None}
    su = int(S.tag_addr[next(i for i in range(S.ntags) if sgrp(i) == 'ugh!')]); tu = int(m.tag_addr[next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'ugh!')])
    BL = {'codec': (0x4, 3), 'playback': (0x10, 0x44), 'scale': (0x1C, 0x14), 'name': (0x28, 4), 'param': (0x34, 0xE), 'pitch': (0x40, 0xC),
          'perm': (0x4C, 0x14), 'langperm': (0x58, 0x94), 'custom': (0x64, 0x48), 'langdur': (0x70, 0x1C), 'flags': (0x7C, 1), 'chunk': (0xA4, 0x20),
          'promo': (0xB0, 0x24), 'extra': (0xBC, 0xC)}
    def urows(mp, a, key):
        off, size = BL[key]; c, p = struct.unpack('<II', mp.mem(a + off, 8)); d = mp.mem(p * 4, size * c) if c else b''
        return [d[size * k:size * (k + 1)] for k in range(c)]
    SU = {k: urows(S, su, k) for k in BL}; TU = {k: urows(m, tu, k) for k in BL}; UGH['rows'] = TU; UGH['addr'] = tu; UGH['changed'] = set()
    # A target's own language permutations (stock dialogue: Kit maps carry their base map's) are kept as they are: imports
    # only append after them, so their indices stay valid (SPR Assets P7, 2026-11-22). The source's aren't handled.
    assert not SU['langperm'], 'language permutations in the source are not handled'
    # runtime permutation flags (checked on HugeGrass and 2Fort; Assembly's SaveSoundResourceTable): a pitch range with encoded
    # permutation data (0) holds a run of runtime "virtual bits" (-1 under 2 permutations), runs back to back, each
    # floor(log2(n - 1)) + n + 1 bits; one without (-1) holds (byte index << 3) into the flags block, ceil(n / 8) bytes each.
    UGH['vbit'] = 0
    for r in TU['pitch']:
        d, f, e = struct.unpack_from('<h', r, 4)[0], struct.unpack_from('<h', r, 6)[0], struct.unpack_from('<I', r, 8)[0]; n = (e >> 20) & 0x3F
        if d != -1 and f >= 0: UGH['vbit'] = max(UGH['vbit'], f + int(math.log2(n - 1)) + n + 1)
    def reuse(key, row):
        rows = TU[key]
        if row in rows: return rows.index(row)
        rows.append(row); UGH['changed'].add(key); return len(rows) - 1
    def append(key, row): TU[key].append(row); UGH['changed'].add(key); return len(TU[key]) - 1
    def name(k):
        if k < 0: return k
        return reuse('name', struct.pack('<I', sid(struct.unpack('<I', SU['name'][k])[0])))
    def sound(raw):
        cnt = raw[3]; codec, fpr, fld = struct.unpack_from('<hhh', raw, 4); pb, sc = struct.unpack_from('<hh', raw, 0xC)
        promo, cp = struct.unpack_from('<bb', raw, 0x10); ei = struct.unpack_from('<h', raw, 0x12)[0]
        assert promo < 0 and cp < 0 and fld < 0, 'a sound with promotions, custom playbacks or language durations'
        if codec >= 0: struct.pack_into('<h', raw, 4, reuse('codec', SU['codec'][codec]))
        if pb >= 0: struct.pack_into('<h', raw, 0xC, reuse('playback', SU['playback'][pb]))
        if sc >= 0: struct.pack_into('<h', raw, 0xE, reuse('scale', SU['scale'][sc]))
        if ei >= 0:
            el = ue['Extra Info']; c, p = struct.unpack('<II', S.mem(su + 0xBC, 8))
            struct.pack_into('<h', raw, 0x12, append('extra', copy(p * 4 + 0xC * ei, el, 0xC)))
        if fpr >= 0 and cnt:
            first = None
            for k in range(fpr, fpr + cnt):
                pr = bytearray(SU['pitch'][k])
                struct.pack_into('<h', pr, 0, name(struct.unpack_from('<h', pr, 0)[0]))
                pi = struct.unpack_from('<h', pr, 2)[0]
                if pi >= 0: struct.pack_into('<h', pr, 2, reuse('param', SU['param'][pi]))
                enc = struct.unpack_from('<I', pr, 8)[0]; pcount, pfirst = (enc >> 20) & 0x3F, enc & 0xFFFFF
                fi, encd = struct.unpack_from('<h', pr, 6)[0], struct.unpack_from('<h', pr, 4)[0]
                if fi >= 0 and encd != -1:                   # encoded: a run of runtime virtual bits, back to back after the last
                    struct.pack_into('<h', pr, 6, UGH['vbit']); UGH['vbit'] += int(math.log2(pcount - 1)) + pcount + 1
                elif fi >= 0:                                # not encoded: (byte index << 3) into the flags block, ceil(n / 8) bytes
                    nb = (pcount + 7) // 8; nf = len(TU['flags'])
                    for f in range(fi >> 3, (fi >> 3) + nb): append('flags', SU['flags'][f])
                    struct.pack_into('<h', pr, 6, nf << 3)
                npf = len(TU['perm'])
                for q in range(pfirst, pfirst + pcount):
                    pm = bytearray(SU['perm'][q]); struct.pack_into('<h', pm, 0, name(struct.unpack_from('<h', pm, 0)[0]))
                    fc, cc = struct.unpack_from('<ih', pm, 8)
                    if fc >= 0 and cc > 0:
                        nc = len(TU['chunk'])
                        for ch in range(fc, fc + cc):
                            row = bytearray(SU['chunk'][ch]); struct.pack_into('<I', row, 0x1C, sid(struct.unpack_from('<I', row, 0x1C)[0])); append('chunk', bytes(row))
                        struct.pack_into('<i', pm, 8, nc)
                    append('perm', bytes(pm))
                assert npf < (1 << 20)
                struct.pack_into('<I', pr, 8, (enc & ~0xFFFFF) | npf)
                n = append('pitch', bytes(pr)); first = n if first is None else first
            struct.pack_into('<h', raw, 6, first)
        return raw
for i in sorted(new):
    a, size = ADDR[i]; data = copy(int(S.tag_addr[i]), plugin(sgrp(i)), size)
    if sgrp(i) == 'snd!': data = bytes(sound(bytearray(data)))
    E.write(a, data)
    print(f'  + {here_name(i)}.{sgrp(i)}  (zone bits of {m.tagname(new[i])})')
# ---- 3. the zone tag: pages, locations, resources, control data, bits, sizes
def put_block(off, rows, size, a=None):
    data = b''.join(rows); na = E.alloc(len(data)); E.write(na, data)
    E.write((ZT.a if a is None else a) + off, struct.pack('<II', len(rows), na // 4))
if RES:
    guid = lambda rows: [r[:0x10] for r in rows]
    assert guid(ZS.rows(0x10, 0x14)) == guid(ZT.rows(0x10, 0x14)) and ZS.rows(0x0, 0x10, ZS.la) == ZT.rows(0x0, 0x10, ZT.la), 'interop or codec tables differ'   # by GUID (names are each map's own strings)
    stype, ttype = guid(ZS.rows(0x4, 0x1C)), guid(ZT.rows(0x4, 0x1C))
    null_t = next((k for k, e in enumerate(TPAGE) if struct.unpack_from('<i', e, 8)[0] == -1), None)
    PMAP = {w: len(TPAGE) + k for k, w in enumerate(PAGES)}
    null_add = None                                     # a Kit map has no null page: add the source's after the copied ones
    if null_t is None:
        null_src = next((w for w in range(len(SPAGE)) if not page_ok(w)), None)
        if null_src is not None:
            null_t = len(TPAGE) + len(PAGES); null_add = bytearray(SPAGE[null_src]); struct.pack_into('<h', null_add, 0x54, 0)
    def page(w):
        if w < 0: return w
        return PMAP[w] if w in PMAP else null_t if not page_ok(w) else None
    scb, cb = ZS.control(), bytearray(ZT.control())
    opt_total = struct.unpack('<i', m.mem(ZT.a + 0x16C, 4))[0]
    new_res, new_loc, refs = [], [], {}
    for k, r in enumerate(RES):
        e = bytearray(SRES[r]); nk, ns = RMAP[r]
        struct.pack_into('<I', e, 12, ref(struct.unpack_from('<I', e, 12)[0])); struct.pack_into('<H', e, 0x10, ns)
        e[0x12] = ttype.index(stype[e[0x12]])
        al = 1 << e[0x13]; co, csz, oco = struct.unpack_from('<iii', e, 0x14)
        cb += bytes((-len(cb)) % al); struct.pack_into('<i', e, 0x14, len(cb)); cb += scb[co:co + csz]
        if struct.unpack_from('<H', e, 0x20)[0] & 2:
            opt_total = (opt_total + al - 1) // al * al; struct.pack_into('<i', e, 0x1C, opt_total); opt_total += csz
        li = struct.unpack_from('<h', e, 0x22)[0]
        if 0 <= li < len(SLOC):
            loc = bytearray(SLOC[li]); p1, p2 = struct.unpack_from('<hh', loc, 0)
            np1, np2 = page(p1), page(p2); assert None not in (np1, np2), f'resource {r}: a page that isn\'t coming'
            struct.pack_into('<hh', loc, 0, np1, np2)
            for w in (np1, np2):
                if w >= 0: refs[w] = refs.get(w, 0) + 1
            struct.pack_into('<h', e, 0x22, len(TLOC) + len(new_loc)); new_loc.append(bytes(loc))
        for bo, es in ((0x28, 8), (0x34, 8)):
            c, p = struct.unpack_from('<II', e, bo)
            if c: na = E.alloc(es * c); E.write(na, S.mem(p * 4, es * c)); struct.pack_into('<II', e, bo, c, na // 4)
        new_res.append(bytes(e))
    new_pages = []
    for w in PAGES:
        e = bytearray(SPAGE[w]); struct.pack_into('<I', e, 8, NEWOFF[w]); struct.pack_into('<h', e, 0x54, refs.get(PMAP[w], 0)); new_pages.append(bytes(e))
    if null_add is not None:
        struct.pack_into('<h', null_add, 0x54, min(0x7FFF, refs.get(null_t, 0))); new_pages.append(bytes(null_add))
    tp = [bytes(e) for e in TPAGE]
    if null_add is None and null_t is not None and refs.get(null_t):
        e = bytearray(tp[null_t]); struct.pack_into('<h', e, 0x54, min(0x7FFF, struct.unpack_from('<h', e, 0x54)[0] + refs[null_t])); tp[null_t] = bytes(e)
    put_block(0x18, tp + new_pages, 0x58, ZT.la); put_block(0x3C, list(TLOC) + new_loc, 0x10, ZT.la); put_block(0x64, list(TRES) + new_res, 0x40)
    na = E.alloc(len(cb)); E.write(na, bytes(cb))
    E.write(ZT.a + 0x148, struct.pack('<I', len(cb))); E.write(ZT.a + 0x148 + 12, struct.pack('<I', na // 4))
    E.write(ZT.a + 0x16C, struct.pack('<i', opt_total))
    # bits: grow every array to the new resource count, the new ones as in the source
    total = rc0 + len(RES); words = (total + 31) // 32
    def src_bits(off, size, bo):
        c, p = ZS.blk(off); acc = set()
        for k in range(c):
            w = ZS.bits(off, size, k, bo); acc |= {i for i in range(32 * len(w)) if w[i // 32] >> (i % 32) & 1}
        return acc
    grown, arrays, slot, srcb = {}, {}, {}, {}
    for off, size in MANIFESTS:
        c, p = ZT.blk(off)
        for k in range(c):
            for bo in BITS:
                bc, bp = struct.unpack('<II', m.mem(p + size * k + bo, 8))
                if not bc: continue
                key = (bp, off, bo); slot[(off, k, bo)] = key
                if key not in grown:
                    if (off, bo) not in srcb: srcb[(off, bo)] = src_bits(off, size, bo) & set(RES)
                    want = srcb[(off, bo)]
                    w = list(struct.unpack(f'<{bc}I', m.mem(bp * 4, 4 * bc))) + [0] * max(0, words - bc)
                    for r in want: n = RMAP[r][0]; w[n // 32] |= 1 << (n % 32)
                    na = E.alloc(4 * len(w)); E.write(na, struct.pack(f'<{len(w)}I', *w)); grown[key] = (len(w), na // 4, len(want)); arrays[key] = w
                E.write(p + size * k + bo, struct.pack('<II', grown[key][0], grown[key][1]))
    if SIZES_OK:
        allres = list(TRES) + new_res
        def req2(off, k):
            if off is None: return [(o, kk, req2(o, kk)) for o, size in MANIFESTS for kk in range(ZT.blk(o)[0])]
            w = arrays.get(slot.get((off, k, 0x0)), [])
            return {i for i in range(min(len(allres), 32 * len(w))) if w[i // 32] >> (i % 32) & 1}
        old_bitm = bitm_of(m, TRES)
        def isb(r):
            if r < rc0: return old_bitm(r)
            return sgrp(struct.unpack_from('<I', SRES[RES[r - rc0]], 12)[0] & 0xFFFF) == 'bitm'
        nv = zone_sizes(allres, list(TLOC) + new_loc, tp + new_pages, req2, isb); ov = stored_sizes(ZT, nv)
        for key, v in nv.items():
            at = ZT.a + key[1] if key[0] == 'zone' else ZT.blk(key[0])[1] + dict(MANIFESTS)[key[0]] * key[1] + key[2]
            E.write(at, struct.pack('<I', v))
        changed = {k: (ov[k], nv[k]) for k in nv if ov[k] != nv[k]}
        print(f'size fields recomputed: {len(changed)} of {len(nv)} changed: ' + ', '.join(f'{k}: {a:#x} -> {b:#x}' for k, (a, b) in changed.items()))
    print(f'zone: +{len(new_res)} resources, +{len(new_loc)} locations, +{len(new_pages)} pages; control data {len(ZT.control()):#x} -> {len(cb):#x}; '
          f'optional control {struct.unpack("<i", m.mem(ZT.a + 0x16C, 4))[0]:#x} -> {opt_total:#x}; {len(grown)} bit arrays grown to {words} words')
    for (bp, off, bo), (n, a, k) in sorted(grown.items(), key=lambda x: (x[0][1], x[0][2])):
        if k: print(f'   manifest +0x{off:x} bits +0x{bo:x}: {k} new resources set')
if UGH:
    for key in sorted(UGH['changed']):
        put_block(BL[key][0], UGH['rows'][key], BL[key][1], a=UGH['addr'])
    print('sound gestalt: ' + ', '.join(f'{k} +{len(UGH["rows"][k]) - len(urows(m, UGH["addr"], k))}' for k in sorted(UGH['changed'])))
# ---- 4. palettes and Forge
A = int(S.tag_addr[next(i for i in range(S.ntags) if sgrp(i) == 'scnr')])
forge_rows = {}
for name, group, like in ROOTS:
    i = SI[(name, group)]; d = NEWD[i]
    if group in PALETTE: print(f'  {name.rsplit(B, 1)[-1]}: scenario {group} palette entry {E.scenario_palette_add(PALETTE[group], d, group)}')
    for fo in FORGE:                                   # the same Forge palette as in the source (spawner crates sit in vehicles)
        c, p = struct.unpack('<II', S.mem(A + fo, 8))
        src = next((bytearray(S.mem(p * 4 + 0x1C * k, 0x1C)) for k in range(c) if struct.unpack('<I', S.mem(p * 4 + 0x1C * k + 12, 4))[0] & 0xFFFF == i), None)
        if src is None: continue
        struct.pack_into('<I', src, 12, d); struct.pack_into('<I', src, 0x10, sid(struct.unpack_from('<I', src, 0x10)[0]))
        TA = int(m.tag_addr[E.scn]); tc, tp_ = struct.unpack('<II', m.mem(TA + fo, 8))
        ents = forge_rows.setdefault(fo, [bytes(m.mem(tp_ * 4 + 0x1C * k, 0x1C)) for k in range(tc)])
        ents.append(bytes(src))
        nid = struct.unpack_from('<I', src, 0x10)[0]; nt = sid_index(nid)
        print(f'  {name.rsplit(B, 1)[-1]}: Forge palette +0x{fo:x} entry {len(ents) - 1} ("{TS[nt] if nt < len(TS) else next(k for k, v in added.items() if v == nid)}")')
for fo, ents in forge_rows.items():
    TA = int(m.tag_addr[E.scn]); na = E.alloc(0x1C * len(ents)); E.write(na, b''.join(ents)); E.write(TA + fo, struct.pack('<II', len(ents), na // 4))
names = {i: S.tagname(i) for i in new}
if NEWNAME: print(f'shader code brought as our own copies (_hg): {len(NEWNAME)} ({", ".join(f"{g} {n}" for g, n in __import__("collections").Counter(sgrp(i) for i in NEWNAME).items())})')
print(f'{len(new)} tags brought in, {len(added)} new strings; ', end='')
ck = E.commit(); print(f'checksum 0x{ck:08x}')
# ---- 5. read back and compare with the source
R = Map(target); RS = strings(R); RI = index_of(R)
bad = 0
for i in new:
    j = RI[(here_name(i), sgrp(i))]; a, b = fields(S, SS, i), fields(R, RS, j)
    b = {k: (('ref', re.sub(r'_hg(\.(rmt2|pixl|vtsh))$', r'\1', v[1])) if v[0] == 'ref' else v) for k, v in b.items()}   # our shader-code copies
    d = [k for k in set(a) | set(b) if a.get(k) != b.get(k) and not (a.get(k, ('',))[0] == 'num' and ('Asset Datum' in k or '[ugh!]' in k))]
    if d: bad += 1; print(f'  DIFFERS: {names[i]}: {len(d)} fields, e.g. {[(k, a.get(k), b.get(k)) for k in sorted(d)[:3]]}')
assert not bad, f'{bad} imported tags differ from the source'
if UGH:                                              # each new sound's gestalt content, decoded on both sides
    def view(mp, st, a, raw):
        rows = {k: urows(mp, a, k) for k in BL}
        nm = lambda k: st[sid_index(struct.unpack('<I', rows['name'][k])[0])] if k >= 0 else None
        cnt = raw[3]; codec, fpr = struct.unpack_from('<hh', raw, 4); pb, sc = struct.unpack_from('<hh', raw, 0xC); ei = struct.unpack_from('<h', raw, 0x12)[0]
        out = [rows['codec'][codec] if codec >= 0 else None, rows['playback'][pb] if pb >= 0 else None, rows['scale'][sc] if sc >= 0 else None]
        for k in range(fpr, fpr + cnt) if fpr >= 0 else ():
            pr = rows['pitch'][k]; enc = struct.unpack_from('<I', pr, 8)[0]; pc, pf = (enc >> 20) & 0x3F, enc & 0xFFFFF
            pi, fi = struct.unpack_from('<hh', pr, 2)
            out += [nm(struct.unpack_from('<h', pr, 0)[0]), rows['param'][pi] if pi >= 0 else None, pr[4:6], enc >> 20,
                    b''.join(rows['flags'][fi:fi + pc]) if fi >= 0 else None]
            for q in range(pf, pf + pc):
                pm = rows['perm'][q]; fc, cc = struct.unpack_from('<ih', pm, 8)
                out += [nm(struct.unpack_from('<h', pm, 0)[0]), pm[2:8], pm[0xC:0x14]]
                out += [(c[:0x1C], st[sid_index(struct.unpack_from('<I', c, 0x1C)[0])]) for c in rows['chunk'][fc:fc + cc]] if fc >= 0 else []
        if ei >= 0:
            c, p = struct.unpack('<II', mp.mem(a + 0xBC, 8)); out.append(sorted(fields_of_extra(mp, st, p * 4 + 0xC * ei).items()))
        return out
    def fields_of_extra(mp, st, addr):
        out = {}
        from tagfields import flat
        return flat(mp, st, addr, ue['Extra Info'], 0xC, '', out)
    RU = int(R.tag_addr[next(i for i in range(R.ntags) if R.tag_group[i] >= 0 and R.groups[R.tag_group[i]] == 'ugh!')])
    bad = 0
    for i in new:
        if sgrp(i) != 'snd!': continue
        j = RI[(here_name(i), 'snd!')]
        if view(S, SS, su, S.mem(int(S.tag_addr[i]), 0x24)) != view(R, RS, RU, R.mem(int(R.tag_addr[j]), 0x24)): bad += 1; print(f'  SOUND DIFFERS: {S.tagname(i)}')
    assert not bad, f'{bad} sounds differ from the source'
    print(f'read back: {sum(1 for i in new if sgrp(i) == "snd!")} sounds: the same codec, playback, scale, pitch ranges, permutations, chunks and extra info as the source')
if RES:
    ZR = Zone(R); RR, RL, RP, rcb = ZR.rows(0x64, 0x40), ZR.rows(0x3C, 0x10, ZR.la), ZR.rows(0x18, 0x58, ZR.la), ZR.control()
    for r in RES:
        nk, ns = RMAP[r]; e, s = RR[nk], SRES[r]
        assert e[0x13:0x14] == s[0x13:0x14] and e[0x20:0x22] == s[0x20:0x22] and e[0x24:0x28] == s[0x24:0x28], f'resource {r}: fields'
        co, csz = struct.unpack_from('<ii', e, 0x14); sco, scsz = struct.unpack_from('<ii', s, 0x14)
        assert rcb[co:co + csz] == scb[sco:sco + scsz], f'resource {r}: control data'
        li, sli = struct.unpack_from('<h', e, 0x22)[0], struct.unpack_from('<h', s, 0x22)[0]
        if 0 <= sli < len(SLOC):
            for w, sw in zip(struct.unpack_from('<hh', RL[li], 0), struct.unpack_from('<hh', SLOC[sli], 0)):
                if sw < 0 or not page_ok(sw): continue
                off, cs, us = struct.unpack_from('<III', RP[w], 8); soff, scs, sus = struct.unpack_from('<III', SPAGE[sw], 8)
                assert (cs, us) == (scs, sus) and bytes(R.mm[off:off + cs]) == bytes(S.mm[soff:soff + scs]), f'resource {r}: page {sw}'
    print(f'read back: {len(new)} tags match the source field for field; {len(RES)} resources: control data and {len(PAGES)} pages byte for byte')
else:
    print(f'read back: all {len(new)} imported tags match the source field for field')
