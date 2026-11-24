# What tells a vehicle's configurations apart (2026-11-23, host on the Falcons: "why so many falcons?"): for each vehicle,
# its default model variant, weapons (the pilot's gun), seats, speeds, and for every variant of its model the objects it
# attaches (side turrets) and the regions/permutations it shows. Project Reclaimer offers each model variant as its own
# Forge entry, so N vehicles on one model with V variants appear as N x V entries.
# usage: python -I vehicle_config.py <map> <vehicle spec> [...]
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sprdiff
from tagfields import fields
def main():
    m, S = sprdiff.load(sys.argv[1])
    models = {}
    for spec in sys.argv[2:]:
        f = fields(m, S, sprdiff.find(m, spec))
        model = f.get('/Model', ('ref', '-'))[1]
        print(f'== {spec}')
        print(f"   model {model}, default variant '{f.get('/Default Model Variant', ('sid', ''))[1]}'")
        print('   weapons: ' + ', '.join(str(v[1]) for k, v in f.items() if re.match(r'^/Weapons\[\d+\]/Weapon$', k)))
        seats = sorted({int(re.match(r'^/Seats\[(\d+)\]', k).group(1)) for k in f if re.match(r'^/Seats\[\d+\]/', k)})
        print(f'   seats ({len(seats)}): ' + ', '.join(f"{f.get(f'/Seats[{s}]/Label', ('', '?'))[1]}" for s in seats))
        for k, v in f.items():
            if re.search(r'(?i)(maximum forward speed|maximum reverse speed|speed acceleration|turn rate|maximum left turn)$', k): print(f'   {k} = {v[1]}')
        models[model] = True
    for model in models:
        if model in ('-', None): continue
        f = fields(m, S, sprdiff.find(m, model))
        n = f.get('/Variants (count)', ('count', 0))[1]
        print(f'== {model}: {n} variants')
        for k in range(n):
            name = f.get(f'/Variants[{k}]/Name', ('sid', '?'))[1]
            objs = [f"{f.get(f'/Variants[{k}]/Objects[{j}]/Parent Marker', ('', '?'))[1]} -> {f.get(f'/Variants[{k}]/Objects[{j}]/Child Object', ('', '?'))[1]}"
                    for j in range(f.get(f'/Variants[{k}]/Objects (count)', ('count', 0))[1])]
            regs = []
            for r in range(f.get(f'/Variants[{k}]/Regions (count)', ('count', 0))[1]):
                rn = f.get(f'/Variants[{k}]/Regions[{r}]/Region Name', ('', '?'))[1]
                perms = [f.get(f'/Variants[{k}]/Regions[{r}]/Permutations[{p}]/Permutation Name', ('', '?'))[1]
                         for p in range(f.get(f'/Variants[{k}]/Regions[{r}]/Permutations (count)', ('count', 0))[1])]
                regs.append(f'{rn}:{"/".join(perms)}')
            print(f"   [{k}] {name}: objects {objs or 'none'}\n        regions {' '.join(regs)}")
main()
