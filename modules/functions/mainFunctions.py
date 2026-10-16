import customtkinter as ctk
import tkinter as tk
import tkinter.messagebox
import textwrap
import threading
import time
import queue
import keyboard
import json
import mido
import sys
import os
import logging
import platform

import select
import atexit

try:
    import evdev
    from evdev import ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    evdev = None
    ecodes = None

try:
    from pynput import keyboard as pynputKeyboard
except Exception:
    pynputKeyboard = None
from modules import configuration
from ui import customTheme
from ui.midiPlayer import MidiPlayerTab
from ui.drumsMacro import DrumsMacroTab
from ui.midiToQWERTY import MidiToQwertyTab
from ui.settings import SettingsTab

osName = platform.system()
appInstance = None
logQueue = queue.Queue(maxsize=1)
logWorkedStarted = False
logCooldown = 0.05
hotkeyButtonActive = None
logger = logging.getLogger(__name__)

listener = None
activeHotkeys = {}
ignoreKeyPress = False
specialKeyMap = {
    "SPACE": "SPACE",
    "ESC": "ESC",
    "ESCAPE": "ESC",
    "ENTER": "ENTER",
    "RETURN": "ENTER",
    "TAB": "TAB",
    "BACKSPACE": "BACKSPACE",
    "DELETE": "DELETE",
    "INSERT": "INSERT",
    "HOME": "HOME",
    "END": "END",
    "PAGE_UP": "PAGE_UP",
    "PAGE_DOWN": "PAGE_DOWN",

    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "UP": "UP",
    "DOWN": "DOWN",

    "SHIFT_L": "LEFT SHIFT",
    "SHIFT_R": "RIGHT SHIFT",
    "SHIFT": "LEFT SHIFT",
    "CTRL_L": "LEFT CTRL",
    "CTRL_R": "RIGHT CTRL",
    "CONTROL": "LEFT CTRL",
    "ALT_L": "LEFT ALT",
    "ALT_R": "RIGHT ALT",
    "ALT": "LEFT ALT",
    "CMD": "CMD",
    "CMD_R": "CMD",

    "F1": "F1", "F2": "F2", "F3": "F3", "F4": "F4", "F5": "F5",
    "F6": "F6", "F7": "F7", "F8": "F8", "F9": "F9", "F10": "F10",
    "F11": "F11", "F12": "F12", "F13": "F13", "F14": "F14", "F15": "F15",

    "NUMPAD0": "NUMPAD0", "NUMPAD1": "NUMPAD1", "NUMPAD2": "NUMPAD2",
    "NUMPAD3": "NUMPAD3", "NUMPAD4": "NUMPAD4", "NUMPAD5": "NUMPAD5",
    "NUMPAD6": "NUMPAD6", "NUMPAD7": "NUMPAD7", "NUMPAD8": "NUMPAD8",
    "NUMPAD9": "NUMPAD9",
    "ADD": "NUMPAD+",
    "SUBTRACT": "NUMPAD-",
    "MULTIPLY": "NUMPAD*",
    "DIVIDE": "NUMPAD/",
    "DECIMAL": "NUMPAD.",

    "CAPS_LOCK": "CAPSLOCK",
    "CAPSLOCK": "CAPSLOCK",
    "NUM_LOCK": "NUMLOCK",
    "NUMLOCK": "NUMLOCK",
    "SCROLL_LOCK": "SCROLLLOCK",
    "SCROLLLOCK": "SCROLLLOCK"
}

