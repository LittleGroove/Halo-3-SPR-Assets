# The Workshop preview of Halo 3 SPR Assets (2026-11-23, host: "go ahead and build one for me"): the pack's own vehicles
# rendered from the H3EK source tags (model.py, render.py), at dusk on a Forge-grid floor, with the title and the SPR
# stamp every SPR Workshop page carries (HugeGrassFix tools\spr_images.py). Rendered at 2x and scaled down (antialiasing).
# Writes <out>.png (full quality) and <out>.jpg (the Workshop preview, under Steam's 1 MB).
# usage: python -I make_preview.py <out path without extension> [scale, default 2] [--quick]
import sys, os, time
HG = __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))), 'lib')
sys.path.insert(0, os.path.join(HG, 'pylib')); sys.path.insert(0, HG)
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(here)); sys.path.insert(0, here)
import numpy as np
import model, render
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import spr_images

W0, H0 = 1280, 720
# (tag, x (away from the camera), y (left), z (height above the floor of its lowest point; None = its own origin on the
# floor), yaw (0 = facing away), pitch, roll)
GROUND = [
    (r'objects\vehicles\scorpion\scorpion_spr', 10.5, 0.55, 0.0, 208, 0, 0),
    (r'objects\vehicles\warthog\warthog', 9.2, 3.75, 0.0, 236, 0, 0),
    (r'objects\vehicles\wraith\wraith_spr', 15.5, -3.9, 0.12, 150, 0, 0),
    (r'objects\vehicles\ghost\ghost_spr', 12.4, -1.95, 0.32, 168, 0, 0),
    (r'objects\vehicles\brute_chopper\brute_chopper_spr', 17.0, 3.6, 0.0, 222, 0, 0),
    (r'objects\vehicles\mongoose\mongoose_spr', 13.2, 3.5, 0.0, 250, 0, 0),
    (r'objects\vehicles\mauler\mauler_spr', 20.0, -0.6, 0.0, 196, 0, 0),
]
AIR = [
    (r'objects\vehicles\sparrowhawk\sparrowhawk_chaingun_spr', 19.5, -6.2, 6.3, 206, -5, 16),
    (r'objects\vehicles\hornet\hornet_spr', 15.0, -1.4, 3.3, 222, 3, -10),
    (r'objects\vehicles\banshee\banshee_spr', 22.0, 5.6, 5.0, 238, -6, -28),
    (r'custom\js\objects\vehicles\kestrel\kestrel_railgun_fast_spr', 26.0, -9.8, 3.6, 178, -2, 8),
]
LOOK = dict(
    key_dir=(0.55, 0.5, -0.6), key=(1.0, 0.92, 0.8), key_i=3.0,
    sky=(0.4, 0.48, 0.62), ground_amb=(0.3, 0.25, 0.2), amb_i=0.85,
    rim=(1.0, 0.62, 0.16), rim_i=1.0, rim_k=0.2, rim_pow=4.0, spec=0.18, gloss=28,
    ground=(0.115, 0.12, 0.135), grid=2.0, grid_w=0.01, grid_c=(0.5, 0.38, 0.18), grid_fade=0.04,
    sky_top=(0.2, 0.29, 0.46), horizon=(0.7, 0.53, 0.42), sky_band=0.36, sky_curve=0.7,
    glow=(1.0, 0.55, 0.12), glow_i=0.9, glow_dir=(1, -0.3), glow_pow=3, glow_fall=14,
    fog=0.004, fog_start=10, ground_fog=0.006, exposure=1.0, shadow_res=4096)
CAM = dict(pos=(0.0, 0.3, 1.55), target=(20.0, -0.4, 3.05), fov=50)
SUBTITLE = 'SPR vehicles and weapons for any Forge map'

def place(sc, tag, x, y, z, yaw, pitch, roll):
    parts = model.load(tag, 'vehi')
    P = np.concatenate([m['pos'] @ R.T + t for m, R, t in parts])
    zoff = z - P[:, 2].min() if z is not None else 0.0
    sc.add(parts, yaw=yaw, pitch=pitch, roll=roll, pos=(x, y, zoff), base_map=model.base_map)

def title(im):
    W, H = im.size; k = W / 1280
    def font(size, weight):
        f = ImageFont.truetype(spr_images.FONT, round(size * k)); f.set_variation_by_name(weight); return f
    x, y = round(52 * k), round(44 * k)
    f1, f2, f3 = font(30, 'SemiBold'), font(92, 'Bold'), font(25, 'SemiLight')
    lines = [('HALO 3', f1, (x, y), (232, 163, 23, 255)), ('SPR ASSETS', f2, (x - round(4 * k), y + round(30 * k)), (255, 255, 255, 255)),
             (SUBTITLE, f3, (x, y + round(132 * k)), (225, 228, 235, 255))]
    shadow = Image.new('RGBA', im.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(shadow)
    for txt, f, xy, c in lines: ds.text(xy, txt, font=f, fill=(0, 0, 0, 170))
    im = Image.alpha_composite(im, shadow.filter(ImageFilter.GaussianBlur(round(6 * k)))); d = ImageDraw.Draw(im)
    for txt, f, xy, c in lines: d.text(xy, txt, font=f, fill=c)
    return im

def main():
    out = sys.argv[1]; scale = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 2
    quick = '--quick' in sys.argv
    W, H = W0 * scale, H0 * scale
    t0 = time.time(); sc = render.Scene()
    for v in GROUND + AIR: place(sc, *v)
    print(f'{len(GROUND) + len(AIR)} vehicles, {sum(len(t) for t in sc.T)} triangles, {len(sc.textures)} textures ({time.time() - t0:.0f} s)')
    cam = render.Camera(CAM['pos'], CAM['target'], CAM['fov'], W, H)
    look = dict(LOOK); look['shadow_res'] = 2048 if quick else LOOK['shadow_res']
    t0 = time.time(); img, hit = render.render(sc, cam, look); print(f'rendered {W}x{H} in {time.time() - t0:.0f} s')
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((W0, H0), Image.LANCZOS).convert('RGBA')
    # a soft vignette
    yy, xx = np.mgrid[0:H0, 0:W0]; r = np.sqrt(((xx - W0 / 2) / (W0 / 2)) ** 2 + ((yy - H0 / 2) / (H0 / 2)) ** 2)
    vig = np.clip(1 - 0.28 * np.clip(r - 0.55, 0, None) ** 1.6, 0, 1)
    a = np.asarray(im).astype(np.float32); a[..., :3] *= vig[..., None]; im = Image.fromarray(a.astype(np.uint8), 'RGBA')
    im = title(im)
    im = spr_images.stamp(im, 'preview', False).convert('RGB')
    im.save(out + '.png')
    q = 92
    while True:
        im.save(out + '.jpg', quality=q, optimize=True, progressive=True)
        if os.path.getsize(out + '.jpg') < spr_images.LIMITS['preview'] or q <= 60: break
        q -= 4
    print(f"{out}.jpg: {os.path.getsize(out + '.jpg') // 1024} KiB (quality {q})")
main()
