import threading
import json
import customtkinter
import os
import platform
import datetime
import keyboard
import logging

from tkinter import filedialog
from mido import MidiFile
from pynput import keyboard as pynputKeyboard

from modules import configuration
from modules.functions import mainFunctions
from ui.drumsMacro import DrumsMacroTab
from ui.settings import SettingsTab
from ui import customTheme

logger = logging.getLogger(__name__)
osName = platform.system()

if osName == 'Windows':
    from modules.midiHandler import drumsWindows as midiHandler
elif osName == 'Darwin':
    from modules.midiHandler import drumsDarwin as midiHandler
elif osName == "Linux":
    from modules.midiHandler import drumsLinux as midiHandler

app = mainFunctions.getApp()

isUserDragging = False
initialSeekTime = 0.0

def onSliderPress(event=None):
    global isUserDragging
    isUserDragging = True

def onSliderDrag(value):
    try:
        val = int(float(value))
        totalTime = int(float(DrumsMacroTab.timelineSlider.cget("to")))
        formattedVal = str(datetime.timedelta(seconds=val))
        formattedTotal = str(datetime.timedelta(seconds=totalTime))
        if configuration.configData['appUI']['timestamp']:
            text = f"{formattedVal} / {formattedTotal}"
        else:
            text = f"X:XX:XX / {formattedTotal}"
        DrumsMacroTab.timelineIndicator.configure(text=text)
    except Exception as e:
        logger.debug(f"onSliderDrag error: {e}")

def onSliderRelease(event=None):
    global isUserDragging, initialSeekTime
    isUserDragging = False
    try:
        targetSeconds = float(DrumsMacroTab.timelineSlider.get())
        totalTime = int(float(DrumsMacroTab.timelineSlider.cget("to")))
        formattedTarget = str(datetime.timedelta(seconds=int(targetSeconds)))
        formattedTotal = str(datetime.timedelta(seconds=totalTime))
        if configuration.configData['appUI']['timestamp']:
            text = f"{formattedTarget} / {formattedTotal}"
        else:
            text = f"X:XX:XX / {formattedTotal}"
        DrumsMacroTab.timelineIndicator.configure(text=text)

        if app and app.isRunning:
            seekPlayback(targetSeconds)
        else:
            initialSeekTime = targetSeconds
    except Exception as e:
        logger.exception(f"onSliderRelease error: {e}")

def seekPlayback(targetSeconds):
    logger.info(f"drums seekPlayback called: {targetSeconds}")
    try:
        midiHandler.seekPlayback(targetSeconds)
    except Exception as e:
        logger.exception(f"drums seekPlayback error: {e}")

def selectFile():
    logger.info("selectFile called")
    try:
        DrumsMacroTab.midiPathDropdown.set("")
        unbindControls()
        stopPlayback()
        DrumsMacroTab.timelineIndicator.configure(text="0:00:00 / 0:00:00")
        if hasattr(DrumsMacroTab, "timelineSlider"):
            DrumsMacroTab.timelineSlider.configure(from_=0, to=100, state="disabled")
            DrumsMacroTab.timelineSlider.set(0)
        DrumsMacroTab.playButton.configure(text="Play")

        filePath = filedialog.askopenfilename(filetypes=[("MIDI files", "*.mid"), ("MIDI files", "*.midi")])
        logger.debug(f"filePath selected: {filePath}")
        if filePath:
            currentVAL = list(DrumsMacroTab.midiPathDropdown.cget("values"))
            if filePath not in currentVAL:
                currentVAL.append(filePath)
                DrumsMacroTab.midiPathDropdown.configure(values=currentVAL)

            DrumsMacroTab.midiPathDropdown.set(filePath)
            midiFile = MidiFile(filePath, clip=True)

            timeLength = midiFile.length
            timelineText = (
                f"0:00:00 / {str(datetime.timedelta(seconds=int(timeLength)))}"
                if configuration.configData['appUI']['timestamp']
                else f"X:XX:XX / {str(datetime.timedelta(seconds=int(timeLength)))}"
            )
            DrumsMacroTab.timelineIndicator.configure(text=timelineText)
            if hasattr(DrumsMacroTab, "timelineSlider"):
                DrumsMacroTab.timelineSlider.configure(from_=0, to=max(1, int(timeLength)), state="normal")
                DrumsMacroTab.timelineSlider.set(0)

            configuration.configData['drumsMacro']['currentFile'] = filePath

            if 'midiList' not in configuration.configData['drumsMacro']:
                configuration.configData['drumsMacro']['midiList'] = []
            if filePath not in configuration.configData['drumsMacro']['midiList']:
                configuration.configData['drumsMacro']['midiList'].append(filePath)
            configuration.configData.save()

            bindControls()
    except Exception as e:
        logger.exception(f"selectFile error: {e}")

