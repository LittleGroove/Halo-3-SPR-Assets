# Raises a map's ceilings for adding tags, once, so later tweaks don't run into them:
#   - debug section +DEBUG bytes (it sits before the tag data in the file, so the tag data moves along in the file;
#     tag addresses don't change). The string buffer, string index and tag-name index move into the new space with
#     lots of room each; the tag-name buffer stays and can grow into what they left behind plus a gap.
#   - tag data +ROOM bytes of new room below the existing data (first memory partition), as expandmeta.py does.
#   - the tag table moves to the start of that room with space reserved for TAG_CAP tags.
#   - every zone manifest's per-tag bit arrays (Active / Top Level Resource Owners) grow to TAG_CAP bits (zeros:
#     a new tag only gets bits when it copies another's, see tagkit).
#   - a ledger at the start of the room ('LGROOM', next free address, room limit, tag-table capacity) for tagkit.
# usage: ceiling.py <map in> <map out> [room in MB, default 4]
import sys, os, struct, html
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from h3map import Map, np
here = os.path.dirname(os.path.abspath(__file__))
src, dst = sys.argv[1], sys.argv[2]
DEBUG, ROOM, TAG_CAP = 0x200000, 0x400000, 20480
if len(sys.argv) > 3: ROOM = int(sys.argv[3]) << 20       # MB of tag-data room (SPR Map Pack 2Fort: 16, for the copied resource tables)
assert os.path.abspath(src) != os.path.abspath(dst)
m = Map(src); h = bytearray(m.h)
u = lambda o: struct.unpack_from('<I', h, o)[0]
assert m.masks == [0, 0, 0, 0]
dbg_a, dbg_s = m.secs[0]; dbg_end = dbg_a + dbg_s
tf, ts = m.sec_file[2]
assert dbg_end == tf and tf + ts == m.size == u(0x08), 'not the expected file layout'
assert m.ntags <= TAG_CAP
base = struct.unpack_from('<Q', h, 0x2E0)[0]
p0a, p0s = struct.unpack_from('<QQ', h, 0x300); assert p0a == base and p0s > 0, 'run expandmeta.py first'
# ---- the new debug layout (file offsets; the section's mask is 0)
R = dbg_end
NAMES_BUF_TO = R + 0x080000            # the tag-name buffer (in place) may grow to here
STR_BUF, STR_IDX, NAME_IDX = R + 0x080000, R + 0x140000, R + 0x170000
str_n, str_buf, str_size, str_idx = u(0x30), u(0x34), u(0x38), u(0x3C)
nm_n, nm_buf, nm_size, nm_idx = u(0x20), u(0x24), u(0x28), u(0x2C)
assert str_size <= STR_IDX - STR_BUF and 4 * str_n <= NAME_IDX - STR_IDX and 4 * nm_n <= R + DEBUG - NAME_IDX
debug_new = bytearray(DEBUG)
debug_new[STR_BUF - R:STR_BUF - R + str_size] = m.mm[str_buf:str_buf + str_size].tobytes()
debug_new[STR_IDX - R:STR_IDX - R + 4 * str_n] = m.mm[str_idx:str_idx + 4 * str_n].tobytes()
debug_new[NAME_IDX - R:NAME_IDX - R + 4 * nm_n] = m.mm[nm_idx:nm_idx + 4 * nm_n].tobytes()
struct.pack_into('<I', h, 0x34, STR_BUF); struct.pack_into('<I', h, 0x3C, STR_IDX); struct.pack_into('<I', h, 0x2C, NAME_IDX)
# ---- the new room's contents: ledger, tag table (with its reserve), grown zone arrays
nb = base - ROOM
room = bytearray(ROOM)
LEDGER = 0x40; TABLE = nb + 0x100
table = m.mem(m.tags_at, 8 * m.ntags)
room[TABLE - nb:TABLE - nb + len(table)] = table
cur = TABLE + 8 * TAG_CAP
writes = []                                            # (address in the tag data, bytes) for existing data
z = next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'zone')
zr = ET.parse(os.path.join(here, 'assembly', 'plugins-h3mcc', 'zone.xml')).getroot()
refs = []                                              # (address of the block's count/pointer, old pointer address, count)
def scan(el, eb, depth):
    for c in el:
        if c.tag != 'tagblock': continue
        cnt, p = struct.unpack('<II', m.mem(eb + int(c.get('offset'), 16), 8))
        sub = {html.unescape(x.get('name')): x for x in c if x.tag == 'tagblock'}
        if 'Active Resource Owners' in sub and cnt < 10000:
            for k in range(cnt):
                e = p * 4 + int(c.get('elementSize'), 16) * k
                for s in ('Active Resource Owners', 'Top Level Resource Owners'):
                    at = e + int(sub[s].get('offset'), 16); bc, bp = struct.unpack('<II', m.mem(at, 8))
                    if bc: refs.append((at, bp * 4, bc))
        elif depth < 2 and 0 < cnt < 500:
            for k in range(cnt): scan(c, p * 4 + int(c.get('elementSize'), 16) * k, depth + 1)