EVDEV_KEY_MAP = {}
if EVDEV_AVAILABLE:
    for i in range(1, 16):
        code = getattr(ecodes, f"KEY_F{i}", None)
        if code is not None:
            EVDEV_KEY_MAP[code] = f"F{i}"
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        code = getattr(ecodes, f"KEY_{c}", None)
        if code is not None:
            EVDEV_KEY_MAP[code] = c
    for d in "0123456789":
        code = getattr(ecodes, f"KEY_{d}", None)
        if code is not None:
            EVDEV_KEY_MAP[code] = d
    for i in range(10):
        code = getattr(ecodes, f"KEY_KP{i}", None)
        if code is not None:
            EVDEV_KEY_MAP[code] = f"NUMPAD{i}"
    EVDEV_KEY_MAP.update({
        ecodes.KEY_SPACE: "SPACE",
        ecodes.KEY_ESC: "ESC",
        ecodes.KEY_ENTER: "ENTER",
        ecodes.KEY_TAB: "TAB",
        ecodes.KEY_BACKSPACE: "BACKSPACE",
        ecodes.KEY_DELETE: "DELETE",
        ecodes.KEY_INSERT: "INSERT",
        ecodes.KEY_HOME: "HOME",
        ecodes.KEY_END: "END",
        ecodes.KEY_PAGEUP: "PAGE_UP",
        ecodes.KEY_PAGEDOWN: "PAGE_DOWN",
        ecodes.KEY_UP: "UP",
        ecodes.KEY_DOWN: "DOWN",
        ecodes.KEY_LEFT: "LEFT",
        ecodes.KEY_RIGHT: "RIGHT",
        ecodes.KEY_LEFTSHIFT: "LEFT SHIFT",
        ecodes.KEY_RIGHTSHIFT: "RIGHT SHIFT",
        ecodes.KEY_LEFTCTRL: "LEFT CTRL",
        ecodes.KEY_RIGHTCTRL: "RIGHT CTRL",
        ecodes.KEY_LEFTALT: "LEFT ALT",
        ecodes.KEY_RIGHTALT: "RIGHT ALT",
        ecodes.KEY_LEFTMETA: "CMD",
        ecodes.KEY_RIGHTMETA: "CMD",
        ecodes.KEY_CAPSLOCK: "CAPSLOCK",
        ecodes.KEY_NUMLOCK: "NUMLOCK",
        ecodes.KEY_SCROLLLOCK: "SCROLLLOCK",
        ecodes.KEY_MINUS: "-",
        ecodes.KEY_EQUAL: "=",
        ecodes.KEY_LEFTBRACE: "[",
        ecodes.KEY_RIGHTBRACE: "]",
        ecodes.KEY_SEMICOLON: ";",
        ecodes.KEY_APOSTROPHE: "'",
        ecodes.KEY_GRAVE: "`",
        ecodes.KEY_BACKSLASH: "\\",
        ecodes.KEY_COMMA: ",",
        ecodes.KEY_DOT: ".",
        ecodes.KEY_SLASH: "/",
        ecodes.KEY_KPPLUS: "NUMPAD+",
        ecodes.KEY_KPMINUS: "NUMPAD-",
        ecodes.KEY_KPASTERISK: "NUMPAD*",
        ecodes.KEY_KPSLASH: "NUMPAD/",
        ecodes.KEY_KPDOT: "NUMPAD.",
        ecodes.KEY_KPENTER: "ENTER",
    })

_evdevThread = None
_evdevStopEvent = None


def _dispatchHotkey(callback):
    app = getApp()
    if app and hasattr(app, "after"):
        try:
            app.after(0, callback)
            return
        except Exception as e:
            logger.debug(f"_dispatchHotkey app.after error: {e}")
    try:
        callback()
    except Exception as e:
        logger.debug(f"_dispatchHotkey direct call error: {e}")


def _isKeyboardDevice(dev):
    try:
        if not dev or not dev.name:
            return False
        if "nanomidiplayer" in dev.name.lower():
            return False
        caps = dev.capabilities()
        if ecodes.EV_KEY not in caps:
            return False
        keys = caps[ecodes.EV_KEY]
        return ecodes.KEY_A in keys and ecodes.KEY_SPACE in keys
    except Exception:
        return False


def _getEvdevKeyboards():
    devices = []
    if not EVDEV_AVAILABLE:
        return devices
    try:
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                if _isKeyboardDevice(dev):
                    devices.append(dev)
                else:
                    dev.close()
            except Exception:
                pass
    except Exception:
        pass
    return devices