def loadSavedFile():
    logger.info("loadSavedFile called")
    try:
        midiList = configuration.configData['drumsMacro'].get('midiList', [])
        currentFile = configuration.configData['drumsMacro'].get('currentFile', '')

        midiList = [f for f in midiList if os.path.exists(f)]
        configuration.configData['drumsMacro']['midiList'] = midiList

        if currentFile and not os.path.exists(currentFile):
            currentFile = ""
            configuration.configData['drumsMacro']['currentFile'] = ""

        configuration.configData.save()

        entryValues = list(DrumsMacroTab.midiPathDropdown.cget("values"))
        for p in midiList:
            if p not in entryValues:
                entryValues.append(p)
        DrumsMacroTab.midiPathDropdown.configure(values=entryValues)

        if currentFile:
            if currentFile not in entryValues:
                entryValues.append(currentFile)
                DrumsMacroTab.midiPathDropdown.configure(values=entryValues)
            DrumsMacroTab.midiPathDropdown.set(currentFile)
            midiFileData = MidiFile(currentFile, clip=True)
            totalTime = midiFileData.length
            timelineText = f"0:00:00 / {str(datetime.timedelta(seconds=int(totalTime)))}" if configuration.configData['appUI']['timestamp'] else f"X:XX:XX / {str(datetime.timedelta(seconds=int(totalTime)))}"
            DrumsMacroTab.timelineIndicator.configure(text=timelineText)
            if hasattr(DrumsMacroTab, "timelineSlider"):
                DrumsMacroTab.timelineSlider.configure(from_=0, to=max(1, int(totalTime)), state="normal")
                DrumsMacroTab.timelineSlider.set(0)
            logger.debug(f"loaded currentFile: {currentFile}")
            return

        if midiList:
            firstFile = midiList[0]
            DrumsMacroTab.midiPathDropdown.set(firstFile)
            configuration.configData['drumsMacro']['currentFile'] = firstFile
            configuration.configData.save()
            midiFileData = MidiFile(firstFile, clip=True)
            totalTime = midiFileData.length
            timelineText = f"0:00:00 / {str(datetime.timedelta(seconds=int(totalTime)))}" if configuration.configData['appUI']['timestamp'] else f"X:XX:XX / {str(datetime.timedelta(seconds=int(totalTime)))}"
            DrumsMacroTab.timelineIndicator.configure(text=timelineText)
            if hasattr(DrumsMacroTab, "timelineSlider"):
                DrumsMacroTab.timelineSlider.configure(from_=0, to=max(1, int(totalTime)), state="normal")
                DrumsMacroTab.timelineSlider.set(0)
            logger.debug(f"loaded firstFile: {firstFile}")
            return

        DrumsMacroTab.midiPathDropdown.set("None")
        DrumsMacroTab.timelineIndicator.configure(text="0:00:00 / 0:00:00")
        if hasattr(DrumsMacroTab, "timelineSlider"):
            DrumsMacroTab.timelineSlider.configure(from_=0, to=100, state="disabled")
            DrumsMacroTab.timelineSlider.set(0)
        logger.debug("no saved files found")
    except Exception as e:
        logger.exception(f"loadSavedFile error: {e}")

def switchMidiEvent(event=None):
    logger.info("switchMidiEvent called")
    try:
        midiFile = DrumsMacroTab.midiPathDropdown.get()
        configuration.configData['drumsMacro']['currentFile'] = midiFile
        configuration.configData.save()

        midiFileData = MidiFile(midiFile, clip=True)
        totalTime = midiFileData.length
        timelineText = f"0:00:00 / {str(datetime.timedelta(seconds=int(totalTime)))}" if configuration.configData['appUI']['timestamp'] else f"X:XX:XX / {str(datetime.timedelta(seconds=int(totalTime)))}"
        DrumsMacroTab.timelineIndicator.configure(text=timelineText)
        if hasattr(DrumsMacroTab, "timelineSlider"):
            DrumsMacroTab.timelineSlider.configure(from_=0, to=max(1, int(totalTime)), state="normal")
            DrumsMacroTab.timelineSlider.set(0)
        bindControls()
        logger.debug(f"switched midi file to: {midiFile}")
    except Exception as e:
        logger.exception(f"switchMidiEvent error: {e}")

