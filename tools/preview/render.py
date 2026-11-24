# A small software renderer for the Workshop preview (2026-11-23): numpy only. Triangles are rasterized in buckets by
# their screen size (every candidate pixel of a bucket at once; the nearest fragment wins), then shaded once per pixel
# (deferred): the object's own base map, a key light with a shadow map, a sky/ground ambient, a rim light and fog.
# Pixels with no object are the ground plane (z = 0, shadowed) or the sky. Linear light, filmic tone map, sRGB out.
import numpy as np

def _norm(v): return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)

class Camera:
    def __init__(self, pos, target, fov, W, H, up=(0, 0, 1), ortho=None):
        self.pos = np.array(pos, float); f = _norm(np.array(target, float) - self.pos)
        r = _norm(np.cross(f, up)); u = np.cross(r, f)
        self.f, self.r, self.u, self.W, self.H, self.ortho = f, r, u, W, H, ortho
        self.fpx = (W / 2) / np.tan(np.radians(fov) / 2) if not ortho else W / ortho
    def project(self, P):
        d = P - self.pos; x, y, z = d @ self.r, d @ self.u, d @ self.f
        if self.ortho: return np.stack([self.W / 2 + x * self.fpx, self.H / 2 - y * self.fpx, z], -1)
        z = np.maximum(z, 1e-6)
        return np.stack([self.W / 2 + x / z * self.fpx, self.H / 2 - y / z * self.fpx, z], -1)
    def rays(self, xs, ys):
        dx = (xs - self.W / 2) / self.fpx; dy = -(ys - self.H / 2) / self.fpx
        return _norm(self.f[None] + dx[:, None] * self.r[None] + dy[:, None] * self.u[None])