def _evdevListenerWorker():
    global _evdevStopEvent
    devMap = {}
    lastScanTime = 0.0

    logger.debug("evdevListenerWorker started")
    while _evdevStopEvent is not None and not _evdevStopEvent.is_set():
        now = time.time()
        if now - lastScanTime >= 3.0 or not devMap:
            lastScanTime = now
            try:
                currentPaths = {d.path for d in devMap.values()}
                for path in evdev.list_devices():
                    if path not in currentPaths:
                        try:
                            dev = evdev.InputDevice(path)
                            if _isKeyboardDevice(dev):
                                devMap[dev.fileno()] = dev
                                logger.debug(f"evdev listener attached to {dev.name} ({dev.path})")
                            else:
                                dev.close()
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"evdev device rescan error: {e}")

        if not devMap:
            time.sleep(0.5)
            continue

        try:
            r, _, _ = select.select(list(devMap.keys()), [], [], 0.5)
        except (ValueError, OSError):
            for fd, dev in list(devMap.items()):
                try:
                    select.select([fd], [], [], 0)
                except Exception:
                    try:
                        dev.close()
                    except Exception:
                        pass
                    devMap.pop(fd, None)
            continue

        for fd in r:
            dev = devMap.get(fd)
            if not dev:
                continue
            try:
                for event in dev.read():
                    if event.type == ecodes.EV_KEY and event.value == 1:
                        if ignoreKeyPress:
                            continue
                        keyName = EVDEV_KEY_MAP.get(event.code)
                        if keyName and keyName in activeHotkeys:
                            _dispatchHotkey(activeHotkeys[keyName])
            except (OSError, IOError):
                logger.debug(f"evdev device disconnected: {getattr(dev, 'path', fd)}")
                try:
                    dev.close()
                except Exception:
                    pass
                devMap.pop(fd, None)

    for dev in devMap.values():
        try:
            dev.close()
        except Exception:
            pass
    devMap.clear()
    logger.debug("evdevListenerWorker stopped")


def stopGlobalListener():
    global listener, _evdevThread, _evdevStopEvent
    if _evdevStopEvent is not None:
        _evdevStopEvent.set()
    if _evdevThread is not None and _evdevThread.is_alive():
        _evdevThread.join(timeout=1.0)
    _evdevThread = None
    _evdevStopEvent = None

    if listener is not None:
        try:
            listener.stop()
        except Exception:
            pass
        listener = None


atexit.register(stopGlobalListener)


def startGlobalListener():
    global listener, _evdevThread, _evdevStopEvent
    if (_evdevThread is not None and _evdevThread.is_alive()) or (listener is not None and getattr(listener, "is_alive", lambda: False)()):
        return

    if osName == "Linux" and EVDEV_AVAILABLE:
        try:
            testDevs = _getEvdevKeyboards()
            if testDevs:
                for d in testDevs:
                    try:
                        d.close()
                    except Exception:
                        pass
                _evdevStopEvent = threading.Event()
                _evdevThread = threading.Thread(target=_evdevListenerWorker, daemon=True, name="evdevGlobalHotkeyListener")
                _evdevThread.start()
                logger.info("evdev-based global hotkey listener started successfully.")
                return
            else:
                logger.info(
                    "evdev found no accessible keyboard devices in /dev/input/event*. "
                    "Falling back to pynput. For global hotkeys under Wayland without window focus, "
                    "add your user to the 'input' group: sudo usermod -aG input $USER"
                )
        except Exception as e:
            logger.info(
                f"evdev keyboard initialization failed ({e}). Falling back to pynput. "
                "For global hotkeys under Wayland without window focus, add your user to the 'input' group: "
                "sudo usermod -aG input $USER"
            )

    if pynputKeyboard is None:
        logger.warning("pynput is not available. Global hotkeys disabled.")
        return

    def onPress(key):
        if ignoreKeyPress:
            return
        try:
            keyStr = None
            if hasattr(key, "char") and key.char:
                keyStr = key.char.upper()
            else:
                rawName = str(key).replace("Key.", "").replace(" ", "_").upper()
                if rawName in ("CTRL", "CONTROL"):
                    rawName = "CTRL_L"
                elif rawName == "SHIFT":
                    rawName = "SHIFT_L"
                elif rawName == "ALT":
                    rawName = "ALT_L"

                keyStr = specialKeyMap.get(rawName, rawName)

            if keyStr in activeHotkeys:
                _dispatchHotkey(activeHotkeys[keyStr])

        except Exception as e:
            logger.debug(f"onPress error: {e}")

    try:
        listener = pynputKeyboard.Listener(on_press=onPress)
        listener.daemon = True
        listener.start()
        logger.debug("pynput global hotkey listener started.")
    except Exception as e:
        logger.warning(f"Failed to start pynput global hotkey listener: {e}")

class ScrollableFrame(ctk.CTkScrollableFrame):
    def check_if_master_is_canvas(self, widget):
        if isinstance(widget, tk.Widget):
            return super().check_if_master_is_canvas(widget)
        return False

def registerApp(app):
    global appInstance
    appInstance = app

def getApp():
    return appInstance

def resourcePath(relativePath):
    if hasattr(sys, '_MEIPASS'):
        basePath = sys._MEIPASS
    else:
        basePath = os.path.abspath(".")
    return os.path.join(basePath, relativePath)

