import re
import keyboard
import mido
import os
import threading
import time
import random
import bisect

try:
    from pynput import keyboard as pynputKeyboard
except Exception:
    pynputKeyboard = None

from modules.functions import mainFunctions
from modules import configuration

pressedKeys = set()
heldKeys = set()
activeTransposedNotes = {}

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

specialKeyMap = {
    "shift": getattr(getattr(pynputKeyboard, "Key", None), "shift", "shift"),
    "ctrl": getattr(getattr(pynputKeyboard, "Key", None), "ctrl", "ctrl"),
    "alt": getattr(getattr(pynputKeyboard, "Key", None), "alt", "alt"),
    "space": getattr(getattr(pynputKeyboard, "Key", None), "space", "space")
} if pynputKeyboard else {
    "shift": "shift", "ctrl": "ctrl", "alt": "alt", "space": "space"
}

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
    if isinstance(keyLower, str) and keyLower in specialKeyMap:
        return specialKeyMap[keyLower]
    elif isinstance(keyLower, str) and len(keyLower) == 1:
        return keyLower
    elif pynputKeyboard and isinstance(key, getattr(pynputKeyboard, "Key", ())):
        return key
    else:
        raise ValueError(f"Unsupported key for pynput: {key}")

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
    inputMod = configuration.configData.get("midiPlayer", {}).get("inputModule", "pynput")
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
    inputMod = configuration.configData.get("midiPlayer", {}).get("inputModule", "pynput")
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

stopEvent = threading.Event()
seekEvent = threading.Event()
clockSeekEvent = threading.Event()
seekTargetTime = 0.0
seekLock = threading.Lock()
totalSongDuration = 0.0
clockThreadRef = None
keyboardHandlers = []
timerList = []

closeThread = False
paused = False
playThread = None
playbackSpeed = 1.0
sustainActive = False
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
    log(f"Seek requested to {seekTargetTime:.2f}s")

def getPianoFingerLimit():
    return int(configuration.configData.get("midiPlayer", {}).get("fingerLimit", 11))

def findVelocityKey(velocity):
    velocityMap = configuration.configData["midiPlayer"]["pianoMap"]["velocityMap"]
    thresholds = sorted(int(k) for k in velocityMap.keys())
    minimum = 0
    maximum = len(thresholds) - 1
    index = 0
    while minimum <= maximum:
        index = (minimum + maximum) // 2
        if index == 0 or index == len(thresholds) - 1:
            break
        if thresholds[index] < velocity:
            minimum = index + 1
        else:
            maximum = index - 1
    return velocityMap[str(thresholds[index])]

def pressAndMaybeRelease(key):
    global heldNoteCount
    limit = getPianoFingerLimit()
    if limit <= 10 and heldNoteCount >= limit:
        log(f"Finger limit ({limit}) reached, skipping note")
        return
    heldNoteCount += 1
    press(key)
    if configuration.configData["midiPlayer"]["customHoldLength"]["enabled"]:
        def _timerRelease():
            global heldNoteCount
            release(key)
            heldNoteCount = max(0, heldNoteCount - 1)
        t = threading.Timer(configuration.configData["midiPlayer"]["customHoldLength"]["noteLength"], _timerRelease)
        timerList.append(t)
        t.start()

def simulateKey(msgType, note, velocity):
    note = note + configuration.configData["midiPlayer"].get("pitchOffset", 0) + configuration.configData["midiPlayer"].get("transposeOffset", 0)
    allow88 = configuration.configData["midiPlayer"]["88Keys"]

    letterNoteMap = configuration.configData["midiPlayer"]["pianoMap"]["61keyMap"]
    lowNotes = configuration.configData["midiPlayer"]["pianoMap"]["88keyMap"]["lowNotes"]
    highNotes = configuration.configData["midiPlayer"]["pianoMap"]["88keyMap"]["highNotes"]

    if not allow88:
        if str(note) not in letterNoteMap:
            log(f"out of range: {note}")
            return
    else:
        if str(note) not in letterNoteMap and str(note) not in lowNotes and str(note) not in highNotes:
            log(f"out of range: {note}")
            return

    if str(note) in letterNoteMap:
        key = letterNoteMap[str(note)]
    elif allow88 and str(note) in lowNotes:
        key = lowNotes[str(note)]
    elif allow88 and str(note) in highNotes:
        key = highNotes[str(note)]
    else:
        log(f"out of range: {note}")
        return

    if msgType == "note_on":
        if configuration.configData["midiPlayer"]["velocity"]:
            velocityKey = findVelocityKey(velocity)
            press("alt")
            press(velocityKey)
            release(velocityKey)
            release("alt")

        if 36 <= note <= 96:
            if configuration.configData["midiPlayer"]["noDoubles"]:
                if re.search("[!@$%^*(]", key):
                    release(letterNoteMap[str(note - 1)])
                else:
                    release(key.lower())
            if re.search("[!@$%^*(]", key):
                press("shift")
                pressAndMaybeRelease(letterNoteMap[str(note - 1)])
                release("shift")
            elif key.isupper():
                press("shift")
                pressAndMaybeRelease(key.lower())
                release("shift")
            else:
                pressAndMaybeRelease(key)
        else:
            release(key.lower())
            press("ctrl")
            pressAndMaybeRelease(key.lower())
            release("ctrl")

    elif msgType == "note_off":
        global heldNoteCount
        if 36 <= note <= 96:
            if re.search("[!@$%^*(]", key):
                release(letterNoteMap[str(note - 1)])
            else:
                release(key.lower())
        else:
            release(key.lower())
        heldNoteCount = max(0, heldNoteCount - 1)