def bindControls():
    logger.info("bindControls called")
    try:
        unbindControls()
        playKey = configuration.configData["hotkeys"].get("play", "F1").upper()
        pauseKey = configuration.configData["hotkeys"].get("pause", "F2").upper()
        stopKey = configuration.configData["hotkeys"].get("stop", "F3").upper()
        speedUpKey = configuration.configData["hotkeys"].get("speedup", "F4").upper()
        slowDownKey = configuration.configData["hotkeys"].get("slowdown", "F5").upper()

        if osName == "Windows":
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(playKey.lower(), lambda e: startPlayback()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(pauseKey.lower(), lambda e: pausePlayback()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(stopKey.lower(), lambda e: stopPlayback()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(speedUpKey.lower(), lambda e: decreaseSpeed()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(slowDownKey.lower(), lambda e: increaseSpeed()))
        else:
            global listener, activeHotkeys

            activeHotkeys = {
                playKey: startPlayback,
                pauseKey: pausePlayback,
                stopKey: stopPlayback,
                speedUpKey: decreaseSpeed,
                slowDownKey: increaseSpeed
            }

            def onPress(key):
                try:
                    if hasattr(key, "char") and key.char:
                        keyStr = key.char.upper()
                    else:
                        keyStr = str(key).replace("Key.", "").upper()
                    if keyStr in activeHotkeys:
                        activeHotkeys[keyStr]()
                except Exception as e:
                    logger.debug(f"onPress error: {e}")

            if listener is None:
                listener = pynputKeyboard.Listener(on_press=onPress)
                listener.daemon = True
                listener.start()
        logger.debug("bindControls complete")
    except Exception as e:
        logger.exception(f"bindControls error: {e}")

def bindControls():
    try:
        playKey = configuration.configData["hotkeys"].get("play", "F1").upper()
        pauseKey = configuration.configData["hotkeys"].get("pause", "F2").upper()
        stopKey = configuration.configData["hotkeys"].get("stop", "F3").upper()
        speedUpKey = configuration.configData["hotkeys"].get("speedup", "F4").upper()
        slowDownKey = configuration.configData["hotkeys"].get("slowdown", "F5").upper()

        if osName == "Windows":
            unbindControls()
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(playKey.lower(), lambda e: startPlayback()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(pauseKey.lower(), lambda e: pausePlayback()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(stopKey.lower(), lambda e: stopPlayback()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(speedUpKey.lower(), lambda e: decreaseSpeed()))
            midiHandler.keyboardHandlers.append(keyboard.on_press_key(slowDownKey.lower(), lambda e: increaseSpeed()))
        else:
            from modules.functions import mainFunctions
            mainFunctions.activeHotkeys.clear()
            mainFunctions.activeHotkeys.update({
                playKey: startPlayback,
                pauseKey: pausePlayback,
                stopKey: stopPlayback,
                speedUpKey: decreaseSpeed,
                slowDownKey: increaseSpeed
            })
            mainFunctions.startGlobalListener()
    except Exception as e:
        logger.exception(f"bindControls error: {e}")

def unbindControls():
    try:
        if osName == "Windows":
            for h in list(midiHandler.keyboardHandlers):
                try:
                    keyboard.unhook(h)
                except Exception:
                    pass
            midiHandler.keyboardHandlers.clear()
        else:
            from modules.functions import mainFunctions
            mainFunctions.activeHotkeys.clear()
    except Exception as e:
        logger.exception(f"unbindControls error: {e}")

def playButton():
    logger.info("playButton called")
    try:
        if not app.isRunning:
            startPlayback()
        else:
            pausePlayback()
    except Exception as e:
        logger.exception(f"playButton error: {e}")

def startPlayback():
    global initialSeekTime
    logger.info("startPlayback called")
    try:
        midiFile = DrumsMacroTab.midiPathDropdown.get()
        logger.debug(f"startPlayback midiFile: {midiFile}")
        if not os.path.exists(midiFile):
            logger.warning("MIDI File does not exist.")
            threading.Thread(target=mainFunctions.insertConsoleText, args=("MIDI File does not exist.", True)).start()
            return

        if app and not app.isRunning:
            app.isRunning = True
            DrumsMacroTab.playButton.configure(
                text="Playing",
                fg_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PlayingColor"],
                hover_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PlayingColorHover"]
            )
            DrumsMacroTab.stopButton.configure(state="normal", fg_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["StopColor"])

            seekOffset = initialSeekTime
            initialSeekTime = 0.0

            def updateTimeline(text, currentSeconds=None):
                def _update():
                    DrumsMacroTab.timelineIndicator.configure(text=text)
                    if currentSeconds is not None and not isUserDragging and hasattr(DrumsMacroTab, "timelineSlider"):
                        DrumsMacroTab.timelineSlider.set(currentSeconds)
                if app and hasattr(app, "after"):
                    try:
                        app.after(0, _update)
                    except Exception:
                        _update()
                else:
                    _update()

            midiHandler.startPlayback(midiFile, updateCallback=updateTimeline, startTimeOffset=seekOffset)
            logger.debug("midiHandler.startPlayback called")
    except Exception as e:
        logger.exception(f"startPlayback error: {e}")

def stopPlayback():
    global initialSeekTime
    logger.info("stopPlayback called")
    try:
        initialSeekTime = 0.0
        if not app.isRunning:
            return
        app.isRunning = False

        try:
            midiHandler.stopPlayback()
            logger.debug("midiHandler.stopPlayback called")
        except Exception as e:
            logger.debug(f"stopPlayback backend cleanup error: {e}")
        finally:
            bindControls()
            DrumsMacroTab.stopButton.configure(
                state="disabled",
                fg_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["StopColorDisabled"]
            )
            DrumsMacroTab.playButton.configure(
                text="Play",
                fg_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PlayColor"],
                hover_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PlayColorHover"]
            )

            if not isUserDragging and hasattr(DrumsMacroTab, "timelineSlider"):
                DrumsMacroTab.timelineSlider.set(0)

            midiFile = DrumsMacroTab.midiPathDropdown.get()
            if os.path.exists(midiFile):
                midiFileData = MidiFile(midiFile, clip=True)
                totalTime = midiFileData.length
                timelineText = (
                    f"0:00:00 / {str(datetime.timedelta(seconds=int(totalTime)))}"
                    if configuration.configData['appUI']['timestamp']
                    else f"X:XX:XX / {str(datetime.timedelta(seconds=int(totalTime)))}"
                )
                DrumsMacroTab.timelineIndicator.configure(text=timelineText)
            logger.debug("stopPlayback completed")
    except Exception as e:
        logger.exception(f"stopPlayback error: {e}")

def pausePlayback():
    logger.info("pausePlayback called")
    try:
        if not app.isRunning:
            return

        paused = False
        midiHandler.pausePlayback()
        paused = midiHandler.paused
        logger.debug(f"midiHandler.paused: {paused}")

        if paused:
            DrumsMacroTab.playButton.configure(
                text="Paused",
                fg_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PausedColor"],
                hover_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PausedColorHover"]
            )
        else:
            DrumsMacroTab.playButton.configure(
                text="Playing",
                fg_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PlayingColor"],
                hover_color=customTheme.activeThemeData["Theme"]["DrumsMacro"]["PlayingColorHover"]
            )
        logger.debug("pausePlayback state updated")
    except Exception as e:
        logger.exception(f"pausePlayback error: {e}")

def setSpeed(speed):
    logger.info(f"setSpeed called with speed: {speed}")
    try:
        midiHandler.playbackSpeed = max(0.01, min(5.0, speed / 100.0))
        app.playbackSpeed = round(midiHandler.playbackSpeed * 100)

        DrumsMacroTab.speedSlider.set(app.playbackSpeed)
        DrumsMacroTab.speedValueEntry.delete(0, "end")
        DrumsMacroTab.speedValueEntry.insert(0, str(app.playbackSpeed))
        logger.debug(f"playbackSpeed set to: {midiHandler.playbackSpeed}, app.playbackSpeed: {app.playbackSpeed}")
    except Exception as e:
        logger.exception(f"setSpeed error: {e}")

def decreaseSpeed():
    logger.info("decreaseSpeed called")
    try:
        midiHandler.changeSpeed(-(configuration.configData["drumsMacro"]["decreaseSize"] / 100))
        app.playbackSpeed = round(midiHandler.playbackSpeed * 100)

        DrumsMacroTab.speedSlider.set(app.playbackSpeed)
        DrumsMacroTab.speedValueEntry.delete(0, "end")
        DrumsMacroTab.speedValueEntry.insert(0, str(app.playbackSpeed))
        logger.debug(f"decreased speed to: {midiHandler.playbackSpeed}")
    except Exception as e:
        logger.exception(f"decreaseSpeed error: {e}")

def increaseSpeed():
    logger.info("increaseSpeed called")
    try:
        midiHandler.changeSpeed(configuration.configData["drumsMacro"]["decreaseSize"] / 100)
        app.playbackSpeed = round(midiHandler.playbackSpeed * 100)

        DrumsMacroTab.speedSlider.set(app.playbackSpeed)
        DrumsMacroTab.speedValueEntry.delete(0, "end")
        DrumsMacroTab.speedValueEntry.insert(0, str(app.playbackSpeed))
        logger.debug(f"increased speed to: {midiHandler.playbackSpeed}")
    except Exception as e:
        logger.exception(f"increaseSpeed error: {e}")
