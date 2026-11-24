# Puts tag-release files into H3EK's tags/data/fmod folders WITHOUT ever replacing a kit file, and takes them out again.
#   check   <src root> : which files of <src root> (holding tags\, data\, fmod\ ...) exist in H3EK already, and whether same bytes
#   deploy  <src root> <name> [subpath filter...] [--into <H3EK path>] : copy what H3EK lacks; files H3EK has with other bytes are SKIPPED and
#                       listed (they'd be the source's changes to stock tags); writes DEPLOY\SPRAssets\overlays\<name>.json
#   remove  <name>     : delete exactly the files that manifest added (only if unchanged since), then empty folders
# usage: python -I overlay.py check|deploy|remove ...
import hashlib, json, os, shutil, sys
EK = r'C:\Program Files (x86)\Steam\steamapps\common\H3EK'
MAN = r'S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\overlays'
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''): h.update(b)
    return h.hexdigest()
def files(root, filters=()):
    for d, ds, fs in os.walk(root):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), root)
            top = rel.split(os.sep)[0].lower()
            if top not in ('tags', 'data', 'fmod'): continue
            if filters and not any(rel.lower().startswith(x.lower().replace('/', os.sep)) for x in filters): continue
            yield rel
cmd = sys.argv[1]
if cmd == 'check':
    src = sys.argv[2]; new = same = diff = 0; diffs = []
    for rel in files(src):
        t = os.path.join(EK, rel)
        if not os.path.exists(t): new += 1
        elif os.path.getsize(t) == os.path.getsize(os.path.join(src, rel)) and sha(t) == sha(os.path.join(src, rel)): same += 1
        else: diff += 1; diffs.append(rel)
    print(f'new {new}, identical to H3EK {same}, H3EK has other bytes {diff}')
    for d in diffs[:80]: print('   differs:', d)
    if len(diffs) > 80: print(f'   ... {len(diffs) - 80} more')
elif cmd == 'deploy':
    # --into <path>: a release whose files start inside one object's folder (the Sparrowhawk zip: bitmaps\, cameras\ ...
    # at its root) goes under <path> in H3EK (e.g. tags\objects\vehicles\sparrowhawk); then <src> is that folder itself
    args = sys.argv[2:]; into = None
    if '--into' in args: k = args.index('--into'); into = args[k + 1]; del args[k:k + 2]
    src, name, filt = args[0], args[1], args[2:]
    os.makedirs(MAN, exist_ok=True); mp = os.path.join(MAN, name + '.json')
    man = json.load(open(mp, encoding='utf-8')) if os.path.exists(mp) else {'source': src, 'added': {}, 'skipped': []}
    if into: man['into'] = into
    def walk_into():
        for d, ds, fs in os.walk(src):
            for f in fs:
                r = os.path.relpath(os.path.join(d, f), src)
                if not filt or any(r.lower().startswith(x.lower().replace('/', os.sep)) for x in filt): yield r
    for rel0 in (walk_into() if into else files(src, filt)):
        rel = os.path.join(into, rel0) if into else rel0
        s, t = os.path.join(src, rel0), os.path.join(EK, rel)
        if os.path.exists(t):
            if rel not in man['added'] and sha(s) != sha(t) and rel not in man['skipped']: man['skipped'].append(rel)
            continue
        os.makedirs(os.path.dirname(t), exist_ok=True); shutil.copy2(s, t); man['added'][rel] = sha(t)
    json.dump(man, open(mp, 'w', encoding='utf-8'), indent=1)
    print(f"{name}: {len(man['added'])} files added to H3EK so far; {len(man['skipped'])} skipped (H3EK has other bytes)")
    for d in man['skipped'][:40]: print('   skipped:', d)
elif cmd == 'add':
    # record files we made in H3EK ourselves (e.g. an _spr copy made there and patched by tool.exe) under <name>,
    # so 'remove' takes them out; refuses a path H3EK shipped (in the kit's archive listing)
    name, rels = sys.argv[2], sys.argv[3:]
    shipped = set()
    lst = r'S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\research (2026-11-22)\kit listings\H3EK.tsv'
    for l in open(lst, encoding='utf-8', errors='replace'):
        if '\t' in l: shipped.add(l.rstrip('\n').split('\t', 1)[1].lower())
    os.makedirs(MAN, exist_ok=True); mp = os.path.join(MAN, name + '.json')
    man = json.load(open(mp, encoding='utf-8')) if os.path.exists(mp) else {'source': 'made in H3EK', 'added': {}, 'skipped': []}
    for rel in rels:
        if rel.lower() in shipped: sys.exit(f'refused: {rel} is one of H3EK\'s own files')
        man['added'][rel] = sha(os.path.join(EK, rel)); print('recorded', rel)
    json.dump(man, open(mp, 'w', encoding='utf-8'), indent=1)
elif cmd == 'adopt':
    # record every file under H3EK\<folder> that H3EK didn't ship and no manifest holds yet (files tool.exe generated,
    # e.g. shader templates), under <name>
    name, folder = sys.argv[2], sys.argv[3]
    shipped = set()
    lst = r'S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\research (2026-11-22)\kit listings\H3EK.tsv'
    for l in open(lst, encoding='utf-8', errors='replace'):
        if '\t' in l: shipped.add(l.rstrip('\n').split('\t', 1)[1].lower())
    held = set()
    for f in os.listdir(MAN):
        if f.endswith('.json'): held.update(k.lower() for k in json.load(open(os.path.join(MAN, f), encoding='utf-8'))['added'])
    mp = os.path.join(MAN, name + '.json')
    man = json.load(open(mp, encoding='utf-8')) if os.path.exists(mp) else {'source': 'generated in H3EK', 'added': {}, 'skipped': []}
    for rel in files(EK, ()):
        if rel.lower().startswith(folder.lower()) and rel.lower() not in shipped and rel.lower() not in held:
            man['added'][rel] = sha(os.path.join(EK, rel)); print('adopted', rel)
    json.dump(man, open(mp, 'w', encoding='utf-8'), indent=1)
elif cmd == 'remove':
    name = sys.argv[2]; mp = os.path.join(MAN, name + '.json'); man = json.load(open(mp, encoding='utf-8')); kept = 0
    for rel, h in man['added'].items():
        t = os.path.join(EK, rel)
        if os.path.exists(t):
            if sha(t) == h: os.remove(t)
            else: kept += 1; print('   changed since deploy, kept:', rel)
    for rel in sorted({os.path.dirname(r) for r in man['added']}, key=len, reverse=True):
        d = os.path.join(EK, rel)
        while d.startswith(EK) and d != EK and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d); d = os.path.dirname(d)
    os.replace(mp, mp + '.removed')
    print(f'{name}: removed {len(man["added"]) - kept}, kept {kept}')
