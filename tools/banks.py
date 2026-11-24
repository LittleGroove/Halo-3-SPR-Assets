# The FMOD banks an SPR Assets map needs (2026-11-23). A sound names its bank by a string (the bank sfx.sabre_hatch.fsb is
# the string "sabre_hatch"), so every custom bank (HugeGrass SPR's, RJ's) whose name is one of the map's strings is
# copied, with its .info. Stock banks are the game's own and aren't shipped. A bank whose name only happens to be a
# string too is copied as well: harmless, and small.
# usage: python -I banks.py <map> <out folder> <bank folder> [<bank folder> ...]
import os, shutil, sys
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'lib'))
from h3map import Map
from tagfields import strings
names = set(s for s in strings(Map(sys.argv[1])) if s)
out = sys.argv[2]; os.makedirs(out, exist_ok=True)
took, size = {}, 0
for folder in sys.argv[3:]:
    for f in sorted(os.listdir(folder)):
        if not (f.startswith('sfx.') and f.endswith('.fsb')): continue
        bank = f[4:-4]
        if bank in names and bank not in took:
            for g in (f, f + '.info'):
                if os.path.exists(os.path.join(folder, g)):
                    shutil.copy2(os.path.join(folder, g), os.path.join(out, g)); size += os.path.getsize(os.path.join(folder, g))
            took[bank] = folder
print(f'{len(took)} banks ({size / 2**20:.1f} MB): {", ".join(sorted(took))}')
