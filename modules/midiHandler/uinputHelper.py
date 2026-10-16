import logging
import atexit

logger = logging.getLogger("nanoMIDIPlayer")

try:
    import evdev
    from evdev import ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    evdev = None
    ecodes = None

_uinputDevice = None
_initAttempted = False

KEY_MAP = {}
if EVDEV_AVAILABLE:
    KEY_MAP = {
        # Lowercase letters
        'a': ecodes.KEY_A, 'b': ecodes.KEY_B, 'c': ecodes.KEY_C, 'd': ecodes.KEY_D,
        'e': ecodes.KEY_E, 'f': ecodes.KEY_F, 'g': ecodes.KEY_G, 'h': ecodes.KEY_H,
        'i': ecodes.KEY_I, 'j': ecodes.KEY_J, 'k': ecodes.KEY_K, 'l': ecodes.KEY_L,
        'm': ecodes.KEY_M, 'n': ecodes.KEY_N, 'o': ecodes.KEY_O, 'p': ecodes.KEY_P,
        'q': ecodes.KEY_Q, 'r': ecodes.KEY_R, 's': ecodes.KEY_S, 't': ecodes.KEY_T,
        'u': ecodes.KEY_U, 'v': ecodes.KEY_V, 'w': ecodes.KEY_W, 'x': ecodes.KEY_X,
        'y': ecodes.KEY_Y, 'z': ecodes.KEY_Z,
        # Uppercase letters
        'A': ecodes.KEY_A, 'B': ecodes.KEY_B, 'C': ecodes.KEY_C, 'D': ecodes.KEY_D,
        'E': ecodes.KEY_E, 'F': ecodes.KEY_F, 'G': ecodes.KEY_G, 'H': ecodes.KEY_H,
        'I': ecodes.KEY_I, 'J': ecodes.KEY_J, 'K': ecodes.KEY_K, 'L': ecodes.KEY_L,
        'M': ecodes.KEY_M, 'N': ecodes.KEY_N, 'O': ecodes.KEY_O, 'P': ecodes.KEY_P,
        'Q': ecodes.KEY_Q, 'R': ecodes.KEY_R, 'S': ecodes.KEY_S, 'T': ecodes.KEY_T,
        'U': ecodes.KEY_U, 'V': ecodes.KEY_V, 'W': ecodes.KEY_W, 'X': ecodes.KEY_X,
        'Y': ecodes.KEY_Y, 'Z': ecodes.KEY_Z,
        # Numbers
        '0': ecodes.KEY_0, '1': ecodes.KEY_1, '2': ecodes.KEY_2, '3': ecodes.KEY_3,
        '4': ecodes.KEY_4, '5': ecodes.KEY_5, '6': ecodes.KEY_6, '7': ecodes.KEY_7,
        '8': ecodes.KEY_8, '9': ecodes.KEY_9,
        # Modifiers and special keys
        'shift': ecodes.KEY_LEFTSHIFT, 'left_shift': ecodes.KEY_LEFTSHIFT, 'right_shift': ecodes.KEY_RIGHTSHIFT,
        'ctrl': ecodes.KEY_LEFTCTRL, 'left_ctrl': ecodes.KEY_LEFTCTRL, 'right_ctrl': ecodes.KEY_RIGHTCTRL,
        'alt': ecodes.KEY_LEFTALT, 'left_alt': ecodes.KEY_LEFTALT, 'right_alt': ecodes.KEY_RIGHTALT,
        'space': ecodes.KEY_SPACE, ' ': ecodes.KEY_SPACE,
        # Common punctuation & symbols
        '-': ecodes.KEY_MINUS, '=': ecodes.KEY_EQUAL,
        '[': ecodes.KEY_LEFTBRACE, ']': ecodes.KEY_RIGHTBRACE,
        ';': ecodes.KEY_SEMICOLON, "'": ecodes.KEY_APOSTROPHE,
        '\\': ecodes.KEY_BACKSLASH, ',': ecodes.KEY_COMMA,
        '.': ecodes.KEY_DOT, '/': ecodes.KEY_SLASH,
        '`': ecodes.KEY_GRAVE, '\t': ecodes.KEY_TAB,
        'enter': ecodes.KEY_ENTER, 'tab': ecodes.KEY_TAB,
        'backspace': ecodes.KEY_BACKSPACE, 'esc': ecodes.KEY_ESC,
        # Shifted number/symbol fallback
        '!': ecodes.KEY_1, '@': ecodes.KEY_2, '#': ecodes.KEY_3, '$': ecodes.KEY_4,
        '%': ecodes.KEY_5, '^': ecodes.KEY_6, '&': ecodes.KEY_7, '*': ecodes.KEY_8,
        '(': ecodes.KEY_9, ')': ecodes.KEY_0, '_': ecodes.KEY_MINUS, '+': ecodes.KEY_EQUAL,
        '{': ecodes.KEY_LEFTBRACE, '}': ecodes.KEY_RIGHTBRACE, ':': ecodes.KEY_SEMICOLON,
        '"': ecodes.KEY_APOSTROPHE, '|': ecodes.KEY_BACKSLASH, '<': ecodes.KEY_COMMA,
        '>': ecodes.KEY_DOT, '?': ecodes.KEY_SLASH, '~': ecodes.KEY_GRAVE,
    }

