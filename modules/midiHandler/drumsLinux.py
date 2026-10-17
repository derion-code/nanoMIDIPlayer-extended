import mido
import time
import random
import threading
import keyboard
import bisect
try:
    from pynput import keyboard as pynputKeyboard
except Exception:
    pynputKeyboard = None

from modules import configuration
from modules.functions import mainFunctions

selectedModule = "pynput"
pressedKeys = set()
heldKeys = set()

log = mainFunctions.log

def logKeys(action, key):
    if pynputKeyboard and isinstance(key, getattr(pynputKeyboard, "Key", ())):
        keyName = key.name if key.name else str(key)
    else:
        keyName = str(key)
    if action == "press":
        pressedKeys.add(keyName)
    elif action == "release" and keyName in pressedKeys:
        pressedKeys.remove(keyName)
    if pressedKeys:
        log(f"{action}: {'+'.join(sorted(pressedKeys))}")
    else:
        log(f"{action}: {keyName}")

from modules.midiHandler import uinputHelper

pynputController = None

def getPynputController():
    global pynputController
    if pynputKeyboard is None:
        log("pynput is unavailable in this environment.")
        return None
    if pynputController is None:
        try:
            pynputController = pynputKeyboard.Controller()
        except Exception as e:
            log(f"Failed to initialize pynput controller: {e}")
    return pynputController

blockedKeys = {f"f{i}" for i in range(1, 13)} | {"tab", "backspace", "esc"}

def translateKey(key):
    keyLower = key.lower() if isinstance(key, str) else key
    if isinstance(keyLower, str) and len(keyLower) == 1:
        return keyLower
    elif pynputKeyboard and isinstance(key, getattr(pynputKeyboard, "Key", ())):
        return key
    else:
        raise ValueError(f"Unsupported key: {key}")

def isBlockedKey(keyObj):
    if isinstance(keyObj, str):
        return keyObj.lower() in blockedKeys
    if pynputKeyboard and isinstance(keyObj, getattr(pynputKeyboard, "Key", ())):
        name = getattr(keyObj, "name", None)
        if isinstance(name, str) and name.lower() in blockedKeys:
            return True
        s = str(keyObj).lower()
        if s.startswith("key.f") and any(s.startswith(f"key.f{i}") for i in range(1, 13)):
            return True
        return False
    return False

def press(key):
    inputMod = configuration.configData.get("drumsMacro", {}).get("inputModule", "pynput")
    if inputMod == "uinput":
        if uinputHelper.pressKey(key):
            logKeys("press", key)
            heldKeys.add(key)
    elif inputMod == "keyboard":
        keyboard.press(key)
        logKeys("press", key)
        heldKeys.add(key)
    else:
        controller = getPynputController()
        if not controller:
            return
        keyObj = translateKey(key)
        if isBlockedKey(keyObj):
            return
        controller.press(keyObj)
        logKeys("press", keyObj)
        heldKeys.add(keyObj)

def release(key):
    inputMod = configuration.configData.get("drumsMacro", {}).get("inputModule", "pynput")
    if inputMod == "uinput":
        if uinputHelper.releaseKey(key):
            logKeys("release", key)
        if key in heldKeys:
            heldKeys.remove(key)
    elif inputMod == "keyboard":
        keyboard.release(key)
        logKeys("release", key)
        if key in heldKeys:
            heldKeys.remove(key)
    else:
        controller = getPynputController()
        if not controller:
            return
        keyObj = translateKey(key)
        if isBlockedKey(keyObj):
            return
        controller.release(keyObj)
        logKeys("release", keyObj)
        if keyObj in heldKeys:
            heldKeys.remove(keyObj)

