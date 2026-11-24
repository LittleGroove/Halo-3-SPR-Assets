#!/usr/bin/env bash
# The release package of Halo 3 SPR Assets from a finished build (2026-11-23): build_pack.sh's package (named spr_assets_p1,
# as LG Forge's forge_mods knows it) renamed to the release name, with ModInfo.json, as a real copy in MODS\SPR.
#   <MODS>\SPR\Halo 3 SPR Assets\
#     halo3_spr_assets.map               the map (its file name is the "donor" saved Forge layouts name: never change it)
#     halo3_spr_assets.forge.json
#     ModInfo.json                       title "Halo 3 SPR Assets", version from tools\release\ModInfo.json; the Workshop ID
#                                        is added by the uploader on the first upload and must be kept from then on
#     halo3\fmod\pc\*.fsb(.info)         the custom sound banks
# Refuses to overwrite a package whose ModInfo already has a Workshop ID unless the new ModInfo carries the same ID.
# Then --kit-tool verify on the copy, and the SHA-256 of the map (for MODS\VERSIONS.md).
# usage: package_release.sh <build dir (pack-rN)>
set -euo pipefail
BUILD=$1
SA=/s/Projects/ProjectReclaimer/DEPLOY/SPRAssets
DEST="/s/Projects/ProjectReclaimer/MODS/SPR/Halo 3 SPR Assets"
PKG=halo3_spr_assets
SRC="$BUILD/pkg/spr_assets_p1"
MCC='H:\SteamLibrary\steamapps\common\Halo The Master Chief Collection'
[ -f "$SRC/spr_assets_p1.map" ] || { echo "no build package in $SRC"; exit 1; }
MODINFO="$SA/tools/release/ModInfo.json"
if [ -f "$DEST/ModInfo.json" ] && grep -q SteamWorkshopId "$DEST/ModInfo.json"; then
    old=$(grep -o '"SteamWorkshopId": *[0-9]*' "$DEST/ModInfo.json" | grep -o '[0-9]*$')
    grep -q "\"SteamWorkshopId\": *$old" "$MODINFO" || { echo "the package in MODS has Workshop ID $old and tools\\release\\ModInfo.json doesn't: put it there first"; exit 1; }
fi
rm -rf "$DEST.new"; mkdir -p "$DEST.new/halo3/fmod/pc"
cp "$SRC/spr_assets_p1.map" "$DEST.new/$PKG.map"
cp "$SRC/spr_assets_p1.forge.json" "$DEST.new/$PKG.forge.json"
cp "$SRC/halo3/fmod/pc/"* "$DEST.new/halo3/fmod/pc/"
cp "$MODINFO" "$DEST.new/ModInfo.json"
rm -rf "$DEST.old"; [ -d "$DEST" ] && mv "$DEST" "$DEST.old"; mv "$DEST.new" "$DEST"; rm -rf "$DEST.old"
"$SA/probe-p1/project-reclaimer.exe" --kit-tool verify --mcc "$MCC" "$(cygpath -w "$DEST/$PKG.map")" 2>&1 | grep -E "tags checked|^error" | head -3
echo "map SHA-256: $(sha256sum "$DEST/$PKG.map" | cut -d' ' -f1)"
du -sh --apparent-size "$DEST" | cut -f1
ls "$DEST"