def rasterize(S, tris, W, H, persp=True, budget=6_000_000):
    """S: screen points (n,3) [x, y, depth]; tris (t,3). -> zbuf (H*W), tri id (H*W, -1 = none), b1, b2 (perspective-correct)"""
    zb = np.full(H * W, np.inf, np.float32); tid = np.full(H * W, -1, np.int32)
    b1b = np.zeros(H * W, np.float32); b2b = np.zeros(H * W, np.float32)
    A, B, C = S[tris[:, 0]], S[tris[:, 1]], S[tris[:, 2]]
    ok = (A[:, 2] > 0.05) & (B[:, 2] > 0.05) & (C[:, 2] > 0.05)
    xmin = np.floor(np.minimum(np.minimum(A[:, 0], B[:, 0]), C[:, 0]) - 0.5).astype(np.int64)
    xmax = np.ceil(np.maximum(np.maximum(A[:, 0], B[:, 0]), C[:, 0]) - 0.5).astype(np.int64)
    ymin = np.floor(np.minimum(np.minimum(A[:, 1], B[:, 1]), C[:, 1]) - 0.5).astype(np.int64)
    ymax = np.ceil(np.maximum(np.maximum(A[:, 1], B[:, 1]), C[:, 1]) - 0.5).astype(np.int64)
    ok &= (xmax >= 0) & (ymax >= 0) & (xmin < W) & (ymin < H)
    xmin, ymin = np.maximum(xmin, 0), np.maximum(ymin, 0); xmax, ymax = np.minimum(xmax, W - 1), np.minimum(ymax, H - 1)
    area = (B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (C[:, 0] - A[:, 0]) * (B[:, 1] - A[:, 1])
    ok &= np.abs(area) > 1e-9
    size = np.maximum(xmax - xmin + 1, ymax - ymin + 1)
    ids = np.nonzero(ok)[0]
    s = 1
    while len(ids):
        sel = ids[size[ids] <= s]; ids = ids[size[ids] > s]
        if len(sel):
            per = max(1, budget // (s * s))
            for c0 in range(0, len(sel), per):
                t = sel[c0:c0 + per]
                gx, gy = np.meshgrid(np.arange(s), np.arange(s)); gx, gy = gx.ravel(), gy.ravel()
                px = xmin[t][:, None] + gx[None]; py = ymin[t][:, None] + gy[None]
                inb = (px <= xmax[t][:, None]) & (py <= ymax[t][:, None])
                cx, cy = px + 0.5, py + 0.5
                a, b, c = A[t], B[t], C[t]; ar = area[t][:, None]
                w0 = ((b[:, 0, None] - cx) * (c[:, 1, None] - cy) - (c[:, 0, None] - cx) * (b[:, 1, None] - cy)) / ar
                w1 = ((c[:, 0, None] - cx) * (a[:, 1, None] - cy) - (a[:, 0, None] - cx) * (c[:, 1, None] - cy)) / ar
                w2 = 1 - w0 - w1
                m = inb & (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
                if not m.any(): continue
                ti = np.broadcast_to(t[:, None], m.shape)[m]
                w0, w1, w2 = w0[m], w1[m], w2[m]
                if persp:
                    za, zb_, zc = A[ti, 2], B[ti, 2], C[ti, 2]
                    iz = w0 / za + w1 / zb_ + w2 / zc; z = 1 / iz
                    p1, p2 = (w1 / zb_) / iz, (w2 / zc) / iz
                else:
                    z = w0 * A[ti, 2] + w1 * B[ti, 2] + w2 * C[ti, 2]; p1, p2 = w1, w2
                pix = py[m] * W + px[m]
                closer = z < zb[pix]
                pix, z, ti, p1, p2 = pix[closer], z[closer], ti[closer], p1[closer], p2[closer]
                o = np.argsort(-z, kind='stable')                    # far first: the nearest write lands last
                zb[pix[o]] = z[o]; tid[pix[o]] = ti[o]; b1b[pix[o]] = p1[o]; b2b[pix[o]] = p2[o]
        s *= 2
    return zb, tid, b1b, b2b

def aces(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)

class Scene:
    def __init__(self):
        self.P, self.N, self.U, self.T, self.TEX = [], [], [], [], []
        self.textures, self.tex_index, self.tint = [], {}, []
        self.nv = 0
    def add(self, parts, yaw=0.0, pos=(0, 0, 0), scale=1.0, pitch=0.0, roll=0.0, tint=None, base_map=None):
        """parts from model.load: [(render model, R, t)]; placed by yaw/pitch/roll (degrees) at pos"""
        cy, sy = np.cos(np.radians(yaw)), np.sin(np.radians(yaw))
        cp, sp = np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
        cr, sr = np.cos(np.radians(roll)), np.sin(np.radians(roll))
        Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]); Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
        Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]]); Rw = Rz @ Ry @ Rx
        for m, R, t in parts:
            if not len(m['tris']): continue
            p = (m['pos'] @ R.T + t) * scale; p = p @ Rw.T + np.array(pos, float)
            n = _norm((m['nrm'] @ R.T) @ Rw.T)
            texid = []
            for sh in m['shaders']:
                name = (sh[0] or '').lower()
                if sh[1] in ('rmd', 'rmd ', 'rmhg') or any(k in name for k in ('decal', 'holo', 'screen', 'display', 'speedo', 'scanner', 'blur')):
                    texid.append(-2); continue                    # decals, holograms, motion blur cards: not drawn
                if any(k in name for k in ('glass', 'windshield', 'canopy', 'cockpit_glass')):
                    texid.append(-3); continue                    # glass: dark, glossy
                key = sh
                if key not in self.tex_index:
                    img = base_map(sh) if base_map else None
                    self.tex_index[key] = len(self.textures) if img is not None else -1
                    if img is not None: self.textures.append(img)
                texid.append(self.tex_index[key])
            tm = np.array([texid[k] if 0 <= k < len(texid) else -1 for k in m['mat']], np.int64)
            keep = tm != -2
            self.P.append(p); self.N.append(n); self.U.append(m['uv']); self.T.append(m['tris'][keep] + self.nv)
            self.TEX.append(tm[keep]); self.tint.append(np.tile(np.array(tint if tint else (1, 1, 1), float), (keep.sum(), 1)))
            self.nv += len(p)
    def arrays(self):
        return (np.concatenate(self.P), np.concatenate(self.N), np.concatenate(self.U), np.concatenate(self.T),
                np.concatenate(self.TEX), np.concatenate(self.tint))

