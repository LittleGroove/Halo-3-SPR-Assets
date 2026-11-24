# The SPR Assets compile scenario for H3EK's own tool.exe (2026-11-23; replaces p2_scenario.sh): a copy of
# salvation.scenario (Epitaph) at levels\spr_assets\spr_assets_p2\ listing every item the inventory builds from source
# (values\inventory.json, source stock or rj). Each item goes:
#   - in the vehicle or weapon palette (brings its tags into the build)
#   - placed once in the vehicles or weapons block, at the origin (this map is only compiled, never played or shipped)
#   - in the Forge ("mv") vehicle or weapon palette: tool.exe carries resources (render models, bitmaps, animations) only
#     for objects the level uses, and without a Forge entry an object's resource rows came out empty (found 2026-11-23:
#     importtags refused banshee.mode's resource datum). Its name is a string id (banshee_spr: a source string id can't
#     hold "Banshee SPR"); importtags brings the entry to the shipped map and forge_palette.py renames it.
# One mbtool batch (one load, one save, every value read back). Remakes the copy every run.
# usage: python -I compile_scenario.py <inventory.json>
import json, os, re, subprocess, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
EK = r'C:\Program Files (x86)\Steam\steamapps\common\H3EK'
MB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mbtool', 'mbtool.exe')
SC = r'levels\spr_assets\spr_assets_p2\spr_assets_p2'
KIND = {'vehi': ('vehicle palette', 'vehicles', 'mv vehicle palette', 'vehicle'),
        'weap': ('weapon palette', 'weapons', 'mv weapon palette', 'weapon')}
def mb(*a):
    r = subprocess.run([MB, EK, *a], capture_output=True, text=True, errors='replace'); return r.returncode, r.stdout.replace('\r', '')
def main():
    inv = json.load(open(sys.argv[1], encoding='utf-8'))
    items = [r for r in inv['items'] if r['source'] in ('stock', 'rj', 'release')]
    dst = os.path.join(EK, 'tags', SC + '.scenario'); os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(os.path.join(EK, 'tags', r'levels\multi\salvation\salvation.scenario'), dst)
    code, out = mb('paths', SC, 'scenario')
    count = {m.group(1): int(m.group(2)) for m in re.finditer(r'^Block:([a-z ]+) = block,(\d+)$', out, re.M)}
    lines, uid = [], 770000
    for r in items:
        name, g = r['tag'].rsplit('.', 1); pal, placed, mv, ext = KIND[g]
        k = count[pal]; count[pal] += 1
        lines += [f'add\tBlock:{pal}', f'set\tBlock:{pal}[{{N}}]/Reference:name\t{name},{ext}',
                  f'add\tBlock:{placed}', f'set\tBlock:{placed}[{{N}}]/ShortBlockIndex:type\t{k}',
                  f'set\tBlock:{placed}[{{N}}]/Struct:object data[0]/Real:scale\t1',
                  f'set\tBlock:{placed}[{{N}}]/Struct:object data[0]/Struct:object id[0]/LongInteger:unique id\t{uid}',
                  f'add\tBlock:{mv}', f'set\tBlock:{mv}[{{N}}]/Reference:name\t{name},{ext}',
                  f'set\tBlock:{mv}[{{N}}]/StringId:display_name\t{name.rsplit(chr(92), 1)[-1]}',
                  f'set\tBlock:{mv}[{{N}}]/LongInteger:maximum allowed\t4',
                  f'set\tBlock:{mv}[{{N}}]/Real:price per instance\t10']
        uid += 1
    bf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'values', 'compile_scenario.batch')
    open(bf, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    code, out = mb('batch', SC, 'scenario', os.path.abspath(bf))
    print(out.strip().splitlines()[-1] if out.strip() else f'mbtool exit {code}')
    print(f'{len(items)} items listed in {SC}: vehicle palette now {count["vehicle palette"]}, weapon palette {count["weapon palette"]}')
    sys.exit(code)
main()