scan(zr, int(m.tag_addr[z]), 0)
WORDS = TAG_CAP // 32
moved = {}
for at, old, bc in refs:
    assert bc <= WORDS
    if old not in moved:
        a = (cur + 15) & ~15; cur = a + 4 * WORDS
        room[a - nb:a - nb + 4 * bc] = m.mem(old, 4 * bc)
        moved[old] = a
    writes.append((at, struct.pack('<II', WORDS, moved[old] // 4)))
room[LEDGER:LEDGER + 32] = b'LGROOM\0\0' + struct.pack('<QQII', (cur + 63) & ~15, base, TAG_CAP, 0)
ih = bytearray(m.ih); struct.pack_into('<q', ih, 0x18, TABLE)
writes.append((m.index, bytes(ih[:0x20])))
# ---- header: sizes and places
struct.pack_into('<I', h, 0x08, m.size + DEBUG + ROOM)
struct.pack_into('<I', h, 0x10, tf + DEBUG); struct.pack_into('<I', h, 0x14, ts + ROOM)
struct.pack_into('<I', h, 0x4E0, dbg_s + DEBUG)
struct.pack_into('<I', h, 0x4EC, tf + DEBUG); struct.pack_into('<I', h, 0x4F0, ts + ROOM)
struct.pack_into('<Q', h, 0x2E0, nb); struct.pack_into('<QQ', h, 0x300, nb, p0s + ROOM)
# ---- write: header | resource, locale, debug as they were | the new debug space | the new room | the tag data
step = 1 << 26
del m
with open(src, 'rb') as fi, open(dst, 'wb') as fo:
    fo.write(h); fi.seek(0x4000)
    left = dbg_end - 0x4000
    while left:
        b = fi.read(min(step, left)); fo.write(b); left -= len(b)
    fo.write(debug_new); fo.write(room)
    while True:
        b = fi.read(step)
        if not b: break
        fo.write(b)
n = Map(dst)
fo_writes = [(n.file_of(a), d) for a, d in writes]
del n
with open(dst, 'r+b') as fh:
    for f, d in fo_writes: fh.seek(f); fh.write(d)
mm = np.memmap(dst, dtype='<u4', mode='r', offset=0x4000); ck = np.uint32(0)
for s0 in range(0, len(mm), 1 << 24): ck ^= np.bitwise_xor.reduce(mm[s0:s0 + (1 << 24)])
del mm
with open(dst, 'r+b') as fh: fh.seek(0x360); fh.write(struct.pack('<I', int(ck)))
print(f'{os.path.basename(dst)}: debug +{DEBUG:#x} (strings, string index, tag-name index moved; names buffer room to {NAMES_BUF_TO:#x}), '
      f'room +{ROOM:#x} at {nb:#x}; tag table at {TABLE:#x} for {TAG_CAP} tags; {len(moved)} zone arrays grown to {WORDS} words '
      f'({len(refs)} references); next free {cur:#x}; checksum 0x{int(ck):08x}')
