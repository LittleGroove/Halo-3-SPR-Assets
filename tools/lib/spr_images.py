# Stamps a map owner's own image so it shows it's our version: a dark plate with SPR in the corner, the owner's art otherwise
# untouched. Test builds say SPR TEST on a red plate, so a test copy can't be mistaken for a release in MCC's menus.
# With our own art (any size: pack_spr.py passes a target size) the image is scaled to cover that size and cropped from the middle.
# The limits are Excession's (spr_excession.py reads them back out of it): a map image 900 KiB recommended, a loading screen
# 3,072 KiB, and Steam's limit for a Workshop preview, under 1 MB.
# usage: spr_images.py <source> <out> <thumbnail|large|loading|preview> [--test] [--size WxH]
import sys, os
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(here, 'pylib'))
from PIL import Image, ImageDraw, ImageFont
FONT = r'C:\Windows\Fonts\bahnschrift.ttf'
AMBER, RED = (232, 163, 23, 255), (214, 40, 40, 255)
LIMITS = {'thumbnail': 900 * 1024, 'large': 900 * 1024, 'loading': 3072 * 1024, 'preview': 999_000}
PLATE = {'thumbnail': 0.235, 'large': 0.2, 'loading': 0.115, 'preview': 0.16}      # plate height, as a share of the image's height
PREVIEW_WIDTH = 1280

def stamp(im, kind, test):
    text = 'SPR TEST' if test else 'SPR'
    im = im.convert('RGBA'); w, h = im.size
    ph = max(24, round(h * PLATE[kind])); size = round(ph * 0.72)
    font = ImageFont.truetype(FONT, size)
    font.set_variation_by_name('Bold')
    l, t, r, b = font.getbbox(text)
    pad = round(ph * 0.34); bar = max(3, round(ph * 0.09)); slant = round(ph * 0.32)
    pw = (r - l) + round(pad * 1.5) + bar + slant; margin = round(h * 0.035)
    x1, y1 = w - margin, h - margin; x0, y0 = x1 - pw, y1 - ph
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    d.polygon([(x0 + slant, y0), (x1, y0), (x1, y1), (x0, y1)], fill=(8, 10, 14, 222))
    d.polygon([(x0 + slant, y0), (x0 + slant + bar, y0), (x0 + bar, y1), (x0, y1)], fill=RED if test else AMBER)
    d.text((x0 + slant + bar + round(pad * 0.5) - l, y0 + (ph - (b - t)) / 2 - t), text, font=font, fill=(255, 255, 255, 255))
    return Image.alpha_composite(im, layer)

def cover(im, size):
    """scaled so it covers size, then cropped from the middle"""
    w, h = size; k = max(w / im.width, h / im.height)
    im = im.convert('RGBA').resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))

def make(src, out, kind, test=False, size=None):
    im = Image.open(src); had_alpha = im.mode in ('RGBA', 'LA', 'PA')
    if had_alpha and im.convert('RGBA').getchannel('A').getextrema() == (255, 255): had_alpha = False   # a screenshot's alpha is all opaque: save plain RGB, as the owners' images are
    if size: im = cover(im, size)
    elif kind == 'preview' and im.width > PREVIEW_WIDTH:
        im = im.convert('RGBA').resize((PREVIEW_WIDTH, round(im.height * PREVIEW_WIDTH / im.width)), Image.LANCZOS)
    done = stamp(im, kind, test)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    if kind == 'preview':
        for q in (92, 88, 84, 80, 75, 70):
            done.convert('RGB').save(out, 'JPEG', quality=q, optimize=True)
            if os.path.getsize(out) < LIMITS[kind]: break
    else:
        (done if had_alpha else done.convert('RGB')).save(out, 'PNG', optimize=True)
        if os.path.getsize(out) > LIMITS[kind]:                # still a true PNG, in fewer colours
            done.convert('RGB').quantize(256, dither=Image.Dither.FLOYDSTEINBERG).save(out, 'PNG', optimize=True)
    size = os.path.getsize(out)
    assert size <= LIMITS[kind], f'{out}: {size} bytes, over the {LIMITS[kind]} limit for a {kind} image'
    return size

if __name__ == '__main__':
    src, out, kind = sys.argv[1:4]
    wh = tuple(int(x) for x in sys.argv[sys.argv.index('--size') + 1].split('x')) if '--size' in sys.argv else None
    size = make(src, out, kind, '--test' in sys.argv, wh)
    print(f'{os.path.basename(out)}: {size // 1024} KiB')