drumsMap = {
    42: configuration.configData['drumsMacro']['drumsMap']['closed_Hi-Hat'],
    44: configuration.configData['drumsMacro']['drumsMap']['closed_Hi-Hat2'],
    46: configuration.configData['drumsMacro']['drumsMap']['open_Hi-Hat'],
    48: configuration.configData['drumsMacro']['drumsMap']['tom1'],
    50: configuration.configData['drumsMacro']['drumsMap']['tom1_2'],
    60: configuration.configData['drumsMacro']['drumsMap']['tom'],
    62: configuration.configData['drumsMacro']['drumsMap']['tom2_2'],
    49: configuration.configData['drumsMacro']['drumsMap']['rightCrash'],
    55: configuration.configData['drumsMacro']['drumsMap']['leftCrash'],
    38: configuration.configData['drumsMacro']['drumsMap']['snare'],
    40: configuration.configData['drumsMacro']['drumsMap']['snare2'],
    37: configuration.configData['drumsMacro']['drumsMap']['snareSide'],
    35: configuration.configData['drumsMacro']['drumsMap']['kick'],
    36: configuration.configData['drumsMacro']['drumsMap']['kick2'],
    51: configuration.configData['drumsMacro']['drumsMap']['ride'],
    53: configuration.configData['drumsMacro']['drumsMap']['rideBell'],
    39: configuration.configData['drumsMacro']['drumsMap']['cowbell'],
    52: configuration.configData['drumsMacro']['drumsMap']['crashChina'],
    57: configuration.configData['drumsMacro']['drumsMap']['splashCrash'],
    45: configuration.configData['drumsMacro']['drumsMap']['lowTom'],
    47: configuration.configData['drumsMacro']['drumsMap']['lowMidTom'],
}

stopEvent = threading.Event()
seekEvent = threading.Event()
clockSeekEvent = threading.Event()
seekTargetTime = 0.0
seekLock = threading.Lock()
totalSongDuration = 0.0
clockThreadRef = None
playThread = None
timerList = []
paused = False
closeThread = False
playbackSpeed = 1.0
keyboardHandlers = []
heldNoteCount = 0

def seekPlayback(targetSeconds):
    global seekTargetTime, totalSongDuration
    with seekLock:
        if totalSongDuration > 0:
            seekTargetTime = max(0.0, min(float(targetSeconds), float(totalSongDuration)))
        else:
            seekTargetTime = max(0.0, float(targetSeconds))
        seekEvent.set()
        clockSeekEvent.set()
    log(f"Drums seek requested to {seekTargetTime:.2f}s")

def getDrumsFingerLimit():
    return int(configuration.configData.get("drumsMacro", {}).get("fingerLimit", 11))

def pressAndMaybeRelease(key):
    global heldNoteCount
    limit = getDrumsFingerLimit()
    if limit <= 10 and heldNoteCount >= limit:
        log(f"Finger limit ({limit}) reached, skipping drum hit")
        return
    heldNoteCount += 1
    press(key)
    if configuration.configData["drumsMacro"]["customHoldLength"]["enabled"]:
        def _timerRelease():
            global heldNoteCount
            release(key)
            heldNoteCount = max(0, heldNoteCount - 1)
        t = threading.Timer(configuration.configData["drumsMacro"]["customHoldLength"]["noteLength"], _timerRelease)
        timerList.append(t)
        t.start()

def parseMidi(message):
    global heldNoteCount
    if message.type == 'note_on' and message.velocity > 0:
        key = drumsMap.get(message.note)
        if key is not None:
            pressAndMaybeRelease(key)
    elif message.type == 'note_off' or (message.type == 'note_on' and message.velocity == 0):
        key = drumsMap.get(message.note)
        if key is not None:
            release(key)
            heldNoteCount = max(0, heldNoteCount - 1)

