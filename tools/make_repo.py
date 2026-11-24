# Fills the public source repository of Halo 3 SPR Assets (2026-11-23) from the working folders, so every release
# refreshes it the same way. Copies (replacing what was there, so removed files go too):
#   Halo3\tags\   every source tag the build makes or changes (values\all.full.json: our _spr copies of stock and RJ's
#                 tags with the SPR values, and the _spr copies of shared tags), read from H3EK's tags folder
#   Halo3\spr\    the values and decisions: inventory, fallback, fixes, compiled fixes, splits, the walk and the full set
#   tools\        the SPR Assets tools, the HugeGrass map libraries they import (tools\lib) and Assembly's plugins
#                 (tools\lib\assembly, GPL-3.0, from Assembly's repository)
# README.md, CREDITS.md, UPSTREAM.md, LICENSE and .gitignore are written in the repository itself, not here.
# usage: python -I make_repo.py <repository folder>
import json, os, shutil, sys
REPO = sys.argv[1]
SA = r'S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets'
HG = r'S:\Projects\ProjectReclaimer\DEPLOY\HugeGrassFix\tools'
EK = r'C:\Program Files (x86)\Steam\steamapps\common\H3EK'
TOOLS = ['banks.py', 'build_pack.sh', 'compile_scenario.py', 'compiled_fix.py', 'deepparity.py', 'forge_entries.py',
         'forge_palette.py', 'inventory.py', 'make_repo.py', 'overlay.py', 'package_release.sh', 'parity.py',
         'provenance.py', 'relayout.py', 'seat_modes.py', 'seats.py', 'split_variants.py', 'sprapply.py', 'sprdiff.py',
         'sprwalk.py', 'tagxml.py', 'vehicle_config.py', 'spr_assets.forge.json', os.path.join('mbtool', 'mbtool.cs'),
         os.path.join('release', 'ModInfo.json')] + [os.path.join('preview', f) for f in ('model.py', 'render.py', 'make_preview.py')]
LIBS = ['h3map.py', 'tagfields.py', 'tagkit.py', 'importtags.py', 'ceiling.py', 'spr_images.py']
VALUES = ['inventory.json', 'fallback.json', 'fixes.json', 'compiled_fixes.json', 'splits.json', 'variants.json', 'all.walk.json',
          'all.full.json']
# Source tags left out of the repository, with why. The build reads them from the author's own release (UPSTREAM.md).
#   Skaboodlydoodle's Sparrowhawk: his Nexus Mods terms say "You are not allowed to upload this file to other sites under
#   any circumstances". The pack ships his vehicle compiled, the only way it can be used; his tag files stay with him.
LEAVE_OUT = [('objects\\vehicles\\sparrowhawk\\', 'Skaboodlydoodle')]
def fresh(path):
    if os.path.isdir(path): shutil.rmtree(path)
    os.makedirs(path)
def main():
    os.makedirs(REPO, exist_ok=True)
    tags = os.path.join(REPO, 'Halo3', 'tags'); fresh(tags)
    full = json.load(open(os.path.join(SA, 'values', 'all.full.json'), encoding='utf-8'))
    n = 0; left = {}
    for kf in sorted({t['kit_file'] for t in full['tags']}):
        who = next((w for p, w in LEAVE_OUT if kf.lower().startswith(p)), None)
        if who: left[who] = left.get(who, 0) + 1; continue
        s = os.path.join(EK, 'tags', kf); d = os.path.join(tags, kf)
        os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy2(s, d); n += 1
    for who, c in left.items(): print(f'left out: {c} source tags of {who}\'s (LEAVE_OUT)')
    spr = os.path.join(REPO, 'Halo3', 'spr'); fresh(spr)
    for v in VALUES: shutil.copy2(os.path.join(SA, 'values', v), spr)
    tools = os.path.join(REPO, 'tools'); fresh(tools)
    for t in TOOLS:
        d = os.path.join(tools, t); os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy2(os.path.join(SA, 'tools', t), d)
    # the tools find the libraries by this PC's absolute path: in the repository, tools\lib next to them
    here_lib = "__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib')"
    for root, ds, fs in os.walk(tools):
        for f in fs:
            if f.endswith('.py'):
                p = os.path.join(root, f); s = open(p, encoding='utf-8').read()
                s2 = s.replace("sys.path.insert(0, r'" + HG + "')", 'sys.path.insert(0, ' + here_lib + ')')
                # tools\preview: the libraries one folder up (tools\lib); Pillow and NumPy from pip, not HugeGrass's pylib
                up_lib = "__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))), 'lib')"
                if os.path.basename(root) == 'preview': s2 = s2.replace("HG = r'" + HG + "'", 'HG = ' + up_lib)
                if s2 != s: open(p, 'w', encoding='utf-8').write(s2)
    lib = os.path.join(tools, 'lib'); os.makedirs(lib)
    for t in LIBS: shutil.copy2(os.path.join(HG, t), lib)
    shutil.copytree(os.path.join(HG, 'assembly'), os.path.join(lib, 'assembly'))
    print(f'{n} source tags, {len(VALUES)} values files, {len(TOOLS)} tools, {len(LIBS)} libraries + Assembly plugins -> {REPO}')
main()
