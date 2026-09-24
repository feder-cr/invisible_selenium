"""`Keys`: the special keys, as the W3C WebDriver code points Selenium uses.

⛔ WRITTEN WITH `chr()`, never as string escapes. The code points live in the
Unicode private-use area, and a literal one in the source is an invisible
character a reviewer cannot see and a tool may strip.
"""


class Keys:
    """Set of special keys codes."""

    NULL = chr(0xE000)
    CANCEL = chr(0xE001)  # ^break
    HELP = chr(0xE002)
    BACKSPACE = chr(0xE003)
    BACK_SPACE = BACKSPACE
    TAB = chr(0xE004)
    CLEAR = chr(0xE005)
    RETURN = chr(0xE006)
    ENTER = chr(0xE007)
    SHIFT = chr(0xE008)
    LEFT_SHIFT = SHIFT
    RIGHT_SHIFT = chr(0xE050)
    CONTROL = chr(0xE009)
    LEFT_CONTROL = CONTROL
    RIGHT_CONTROL = chr(0xE051)
    ALT = chr(0xE00A)
    LEFT_ALT = ALT
    RIGHT_ALT = chr(0xE052)
    PAUSE = chr(0xE00B)
    ESCAPE = chr(0xE00C)
    SPACE = chr(0xE00D)
    PAGE_UP = chr(0xE00E)
    PAGE_DOWN = chr(0xE00F)
    END = chr(0xE010)
    HOME = chr(0xE011)
    LEFT = chr(0xE012)
    ARROW_LEFT = LEFT
    UP = chr(0xE013)
    ARROW_UP = UP
    RIGHT = chr(0xE014)
    ARROW_RIGHT = RIGHT
    DOWN = chr(0xE015)
    ARROW_DOWN = DOWN
    INSERT = chr(0xE016)
    DELETE = chr(0xE017)
    SEMICOLON = chr(0xE018)
    EQUALS = chr(0xE019)

    NUMPAD0 = chr(0xE01A)  # number pad keys
    NUMPAD1 = chr(0xE01B)
    NUMPAD2 = chr(0xE01C)
    NUMPAD3 = chr(0xE01D)
    NUMPAD4 = chr(0xE01E)
    NUMPAD5 = chr(0xE01F)
    NUMPAD6 = chr(0xE020)
    NUMPAD7 = chr(0xE021)
    NUMPAD8 = chr(0xE022)
    NUMPAD9 = chr(0xE023)
    MULTIPLY = chr(0xE024)
    ADD = chr(0xE025)
    SEPARATOR = chr(0xE026)
    SUBTRACT = chr(0xE027)
    DECIMAL = chr(0xE028)
    DIVIDE = chr(0xE029)

    F1 = chr(0xE031)  # function keys
    F2 = chr(0xE032)
    F3 = chr(0xE033)
    F4 = chr(0xE034)
    F5 = chr(0xE035)
    F6 = chr(0xE036)
    F7 = chr(0xE037)
    F8 = chr(0xE038)
    F9 = chr(0xE039)
    F10 = chr(0xE03A)
    F11 = chr(0xE03B)
    F12 = chr(0xE03C)

    META = chr(0xE03D)
    LEFT_META = META
    RIGHT_META = chr(0xE053)
    COMMAND = chr(0xE03D)
    LEFT_COMMAND = COMMAND
    ZENKAKU_HANKAKU = chr(0xE040)

    OPTION = ALT
    LEFT_OPTION = LEFT_ALT
    RIGHT_OPTION = RIGHT_ALT


__all__ = ["Keys"]
