# Reads a Halo 3 MCC (cache v13) map's header, sections, tag index and tag names.
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pylib'))
import numpy as np

M32 = 1 << 32

class Map:
    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(path)
        self.mm = np.memmap(path, dtype=np.uint8, mode='r')
        h = bytes(self.mm[:0x4000]); self.h = h
        self.u32 = lambda o: struct.unpack_from('<I', h, o)[0]
        self.base = struct.unpack_from('<q', h, 0x2E0)[0]
        self.index = struct.unpack_from('<q', h, 0x2E8)[0]
        self.masks = [self.u32(0x4CC + 4 * i) for i in range(4)]
        self.secs = [(self.u32(0x4DC + 8 * i), self.u32(0x4E0 + 8 * i)) for i in range(4)]  # debug, resource, tags, locale
        self.sec_file = [((a + m) % M32, s) for (a, s), m in zip(self.secs, self.masks)]
        self.tagsfile, self.tagssize = self.sec_file[2]
        ih = self.mem(self.index, 0x40, strict=False); self.ih = ih
        self.ngroups, self.groups_at = struct.unpack_from('<I', ih, 0)[0], struct.unpack_from('<q', ih, 8)[0]
        self.ntags, self.tags_at = struct.unpack_from('<I', ih, 0x10)[0], struct.unpack_from('<q', ih, 0x18)[0]
        g = self.mem(self.groups_at, 16 * self.ngroups, strict=False)
        self.groups = [g[16*i:16*i+4][::-1].decode('latin1') for i in range(self.ngroups)]
        t = np.frombuffer(self.mem(self.tags_at, 8 * self.ntags, strict=False), dtype='<u4').reshape(-1, 2)
        self.tag_group = (t[:, 0] & 0xFFFF).astype(np.int16)
        self.tag_salt = (t[:, 0] >> 16).astype(np.uint16)
        self.tag_addr = t[:, 1].astype(np.int64) * 4
        # tag names: 0x20 count, 0x24 buffer, 0x28 buffer size, 0x2C index (debug section addresses)
        cnt, buf, bsize, idx = (self.u32(o) for o in (0x20, 0x24, 0x28, 0x2C))
        dm = self.masks[0]
        self.names_count, self.names_buf, self.names_size, self.names_idx = cnt, buf, bsize, idx
        fb, fi = (buf + dm) % M32, (idx + dm) % M32
        offs = np.frombuffer(bytes(self.mm[fi:fi + 4 * cnt]), dtype='<i4')
        blob = bytes(self.mm[fb:fb + bsize])
        self.names = []
        for o in offs:
            if o < 0 or o >= bsize: self.names.append(None); continue
            e = blob.find(b'\0', o); self.names.append(blob[o:e].decode('latin1'))
        self.names_file = (fb, fb + bsize, fi, fi + 4 * cnt)

    def file_of(self, addr):
        return self.tagsfile + (addr - self.base)

    def mem(self, addr, n, strict=True):
        off = addr - self.base
        if strict and (off < 0 or off + n > self.tagssize): raise ValueError(f'0x{addr:x}+{n} outside tag data')
        f = self.tagsfile + off
        return bytes(self.mm[f:f + n])

    def tagname(self, i):
        g = self.tag_group[i]
        return f'{self.names[i] if i < len(self.names) else "?"}.{self.groups[g] if 0 <= g < len(self.groups) else "<none>"}'
