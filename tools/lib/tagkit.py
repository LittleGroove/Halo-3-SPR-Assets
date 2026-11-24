# Helpers for adding to a built Halo 3 MCC map that has free room below its tag data (expandmeta.py):
#   alloc(n)              room for new data (after everything already in the room)
#   add_string(text)      a new string id (appended to the string table; returns its id value)
#   add_tag(name, group, addr)  a new tag: tag table entry (the table moves into the room the first time) and name
#   write(addr, bytes)    tag-data writes;  commit() writes everything and the checksum
# Strings and tag names live in the debug section, whose tables each have some spare room before the next one.
import os, struct, re
from h3map import Map, np
B = chr(92)
# The scenario's Simulation Definition Table (scnr +0x6A4, 4-byte datums; Bungie's maps leave it empty) is where
# Assembly lists the tags it duplicates. MCC's halo3.dll doesn't read it: it builds its network definition table at map
# load from every weap/proj/eqip/obje/jpt!/effe/lsnd/snd! tag (0x51a08). New tags are listed anyway, as Assembly does;
# what the game does need is a salt in the map's own sequence (next_salt).
SIM_TABLE = 0x6A4
SIM_GROUPS = {'weap', 'proj', 'vehi', 'bipd', 'eqip', 'bloc', 'scen', 'mach', 'ctrl', 'term', 'gint', 'crea', 'efsc', 'ssce', 'jpt!', 'effe'}

