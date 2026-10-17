# nanoMIDIPlayer-extended

<div align="center">

<img width="804" height="249" alt="nanoMIDIPlayer Banner" src="https://github.com/user-attachments/assets/63d98de7-416e-493c-876b-f76d1ee8599b" />

**A lightweight, high-performance MIDI player and macro engine with native Wayland support, kernel-level global hotkeys, real-time timeline scrubbing, and direct MIDI hardware output.**

[![Latest Release](https://img.shields.io/github/v/release/derion-code/nanoMIDIPlayer-extended?style=for-the-badge&color=blue)](https://github.com/derion-code/nanoMIDIPlayer-extended/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/derion-code/nanoMIDIPlayer-extended/total?style=for-the-badge&color=brightgreen)](https://github.com/derion-code/nanoMIDIPlayer-extended/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge)](https://www.gnu.org/licenses/gpl-3.0)

[**Download Releases**](https://github.com/derion-code/nanoMIDIPlayer-extended/releases) • [**Linux Wayland Setup**](#-linux-setup-wayland--x11) • [**CLI Usage**](#-cli-arguments) • [**Credits & Upstream**](#-credits--license)

</div>

---

> [!NOTE]
> **nanoMIDIPlayer-extended** is an active, enhanced fork of [NotHammer043/nanoMIDIPlayer](https://github.com/NotHammer043/nanoMIDIPlayer). It resolves longstanding Linux/Wayland compatibility limitations through native kernel `uinput` virtual device injection and `evdev` global hotkeys, eliminates playback deadlocks, introduces timeline scrubbing, and integrates a modern theme-aware file browser.

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Screenshots](#-screenshots)
- [Key Enhancements in this Fork](#-key-enhancements-in-this-fork)
- [Features](#-features)
- [Linux Setup (Wayland & X11)](#-linux-setup-wayland--x11)
- [Installation & Quick Start](#-installation--quick-start)
- [CLI Arguments](#-cli-arguments)
- [Hotkeys & Keymaps](#-hotkeys--keymaps)
- [Building from Source](#-building-from-source)
- [Credits & License](#-credits--license)

---

## 🌟 Overview

**nanoMIDIPlayer-extended** is a versatile MIDI playback tool and macro utility. It reads standard `.mid` and `.midi` files and accurately converts musical notes into simulated QWERTY keystrokes for virtual piano games (such as Roblox, Garry's Mod, Rust, Web-based pianos) or sends raw MIDI data directly to physical synthesizers and virtual MIDI loopback devices.

Unlike standard macro players that break under modern Linux environments, **nanoMIDIPlayer-extended** features a dedicated Linux architecture that works out-of-the-box across **Wayland** compositors (GNOME, KDE Plasma, Hyprland, Sway) and X11 without window focus constraints.

---

## 📸 Screenshots

<!-- Placeholders for GitHub image drag-and-drop -->

| MIDI Player (Timeline & Controls) | Drums Macro Tab |
|:---:|:---:|
| <img src="assets/screenshot_main.png" width="450" alt="Main Player UI"> | <img src="assets/screenshot_drums.png" width="450" alt="Drums Macro UI"> |

| Live MIDI to QWERTY Visualizer | Modern Custom File Dialog |
|:---:|:---:|
| <img src="assets/screenshot_midi_to_qwerty.png" width="450" alt="MIDI to QWERTY UI"> | <img src="assets/screenshot_file_dialog.png" width="450" alt="File Dialog UI"> |

<div align="center">

| Settings |
|:---:|
| <img src="assets/screenshot_settings.png" width="450" alt="Settings UI"> |

</div>

---

## ✨ Key Enhancements in this Fork

### 🐧 Native Wayland & `uinput` Keystroke Simulation
Under Wayland, traditional X11 synthetic key injectors (`pynput`, `xdotool`, `keyboard`) fail or are blocked by compositor security policies. This fork introduces a dedicated `uinput` backend that creates a virtual kernel input device (`/dev/uinput`). Keystrokes are recognized system-wide across all Wayland desktop environments and full-screen games.

### 🎯 Kernel-Level `evdev` Global Hotkeys
Global hotkeys often fail when a game or another application captures focus. This fork adds an `evdev` event listener reading raw device events from `/dev/input/event*`:
- Hotkeys trigger reliably even when the player is minimized or unfocused.
- Dynamic hotplugging automatically detects connected and disconnected keyboards.
- Feedback loops from the virtual keyboard are filtered out safely.
- Graceful fallback to `pynput` on platforms or configurations without `evdev`.

### ⏱️ Interactive Timeline Scrubbing & Seeking
Both the **MIDI Player** and **Drums Macro** tabs feature interactive timeline sliders:
- Drag or click anywhere on the progress bar to seek instantly to any position.
- Uses binary search indexing (`bisect`) for instantaneous zero-latency seeks.
- Automatically cleans up and releases held keys during seek operations to prevent stuck notes.

### 🛡️ Deadlock Prevention & Thread-Safety Hardening
- **Self-Join Deadlock Fix**: Prevents playback worker threads from freezing when hotkeys trigger re-entrant stop commands.
- **Immediate State Signaling**: Flags `stopEvent` and `closeThread` instantly so background loops exit without lag.
- **Safe UI Dispatch**: Background threads dispatch GUI modifications and stop sequences onto Tkinter's main thread using `app.after(0, ...)`.
- **Resource Recovery**: Critical playback loops are guarded with robust `try/finally` blocks ensuring keys and timers are released even if a file is malformed.

### 📂 Integrated Modern File Browser
Replaced native OS file dialogs with an in-app CustomTkinter file picker:
- Matches the active application theme automatically.
- Real-time search with typing debounce.
- Remembers your last-used MIDI folder across sessions.
- Breadcrumb navigation, quick-access drives, and double-click folder navigation.

### 🎼 Extended Pitch, Key Transpose & Finger Limiting
- **Pitch Octave Shifting**: Shift playback by octaves (`Lowest` -2 oct, `Low` -1 oct, `Middle` default, `High` +1 oct, `Highest` +2 oct).
- **Semitone Transposition**: Transpose playback across all 12 musical keys (`C` through `B`).
- **Polyphony Limiter**: Restrict simultaneous active keys from 1 to 10 fingers, or choose unlimited (`∞`).

---

## 🚀 Features

- **Dual Output Modes**:
  - **Macro Mode**: Simulates keystrokes for virtual pianos (61-key and 88-key layouts).
  - **MIDI Output Device**: Emits raw MIDI signals directly to hardware synthesizers or virtual loopback devices (via `python-rtmidi`).
- **Live MIDI Input to QWERTY**:
  - Connect a USB MIDI keyboard or controller to play notes in real time.
  - Interactive **88-key graphical piano visualizer** renders active keys live.
- **Drums Macro Player**: Dedicated drum track engine with custom drum piece mappings (Kick, Snare, Toms, Hi-Hats, Crashes, Ride, Cowbell).
- **Online MIDI Hub**: Integrated in-app browser powered by the [nanoMIDI.net](https://nanomidi.net) library with search and sorting (Newest, Oldest, Downloads, Views).
- **Expressive Keystrokes**:
  - **Velocity Simulation**: Simulates key hit velocity using `ALT` key combinations.
  - **Sustain Pedal**: Emulates damper pedal with `Spacebar` and adjustable cutoff threshold.
  - **No Doubles**: Anti-ghosting algorithm to prevent accidental double-strikes.
- **Humanization (Random Fail)**: Simulates human imperfection with configurable sliders for speed drift and transposition error rates.
- **Themes & UI Customization**:
  - Built-in color themes: Dark, Light, Discord, Oceanic, Forest, Halloween, Red Velvet.
  - Support for custom JSON themes placed in `~/Documents/nanoMIDIPlayer/assets/customThemes/`.
  - Always-on-top window toggle, live console output, and tooltip hints.

---

## 🐧 Linux Setup (Wayland & X11)

> [!IMPORTANT]
> To use `uinput` simulation and `evdev` global hotkeys under Linux, your user account needs permission to access `/dev/uinput` and `/dev/input/event*`. Without these permissions, the application falls back to `pynput` (which cannot send keystrokes to Wayland windows or capture global hotkeys without focus).

Follow these three steps to configure your system:

### 1. Load the `uinput` Kernel Module
Ensure the kernel module is loaded:
```bash
sudo modprobe uinput
```
To load it automatically on every boot:
```bash
echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf
```

### 2. Install the udev Rule
Create a udev rule to grant the `input` group write access to `/dev/uinput`:
```bash
echo 'KERNEL=="uinput", MODE="0660", GROUP="input", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/99-uinput.rules
```
Reload and trigger the updated rules:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 3. Add Your User to the `input` Group
Add your current user to the `input` group:
```bash
sudo usermod -aG input $USER
```

> [!WARNING]
> You **MUST log out and log back in** (or restart your session) for the new group membership to take effect. You can verify your active groups by running `groups` in a terminal.

---

## 📥 Installation & Quick Start

### Option A: Pre-built Binaries (Recommended)
Download the latest pre-compiled binary for your operating system from the [**Releases Page**](https://github.com/derion-code/nanoMIDIPlayer-extended/releases):
- **Windows**: `.zip` (extract and run `.exe`)
- **macOS**: `.dmg` (mount and drag to Applications)
- **Linux (Ubuntu/Debian/Mint)**: `.deb` (install via `apt` or double-click)
- **Linux (Arch)**: `.pkg.tar.zst` (install via `pacman -U`)
- **Linux (Universal)**: `.AppImage` (`chmod +x` and run) or `.tar.gz`

### Option B: Running from Source

#### Prerequisites
- Python 3.10 or higher
- Git

#### 1. Clone the Repository
```bash
git clone https://github.com/derion-code/nanoMIDIPlayer-extended.git
cd nanoMIDIPlayer-extended
```

#### 2. Create and Activate a Virtual Environment
```bash
# On Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# On Windows (Command Prompt):
python -m venv venv
call venv\Scripts\activate.bat

# On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Launch Application
```bash
# On Linux (recommended with uinput for Wayland):
python main.py --input-module uinput

# On Windows / macOS:
python main.py
```

---

## 💻 CLI Arguments

`main.py` accepts command-line flags to customize execution:

| Argument | Options | Description |
| :--- | :--- | :--- |
| `--input-module` | `uinput`, `pynput`, `keyboard` | Sets the preferred keystroke simulation driver across MIDI Player, Drums Macro, and MIDI to QWERTY tabs. |
| `--debug` | *(None)* | Spawns an attached debug console window with detailed runtime logging. |
| `-h`, `--help` | *(None)* | Displays help information and exits. |

### CLI Examples

* **Launch with Wayland `uinput` backend:**
  ```bash
  python main.py --input-module uinput
  ```
* **Launch with debug logging enabled:**
  ```bash
  python main.py --debug
  ```
* **Combine options:**
  ```bash
  python main.py --input-module uinput --debug
  ```

---

## ⌨️ Hotkeys & Keymaps

### Default Global Hotkeys

All hotkeys are customizable in the **Settings** tab:

| Function | Default Key | Description |
| :--- | :---: | :--- |
| **Play** | `F1` | Starts or restarts playback of the loaded MIDI file. |
| **Pause** | `F2` | Pauses or resumes playback (releases held keys if configured). |
| **Stop** | `F3` | Stops playback immediately and resets timeline to start. |
| **Speed Up** | `F4` | Increases playback speed by the configured step size. |
| **Slow Down** | `F5` | Decreases playback speed by the configured step size. |

### Virtual Piano Keymapping
- **61-Key Mode**: Standard octave keys mapped across digits `1`-`0`, lowercase `q`-`p`, `a`-`l`, `z`-`m`, with black keys triggered via `Shift` modifier (or symbol keys like `!`, `@`, `$`, `%`, etc.).
- **88-Key Mode**: Extends range to the lowest and highest piano octaves using `Ctrl` modifier keys.
- **Velocity Mapping**: Dynamically triggers note loudness levels via `Alt` key combinations in supported virtual pianos.
- **Sustain**: Transmits `Spacebar` while sustain control events exceed the configured cutoff threshold (default: `63`).

---

## 🛠️ Building from Source

Building from source is no longer required for end-users. Official binaries are automatically built and released via GitHub Actions for all platforms (Windows, macOS, Linux, Arch) whenever a new tag is pushed. Developers can still run the app locally using Python (see Option B above).

---

## 📜 Credits & License

### Original Upstream Project
**nanoMIDIPlayer-extended** is an extended fork of **[nanoMIDIPlayer](https://github.com/NotHammer043/nanoMIDIPlayer)**, originally developed and maintained by **[NotHammer043](https://github.com/NotHammer043)**.

- **Upstream Repository**: [NotHammer043/nanoMIDIPlayer](https://github.com/NotHammer043/nanoMIDIPlayer)
- **Official Website & MIDI Hub**: [nanoMIDI.net](https://nanomidi.net)
- **Support the Original Author**: Consider supporting upstream development via **BuyMeACoffee**:

<div align="center">

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/nanoMIDI)

</div>

Special thanks to NotHammer043, [fearsomeorc1406](https://discord.com/users/1292364099581116416) (creator of Drums Macro), and the upstream nanoMIDI community for the foundation, themes, and community support.

### License
This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. See the [LICENSE](file:///home/derion/projects/nanoMIDIPlayer-extended/LICENSE) file for complete details.
