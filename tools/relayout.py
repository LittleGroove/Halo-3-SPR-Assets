# Lays a Reclaimer-Kit-built (or Bungie-built) Halo 3 map out the way RJ's HugeGrass and our HugeGrassFix tools expect:
# every section mask 0 and the sections in the file in the order resource, locale, debug, tags (tags last, ending the
# file). Kit maps keep Bungie's form: masks set (section file offset = address + mask) and the order resource, debug,
# tags, locale. ceiling.py and importtags.py need the flat form, so this runs before them (P7, 2026-11-22).
#
# What points into a section that moves or loses its mask, and is rewritten:
#   - header: each section's {address, size} at 0x4DC + 8*s (address = its new file offset), masks at 0x4CC zeroed;
#     debug-section fields 0x24 tag-name buffer, 0x2C tag-name index, 0x34 string buffer, 0x3C string index, 0x44
#     string-id namespace table; tags-section field 0x10 the tag data
#   - zone tag (cache_file_resource_gestalt) raw pages (+0x34 block, 0x58 each): a page held in this map (shared file
#     index +4 == -1) has its offset at +8 relative to the resource section's address (Bungie form) -> made absolute
#   - globals (matg): the 12 language packs (+0x8 + 0x50*k, at +0x10 {count, size, index offset, data offset}) hold
#     locale-section addresses -> moved with the locale section
#   - checksum (header 0x360, the XOR of every u32 after the 16 KB header): updated for the words changed
# Tag data addresses (0x2E0 base, the tag table, block pointers) are memory addresses and don't change.
# Checked after writing: same tag names, tag addresses, string table; every page held in the map has the same bytes at
# its new offset; the language packs' index and data read the same. Run PR's `--kit-tool verify` on the result too.
# usage: python -I relayout.py <map in> <map out>
import os, struct, sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
from h3map import Map
from tagfields import strings
M32 = 1 << 32
src, dst = sys.argv[1], sys.argv[2]
assert os.path.abspath(src) != os.path.abspath(dst)
m = Map(src)
h = bytearray(m.h); u = lambda o: struct.unpack_from('<I', h, o)[0]
DEBUG, RES, TAGS, LOC = 0, 1, 2, 3
old = {s: m.sec_file[s] for s in range(4)}                         # file offset, size (address + mask)
align = lambda x: (x + 0xFFF) & ~0xFFF
# Kit maps: resource, debug, tags, locale, with the base map's old debug space left before the resource section (kept as
# it is). Stock Bungie maps (salvation.map): debug, resource, tags, locale. 2026-11-23: when a section sits ahead of the
# resource section (stock), the resource section moves to 0x4000, so the SPR Assets base can be a copy of stock Epitaph
# (the Kit's build of an empty project is that very file).
ahead = [s for s in (DEBUG, TAGS, LOC) if old[s][1] and old[s][0] < old[RES][0]]
assert all(old[s][0] + old[s][1] <= old[RES][0] for s in ahead), 'a section overlaps the resource section'
new = {RES: (0x4000, old[RES][1]) if ahead else old[RES]}
start = align(new[RES][0] + old[RES][1]); pos = start
for s in (LOC, DEBUG, TAGS):                                       # HugeGrass's order: resource, locale, debug, tags
    new[s] = (pos, old[s][1]); pos += old[s][1]
assert pos == m.size, f'the sections don\'t end the file (0x{pos:x} vs 0x{m.size:x}): something sits between them'
shift = lambda s, v: v + m.masks[s] - old[s][0] + new[s][0]        # an address in section s -> its new address (= file offset)

patches = {}                                                       # old file offset -> new u32 (in tag data)
def tagfield(addr): return m.file_of(addr)
# Raw pages: a page's file position is its offset + the resource section's MASK (checked 2026-11-22: Epitaph and the Kit
# map, mask 0xFA000, own pages from offset 0; HugeGrass, mask 0, pages at absolute offsets from 0x4000). Their table is
# in the zone tag (+0x34, tool.exe single-file builds: HugeGrass, 2Fort) or in the play tag (+0x18, Bungie's shared
# builds and Kit maps). Pages held in this map (shared file index -1) get the mask added; pages in shared.map etc. don't.
zi = next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'zone')
za = int(m.tag_addr[zi])
pi = [i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'play']
tables = [za + 0x34] + ([int(m.tag_addr[pi[0]]) + 0x18] if pi and int(m.tag_addr[pi[0]]) else [])
pages = 0; page_list = []
for t in tables:
    cnt, ptr = struct.unpack('<II', m.mem(t, 8))
    for k in range(cnt):
        e = (ptr * 4) + 0x58 * k
        shared, = struct.unpack('<h', m.mem(e + 4, 2)); off, cs, us = struct.unpack('<III', m.mem(e + 8, 12))
        if shared == -1 and off != 0xFFFFFFFF:
            was = (off + m.masks[RES]) % M32; now = was - old[RES][0] + new[RES][0]   # its file position, before and after
            patches[tagfield(e + 8)] = now; pages += 1; page_list.append((was, now, cs, us))
# matg language packs
gi = next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'matg')
G = int(m.tag_addr[gi]); packs = 0
for k in range(12):
    a = G + 0x8 + 0x50 * k + 0x10
    c, size, io, do = struct.unpack('<IIII', m.mem(a, 16))
    if c:
        la, ls = m.secs[LOC]
        assert la <= io < la + ls and la <= do < la + ls, 'a language pack outside the locale section'
        patches[tagfield(a + 8)] = shift(LOC, io) % M32; patches[tagfield(a + 12)] = shift(LOC, do) % M32; packs += 1