def playMidiOnce(filePath, startTimeOffset=0.0):
    global heldNoteCount, totalSongDuration
    mid = mido.MidiFile(filePath, clip=True)
    messages = []
    t = 0.0
    for msg in mid:
        t += msg.time
        messages.append((t, msg))
    
    totalSongDuration = messages[-1][0] if messages else 0.0

    idx = 0
    if startTimeOffset > 0:
        clampedTarget = max(0.0, min(float(startTimeOffset), float(totalSongDuration)))
        idx = bisect.bisect_left(messages, clampedTarget, key=lambda x: x[0])
        if idx >= len(messages):
            return True
        firstDelay = max(0.0, messages[idx][0] - clampedTarget) / playbackSpeed
    else:
        firstDelay = (messages[0][0] / playbackSpeed) if messages else 0.0

    startTime = time.monotonic()
    currentTime = firstDelay

    while idx < len(messages):
        if stopEvent.is_set() or closeThread:
            return False

        if seekEvent.is_set():
            with seekLock:
                seekEvent.clear()
                targetSeconds = seekTargetTime

            for key in list(heldKeys):
                try:
                    release(key)
                except Exception:
                    pass
            heldNoteCount = 0
            for t_item in list(timerList):
                try:
                    t_item.cancel()
                except Exception:
                    pass
            timerList.clear()

            clampedTarget = max(0.0, min(float(targetSeconds), float(totalSongDuration)))
            idx = bisect.bisect_left(messages, clampedTarget, key=lambda x: x[0])
            if idx >= len(messages):
                return True

            startTime = time.monotonic()
            firstDelay = max(0.0, messages[idx][0] - clampedTarget) / playbackSpeed
            currentTime = firstDelay
            continue

        msgTime, msg = messages[idx]
        targetTime = startTime + currentTime

        while time.monotonic() < targetTime:
            if stopEvent.is_set() or closeThread:
                return False

            if seekEvent.is_set():
                break

            while paused and not (stopEvent.is_set() or closeThread):
                if seekEvent.is_set():
                    break
                pauseStart = time.monotonic()
                if seekEvent.wait(timeout=0.05):
                    break
                pauseDuration = time.monotonic() - pauseStart
                startTime += pauseDuration
                targetTime += pauseDuration

            if seekEvent.is_set():
                break

            remaining = targetTime - time.monotonic()
            if remaining > 0:
                sleepChunk = min(remaining, 0.005)
                if seekEvent.wait(timeout=sleepChunk):
                    break

        if seekEvent.is_set():
            continue

        if not msg.is_meta:
            parseMidi(msg)

        idx += 1
        if idx < len(messages):
            nextMsg = messages[idx][1]
            adjustedDelay = nextMsg.time / playbackSpeed
            if configuration.configData["drumsMacro"]["randomFail"]["enabled"] and not nextMsg.is_meta:
                if random.random() < configuration.configData["drumsMacro"]["randomFail"]["speed"] / 100:
                    speedFactor = random.uniform(0.5, 1.5)
                    adjustedDelay *= speedFactor
            currentTime += adjustedDelay

    return True

def playMidiFile(filePath, startTimeOffset=0.0):
    crashed = False
    try:
        firstPlay = True
        while not (stopEvent.is_set() or closeThread):
            offset = startTimeOffset if firstPlay else 0.0
            firstPlay = False
            finished = playMidiOnce(filePath, startTimeOffset=offset)
            if not configuration.configData["drumsMacro"]["loopSong"] or not finished or stopEvent.is_set() or closeThread:
                break
            for key in list(heldKeys):
                release(key)
    except Exception as e:
        crashed = True
        mainFunctions.logger.debug(f"playMidiFile error: {e}")
    finally:
        for key in list(heldKeys):
            try:
                release(key)
            except Exception:
                pass

        if (crashed or not configuration.configData["drumsMacro"]["loopSong"]) and not (stopEvent.is_set() or closeThread):
            from modules.functions.drumsMacroFunctions import stopPlayback
            app = mainFunctions.getApp()
            if app and hasattr(app, "after"):
                try:
                    app.after(0, stopPlayback)
                except Exception as e:
                    mainFunctions.logger.debug(f"app.after stopPlayback error: {e}")
                    stopPlayback()
            else:
                stopPlayback()

