#!/usr/bin/env bash
# Builds the whole SPR Assets pack (2026-11-23), every item in values\inventory.json:
#   1. compile_scenario.py lists every item with source in the compile scenario; H3EK's tool.exe compiles it (Bungie's
#      postprocessing). The compile map is never shipped (about 1 GB: no resource sharing).
#   2. the shipped map starts as a copy of stock Epitaph (the Kit's build of an empty project is that file): relayout.py,
#      ceiling.py
#   3. importtags.py: the source-built items from the compile map, then the fallback items (no source yet, host's decision
#      12) copied compiled from HugeGrass SPR
#   4. forge_palette.py names the source-built items' Forge entries ("Banshee SPR"); the fallback items bring HugeGrass
#      SPR's own entries
#   5. package: the map, forge.json, the custom FMOD banks its sounds name (banks.py) -> --kit-tool verify
# The package keeps the name spr_assets_p1 for now (LG Forge's forge_mods names it; the release name comes later).
# usage: build_pack.sh <out dir>      (REUSE_COMPILE=<map> skips step 1 with a compile map built from the current source)
set -euo pipefail
OUT=$(realpath -m "$1")          # absolute: the build cds into it, and verify names the package by $OUT
SA=/s/Projects/ProjectReclaimer/DEPLOY/SPRAssets
T=/s/Projects/ProjectReclaimer/DEPLOY/HugeGrassFix/tools
EXE=$SA/probe-p1/project-reclaimer.exe
EK='C:/Program Files (x86)/Steam/steamapps/common/H3EK'
HG='S:/Projects/ProjectReclaimer/MODS/SPR/HugeGrass SPR'
MCC='H:\SteamLibrary\steamapps\common\Halo The Master Chief Collection'
EPITAPH='H:/SteamLibrary/steamapps/common/Halo The Master Chief Collection/halo3/maps/salvation.map'
INV="$SA/values/inventory.json"
export RECLAIMER_PROFILE_DIR='S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\probe-p1\profile'
export RECLAIMER_CACHE_DIR='S:\Projects\ProjectReclaimer\DEPLOY\SPRAssets\probe-p1\cache'
mkdir -p "$OUT"; cd "$OUT"
roots() {   # <source|fallback>: importtags roots "tag=like" for the inventory's items of that kind
    python -I -c "
import json, sys
inv = json.load(open(sys.argv[1], encoding='utf-8'))
like = {'vehi': r'objects\vehicles\mongoose\mongoose', 'weap': r'objects\weapons\rifle\assault_rifle\assault_rifle'}
src = sys.argv[2] == 'source'
for r in inv['items']:
    if (r['source'] in ('stock', 'rj', 'release')) == src: print(r['tag'] + '=' + like[r['tag'].rsplit('.', 1)[1]])
" "$(cygpath -w "$INV")" "$1" | tr -d '\r'
}
echo "1. tool.exe compile map"
if [ -n "${REUSE_COMPILE:-}" ]; then
    mv "$REUSE_COMPILE" compile.map; echo "   reused $REUSE_COMPILE (built from the current source)"
else
    python -I "$SA/tools/compile_scenario.py" "$(cygpath -w "$INV")"
    rm -f "$EK/maps/spr_assets_p2.map"
    (cd "$EK" && ./tool.exe build-cache-file 'levels\spr_assets\spr_assets_p2\spr_assets_p2' pc english use-fmod-data) > tool.log 2>&1
    grep -a -c -E "^-ERROR-" tool.log | sed 's/^/   tool.exe errors: /' || true
    grep -a -E "successfully built" tool.log || { tail -5 tool.log; exit 1; }
    mv "$EK/maps/spr_assets_p2.map" compile.map
