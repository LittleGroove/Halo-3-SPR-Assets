# Halo 3 SPR Assets

The SPR vehicles and weapons as Forge objects for any Halo 3 map on
[Project Reclaimer](https://projectreclaimer.dev): 62 vehicles and 23 weapons, tuned by Halo lore for speed, mass,
armour, weapon reach and lock-on range. This repository is its source: the tags it's built from, the SPR values, and
the tools that build, check and package it.

- **Players and hosts:** get the pack from the Steam Workshop: (link to be added). Hosting and Forge use are on that page.
- **Who made what:** [CREDITS.md](CREDITS.md). Very little of it starts with us: every item comes from
  RejectedShotgun's HugeGrass, through our build of it, HugeGrass SPR.
- **Version:** v1.0 (2026-11-23).

## What's here

| Folder | What |
| --- | --- |
| `Halo3/tags/` | The source tags the build makes or changes: the `_spr` copies of Bungie's stock tags and of the published releases' tags, with the SPR values written in, and the `_spr` copies of shared tags SPR changes. Laid out as in the Halo 3 Editing Kit's `tags` folder. |
| `Halo3/spr/` | The values and decisions, as data: which items come from source and which are copied compiled (`inventory.json`, `fallback.json`, with a reason for each), the SPR values (`all.walk.json`, `all.full.json`), fixes (`fixes.json`, `compiled_fixes.json`) and the Forge entries (`splits.json` for the Falcons, `variants.json` for every other vehicle). |
| `tools/` | The build. `tools/lib/` holds the map libraries the tools share with HugeGrass SPR's build, and Assembly's Halo 3 plugins (GPL-3.0). `tools/preview/` renders the Workshop image. |

Left out on purpose: **Skaboodlydoodle's Sparrowhawk tags.** His terms don't allow re-uploading his files, so the
Sparrowhawk tags stay with him: get his release from Nexus Mods ([UPSTREAM.md](UPSTREAM.md)) and the build writes the
SPR values into it.

## How the pack is built

Every item is the SPR version HugeGrass SPR plays. The build reproduces those versions from source wherever source
exists, and checks them field by field against HugeGrass SPR.

1. **Source.** The Halo 3 Editing Kit (H3EK) holds Bungie's stock tags. The published releases (RejectedShotgun's
   tags, J-S's Kestrel and Vulture, Skaboodlydoodle's Sparrowhawk, R3ACH) are added to its `tags` folder with
   `tools/overlay.py deploy`, which never replaces a kit file and records what it added so `remove` can take it out.
2. **Values.** `inventory.py` lists the items from HugeGrass SPR's Forge palettes. `sprwalk.py` and `deepparity.py`
   read every value HugeGrass SPR changes, deep into each item's tag tree (`all.walk.json`, `all.full.json`).
   `sprapply.py` writes them into `_spr` copies of the source tags with H3EK's `tool.exe`, falling back to a small
   ManagedBlam program (`tools/mbtool`) for fields `tool.exe` can't reach, and reads every value back.
3. **Compile.** `compile_scenario.py` puts every source item in a scenario's palettes, and H3EK's
   `tool.exe build-cache-file` compiles it, with Bungie's own processing (physics, resources).
4. **The map.** `build_pack.sh`: the shipped map starts as a copy of Halo 3's Epitaph, laid out with room for the
   items (`relayout.py`, `ceiling.py`); `importtags.py` brings in the items copied compiled from HugeGrass SPR (the
   ones without published source yet), then the source-built items from the compile map. Then one Forge entry per
   vehicle setup (`split_variants.py`), the fixes on copied items (`compiled_fix.py`), the Forge names
   (`forge_palette.py`), the custom sound banks the items name (`banks.py`), and `project-reclaimer --kit-tool verify`.
5. **Check.** `deepparity.py` compares the built pack with HugeGrass SPR, tag by tag and field by field.
   `forge_entries.py` lists what Project Reclaimer's Forge will offer.
6. **Package.** `package_release.sh` names the package for release and writes `ModInfo.json`.

### What you need

- Windows, Git Bash, Python 3.13 with NumPy and Pillow (`pip install numpy pillow`), and the .NET SDK to build
  `tools/mbtool` against H3EK's ManagedBlam.
- The Halo 3 Editing Kit (Steam) and Halo: The Master Chief Collection (Epitaph's map is the donor).
- Project Reclaimer 0.10.9 or later, for `--kit-tool verify`.
- HugeGrass SPR v3.0.SPR.1.2 and the releases in [UPSTREAM.md](UPSTREAM.md).
- The tools name this PC's folders at their tops (`SA`, `EK`, `MCC` and the like): set them to yours.

## Rules the pack keeps

- **Tag paths, the map's file name (`halo3_spr_assets.map`) and the title are fixed for good.** Saved Forge maps name
  the pack's objects by them. Items are only ever added.
- **A stock or published tag is never changed under its own path.** Every changed tag gets an `_spr` path, so a map
  merging this pack never sees two different tags with one name.
- **"SPR" in every name:** `_spr` in tag names, "SPR" in Forge names.
- **Nothing that needs a map's scripts.**
- **Credit everyone,** with links and their terms ([CREDITS.md](CREDITS.md)). The pack is free and is never sold.

## Licence

The tools (`tools/`) are SPR's, under the GNU General Public License v3.0 ([LICENSE](LICENSE)). Assembly's plugins in
`tools/lib/assembly` keep their own GPL-3.0 licence.

The tags and values in `Halo3/` are Halo game content, not ours to license: they belong to their authors and to
Microsoft, and are here under each author's terms ([CREDITS.md](CREDITS.md)) and Microsoft's Game Content Usage Rules.

Your work in this pack? Tell us on the SPR Discord and we'll credit it differently or take it out:
<https://discord.gg/4bYtHw5JCW>

*Halo © Microsoft Corporation. Halo 3 SPR Assets was created under Microsoft's "Game Content Usage Rules" using assets
from Halo: The Master Chief Collection, and it is not endorsed by or affiliated with Microsoft.*
