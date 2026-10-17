import mido
import threading
import time
import random
import bisect

from modules.functions import mainFunctions
from modules import configuration

activeTransposedNotes = {}
activeNotes = set()
stopEvent = threading.Event()
seekEvent = threading.Event()
clockSeekEvent = threading.Event()
seekTargetTime = 0.0
seekLock = threading.Lock()
totalSongDuration = 0.0
clockThreadRef = None
timerList = []
closeThread = False
paused = False
playThread = None
playbackSpeed = 1.0
sustainActive = False
midiOut = None

def seekPlayback(targetSeconds):
    global seekTargetTime, totalSongDuration
    with seekLock:
        if totalSongDuration > 0:
            seekTargetTime = max(0.0, min(float(targetSeconds), float(totalSongDuration)))
        else:
            seekTargetTime = max(0.0, float(targetSeconds))
        seekEvent.set()
        clockSeekEvent.set()
    log(f"MIDI Out seek requested to {seekTargetTime:.2f}s")

log = mainFunctions.log

def noteAllowed(note):
    allow88 = configuration.configData["midiPlayer"]["88Keys"]
    maps = configuration.configData["midiPlayer"]["pianoMap"]
    if not allow88:
        return str(note) in maps["61keyMap"]
    return str(note) in maps["61keyMap"] or str(note) in maps["88keyMap"]["lowNotes"] or str(note) in maps["88keyMap"]["highNotes"]

def parseMidi(message):
    global sustainActive, activeNotes
    log(str(message))

    if message.type == "control_change":
        if message.control == 64:
            if not configuration.configData["midiPlayer"]["sustain"]:
                return
            if message.value > configuration.configData["midiPlayer"]["sustainCutoff"]:
                sustainActive = True
                if midiOut:
                    midiOut.send(message)
            else:
                sustainActive = False
                if midiOut:
                    midiOut.send(message)
            return

    if message.type in ("note_on", "note_off"):
        noteOffset = configuration.configData["midiPlayer"].get("pitchOffset", 0) + configuration.configData["midiPlayer"].get("transposeOffset", 0)
        note = message.note + noteOffset
        if not noteAllowed(note):
            log(f"out of range: {note}")
            return

        if message.type == "note_on":
            if message.velocity == 0:
                msgType = "note_off"
            else:
                msgType = "note_on"
        else:
            msgType = "note_off"

        if msgType == "note_on" and not configuration.configData["midiPlayer"]["velocity"]:
            message.velocity = 78
        elif msgType == "note_off":
            message.velocity = 0

        channel = message.channel if hasattr(message, "channel") else 0
        key = (note, channel)

        if configuration.configData["midiPlayer"]["noDoubles"]:
            if msgType == "note_on" and key in activeNotes:
                log(f"skipped double: note {note} ch {channel}")
                return

        if msgType == "note_on":
            activeNotes.add(key)
        if msgType == "note_off" and key in activeNotes:
            activeNotes.remove(key)

        if midiOut:
            midiOut.send(message)

def playMidiOnce(midiFile, startTimeOffset=0.0):
    global sustainActive, totalSongDuration
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

    while idx < len(messages):
        if stopEvent.is_set() or closeThread:
            return False

        if seekEvent.is_set():
            with seekLock:
                seekEvent.clear()
                targetSeconds = seekTargetTime

            if midiOut:
                for note, channel in list(activeNotes):
                    try:
                        midiOut.send(mido.Message("note_off", note=note, velocity=0, channel=channel))
                    except Exception:
                        pass
                if sustainActive:
                    try:
                        midiOut.send(mido.Message("control_change", control=64, value=0))
                    except Exception:
                        pass
            activeNotes.clear()
            sustainActive = False
            activeTransposedNotes.clear()

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
                delta = time.monotonic() - pauseStart
                startTime += delta
                targetTime += delta

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
            if hasattr(msg, "note"):
                n = msg.note

                if not noteAllowed(n):
                    log(f"out of range: {n}")
                    idx += 1
                    continue

                if msg.type == "note_on" and msg.velocity > 0:
                    if configuration.configData["midiPlayer"]["randomFail"]["enabled"]:
                        if random.random() < configuration.configData["midiPlayer"]["randomFail"]["transpose"] / 100:
                            delta = random.randint(-12, 12)
                            newNote = n + delta
                            if not noteAllowed(newNote):
                                log(f"out of range: {newNote}")
                                idx += 1
                                continue
                            if n not in activeTransposedNotes:
                                activeTransposedNotes[n] = []
                            activeTransposedNotes[n].append(newNote)
                            original = msg.note
                            msg.note = newNote
                            parseMidi(msg)
                            msg.note = original
                            idx += 1
                            continue

                if msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                    if n in activeTransposedNotes and activeTransposedNotes[n]:
                        transNote = activeTransposedNotes[n].pop(0)
                        if not activeTransposedNotes[n]:
                            del activeTransposedNotes[n]
                        if noteAllowed(transNote):
                            original = msg.note
                            msg.note = transNote
                            parseMidi(msg)
                            msg.note = original
                        else:
                            log(f"out of range: {transNote}")
                        idx += 1
                        continue

            parseMidi(msg)

        idx += 1
        if idx < len(messages):
            nextMsg = messages[idx][1]
            adjustedDelay = nextMsg.time / playbackSpeed
            if configuration.configData["midiPlayer"]["randomFail"]["enabled"] and not nextMsg.is_meta:
                if random.random() < configuration.configData["midiPlayer"]["randomFail"]["speed"] / 100:
                    adjustedDelay *= random.uniform(0.5, 1.5)
            currentTime += adjustedDelay

    return True