def formatTime(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:0}:{minutes:02}:{secs:02}"

def clockThread(totalSeconds, updateCallback=None, initialSeconds=0):
    global closeThread, playbackSpeed, paused
    currentSeconds = int(initialSeconds)
    while not (stopEvent.is_set() or closeThread):
        if clockSeekEvent.is_set():
            with seekLock:
                clockSeekEvent.clear()
                currentSeconds = int(seekTargetTime)
            shown = min(int(totalSeconds), max(0, currentSeconds))
            formattedTime = f"{formatTime(shown)} / {formatTime(totalSeconds)}"
            if configuration.configData['appUI']['timestamp']:
                if updateCallback:
                    try:
                        updateCallback(formattedTime, currentSeconds)
                    except TypeError:
                        updateCallback(formattedTime)
                else:
                    log(formattedTime)

        if not paused:
            shown = min(int(totalSeconds), max(0, currentSeconds % max(1, int(totalSeconds))))
            formattedTime = f"{formatTime(shown)} / {formatTime(totalSeconds)}"
            if configuration.configData['appUI']['timestamp']:
                if updateCallback:
                    try:
                        updateCallback(formattedTime, currentSeconds)
                    except TypeError:
                        updateCallback(formattedTime)
                else:
                    log(formattedTime)
            currentSeconds += 1
            for _ in range(10):
                if stopEvent.is_set() or closeThread or clockSeekEvent.is_set():
                    break
                time.sleep(0.1 / playbackSpeed)
        else:
            if clockSeekEvent.wait(timeout=0.1):
                pass

def startPlayback(filePath, updateCallback=None, startTimeOffset=0.0):
    global playThread, stopEvent, clockThreadRef, closeThread, paused, seekEvent, clockSeekEvent, totalSongDuration
    stopEvent.clear()
    seekEvent.clear()
    clockSeekEvent.clear()
    closeThread = False
    paused = False
    if playThread is not None and isinstance(playThread, threading.Thread) and playThread.is_alive():
        return
    totalSeconds = mido.MidiFile(filePath, clip=True).length
    totalSongDuration = totalSeconds
    playThread = threading.Thread(target=playMidiFile, args=(filePath, startTimeOffset), daemon=True)
    clockThreadRef = threading.Thread(target=clockThread, args=(totalSeconds, updateCallback, startTimeOffset), daemon=True)
    clockThreadRef.start()
    playThread.start()

def pausePlayback():
    global paused
    paused = not paused
    if paused and configuration.configData["drumsMacro"]["releaseOnPause"]:
        for key in list(heldKeys):
            release(key)

def changeSpeed(amount):
    global playbackSpeed
    playbackSpeed = max(0.1, min(5.0, playbackSpeed + amount))
    log(f"Speed: {playbackSpeed * 100:.0f}%")

def stopPlayback():
    global closeThread, stopEvent, playThread, clockThreadRef, timerList, keyboardHandlers, heldNoteCount
    stopEvent.set()
    closeThread = True
    heldNoteCount = 0
    for key in list(heldKeys):
        try:
            release(key)
        except Exception:
            pass
    for t in list(timerList):
        try:
            t.cancel()
        except Exception:
            pass
    timerList.clear()
    try:
        for h in list(keyboardHandlers):
            try:
                keyboard.unhook(h)
            except Exception:
                pass
        keyboardHandlers.clear()
    except Exception:
        pass
    if playThread is not None and isinstance(playThread, threading.Thread) and playThread is not threading.current_thread():
        try:
            playThread.join(timeout=1.0)
        except Exception:
            pass
    if clockThreadRef is not None and isinstance(clockThreadRef, threading.Thread) and clockThreadRef is not threading.current_thread():
        try:
            clockThreadRef.join(timeout=1.0)
        except Exception:
            pass