def sample(img, uv):
    h, w = img.shape[:2]
    u = (uv[:, 0] % 1.0) * w - 0.5; v = (uv[:, 1] % 1.0) * h - 0.5
    x0 = np.floor(u).astype(np.int64); y0 = np.floor(v).astype(np.int64); fx = (u - x0)[:, None]; fy = (v - y0)[:, None]
    x0m, x1m, y0m, y1m = x0 % w, (x0 + 1) % w, y0 % h, (y0 + 1) % h
    return ((img[y0m, x0m] * (1 - fx) + img[y0m, x1m] * fx) * (1 - fy) + (img[y1m, x0m] * (1 - fx) + img[y1m, x1m] * fx) * fy)

def render(scene, cam, look):
    """look: lighting and background settings (dict). -> float RGB image (H, W, 3) in display space 0..1"""
    W, H = cam.W, cam.H
    P, N, U, T, TX, TI = scene.arrays()
    S = cam.project(P)
    zb, tid, b1, b2 = rasterize(S, T, W, H)
    # shadow map along the key light
    L = _norm(np.array(look['key_dir'], float))             # direction the light travels
    lo, hi = P.min(0), P.max(0); ctr = (lo + hi) / 2; rad = np.linalg.norm(hi - lo) / 2 + 2
    SM = look.get('shadow_res', 4096)
    lc = Camera(ctr - L * rad * 3, ctr, 0, SM, SM, up=(0, 0, 1) if abs(L[2]) < 0.95 else (1, 0, 0), ortho=rad * 2)
    LS = lc.project(P)
    sz, _, _, _ = rasterize(LS, T, SM, SM, persp=False)
    sz = sz.reshape(SM, SM)
    def shadow(Wp, bias):
        q = lc.project(Wp); out = np.zeros(len(Wp))
        k = 0
        for dx in (-1.5, 0, 1.5):
            for dy in (-1.5, 0, 1.5):
                xi = np.clip((q[:, 0] + dx).astype(np.int64), 0, SM - 1); yi = np.clip((q[:, 1] + dy).astype(np.int64), 0, SM - 1)
                out += (q[:, 2] - bias > sz[yi, xi]); k += 1
        return out / k                                       # 1 = fully in shadow
    img = np.zeros((H * W, 3))
    lin = lambda c: np.array(c, float) ** 2.2
    key_c, sky_c, gnd_c, rim_c = lin(look['key']) * look.get('key_i', 3.0), lin(look['sky']), lin(look['ground_amb']), lin(look['rim']) * look.get('rim_i', 1.5)
    # objects
    hit = tid >= 0; idx = np.nonzero(hit)[0]
    t = tid[idx]; w1, w2 = b1[idx][:, None], b2[idx][:, None]; w0 = 1 - w1 - w2
    v0, v1, v2 = T[t, 0], T[t, 1], T[t, 2]
    wp = P[v0] * w0 + P[v1] * w1 + P[v2] * w2
    n = _norm(N[v0] * w0 + N[v1] * w1 + N[v2] * w2)
    uv = U[v0] * w0 + U[v1] * w1 + U[v2] * w2
    if look.get('flip_v', False): uv = np.stack([uv[:, 0], 1 - uv[:, 1]], -1)
    view = _norm(cam.pos[None] - wp)
    n = np.where((np.sum(n * view, -1) < 0)[:, None], -n, n)
    alb = np.full((len(idx), 3), look.get('default_albedo', 0.35))
    tx = TX[t]
    for k in np.unique(tx):
        s_ = tx == k
        if k >= 0: alb[s_] = sample(scene.textures[k], uv[s_]) ** 2.2
        elif k == -3: alb[s_] = lin((0.06, 0.08, 0.10))
    alb *= TI[t]
    sh = shadow(wp + n * 0.02, 0.02)
    ndl = np.clip(np.sum(n * -L[None], -1), 0, 1)
    hemi = (n[:, 2:3] * 0.5 + 0.5)
    amb = sky_c[None] * hemi + gnd_c[None] * (1 - hemi)
    h_ = _norm(-L[None] + view); spec = np.clip(np.sum(n * h_, -1), 0, 1) ** look.get('gloss', 24) * look.get('spec', 0.25)
    spec = np.where(tx == -3, spec * 4, spec)
    rim = (1 - np.clip(np.sum(n * view, -1), 0, 1)) ** look.get('rim_pow', 3.0)
    col = alb * (key_c[None] * (ndl * (1 - sh))[:, None] + amb * look.get('amb_i', 1.0)) + (key_c[None] * (spec * (1 - sh))[:, None]) + rim_c[None] * rim[:, None] * look.get('rim_k', 0.6)
    dist = np.linalg.norm(wp - cam.pos[None], axis=-1)
    fog = 1 - np.exp(-np.maximum(dist - look.get('fog_start', 0), 0) * look.get('fog', 0.0))
    # background: ground plane z = 0 and sky
    ys, xs = np.divmod(np.arange(H * W), W)
    miss = np.nonzero(~hit)[0]
    rays = cam.rays(xs[miss] + 0.5, ys[miss] + 0.5)
    bg = np.zeros((len(miss), 3))
    down = rays[:, 2] < -1e-4
    tg = np.where(down, -cam.pos[2] / np.where(down, rays[:, 2], -1), np.inf)
    g = np.nonzero(down & (tg < look.get('ground_far', 4000)))[0]
    gp = cam.pos[None] + rays[g] * tg[g, None]
    gsh = shadow(gp + np.array([0, 0, 0.01]), 0.03)
    gl = np.clip(-L[2], 0, 1)
    galb = lin(look['ground'])[None]
    if look.get('grid'):                                    # faint Forge-style grid lines
        gs = look['grid']; fx_, fy_ = np.abs((gp[:, 0] / gs) % 1 - 0.5), np.abs((gp[:, 1] / gs) % 1 - 0.5)
        line = np.clip((np.maximum(fx_, fy_) - (0.5 - look.get('grid_w', 0.012))) / look.get('grid_w', 0.012), 0, 1)
        fade = np.exp(-tg[g] * look.get('grid_fade', 0.02))[:, None]
        galb = galb + lin(look['grid_c'])[None] * (line[:, None] * fade)
    gcol = galb * (key_c[None] * (gl * (1 - gsh))[:, None] + sky_c[None] * look.get('amb_i', 1.0))
    # sky: a vertical gradient with a glow near the horizon toward the light
    el = np.clip(rays[:, 2], -1, 1)
    tt = np.clip(el[:, None] / look.get('sky_band', 0.3), 0, 1) ** look.get('sky_curve', 0.6)
    sky = lin(look['sky_top'])[None] * tt + lin(look['horizon'])[None] * (1 - tt)
    gd = _norm(np.array(look.get('glow_dir', -L[:2]), float)[:2])
    toward = np.clip(np.sum(rays[:, :2] * gd[None], -1), 0, 1) ** look.get('glow_pow', 6)
    sky = sky + lin(look['glow'])[None] * (toward * np.exp(-np.abs(el) * look.get('glow_fall', 6)))[:, None] * look.get('glow_i', 1.0)
    bg[:] = sky
    def haze(d):                                            # the sky's own color at the horizon in those directions
        d = _norm(np.concatenate([d[:, :2], np.zeros((len(d), 1))], -1))
        tw = np.clip(np.sum(d[:, :2] * gd[None], -1), 0, 1) ** look.get('glow_pow', 6)
        return lin(look['horizon'])[None] + lin(look['glow'])[None] * tw[:, None] * look.get('glow_i', 1.0)
    gfog = 1 - np.exp(-tg[g] * look.get('ground_fog', look.get('fog', 0.0)))
    bg[g] = gcol * (1 - gfog[:, None]) + haze(rays[g]) * gfog[:, None]
    col = col * (1 - fog[:, None]) + haze(wp - cam.pos[None]) * fog[:, None]
    img[idx] = col; img[miss] = bg
    img = aces(img * look.get('exposure', 1.0)) ** (1 / 2.2)
    return img.reshape(H, W, 3), hit.reshape(H, W)
