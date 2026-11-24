# Upstream

What the v1.0 build reads, and where to get it. Who made each one, and their terms: [CREDITS.md](CREDITS.md).

## The SPR versions

| What | Version | Where |
| --- | --- | --- |
| HugeGrass SPR | v3.0.SPR.1.2, map SHA-256 `d324d220fcc3a3ff98e714fefc4ed0531f85c80dcc6fbbbb5db9534eaee88476` | Steam Workshop item [3832239928](https://steamcommunity.com/sharedfiles/filedetails/?id=3832239928) |

Every item's SPR values come from it, and the 51 items without published source are copied compiled from it.

## Source tags

Added to H3EK's `tags` folder with `tools/overlay.py deploy <release folder> <name>`.

| Release | Version | Get it | Overlay |
| --- | --- | --- | --- |
| Halo 3 Editing Kit | as installed by Steam (2026-11) | Steam, [app 1695791](https://store.steampowered.com/app/1695791/) | (the kit itself) |
| RejectedShotgun-Tags, `Halo3` | commit `dc29731` (2026-06-08) | <https://github.com/RJShotgun/RejectedShotgun-Tags> | `rj-halo3`: 1,740 files (3 the kit already has, skipped) |
| J-S, Halo 3 AV-30 Kestrel tags | 1.0: `Kestrel tags-2524-1-0-1711566413.zip` (`Kestrel_tags`) | [Nexus Mods 2524](https://www.nexusmods.com/halothemasterchiefcollection/mods/2524) | `nexus-2524-kestrel`: 375 files |
| J-S, Halo 3 custom Vulture tags | 1.0: `Vulture tags-2247-1-0-1673830950.zip` (`vulture`) | [Nexus Mods 2247](https://www.nexusmods.com/halothemasterchiefcollection/mods/2247) | `nexus-2247-vulture`: 431 files |
| Skaboodlydoodle, AV-22 Sparrowhawk Tags | 1: `Sparrowhawk tags-2327-1-1684175607.zip` | [Nexus Mods 2327](https://www.nexusmods.com/halothemasterchiefcollection/mods/2327) | `nexus-2327-sparrowhawk`, `--into tags\objects\vehicles\sparrowhawk`: 412 files |
| R3ACH, Halo Reach Weapon Pack | 1.0.2: `r3ach_102_tags-2646-1-0-2-1733563842.7z` | [Nexus Mods 2646](https://www.nexusmods.com/halothemasterchiefcollection/mods/2646) | `nexus-2646-r3ach`: 1,202 files |

Made in H3EK by the build, not downloaded: the `_spr` tags themselves (in `Halo3/tags` here), the compile scenario, and
15 shader templates RejectedShotgun's Lich shaders name (`tool.exe generate-specified-template win64 shaders\shader
<template>`).

## Sound banks

Shipped as files beside the map, the bytes of their sources: RejectedShotgun's from HugeGrass SPR and his repository,
J-S's Kestrel bank from the Kestrel release, R3ACH's `sfx.r3ach`, and SPR's Reach Shade banks (rebuilt from Halo:
Reach's own audio in MCC). The list: [CREDITS.md, Sound banks](CREDITS.md#sound-banks).

## Tools

| Tool | Version | Where |
| --- | --- | --- |
| Project Reclaimer | 0.10.9 (`--kit-tool verify`) | <https://github.com/ProjectReclaimer/project-reclaimer-releases> |
| Assembly's Halo 3 MCC plugins | as in `tools/lib/assembly` (GPL-3.0) | <https://github.com/XboxChaos/Assembly> |
| The donor map | Halo 3's Epitaph, `halo3\maps\salvation.map` in MCC | Halo: The Master Chief Collection |
