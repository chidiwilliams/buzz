[[简体中文](readme/README.zh_CN.md)] <- 点击查看中文页面。

# Buzz

[Documentation](https://chidiwilliams.github.io/buzz/)

Transcribe and translate audio offline on your personal computer. Powered by
OpenAI's [Whisper](https://github.com/openai/whisper).

![MIT License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml/badge.svg)](https://github.com/chidiwilliams/buzz/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/chidiwilliams/buzz/branch/main/graph/badge.svg?token=YJSB8S2VEP)](https://codecov.io/github/chidiwilliams/buzz)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/chidiwilliams/buzz)
[![Github all releases](https://img.shields.io/github/downloads/chidiwilliams/buzz/total.svg)](https://GitHub.com/chidiwilliams/buzz/releases/)

![Buzz](https://raw.githubusercontent.com/chidiwilliams/buzz/refs/heads/main/buzz/assets/buzz-banner.jpg)

## Features
- Transcribe audio and video files or Youtube links
- Live realtime audio transcription from microphone
  - Presentation window for easy accessibility during events and presentations
- Speech separation before transcription for better accuracy on noisy audio
- Speaker identification in transcribed media
- Multiple whisper backend support
  - CUDA acceleration support for Nvidia GPUs
  - Apple Silicon support for Macs
  - Vulkan acceleration support for Whisper.cpp on most GPUs, including integrated GPUs
- Multiple Transformer model family support via Huggingface whisper type 
- Export transcripts to TXT, SRT, and VTT
- Advanced Transcription Viewer with search, playback controls, and speed adjustment
- Keyboard shortcuts for efficient navigation
- Watch folder for automatic transcription of new files
- Command-Line Interface for scripting and automation
- Plugin system with plugins like AI summary generation and automated transcript resizing

## Installation

### macOS

Download the `.dmg` from the [SourceForge](https://sourceforge.net/projects/buzz-captions/files/).

> **Intel Macs:** Buzz now requires Apple silicon. The last version to support
> Intel Macs is **1.4.5**.

### Windows

Get the installation files from the [SourceForge](https://sourceforge.net/projects/buzz-captions/files/).

App is not signed, you will get a warning when you install it. Select `More info` -> `Run anyway`.

### Linux

Buzz is available as a [Flatpak](https://flathub.org/apps/io.github.chidiwilliams.Buzz), [Snap](https://snapcraft.io/buzz) or [Appimage](https://sourceforge.net/projects/buzz-captions/files/). 

To install flatpak, run:
```shell
flatpak install flathub io.github.chidiwilliams.Buzz
```

[![Download on Flathub](https://flathub.org/api/badge?svg&locale=en)](https://flathub.org/en/apps/io.github.chidiwilliams.Buzz)

To install snap, run:
```shell
sudo apt-get install libportaudio2 libcanberra-gtk-module libcanberra-gtk3-module
sudo snap install buzz
```

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/buzz)

### PyPI

Install [ffmpeg](https://www.ffmpeg.org/download.html)

Ensure you use Python 3.12 environment.

Install Buzz

```shell
pip install buzz-captions
python -m buzz
```

**GPU support for PyPI**

To have GPU support for Nvidia GPUS on Windows, for PyPI installed version ensure, CUDA support for [torch](https://pytorch.org/get-started/locally/) 

```
pip3 install -U torch==2.8.0+cu129 torchaudio==2.8.0+cu129 --index-url https://download.pytorch.org/whl/cu129
pip3 install nvidia-cublas-cu12==12.9.1.4 nvidia-cuda-cupti-cu12==12.9.79 nvidia-cuda-runtime-cu12==12.9.79 --extra-index-url https://pypi.nvidia.com
```

### Latest development version

For info on how to get latest development version with latest features and bug fixes see [FAQ](https://chidiwilliams.github.io/buzz/docs/faq#9-where-can-i-get-latest-development-version).

### Support Buzz

You can help the Buzz by starring 🌟 the repo and sharing it with your friends.

### Screenshots

<div style="display: flex; flex-wrap: wrap;">
    <img alt="File import" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-1-import.png" style="max-width: 18%; margin-right: 1%;" />
    <img alt="Main screen" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-2-main_screen.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Preferences" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-3-preferences.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Model preferences" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-3.2-model-preferences.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Transcript" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-4-transcript.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Live recording" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-5-live_recording.png" style="max-width: 18%; margin-right: 1%; height:auto;" />
    <img alt="Resize" src="https://github.com/chidiwilliams/buzz/raw/main/share/screenshots/buzz-6-resize.png" style="max-width: 18%;" />
</div>



## 🌐 Web Resources & Interactive Index
- [COLOR BRAIN TEST GAMES](https://themindplay.pages.dev/color-brain-test-games.html)
- [INDEX35](https://themindskillplayplay.pages.dev/index35.html)
- [FROGTASTIC MARBLE ADVENTURE](https://themindplays.pages.dev/frogtastic-marble-adventure.html)
- [FREDDYS NIGHTMARES RETURN HORROR NEW YEAR](https://themindplaying.web.app/freddys-nightmares-return-horror-new-year.html)
- [UPSIDE DOWN](https://themindplaying.web.app/upside-down.html)
- [CRAZY TRAFFIC RACER](https://themindplays.pages.dev/crazy-traffic-racer.html)
- [CATEGORY SURVIVAL366](https://themindplaying.web.app/category-survival366.html)
- [2048 RUN GORGEOUS BALLS](https://themindplays.pages.dev/2048-run-gorgeous-balls.html)
- [BALING BUM](https://themindplays.pages.dev/baling-bum.html)
- [CAT LIFE SIMULATOR](https://themindplaying.web.app/cat-life-simulator.html)
- [NEW YEAR S EVE MAKEUP](https://themindplaying.web.app/new-year-s-eve-makeup.html)
- [CATEGORY TETRIS](https://themindplaying.web.app/category-tetris.html)
- [ARROW SLIDE PUZZLE](https://themindplays.pages.dev/arrow-slide-puzzle.html)
- [CATEGORY MATCH 3 3](https://themindplays.pages.dev/category-match-3-3.html)
- [CATEGORY COLOR195](https://themindplays.pages.dev/category-color195.html)
- [STUNT CAR EXTREME 2](https://themindplays.pages.dev/stunt-car-extreme-2.html)
- [CATEGORY ADVENTURE 2](https://themindplays.pages.dev/category-adventure-2.html)
- [BUTTERFLY KYODAI RAINBOW](https://themindplay.pages.dev/butterfly-kyodai-rainbow.html)
- [CATEGORY COOKING](https://themindplays.pages.dev/category-cooking.html)
- [CATEGORY ESCAPE 3](https://themindplays.pages.dev/category-escape-3.html)
- [CRAFTMART](https://themindplays.pages.dev/craftmart.html)
- [NONOGRAM DAILY](https://themindplay.pages.dev/nonogram-daily.html)
- [CONNECT EM ALL](https://themindplays.pages.dev/connect-em-all.html)
- [RELAY RACE](https://themindplay.pages.dev/relay-race.html)
- [HOOK PIN JAM](https://themindplays.pages.dev/hook-pin-jam.html)
- [ICE CREAM INC](https://themindplay.pages.dev/ice-cream-inc.html)
- [DOLPHIN COUPLE UNDERWATER DRESS UP](https://themindplay.pages.dev/dolphin-couple-underwater-dress-up.html)
- [CATEGORY CRASH32](https://themindplays.pages.dev/category-crash32.html)
- [ZOMBIE ROAD](https://themindplays.pages.dev/zombie-road.html)
- [OBBY DUMB OR GENIUS IQ TEST](https://themindplaying.web.app/obby-dumb-or-genius-iq-test.html)
- [HOUSE DEEP CLEAN SIM](https://themindplaying.web.app/house-deep-clean-sim.html)
- [MAHJONG ADVENTURE WORLD QUEST](https://themindplay.pages.dev/mahjong-adventure-world-quest.html)
- [HALLOWEEN CHALLENGE](https://themindplaying.web.app/halloween-challenge.html)
- [100 DOORS CHALLENGE](https://themindplaying.web.app/100-doors-challenge.html)
- [BELOTE 3IN1](https://themindplaying.web.app/belote-3in1.html)
- [MINE JUMP](https://themindplay.pages.dev/mine-jump.html)
- [KICK LUCKY BOXES ONLINE](https://themindplaying.web.app/kick-lucky-boxes-online.html)
- [CATEGORY TOP DOWN251](https://skillplay.github.io/category-top-down251.html)
- [MONSTERELLA FANTASY MAKEUP](https://themindplay.pages.dev/monsterella-fantasy-makeup.html)
- [GIANT RUN 3D](https://themindplays.pages.dev/giant-run-3d.html)
- [CUT THE GRASS 3D](https://themindplay.pages.dev/cut-the-grass-3d.html)
- [MERGE TOWER HERO](https://themindplay.pages.dev/merge-tower-hero.html)
- [WORLD CUP 2026 SOCCER GAME](https://themindplays.pages.dev/world-cup-2026-soccer-game.html)
- [PAINT IT](https://themindplaying.web.app/paint-it.html)
- [GRUNGE CHIC ALT FASHION](https://skillplay.github.io/grunge-chic-alt-fashion.html)
- [CATEGORY CASUAL 16](https://themindplays.pages.dev/category-casual-16.html)
- [MONSTER SLAYER MERGE SURVIVE](https://themindplay.pages.dev/monster-slayer-merge-survive.html)
- [CATEGORY STICKMAN175](https://skillplay.github.io/category-stickman175.html)
- [HOSPITAL GAME HAPPY CLINIC](https://themindplay.pages.dev/hospital-game-happy-clinic.html)
- [TILE HEXA SORT](https://themindplaying.web.app/tile-hexa-sort.html)
- [CATEGORY CARTOON76](https://themindplays.pages.dev/category-cartoon76.html)
- [SWEET MERGE](https://skillplay.github.io/sweet-merge.html)
- [HERO RAGDOLL FIGHTING](https://themindplaying.web.app/hero-ragdoll-fighting.html)
- [CUBE DROP PUZZLE](https://themindplaying.web.app/cube-drop-puzzle.html)
- [ULTRA PIXEL SURVIVE 2](https://themindplaying.web.app/ultra-pixel-survive-2.html)
- [GARDEN BLOCK PUZZLE](https://themindplaying.web.app/garden-block-puzzle.html)
- [CATEGORY MATCH 3](https://skillplay.github.io/category-match-3.html)
- [CATEGORY DRAWING34](https://themindplays.pages.dev/category-drawing34.html)
- [LINK FLOW](https://themindplays.pages.dev/link-flow.html)
- [MR RACER CAR RACING](https://themindplay.pages.dev/mr-racer-car-racing.html)
- [POPPING CANDIES](https://themindplaying.web.app/popping-candies.html)
- [THE SURVEY](https://themindplays.pages.dev/the-survey.html)
- [PERFECT CAKE MAKER](https://themindplay.pages.dev/perfect-cake-maker.html)
- [ANIME DRESS UP DOLL DRESS UP](https://themindplaying.web.app/anime-dress-up-doll-dress-up.html)
- [CATEGORY CASUAL 4](https://themindplays.pages.dev/category-casual-4.html)
- [CATEGORY DRIFTING116](https://themindplays.pages.dev/category-drifting116.html)
- [CATEGORY MATCH 3117](https://themindplays.pages.dev/category-match-3117.html)
- [CATEGORY CASUAL 15](https://themindplays.pages.dev/category-casual-15.html)
- [GRILL IT ALL](https://themindplays.pages.dev/grill-it-all.html)
- [EMOJI CHALLENGE](https://themindplaying.web.app/emoji-challenge.html)
- [CUPIDS STORY LOVE ARCHER BOW](https://themindplays.pages.dev/cupids-story-love-archer-bow.html)
- [CATEGORY COOKING46](https://themindplays.pages.dev/category-cooking46.html)
- [CRAZY AXE](https://themindplays.pages.dev/crazy-axe.html)
- [ITALIAN BRAINROT SURVIVE PARKOUR](https://themindplays.pages.dev/italian-brainrot-survive-parkour.html)
- [CUT THE GRASS 3D](https://themindplays.pages.dev/cut-the-grass-3d.html)
- [INDEX37](https://themindplays.pages.dev/index37.html)
- [GRANDMAS LAST STAND](https://themindplay.pages.dev/grandmas-last-stand.html)
- [MINEBLOCKS 3D MAZE](https://themindplay.pages.dev/mineblocks-3d-maze.html)
- [ZOMBIE TERMINATOR](https://themindplaying.web.app/zombie-terminator.html)
- [MAHJONG ADVENTURE WORLD QUEST](https://skillplay.github.io/mahjong-adventure-world-quest.html)
- [CAR VS ZOMBIES](https://themindplays.pages.dev/car-vs-zombies.html)
- [CATEGORY MATCH 3117](https://skillplay.github.io/category-match-3117.html)
- [CATEGORY ART](https://themindplays.pages.dev/category-art.html)
- [CITYMIX SOLITAIRE](https://themindplays.pages.dev/citymix-solitaire.html)
- [STICKMAN WARRIOR WAY](https://themindplaying.web.app/stickman-warrior-way.html)
- [HIDDEN OBJECT ADVENTURE](https://themindplays.pages.dev/hidden-object-adventure.html)
- [CATEGORY SHOOTER](https://skillplay.github.io/category-shooter.html)
- [CATEGORY CONTROLLER 2](https://themindplays.pages.dev/category-controller-2.html)
- [CATEGORY FLASH 3](https://themindplays.pages.dev/category-flash-3.html)
- [SWEET MERGE](https://themindplaying.web.app/sweet-merge.html)
- [PET TILE MASTER](https://themindplaying.web.app/pet-tile-master.html)
- [CATEGORY MATCH 3](https://themindplays.pages.dev/category-match-3.html)
- [CATEGORY CUTE](https://themindplays.pages.dev/category-cute.html)
- [COOKING WORLD REBORN](https://themindplay.pages.dev/cooking-world-reborn.html)
- [FEED ME MONSTERS IDLE BATTLE](https://themindplay.pages.dev/feed-me-monsters-idle-battle.html)
- [BADLANDS HERO](https://themindplay.pages.dev/badlands-hero.html)
- [MY DOGY VIRTUAL PET](https://themindplay.pages.dev/my-dogy-virtual-pet.html)
- [MOTO ATTACK BIKE RACING](https://themindplay.pages.dev/moto-attack-bike-racing.html)
- [BRICK BREAKER CHIPI CHIPI CHAPA CHAPA CAT](https://skillplay.github.io/brick-breaker-chipi-chipi-chapa-chapa-cat.html)
- [SPACE BLAST](https://themindplay.pages.dev/space-blast.html)
- [HIDE AND LUIG](https://themindplays.pages.dev/hide-and-luig.html)
- [TRAFFIC RACING](https://themindplaying.web.app/traffic-racing.html)
- [JUICE MERGE](https://themindplays.pages.dev/juice-merge.html)
- [SUPER SNIPER MISSIONS](https://themindplay.pages.dev/super-sniper-missions.html)
- [HOTGEAR](https://themindplays.pages.dev/hotgear.html)
- [CATEGORY RESTAURANT64](https://skillplay.github.io/category-restaurant64.html)
- [PET DOCTOR BUSINESS TYCOON PET CARE GAME](https://iskillquest.pages.dev/pet-doctor-business-tycoon-pet-care-game.html)
- [CATEGORY RACING DRIVING](https://skillplay.github.io/category-racing-driving.html)
- [FLOW BLOCK](https://theskillquest.pages.dev/flow-block.html)
- [BUBBLE TROUBLE 2 REBUBBLED](https://theskillquest.pages.dev/bubble-trouble-2-rebubbled.html)
- [CHECKERS](https://themindplay.pages.dev/checkers.html)
- [ESCAPE FROM TUNG TUNG SAHUR](https://theskillquest.pages.dev/escape-from-tung-tung-sahur.html)
- [DEAD ZONE MECH OPS](https://themindplays.pages.dev/dead-zone-mech-ops.html)
- [INDEX11](https://iskillquest.pages.dev/index11.html)
- [CATEGORY PUZZLE 7](https://iskillquest.pages.dev/category-puzzle-7.html)
- [CATEGORY CONTROLLER](https://iskillquest.pages.dev/category-controller.html)
- [FALLING ART RAGDOLL SIMULATOR](https://themindplay.pages.dev/falling-art-ragdoll-simulator.html)
- [SUPERMARKET SHOPPING FOR KIDS](https://theskillquest.pages.dev/supermarket-shopping-for-kids.html)
- [CATEGORY DRESS UP 3](https://iskillquest.pages.dev/category-dress-up-3.html)
- [CATEGORY FIGHTING](https://iskillquest.pages.dev/category-fighting.html)
- [SNAKE IO](https://theskillquest.pages.dev/snake-io.html)
- [FUNNY BALLS 2048](https://themindplays.pages.dev/funny-balls-2048.html)
- [CATEGORY UNBLOCKED WEBSITES](https://themindplay.pages.dev/category-unblocked-websites.html)
- [CATEGORY LOVE12](https://themindplay.pages.dev/category-love12.html)
- [CATEGORY PHYSICS371](https://themindplay.pages.dev/category-physics371.html)
- [CATEGORY QUIZ40](https://skillplay.github.io/category-quiz40.html)
- [CATEGORY MAKEUP](https://themindplay.github.io/category-makeup.html)
- [BLOCK PARKOUR TRIALS](https://themindplaying.web.app/block-parkour-trials.html)
- [CUTE ANIMAL WORLD](https://themindplaying.web.app/cute-animal-world.html)
- [PET CONNECT MATCH](https://iskillquest.pages.dev/pet-connect-match.html)