def logWorker():
    logger.debug("logWorker started")
    while True:
        try:
            msg = logQueue.get()
        except Exception as e:
            logger.error(f"logWorker error: {e}")
            continue
        insertConsoleText(msg, False)
        time.sleep(logCooldown)

def log(string):
    global logWorkedStarted
    if configuration.configData['appUI']['console']:
        if not logWorkedStarted:
            logger.debug("starting logWorker thread")
            threading.Thread(target=logWorker, daemon=True).start()
            logWorkedStarted = True
        try:
            if logQueue.full():
                try:
                    logQueue.get_nowait()
                except Exception as e:
                    logger.error(f"logQueue get_nowait error: {e}")
            logQueue.put_nowait(string)
        except Exception as e:
            logger.error(f"logQueue put_nowait error: {e}")

def insertConsoleText(text, ignoreConsoleCheck=False, app=None):
    logger.debug(text)
    app = app or getApp()

    if not (ignoreConsoleCheck or configuration.configData['appUI']['console']):
        return

    currentPage = getattr(app, "currentPage", 0) if app else 0
    if currentPage == 1:
        consoleLocation = DrumsMacroTab.consoleFrame
    elif currentPage == 3:
        consoleLocation = MidiToQwertyTab.consoleFrame
    else:
        consoleLocation = MidiPlayerTab.consoleFrame
    
    if app:
        if currentPage == 1:
            maxMessages = getattr(app, "maxDrumPlayerConsoleLog", 14)
        elif currentPage == 3:
            maxMessages = getattr(app, "maxMidiToQWERTYLog", 13)
        else:
            maxMessages = getattr(app, "maxMidiPlayerConsoleLog", 8)
    else:
        maxMessages = 15

    if app and (not hasattr(app, "logLabels") or app.logLabels is None):
        app.logLabels = []

    wrappedLines = []
    for line in text.split("\n"):
        wrappedLines.extend(
            textwrap.wrap(line, width=27, break_long_words=True, break_on_hyphens=False)
        )
    wrappedText = "\n".join(wrappedLines)

    def createLabel():
        logLabel = tk.Label(
            consoleLocation,
            text=wrappedText,
            fg=customTheme.activeThemeData["Theme"]["MidiPlayer"]["TextColor"],
            bg=customTheme.activeThemeData["Theme"]["MidiPlayer"]["ConsoleBackground"],
            font=customTheme.globalFont12,
            anchor="w",
            justify="left",
            wraplength=0,
        )
        logLabel.pack(anchor="sw", fill="x")

        if app:
            app.logLabels.append(logLabel)
            if len(app.logLabels) > maxMessages:
                oldLabel = app.logLabels.pop(0)
                try:
                    oldLabel.destroy()
                except Exception as e:
                    logger.error(f"destroy oldLabel error: {e}")

        if len(consoleLocation.winfo_children()) > 20:
            for widget in consoleLocation.winfo_children():
                try:
                    widget.destroy()
                except Exception as e:
                    logger.error(f"destroy widget error: {e}")

        consoleLocation.update_idletasks()

    consoleLocation.after(0, createLabel)

def clearConsole(app=None):
    logger.debug("clearConsole")
    app = app or getApp()
    currentPage = getattr(app, "currentPage", 0) if app else 0

    if currentPage == 1:
        consoleLocation = DrumsMacroTab.consoleFrame
    elif currentPage == 3:
        consoleLocation = MidiToQwertyTab.consoleFrame
    else:
        consoleLocation = MidiPlayerTab.consoleFrame

    for widget in consoleLocation.winfo_children():
        try:
            widget.destroy()
        except Exception as e:
            logger.error(f"clearConsole destroy widget error: {e}")
    if app and hasattr(app, "logLabels"):
        app.logLabels.clear()
    consoleLocation.update_idletasks()