class Editor:
    def __init__(self, path):
        self.path = path; self.m = m = Map(path); self.h = bytearray(m.h)
        assert m.masks == [0, 0, 0, 0], 'section masks set'
        self.u = lambda o: struct.unpack_from('<I', self.h, o)[0]
        self.writes = []                                  # (file offset, bytes)
        part = struct.unpack_from('<QQ', m.h, 0x300); assert part[0] == m.base and part[1] > 0, 'no room'
        self.room_lo, self.room_hi = m.base, m.base + part[1]
        led = m.mem(m.base + 0x40, 32)                   # ceiling.py's ledger: next free, room limit, tag-table capacity
        if led[:8] == b'LGROOM\0\0':
            self.cur, self.room_hi, self.table_cap, _ = struct.unpack_from('<QQII', led, 8)
            self.ledger = m.base + 0x40
        else:
            self.cur = self._room_end(); self.table_cap = 0; self.ledger = None
        self.new_tags = []; self.new_strings = []; self.sim_new = []
        self.scn = next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'scnr')
    def _room_end(self):                                  # past every block pointing into the room, and every byte in use
        m = self.m; ends = []
        room = np.frombuffer(m.mem(self.room_lo, self.room_hi - self.room_lo), dtype=np.uint8)
        if room.any(): ends.append(self.room_lo + int(np.nonzero(room)[0][-1]) + 1)
        w = np.frombuffer(m.mm[m.tagsfile:m.tagsfile + m.tagssize // 4 * 4], dtype='<u4')
        lo4, hi4 = self.room_lo // 4, self.room_hi // 4      # block (count, pointer/4) pairs whose pointer is in the room
        idx = np.nonzero((w[1:] >= lo4) & (w[1:] < hi4) & (w[:-1] > 0) & (w[:-1] < 100000))[0]
        for i in idx.tolist():
            ends.append(int(w[i + 1]) * 4)                  # at least the start; sizes come from the known blocks below
        A = int(m.tag_addr[next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'scnr')])
        for off, size in ((0x3EC, 0x34), (0x3F8, 0x28), (0x49C, 0x18), (0x5BC, 0xB0), (0x1E0, 0x1C), (0x1EC, 0x1C),
                          (0x1F8, 0x1C), (0x204, 0x1C), (0x210, 0x1C), (0x21C, 0x1C), (0x228, 0x1C)):
            c, p = struct.unpack('<II', m.mem(A + off, 8))
            if self.room_lo <= p * 4 < self.room_hi: ends.append(p * 4 + c * size)
        if self.room_lo <= m.tags_at < self.room_hi: ends.append(m.tags_at + 8 * m.ntags)
        return (max(ends) + 63) & ~15 if ends else self.room_lo
    def alloc(self, n):
        a = (self.cur + 15) & ~15; self.cur = a + n
        assert self.cur <= self.room_hi, 'out of room'
        return a
    def write(self, addr, data):
        self.writes.append((self.m.file_of(addr), bytes(data)))
    def mem(self, addr, n): return self.m.mem(addr, n)
    def tag(self, name, group):
        name = name.replace('/', B); m = self.m
        return next(i for i in range(m.ntags) if m.names[i] == name and m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == group)
    def datum(self, i):
        for k, (nm, g, a, salt) in enumerate(self.new_tags):
            if self.m.ntags + k == i: return (salt << 16) | i
        return (int(self.m.tag_salt[i]) << 16) | i
    # ---- strings
    def add_string(self, text):
        m = self.m; n = self.u(0x30) + len(self.new_strings); t = n
        assert t >= 3387, 'string table too small for the id mapping'
        self.new_strings.append(text)
        return t - 2187                                   # string table index -> string id (index >= 1200 range)
    def sid_of(self, text):
        u = self.u; cnt, buf, size, idx = u(0x30), u(0x34), u(0x38), u(0x3C); m = self.m
        offs = np.frombuffer(bytes(m.mm[idx:idx + 4 * cnt]), dtype='<i4'); blob = bytes(m.mm[buf:buf + size])
        for t, o in enumerate(offs):
            if 0 <= o < size and blob[o:blob.find(bytes(1), o)].decode('latin1') == text:
                from tagfields import sid_value
                return sid_value(t)
        return None
    # ---- tags
    # A new tag's salt continues the map's own sequence (salt = index + the last tag's offset), as Bungie's tools number
    # them. halo3.dll looks object, projectile, damage and sound definitions up in a network table sorted by signed datum
    # with a comparator that returns key - element as a 32-bit int (0x51eb0); a salt far from its neighbours ('LG'
    # 0x4C47, or Assembly's 0x4153) makes that subtraction overflow, the search misses the tag and the game sends the
    # weapon as NONE: LG 1.0.2-1.0.5's copies could be picked up but never reached the player's hands. commit() checks it.
    # SPR Map Pack (2026-10-27): Wize's 2Fort ends in 2,470 tags Assembly injected with salt 0x4153, and continuing that
    # sequence made 8 of the map's own projectiles unfindable. The sequence is kept when a simulated 1,024 more tags of
    # each looked-up group leave every lookup working (LG: always); otherwise the middle of the widest run of offsets
    # that do (2Fort: new datums just below zero, among most of the map's own).
    salt_offset = None
    def next_salt(self, i):
        if self.salt_offset is None: self.salt_offset = self._pick_salt_offset()
        s = (self.salt_offset + i) & 0xFFFF
        return s if s != 0xFFFF else 0
    def _pick_salt_offset(self):
        import nettable
        m = self.m; last = next(k for k in range(m.ntags - 1, -1, -1) if m.tag_salt[k] != 0xFFFF)
        default = (int(m.tag_salt[last]) - last) & 0xFFFF
        before = {(i, g) for i, g, d in nettable.missed(m)}
        if nettable.simulate(m, default, 1024, before) == 0: return default
        ok = [o for o in range(0, 0x10000, 0x400) if nettable.simulate(m, o, 1024, before) == 0]
        assert ok, 'no salt sequence keeps every tag findable'
        runs, run = [], [ok[0]]
        for o in ok[1:]:
            if o == run[-1] + 0x400: run.append(o)
            else: runs.append(run); run = [o]
        runs.append(run); best = max(runs, key=len)
        print(f"salts: the map's own sequence (offset 0x{default:04x}) would hide tags from the network lookup; "
              f'using offset 0x{best[len(best) // 2]:04x} (safe 0x{best[0]:04x}-0x{best[-1]:04x})')
        return best[len(best) // 2]
    def add_tag(self, name, group, addr, salt=None, like=None):
        """like: the tag this one copies; it gets the same zone bits (see zone_like), or the game won't load it."""
        name = name.replace('/', B); m = self.m
        assert not any(m.names[i] == name and m.groups[m.tag_group[i]] == group for i in range(m.ntags)), f'{name}.{group} exists'
        i = m.ntags + len(self.new_tags)
        salt = salt if salt is not None else self.next_salt(i)
        self.new_tags.append((name, group, addr, salt))
        if like is not None: self.zone_like(i, like)
        if group in SIM_GROUPS: self.sim_new.append((salt << 16) | i)
        return i, (salt << 16) | i
    # ---- zone manifests: the cache file resource gestalt keeps, per manifest (global, per BSP, per zone set ...), a bit
    # per tag in "Active Resource Owners" and "Top Level Resource Owners". A tag whose bits are all 0 isn't loaded, so
    # Forge can't create it ("too many on map"). A copy gets its original's bits, array by array (some are shared).
    zone_pairs = None
    own_predictions = frozenset()
    def zone_like(self, new_index, like_index):
        if self.zone_pairs is None: self.zone_pairs = []
        self.zone_pairs.append((new_index, like_index))
    def _zone_arrays(self):
        import xml.etree.ElementTree as ET, html
        m = self.m; here = os.path.dirname(os.path.abspath(__file__))
        z = next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'zone')
        r = ET.parse(os.path.join(here, 'assembly', 'plugins-h3mcc', 'zone.xml')).getroot(); arrays = set()
        def scan(el, base, depth):
            for c in el:
                if c.tag != 'tagblock': continue
                cnt, p = struct.unpack('<II', m.mem(base + int(c.get('offset'), 16), 8))
                sub = {html.unescape(x.get('name')): x for x in c if x.tag == 'tagblock'}
                if 'Active Resource Owners' in sub and cnt < 10000:
                    for k in range(cnt):
                        eb = p * 4 + int(c.get('elementSize'), 16) * k
                        for s in ('Active Resource Owners', 'Top Level Resource Owners'):
                            bc, bp = struct.unpack('<II', m.mem(eb + int(sub[s].get('offset'), 16), 8))
                            if bc: arrays.add((bp * 4, bc))
                elif depth < 2 and 0 < cnt < 500:
                    for k in range(cnt): scan(c, p * 4 + int(c.get('elementSize'), 16) * k, depth + 1)
        scan(r, int(m.tag_addr[z]), 0)
        return sorted(arrays)
    def _apply_zone(self):
        words = {}                                        # (array address, word index) -> new value
        set_count = 0
        for a, n in self._zone_arrays():
            for new, like in self.zone_pairs:
                assert new // 32 < n, f'zone bit arrays hold {32 * n} tags; tag {new} needs them grown'
                src = (struct.unpack('<I', self.m.mem(a + 4 * (like // 32), 4))[0] >> (like % 32)) & 1
                if not src: continue
                key = (a, new // 32)
                cur = words.get(key, struct.unpack('<I', self.m.mem(a + 4 * (new // 32), 4))[0])
                words[key] = cur | (1 << (new % 32)); set_count += 1
        for (a, w), v in words.items(): self.write(a + 4 * w, struct.pack('<I', v))
        return set_count
    # ---- resource predictions: the zone tag's Prediction Molecule Keys (+0x20C: tag datum, two values) and the parallel
    # Prediction Molecules (+0x200: molecule atom count/index, quanta count/index) tell the game which resources to page
    # in for a tag (render and first-person models, bitmaps, sounds). A copy gets its original's keys with its own datum
    # and the same molecules (same atoms and quanta: the resources are shared). Appended, as Assembly does.
    def _apply_predictions(self):
        m = self.m
        z = next(i for i in range(m.ntags) if m.tag_group[i] >= 0 and m.groups[m.tag_group[i]] == 'zone'); za = int(m.tag_addr[z])
        kc, kp = struct.unpack('<II', m.mem(za + 0x20C, 8)); mc, mp = struct.unpack('<II', m.mem(za + 0x200, 8))
        assert kc == mc, 'prediction keys and molecules differ in count'
        keys = bytearray(m.mem(kp * 4, 12 * kc)); mols = bytearray(m.mem(mp * 4, 8 * mc))
        added = 0
        for new, like in sorted(self.zone_pairs):
            if new in self.own_predictions: continue      # importtags.py writes these tags' own, from their source map
            for k in range(kc):
                d, v1, v2 = struct.unpack_from('<Iii', keys, 12 * k)
                if (d & 0xFFFF) == like and d != 0xFFFFFFFF:
                    keys += struct.pack('<Iii', self.datum(new), v1, v2); mols += mols[8 * k:8 * k + 8]; added += 1
        if added:
            ka = self.alloc(len(keys)); self.write(ka, keys); ma = self.alloc(len(mols)); self.write(ma, mols)
            self.write(za + 0x20C, struct.pack('<II', kc + added, ka // 4)); self.write(za + 0x200, struct.pack('<II', mc + added, ma // 4))
        return added
    # ---- a struct with its own copy of every block and data reference under it (as Assembly's duplicate rebuilds a tag
    # through its layout). el: the plugin element describing the struct (the root for a tag). Returns the struct's bytes.
    def deep_copy(self, addr, el, size):
        raw = bytearray(self.mem(addr, size))
        for c in el:
            if c.get('offset') is None: continue
            off = int(c.get('offset'), 16)
            if c.tag == 'tagblock':
                es = int(c.get('elementSize'), 16); cnt, p = struct.unpack_from('<II', raw, off)
                if not cnt or not es or not p: continue
                block = b''.join(self.deep_copy(p * 4 + es * k, c, es) for k in range(cnt))
                na = self.alloc(len(block)); self.write(na, block); struct.pack_into('<II', raw, off, cnt, na // 4)
            elif c.tag.lower() == 'dataref':
                sz, dp = struct.unpack_from('<I', raw, off)[0], struct.unpack_from('<I', raw, off + 12)[0]
                if not sz or not dp: continue
                na = self.alloc(sz); self.write(na, self.mem(dp * 4, sz)); struct.pack_into('<I', raw, off + 12, na // 4)
        return bytes(raw)
    # ---- the scenario's own object palettes (Weapon Palette +0x120, Vehicle Palette +0xF0, ...: 0x10-byte tag references).
    # A map's custom weapons are all listed in its Weapon Palette, Forge ones included (Bungie's maps list every weapon
    # they use); a copy that isn't listed can be placed and picked up but never readies (LG HugeGrass 1.0.2-1.0.4).
    def scenario_palette_add(self, off, datum, group):
        m = self.m; A = int(m.tag_addr[self.scn])
        if not hasattr(self, '_palettes'): self._palettes = {}
        if off not in self._palettes:                     # this commit's copy of the palette, so several adds add up
            c, p = struct.unpack('<II', m.mem(A + off, 8))
            self._palettes[off] = bytearray(m.mem(p * 4, 0x10 * c)) if c else bytearray()
        ents = self._palettes[off]; c = len(ents) // 0x10
        if any(struct.unpack_from('<I', ents, 0x10 * k + 12)[0] == datum for k in range(c)): return c
        ents += group[::-1].encode('latin1') + bytes(8) + struct.pack('<I', datum)
        na = self.alloc(len(ents)); self.write(na, ents); self.write(A + off, struct.pack('<II', c + 1, na // 4))
        return c                                          # the new entry's index
    def _starts(self): return sorted({self.u(0x24), self.u(0x2C), self.u(0x34), self.u(0x3C), self.u(0x44)})
    def _room_after(self, a):
        sec_end = self.m.secs[0][0] + self.m.secs[0][1]
        return next((s for s in self._starts() if s > a), sec_end) - a
    def commit(self):
        m, u, h = self.m, self.u, self.h
        self.zone_bits_set = self._apply_zone() if self.zone_pairs else 0
        self.predictions_added = self._apply_predictions() if self.zone_pairs else 0
        if self.sim_new:                                 # the scenario's Simulation Definition Table, with the new tags
            A = int(m.tag_addr[self.scn]); c, p = struct.unpack('<II', m.mem(A + SIM_TABLE, 8))
            old = [struct.unpack('<I', m.mem(p * 4 + 4 * k, 4))[0] for k in range(c)] if c else []
            table = old + [d for d in self.sim_new if d not in old]
            table.sort(key=lambda d: d - (1 << 32) if d & 0x80000000 else d)   # the game binary-searches it by signed datum
            ta = self.alloc(4 * len(table)); self.write(ta, struct.pack(f'<{len(table)}I', *table))
            self.write(A + SIM_TABLE, struct.pack('<II', len(table), ta // 4))
            self.sim_count = len(table)
        if self.new_strings:
            cnt, buf, size, idx = u(0x30), u(0x34), u(0x38), u(0x3C)
            add = b''.join(s.encode('latin1') + bytes(1) for s in self.new_strings)
            offs, at = [], size
            for s in self.new_strings: offs.append(at); at += len(s.encode('latin1')) + 1
            assert size + len(add) <= self._room_after(buf) and 4 * (cnt + len(offs)) <= self._room_after(idx), 'no room for strings'
            self.writes.append((buf + size, add)); self.writes.append((idx + 4 * cnt, struct.pack(f'<{len(offs)}i', *offs)))
            struct.pack_into('<I', h, 0x30, cnt + len(offs)); struct.pack_into('<I', h, 0x38, size + len(add))
        if self.new_tags:
            gi = {g: k for k, g in enumerate(m.groups)}
            ncnt, nbuf, nsize, nidx = u(0x20), u(0x24), u(0x28), u(0x2C)
            assert ncnt == m.ntags
            add = b''.join(nm.encode('latin1') + bytes(1) for nm, g, a, s in self.new_tags)
            offs, at = [], nsize
            for nm, g, a, s in self.new_tags: offs.append(at); at += len(nm.encode('latin1')) + 1
            assert nsize + len(add) <= self._room_after(nbuf) and 4 * (ncnt + len(offs)) <= self._room_after(nidx), 'no room for names'
            self.writes.append((nbuf + nsize, add)); self.writes.append((nidx + 4 * ncnt, struct.pack(f'<{len(offs)}i', *offs)))
            struct.pack_into('<I', h, 0x20, ncnt + len(offs)); struct.pack_into('<I', h, 0x28, nsize + len(add))
            entries = b''.join(struct.pack('<II', (s << 16) | gi[g], a // 4) for nm, g, a, s in self.new_tags)
            ih = bytearray(m.ih); struct.pack_into('<I', ih, 0x10, m.ntags + len(self.new_tags))
            if self.table_cap and m.ntags + len(self.new_tags) <= self.table_cap:
                self.write(m.tags_at + 8 * m.ntags, entries)  # into the table's reserved space
            else:
                table = bytes(m.mem(m.tags_at, 8 * m.ntags)) + entries
                ta = self.alloc(len(table)); self.write(ta, table); struct.pack_into('<q', ih, 0x18, ta)
            self.write(m.index, bytes(ih[:0x20]))
        if self.ledger is not None:                      # move the ledger's next-free mark past this commit's data
            self.write(self.ledger + 8, struct.pack('<Q', (self.cur + 63) & ~15))
        fo = list(self.writes); hdr = bytes(h); path = self.path
        import nettable                                   # what the map's own tags already miss (2Fort: 129 of Wize's sounds)
        missed_before = {(i, g) for i, g, d in nettable.missed(self.m)}
        del self.m
        with open(path, 'r+b') as fh:
            for f, d in fo: fh.seek(f); fh.write(d)
            fh.seek(0); fh.write(hdr)
        mm = np.memmap(path, dtype='<u4', mode='r', offset=0x4000); ck = np.uint32(0)
        for s0 in range(0, len(mm), 1 << 24): ck ^= np.bitwise_xor.reduce(mm[s0:s0 + (1 << 24)])
        del mm
        with open(path, 'r+b') as fh: fh.seek(0x360); fh.write(struct.pack('<I', int(ck)))
        # every network definition must still be findable (see next_salt); a map whose own tags are already missed (made-up
        # salts from Assembly) may keep those, but nothing this commit adds or moves may join them
        missed = [x for x in nettable.missed(Map(path)) if (x[0], x[1]) not in missed_before]
        assert not missed, f'the game could not find these tags in its network table: {missed}'
        self.missed_before = len(missed_before)
        return int(ck)