fi
echo "2. stock Epitaph, relayout, room"
rm -f flat.map spr_assets_p1.map
python -I "$SA/tools/relayout.py" "$EPITAPH" flat.map | cut -c1-160
python -I "$T/ceiling.py" flat.map spr_assets_p1.map 96 | cut -c1-120; rm -f flat.map
# Fallback items first: importtags keeps a tag the map already has by name, so whichever comes first sets the shared
# stock-named tags. First, they are HugeGrass SPR's own (RJ's changes to stock tags included) for the fallback items; the
# source-built items point at their own _spr copies of every shared tag HugeGrass changed (deepparity.py), so they don't
# depend on the order. (Round 1, source first, gave the fallback items the source's versions: deep-r1-fallback.txt.)
# SOURCE_FIRST=1 swaps the order: the build deepparity.py --write compares against, so every shared tag the source items
# use is the source's own and each difference from HugeGrass shows (not a release build).
import_fallback() {
    echo "   fallback items copied from HugeGrass SPR"
    mapfile -t FB < <(roots fallback); echo "   ${#FB[@]} items"
    python -I "$T/importtags.py" spr_assets_p1.map "$HG/maps/hugegrass_spr.map" "${FB[@]}" > import_fallback.log 2>&1 || { tail -8 import_fallback.log; exit 1; }
    grep -E "^read back|tags brought in" import_fallback.log
}
import_source() {
    echo "   source-built items from the compile map"
    mapfile -t SRC < <(roots source); echo "   ${#SRC[@]} items"
    python -I "$T/importtags.py" spr_assets_p1.map compile.map "${SRC[@]}" > import_source.log 2>&1 || { tail -8 import_source.log; exit 1; }
    grep -E "^read back|tags brought in" import_source.log
}
echo "3a/3b. the items"
if [ -n "${SOURCE_FIRST:-}" ]; then import_source; import_fallback; else import_fallback; import_source; fi
echo "3c. one Forge entry per configuration (values\splits.json: the Falcons)"
python -I "$SA/tools/split_variants.py" spr_assets_p1.map "$(cygpath -w "$SA/values/splits.json")" | tail -1
if [ -f "$SA/values/falcon_tests.json" ]; then          # TEST Falcons for the AI seats (plans/falcon-ai-seats.md), until the host decides
    echo "3c'. test Falcons (values\falcon_tests.json)"
    python -I "$SA/tools/split_variants.py" spr_assets_p1.map "$(cygpath -w "$SA/values/falcon_tests.json")" | tail -1
fi
# PR's Forge offers every model variant as an entry of its own (leftovers on the first vehicle with that model). The host's
# trim (2026-11-23, research (2026-11-23 variants)\variants.md): the setups worth having become vehicles of their own, and
# every other vehicle keeps only its default variant (trim_all), so each Forge entry is one vehicle with one name.
echo "3c''. the other vehicles' setups (values\variants.json: 14 new vehicles, every vehicle trimmed to one variant)"
python -I "$SA/tools/split_variants.py" spr_assets_p1.map "$(cygpath -w "$SA/values/variants.json")" | tail -1
echo "3d. our fixes on the fallback items (values\compiled_fixes.json, and the test Falcons' seats)"
FIXES=("$(cygpath -w "$SA/values/compiled_fixes.json")")
[ -f "$SA/values/falcon_tests_fixes.json" ] && FIXES+=("$(cygpath -w "$SA/values/falcon_tests_fixes.json")")
python -I "$SA/tools/compiled_fix.py" spr_assets_p1.map "${FIXES[@]}" | tail -1
echo "4. Forge names of the source-built items"
mapfile -t NAMES < <(python -I -c "
import json, sys
for r in json.load(open(sys.argv[1], encoding='utf-8'))['items']:
    if r['source'] in ('stock', 'rj', 'release'): print(r['tag'] + '=' + r['label'])
" "$(cygpath -w "$INV")" | tr -d '\r')
python -I "$SA/tools/forge_palette.py" spr_assets_p1.map "${NAMES[@]}" | tail -1
echo "5. package"
rm -rf pkg; mkdir -p pkg/spr_assets_p1/halo3/fmod/pc; ln spr_assets_p1.map pkg/spr_assets_p1/spr_assets_p1.map
cp "$SA/tools/spr_assets.forge.json" pkg/spr_assets_p1/spr_assets_p1.forge.json
python -I "$SA/tools/banks.py" spr_assets_p1.map pkg/spr_assets_p1/halo3/fmod/pc "$HG/halo3/fmod/pc" "$SA/upstream/RejectedShotgun-Tags/Halo3/fmod/pc" | cut -c1-300
echo "6. verify"
"$EXE" --kit-tool verify --mcc "$MCC" "$(cygpath -w "$OUT/pkg/spr_assets_p1/spr_assets_p1.map")" > verify.log 2>&1 || true
grep -E "tags checked|^error" verify.log | head -5
du -sh --apparent-size pkg/spr_assets_p1 | cut -f1