def tabBind(tab):
    logger.info(f"tabBind: {tab}")
    clearConsole()
    from modules.functions import midiPlayerFunctions
    from modules.functions import drumsMacroFunctions
    from modules.functions import midiHubFunctions
    from ui.midiHub import MidiHubTab

    if osName == "Windows":
        if tab == 0:
            drumsMacroFunctions.unbindControls()
            midiPlayerFunctions.bindControls()
            MidiHubTab.searchEntry.unbind("<Return>")
        elif tab == 1:
            threading.Thread(target=insertConsoleText, args=("Note: This will only work if your MIDI file specifically uses a drum instrument.", True)).start()
            midiPlayerFunctions.unbindControls()
            drumsMacroFunctions.bindControls()
            MidiHubTab.searchEntry.unbind("<Return>")
        elif tab == 2:
            midiPlayerFunctions.unbindControls()
            drumsMacroFunctions.unbindControls()
            threading.Thread(target=midiHubFunctions.loadMidiData).start()
            MidiHubTab.searchEntry.bind("<Return>", midiHubFunctions.searchBar)
        else:
            MidiHubTab.searchEntry.unbind("<Return>")
            midiPlayerFunctions.unbindControls()
            drumsMacroFunctions.unbindControls()
    else:
        if tab == 0:
            midiPlayerFunctions.bindControls()
            MidiHubTab.searchEntry.unbind("<Return>")
        elif tab == 1:
            threading.Thread(target=insertConsoleText, args=("Note: This will only work if your MIDI file specifically uses a drum instrument.", True)).start()
            drumsMacroFunctions.bindControls()
            MidiHubTab.searchEntry.unbind("<Return>")
        elif tab == 2:
            midiPlayerFunctions.unbindControls()
            drumsMacroFunctions.unbindControls()
            threading.Thread(target=midiHubFunctions.loadMidiData).start()
            MidiHubTab.searchEntry.bind("<Return>", midiHubFunctions.searchBar)
        else:
            MidiHubTab.searchEntry.unbind("<Return>")
            midiPlayerFunctions.unbindControls()
            drumsMacroFunctions.unbindControls()

def setHotkey(keyType):
    logger.info(f"setHotkey: {keyType}")
    from modules.functions import midiPlayerFunctions
    from modules.functions import drumsMacroFunctions
    global hotkeyButtonActive, hotkeyHook
    hotkeyButtonActive = keyType
    hotkeyHook = None

    buttons = {
        'play': [MidiPlayerTab.playHotkeyButton, DrumsMacroTab.playHotkeyButton, SettingsTab.playHotkeyButton],
        'pause': [MidiPlayerTab.pauseHotkeyButton, DrumsMacroTab.pauseHotkeyButton, SettingsTab.pauseHotkeyButton],
        'stop': [MidiPlayerTab.stopHotkeyButton, DrumsMacroTab.stopHotkeyButton, SettingsTab.stopHotkeyButton],
        'speedup': [MidiPlayerTab.speedUpHotkeyButton, DrumsMacroTab.speedUpHotkeyButton, SettingsTab.speedUpHotkeyButton],
        'slowdown': [MidiPlayerTab.slowHotkeyButton, DrumsMacroTab.slowHotkeyButton, SettingsTab.slowHotkeyButton]
    }

    oldHotkey = configuration.configData["hotkeys"][keyType]
    midiPlayerFunctions.unbindControls()
    drumsMacroFunctions.unbindControls()

    for btnType, btnList in buttons.items():
        for btn in btnList:
            if btnType == keyType:
                btn.configure(text="...")
            else:
                btn.configure(state="disabled")

    def resetButtons():
        for btnList in buttons.values():
            for btn in btnList:
                btn.configure(state="normal")

    def finishHotkey(newHotkey):
        currentHotkeys = {k: v for k, v in configuration.configData["hotkeys"].items() if k != keyType}
        if newHotkey in currentHotkeys.values():
            for btn in buttons[keyType]:
                btn.configure(text=oldHotkey.upper(), state="normal")
            configuration.configData["hotkeys"][keyType] = oldHotkey
            configuration.configData.save()
            conflictAction = [k for k, v in currentHotkeys.items() if v == newHotkey][0]
            tkinter.messagebox.showinfo(title="Keybind Conflict", message=f"This keybind is in use!\n{conflictAction}: {newHotkey}", icon='warning')
        else:
            for btn in buttons[keyType]:
                btn.configure(text=newHotkey.upper(), state="normal")
            configuration.configData["hotkeys"][keyType] = newHotkey
            configuration.configData.save()

        global hotkeyButtonActive, hotkeyHook
        if osName == "Windows" and hotkeyHook:
            keyboard.unhook(hotkeyHook)
        hotkeyButtonActive = None
        resetButtons()

        app = getApp()
        if app.currentPage == 0:
            midiPlayerFunctions.bindControls()
        elif app.currentPage == 1:
            drumsMacroFunctions.bindControls()

    def onKeyPressWindows(event):
        if hotkeyButtonActive:
            finishHotkey(event.name)

    def onKeyPressShared(keyName):
        if hotkeyButtonActive:
            finishHotkey(keyName.lower())

    if osName == "Windows":
        hotkeyHook = keyboard.on_press(onKeyPressWindows)
    else:
        activeHotkeys.clear()
        supportedKeys = [
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13", "F14", "F15",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",

            "-", "=", "BACKSPACE", "`", "TAB", "[", "]", "ENTER", ";", "'", "\\", ",", ".", "/", 
            "LEFT SHIFT", "RIGHT SHIFT", "LEFT CTRL", "RIGHT CTRL", "CMD", 
            "LEFT ALT", "RIGHT ALT", "INSERT", "HOME", "PAGE_UP", "DELETE", "END", "PAGE_DOWN",

            "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P",
            "A", "S", "D", "F", "G", "H", "J", "K", "L",
            "Z", "X", "C", "V", "B", "N", "M",

            "NUMPAD1", "NUMPAD2", "NUMPAD3", "NUMPAD4", "NUMPAD5", 
            "NUMPAD6", "NUMPAD7", "NUMPAD8", "NUMPAD9",
            "NUMPAD*", "NUMPAD/", "NUMPAD.", "NUMPAD+", "NUMPAD-",

            "LEFT", "DOWN", "UP", "RIGHT",

            "CAPSLOCK",
            "NUMLOCK",
            "SCROLLLOCK",
        ]

        for key in supportedKeys:
            activeHotkeys[key] = lambda k=key: onKeyPressShared(k)
        startGlobalListener()