def playMidiFile(midiFile, startTimeOffset=0.0):
    log("nanoMIDI Direct MIDI Out v1.0")
    log(f"Playing MIDI file: {midiFile}")

    firstPlay = True
    while not (stopEvent.is_set() or closeThread):
        offset = startTimeOffset if firstPlay else 0.0
        firstPlay = False
        finished = playMidiOnce(midiFile, startTimeOffset=offset)

        if stopEvent.is_set() or closeThread:
            break

        if not finished:
            break

        if not configuration.configData["midiPlayer"]["loopSong"]:
            from modules.functions.midiPlayerFunctions import stopPlayback
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

def startPlayback(midiFile, outputDevice, updateCallback=None, startTimeOffset=0.0):
    global playThread, stopEvent, clockThreadRef, closeThread, paused, midiOut, seekEvent, clockSeekEvent, totalSongDuration
    stopEvent.clear()
    seekEvent.clear()
    clockSeekEvent.clear()
    closeThread = False
    paused = False
    if playThread is not None and isinstance(playThread, threading.Thread) and playThread.is_alive():
        return
    midiOut = mido.open_output(outputDevice)
    totalSeconds = mido.MidiFile(midiFile, clip=True).length
    totalSongDuration = totalSeconds
    playThread = threading.Thread(target=playMidiFile, args=(midiFile, startTimeOffset), daemon=True)
    clockThreadRef = threading.Thread(target=clockThread, args=(totalSeconds, updateCallback, startTimeOffset), daemon=True)
    clockThreadRef.start()
    playThread.start()

def pausePlayback():
    global paused, sustainActive
    paused = not paused
    
    if paused and configuration.configData["midiPlayer"]["releaseOnPause"]:
        if midiOut:
            for note, channel in list(activeNotes):
                try:
                    midiOut.send(mido.Message("note_off", note=note, velocity=0, channel=channel))
                    activeNotes.remove((note, channel))
                except:
                    pass
            
            if sustainActive:
                sustainOff = mido.Message("control_change", control=64, value=0)
                midiOut.send(sustainOff)
                sustainActive = False
    
    log("Playback paused." if paused else "Playback resumed.")

def changeSpeed(amount):
    global playbackSpeed
    playbackSpeed = max(0.1, min(5.0, playbackSpeed + amount))
    log(f"Speed: {playbackSpeed * 100:.0f}%")

def stopPlayback():
    global closeThread, stopEvent, playThread, clockThreadRef, timerList, midiOut, activeNotes
    if stopEvent.is_set():
        return
    stopEvent.set()
    closeThread = True
    for t in list(timerList):
        try:
            t.cancel()
        except:
            pass
    timerList.clear()
    if playThread is not None and isinstance(playThread, threading.Thread):
        try:
            playThread.join(timeout=1.0)
        except:
            pass
    if clockThreadRef is not None and isinstance(clockThreadRef, threading.Thread):
        try:
            clockThreadRef.join(timeout=1.0)
        except:
            pass
    if midiOut:
        try:
            for note, channel in list(activeNotes):
                midiOut.send(mido.Message("note_off", note=note, velocity=0, channel=channel))
            activeNotes.clear()
            midiOut.close()
        except:
            pass
        midiOut = None
    log("Playback fully stopped.")