def parseMidi(message):
    global sustainActive
    if message.type == "control_change" and configuration.configData["midiPlayer"]["sustain"]:
        if not sustainActive and message.value > configuration.configData["midiPlayer"]["sustainCutoff"]:
            sustainActive = True
            press("space")
        elif sustainActive and message.value < configuration.configData["midiPlayer"]["sustainCutoff"]:
            sustainActive = False
            release("space")
    elif message.type in ("note_on", "note_off"):
        try:
            if message.velocity == 0:
                simulateKey("note_off", message.note, message.velocity)
            else:
                simulateKey(message.type, message.note, message.velocity)
        except IndexError:
            pass
    return sustainActive

def playMidiOnce(midiFile, startTimeOffset=0.0):
    global sustainActive, paused, totalSongDuration, heldNoteCount
    mid = mido.MidiFile(midiFile, clip=True)
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
    wasPaused = False

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
            if sustainActive:
                try:
                    release("space")
                except Exception:
                    pass
                sustainActive = False
            activeTransposedNotes.clear()
            heldNoteCount = 0

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

            if paused and not wasPaused:
                wasPaused = True
                if configuration.configData["midiPlayer"]["releaseOnPause"]:
                    for key in list(heldKeys):
                        release(key)
                    if sustainActive:
                        release("space")
                        sustainActive = False

            if not paused and wasPaused:
                wasPaused = False

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
            if not paused:
                if hasattr(msg, "note"):
                    if msg.type == "note_on" and msg.velocity > 0:
                        if configuration.configData["midiPlayer"]["randomFail"]["enabled"] and random.random() < configuration.configData["midiPlayer"]["randomFail"]["transpose"] / 100:
                            delta = random.randint(-12, 12)
                            newNote = msg.note + delta
                            if msg.note not in activeTransposedNotes:
                                activeTransposedNotes[msg.note] = []
                            activeTransposedNotes[msg.note].append(newNote)
                            original = msg.note
                            msg.note = newNote
                            parseMidi(msg)
                            msg.note = original
                        else:
                            parseMidi(msg)
                    elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                        if msg.note in activeTransposedNotes and activeTransposedNotes[msg.note]:
                            transNote = activeTransposedNotes[msg.note].pop(0)
                            if not activeTransposedNotes[msg.note]:
                                del activeTransposedNotes[msg.note]
                            original = msg.note
                            msg.note = transNote
                            parseMidi(msg)
                            msg.note = original
                        else:
                            parseMidi(msg)
                    else:
                        parseMidi(msg)
                else:
                    parseMidi(msg)
            else:
                if msg.type == "control_change" and msg.control == 64:
                    if configuration.configData["midiPlayer"]["sustain"]:
                        if msg.value > configuration.configData["midiPlayer"]["sustainCutoff"]:
                            sustainActive = True
                        else:
                            sustainActive = False

        idx += 1
        if idx < len(messages):
            nextMsg = messages[idx][1]
            adjustedDelay = nextMsg.time / playbackSpeed
            if configuration.configData["midiPlayer"]["randomFail"]["enabled"] and not nextMsg.is_meta:
                if random.random() < configuration.configData["midiPlayer"]["randomFail"]["speed"] / 100:
                    speedFactor = random.uniform(0.5, 1.5)
                    adjustedDelay *= speedFactor
            currentTime += adjustedDelay

    return True

def playMidiFile(midiFile, startTimeOffset=0.0):
    log("nanoMIDI Mid2VK Translator v3.0")
    log(f"Playing MIDI file: {midiFile}")
    crashed = False
    try:
        firstPlay = True
        while not (stopEvent.is_set() or closeThread):
            offset = startTimeOffset if firstPlay else 0.0
            firstPlay = False
            finished = playMidiOnce(midiFile, startTimeOffset=offset)
            if not configuration.configData["midiPlayer"]["loopSong"] or not finished or stopEvent.is_set() or closeThread:
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

        if (crashed or not configuration.configData["midiPlayer"]["loopSong"]) and not (stopEvent.is_set() or closeThread):
            from modules.functions.midiPlayerFunctions import stopPlayback
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

def startPlayback(midiFile, updateCallback=None, startTimeOffset=0.0):
    global playThread, stopEvent, clockThreadRef, closeThread, paused, seekEvent, clockSeekEvent, totalSongDuration
    stopEvent.clear()
    seekEvent.clear()
    clockSeekEvent.clear()
    closeThread = False
    paused = False
    if playThread is not None and isinstance(playThread, threading.Thread) and playThread.is_alive():
        return
    totalSeconds = mido.MidiFile(midiFile, clip=True).length
    totalSongDuration = totalSeconds
    playThread = threading.Thread(target=playMidiFile, args=(midiFile, startTimeOffset), daemon=True)
    clockThreadRef = threading.Thread(target=clockThread, args=(totalSeconds, updateCallback, startTimeOffset), daemon=True)
    clockThreadRef.start()
    playThread.start()

def pausePlayback():
    global paused, sustainActive
    paused = not paused
    
    if paused:
        if configuration.configData["midiPlayer"]["releaseOnPause"]:
            for key in list(heldKeys):
                release(key)
            if sustainActive:
                release("space")
                sustainActive = False
    
    log("Playback paused." if paused else "Playback resumed.")

def changeSpeed(amount):
    global playbackSpeed
    playbackSpeed = max(0.1, min(5.0, playbackSpeed + amount))
    log(f"Speed: {playbackSpeed * 100:.0f}%")

def stopPlayback():
    global closeThread, stopEvent, playThread, clockThreadRef, keyboardHandlers, timerList, heldNoteCount
    if closeThread or stopEvent.is_set():
        return
    
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
    log("Playback fully stopped.")