def refreshOutputDevices():
    logger.debug("refreshOutputDevices")
    from modules.functions import midiPlayerFunctions
    devices = mido.get_output_names()
    logger.debug(f"output devices: {devices}")
    loopbeDevice = next((device for device in devices if "LoopBe" in device), None)

    if not devices:
        devices = []
        defaultDevice = "No output devices"
        MidiPlayerTab.outputDeviceDropdown.configure(values=[defaultDevice])
        MidiPlayerTab.outputDeviceDropdown.set(defaultDevice)
        MidiPlayerTab.midiToggleSwitch.configure(state="disabled")
        configuration.configData["midiPlayer"]['useMIDIOutput'] = False
        configuration.configData.save()
    else:
        defaultDevice = loopbeDevice if loopbeDevice else devices[0]
        MidiPlayerTab.outputDeviceDropdown.configure(values=devices)
        MidiPlayerTab.outputDeviceDropdown.set(defaultDevice)
        MidiPlayerTab.midiToggleSwitch.configure(state="normal")

    if not configuration.configData["midiPlayer"]['useMIDIOutput']:
        MidiPlayerTab.outputDeviceDropdown.configure(state="disabled")
    elif configuration.configData["midiPlayer"]['useMIDIOutput'] and devices:
        MidiPlayerTab.outputDeviceDropdown.configure(state="normal")

def refreshInputDevices():
    logger.debug("refreshInputDevices")
    devices = mido.get_input_names()
    logger.debug(f"input devices: {devices}")
    loopbeDevice = next((device for device in devices if "LoopBe" in device), None)
    previous = MidiToQwertyTab.inputDeviceDropdown.get() if hasattr(MidiToQwertyTab, "inputDeviceDropdown") else None

    if not devices:
        devices = []
        defaultDevice = "No input devices"
        MidiToQwertyTab.inputDeviceDropdown.configure(values=[defaultDevice], state="disabled")
        MidiToQwertyTab.inputDeviceDropdown.set(defaultDevice)
    else:
        defaultDevice = previous if previous in devices else (loopbeDevice if loopbeDevice else devices[0])
        MidiToQwertyTab.inputDeviceDropdown.configure(values=devices, state="normal")
        MidiToQwertyTab.inputDeviceDropdown.set(defaultDevice)

def playHotkeyCommand():
    logger.debug("playHotkeyCommand")
    setHotkey('play')

def pauseHotkeyCommand():
    logger.debug("pauseHotkeyCommand")
    setHotkey('pause')

def stopHotkeyCommand():
    logger.debug("stopHotkeyCommand")
    setHotkey('stop')

def speedUpHotkeyCommand():
    logger.debug("speedUpHotkeyCommand")
    setHotkey('speedup')

def slowHotkeyCommand():
    logger.debug("slowHotkeyCommand")
    setHotkey('slowdown')