BLOCKED_KEYS = {f"f{i}" for i in range(1, 13)} | {"tab", "backspace", "esc"}


def toKeyName(key):
    if hasattr(key, "name") and key.name:
        return key.name.lower()
    return str(key)


def _logMsg(msg):
    try:
        from modules.functions import mainFunctions
        mainFunctions.log(msg)
    except Exception:
        pass


def getUInputDevice():
    global _uinputDevice, _initAttempted
    if _uinputDevice is not None:
        return _uinputDevice
    if _initAttempted:
        return None
    _initAttempted = True

    if not EVDEV_AVAILABLE:
        logger.error("evdev package is not installed. uinput backend unavailable.")
        _logMsg("Error: evdev is not installed. uinput unavailable.")
        return None

    try:
        _uinputDevice = evdev.UInput(name="nanoMIDIPlayer-Virtual-Keyboard")
        logger.info("uinput virtual keyboard successfully initialized (/dev/uinput)")
        _logMsg("uinput virtual keyboard initialized successfully.")
        return _uinputDevice
    except PermissionError:
        msg = (
            "Permission denied for /dev/uinput. To enable uinput under Wayland:\n"
            "1. sudo usermod -aG input $USER\n"
            "2. echo 'KERNEL==\"uinput\", MODE=\"0660\", GROUP=\"input\", TAG+=\"uaccess\"' | sudo tee /etc/udev/rules.d/99-uinput.rules\n"
            "3. sudo udevadm control --reload-rules && sudo udevadm trigger"
        )
        logger.error(msg)
        _logMsg("Permission denied for /dev/uinput. See log for setup instructions.")
        return None
    except Exception as e:
        logger.exception("Failed to initialize uinput device: %s", e)
        _logMsg(f"Failed to initialize uinput: {e}")
        return None


def pressKey(key):
    device = getUInputDevice()
    if not device:
        return False
    keyName = toKeyName(key)
    if keyName.lower() in BLOCKED_KEYS:
        return False
    code = KEY_MAP.get(keyName) or KEY_MAP.get(keyName.lower())
    if code is None:
        logger.warning("Unsupported key for uinput: %s", key)
        return False
    try:
        device.write(ecodes.EV_KEY, code, 1)
        device.syn()
        return True
    except Exception as e:
        logger.error("Error writing key press to uinput: %s", e)
        return False


def releaseKey(key):
    device = getUInputDevice()
    if not device:
        return False
    keyName = toKeyName(key)
    if keyName.lower() in BLOCKED_KEYS:
        return False
    code = KEY_MAP.get(keyName) or KEY_MAP.get(keyName.lower())
    if code is None:
        return False
    try:
        device.write(ecodes.EV_KEY, code, 0)
        device.syn()
        return True
    except Exception as e:
        logger.error("Error writing key release to uinput: %s", e)
        return False


def closeUInputDevice():
    global _uinputDevice, _initAttempted
    if _uinputDevice is not None:
        try:
            _uinputDevice.close()
        except Exception:
            pass
        _uinputDevice = None
    _initAttempted = False


atexit.register(closeUInputDevice)