# header (the resource section takes the padding up to the next section, so whatever importtags appends starts 0x1000-aligned)
new[RES] = (new[RES][0], start - new[RES][0])
for s in range(4):
    struct.pack_into('<I', h, 0x4DC + 8 * s, new[s][0] if new[s][1] else 0); struct.pack_into('<I', h, 0x4E0 + 8 * s, new[s][1])
    struct.pack_into('<I', h, 0x4CC + 4 * s, 0)
for o in (0x24, 0x2C, 0x34, 0x3C, 0x44):
    v = u(o); la, ls = m.secs[DEBUG]; assert la <= v < la + ls, f'header 0x{o:x} outside the debug section'
    struct.pack_into('<I', h, o, shift(DEBUG, v) % M32)
v = u(0x10); la, ls = m.secs[TAGS]; assert la <= v < la + ls, 'header 0x10 outside the tags section'
struct.pack_into('<I', h, 0x10, shift(TAGS, v) % M32)
# checksum (0x360, XOR of every u32 after the header): the Kit doesn't keep it (its maps carry the base map's value:
# spr_assets_p1 had Epitaph's 5b184e98 against a real XOR of c677ae7e), so it's computed afresh on the output below
before = (m.names, m.tag_addr.tolist(), m.ntags, strings(m))
page_check = [(now, cs, us, bytes(m.mm[was:was + min(cs, 64)])) for was, now, cs, us in page_list if cs]
oldmm = m.mm
def remap(f):                                                      # old file offset in a moved section -> new file offset
    for s in (RES, LOC, DEBUG, TAGS):
        if old[s][0] <= f < old[s][0] + old[s][1]: return f - old[s][0] + new[s][0]
    return f
with open(src, 'rb') as fi, open(dst + '.tmp', 'wb') as fo:
    fo.write(bytes(h))
    if not ahead:                                                  # the resource section stays: everything up to it as it is
        fi.seek(0x4000); left = old[RES][0] - 0x4000
        while left:
            b = fi.read(min(1 << 26, left)); fo.write(b); left -= len(b)
    for s in (RES, LOC, DEBUG, TAGS):
        fo.write(b'\0' * (new[s][0] - fo.tell()))                  # the resource section's alignment padding
        fi.seek(old[s][0]); left = old[s][1]
        while left:
            b = fi.read(min(1 << 26, left)); fo.write(b); left -= len(b)
del m
with open(dst + '.tmp', 'r+b') as fh:
    for f, nv in patches.items(): fh.seek(remap(f)); fh.write(struct.pack('<I', nv))
import numpy as np
mm = np.memmap(dst + '.tmp', dtype=np.uint8, mode='r')
ck = int(np.bitwise_xor.reduce(np.frombuffer(mm[0x4000:], dtype='<u4'))); del mm
with open(dst + '.tmp', 'r+b') as fh: fh.seek(0x360); fh.write(struct.pack('<I', ck))
os.replace(dst + '.tmp', dst)
n = Map(dst)
assert n.masks == [0, 0, 0, 0], 'masks not zero'
assert (n.names, n.tag_addr.tolist(), n.ntags, strings(n)) == before, 'the map reads differently after the relayout'
import zlib
nt = [n.file_of(za + 0x34)] + ([n.file_of(int(n.tag_addr[pi[0]]) + 0x18)] if pi and int(n.tag_addr[pi[0]]) else [])
inflated = 0
for off, cs, us, head in page_check:                               # same bytes where the new offset says, and they inflate
    assert bytes(n.mm[off:off + len(head)]) == head, f'page at 0x{off:x} moved'
    if us and cs != us:
        d = zlib.decompressobj(-15).decompress(bytes(n.mm[off:off + cs]))
        assert len(d) == us, f'page at 0x{off:x} inflates to {len(d)}, not {us}'; inflated += 1
newoffs = set()
for t in tables:                                                   # and the tables now hold exactly those absolute offsets
    cnt, ptr = struct.unpack('<II', n.mem(t, 8))
    for k in range(cnt):
        e = (ptr * 4) + 0x58 * k
        shared, = struct.unpack('<h', n.mem(e + 4, 2)); off, = struct.unpack('<I', n.mem(e + 8, 4))
        if shared == -1 and off != 0xFFFFFFFF: newoffs.add(off)
assert newoffs == {p[1] for p in page_list}, 'the page tables do not hold the moved offsets'
xor = 0
import numpy as np
words = np.frombuffer(n.mm[0x4000:], dtype='<u4'); xor = int(np.bitwise_xor.reduce(words))
assert xor == struct.unpack_from('<I', n.h, 0x360)[0], f'checksum 0x{struct.unpack_from("<I", n.h, 0x360)[0]:08x} != XOR 0x{xor:08x}'
print(f'{os.path.basename(dst)}: masks 0; order resource, locale 0x{new[LOC][0]:x}, debug 0x{new[DEBUG][0]:x}, tags 0x{new[TAGS][0]:x}; '
      f'{pages} pages made absolute ({inflated} inflated to their size), {packs} language packs moved; checksum 0x{xor:08x} checked; '
      f'{n.ntags} tags read the same')
