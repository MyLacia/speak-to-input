"""
Keyboard emulation module for sending text to target applications.
Supports both direct typing and clipboard-based input for Chinese text.
Also includes mouse listener for left-button long-press trigger with cursor detection.
"""

import logging
import time
from typing import Optional, List, Union, Callable
from enum import Enum
import threading
import ctypes
from ctypes import wintypes

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from config import KeyboardConfig, get_config


logger = logging.getLogger(__name__)


# =============================================================================
# Windows API for cursor detection
# =============================================================================

# Windows API types and functions
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Define Windows types
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

# Constants
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
GW_CHILD = 5
GW_HWNDNEXT = 2

# Window class names that typically have editable text input
EDITABLE_WINDOW_CLASSES = {
    'Edit', 'TextBox', 'RichEdit', 'RichEdit20A', 'RichEdit20W',
    'ComboBox', 'ListBox', 'SysListView32', 'SysTreeView32',
    # Browser edit controls
    'Chrome_WidgetWin_1', 'MozillaWindowClass', 'Internet Explorer_Server',
    # Common app classes
    'ThunderTextBox', 'ThunderCommandButton', 'TXTextControl',
    # WebView/Chromium based
    'Chrome_RenderWidgetHostHWND', 'Chromium',
}

# Window titles that suggest editable input
EDITABLE_WINDOW_TITLES = {
    'notepad', 'text', 'input', 'search', 'find', 'replace',
    '记事本', '输入', '搜索', '查找', '替换'
}


def get_focused_window_info() -> tuple:
    """
    Get information about the currently focused window.

    Returns:
        tuple: (hwnd, title, class_name) or (None, None, None) if no window
    """
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None, None

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buffer = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buffer, length)
        title = buffer.value

        # Get window class name
        class_name_len = 256
        class_buffer = ctypes.create_unicode_buffer(class_name_len)
        user32.GetClassNameW(hwnd, class_buffer, class_name_len)
        class_name = class_buffer.value

        return hwnd, title, class_name
    except Exception as e:
        logger.debug(f"Error getting focused window: {e}")
        return None, None, None


def is_command_window_focused() -> bool:
    """
    Check if the currently focused window is a command prompt/terminal window.

    Returns:
        True if the focused window is a terminal/command window
    """
    hwnd, title, class_name = get_focused_window_info()

    if not hwnd:
        return False

    # Check window class names for known terminal/console windows
    terminal_classes = {
        'ConsoleWindowClass',  # Windows Console
        'CASCADIA_HOSTING_WINDOW_CLASS',  # Windows Terminal
        'VirtualConsoleClass',  # Some terminal emulators
        'PuTTYClass',  # PuTTY SSH client
    }

    if class_name in terminal_classes:
        return True

    # Check window title for common terminal indicators
    if title:
        title_lower = title.lower()
        terminal_indicators = [
            'command prompt', 'cmd', 'powershell', 'terminal',
            '命令提示符', '命令行', '终端', 'python',
        ]
        if any(indicator in title_lower for indicator in terminal_indicators):
            return True

    return False


def has_editable_cursor() -> bool:
    """
    Check if the currently focused window has an editable text cursor.

    This uses multiple heuristics:
    1. Window class name check
    2. Window title check
    3. Cursor shape check (IBeam cursor)

    Returns:
        True if the window likely has an editable text input
    """
    hwnd, title, class_name = get_focused_window_info()

    if not hwnd:
        return False

    # Check 1: Window class name
    if class_name:
        # Direct match for known editable classes
        if any(editable_class.lower() in class_name.lower()
               for editable_class in EDITABLE_WINDOW_CLASSES):
            logger.debug(f"Editable cursor detected by class: {class_name}")
            return True

    # Check 2: Window title
    if title:
        title_lower = title.lower()
        if any(keyword in title_lower for keyword in EDITABLE_WINDOW_TITLES):
            logger.debug(f"Editable cursor detected by title: {title}")
            return True

    # Check 3: Cursor shape (IBeam = text cursor)
    try:
        # Get cursor info
        class CURSORINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('flags', wintypes.DWORD),
                ('hCursor', wintypes.HCURSOR),
                ('ptScreenPos', wintypes.POINT),
            ]

        cursor_info = CURSORINFO()
        cursor_info.cbSize = ctypes.sizeof(CURSORINFO)

        if user32.GetCursorInfo(ctypes.byref(cursor_info)):
            # Check if it's an IBeam cursor (IDC_IBEAM = 32514)
            # IBeam cursor indicates text input position
            if cursor_info.hCursor:
                # 32514 is the IBeam cursor handle
                # We check if the cursor is likely an IBeam
                cursor_type = user32.GetCursor()
                # Common IBeam cursor values
                if cursor_type in (32514, 65541, 65543):
                    logger.debug(f"Editable cursor detected by cursor shape: {cursor_type}")
                    return True
    except Exception as e:
        logger.debug(f"Cursor check failed: {e}")

    return False


class InputMethod(Enum):
    """Text input methods"""
    DIRECT = "direct"  # Direct keystroke simulation
    CLIPBOARD = "clipboard"  # Clipboard + Ctrl+V paste


class KeyboardEmulator:
    """Emulate keyboard input to send text to applications"""

    def __init__(self, config: Optional[KeyboardConfig] = None):
        """
        Args:
            config: Keyboard configuration
        """
        self.config = config or get_config().keyboard
        self.controller = keyboard.Controller()
        self.input_method = InputMethod(self.config.method)

        # Store previous clipboard content
        self._previous_clipboard: Optional[str] = None

    def _save_clipboard(self) -> None:
        """Save current clipboard content"""
        if CLIPBOARD_AVAILABLE:
            try:
                self._previous_clipboard = pyperclip.paste()
            except Exception as e:
                logger.debug(f"Failed to save clipboard: {e}")

    def _restore_clipboard(self) -> None:
        """Restore previous clipboard content"""
        if CLIPBOARD_AVAILABLE and self._previous_clipboard is not None:
            try:
                pyperclip.copy(self._previous_clipboard)
            except Exception as e:
                logger.debug(f"Failed to restore clipboard: {e}")

    def send_text(self, text: str, restore_clipboard: bool = True) -> bool:
        """
        Send text to the active application.

        Args:
            text: Text to send
            restore_clipboard: Whether to restore clipboard after pasting

        Returns:
            True if successful
        """
        if not text:
            return False

        try:
            if self.input_method == InputMethod.CLIPBOARD:
                return self._send_via_clipboard(text, restore_clipboard)
            else:
                return self._send_via_typing(text)

        except Exception as e:
            logger.error(f"Failed to send text: {e}")
            return False

    def _send_via_clipboard(self, text: str, restore_clipboard: bool) -> bool:
        """Send text using clipboard + Ctrl+V paste"""
        if not CLIPBOARD_AVAILABLE:
            logger.warning("Clipboard method not available, falling back to direct")
            return self._send_via_typing(text)

        try:
            # Save current clipboard
            if restore_clipboard:
                self._save_clipboard()

            # Copy text to clipboard
            pyperclip.copy(text)
            time.sleep(0.01)  # Small delay to ensure copy completes

            # Simulate Ctrl+V to paste
            with self.controller.pressed(Key.ctrl_l):
                self.controller.press(KeyCode.from_char("v"))
                self.controller.release(KeyCode.from_char("v"))

            # Wait for paste to complete
            time.sleep(self.config.paste_delay)

            # Restore clipboard
            if restore_clipboard:
                self._restore_clipboard()

            logger.debug(f"Sent text via clipboard: {len(text)} chars")
            return True

        except Exception as e:
            logger.error(f"Clipboard input failed: {e}")
            return False

    def _send_via_typing(self, text: str) -> bool:
        """Send text by simulating individual keystrokes"""
        try:
            for char in text:
                if char == "\n":
                    self.controller.press(Key.enter)
                    self.controller.release(Key.enter)
                elif char == "\t":
                    self.controller.press(Key.tab)
                    self.controller.release(Key.tab)
                elif char == " ":
                    self.controller.press(Key.space)
                    self.controller.release(Key.space)
                else:
                    # Type the character
                    self.controller.type(char)

                time.sleep(self.config.typing_speed)

            logger.debug(f"Sent text via typing: {len(text)} chars")
            return True

        except Exception as e:
            logger.error(f"Direct typing failed: {e}")
            return False

    def send_key(self, key: Union[Key, KeyCode, str]) -> None:
        """
        Send a single key press.

        Args:
            key: Key to send (Key, KeyCode, or single character string)
        """
        try:
            if isinstance(key, str) and len(key) == 1:
                self.controller.press(key)
                self.controller.release(key)
            else:
                self.controller.press(key)
                self.controller.release(key)
        except Exception as e:
            logger.error(f"Failed to send key: {e}")

    def send_hotkey(self, *keys: Union[str, Key]) -> None:
        """
        Send a hotkey combination (all keys pressed together).

        Args:
            *keys: Keys to press (e.g., 'c', Key.ctrl, Key.shift)
        """
        try:
            with self.controller.pressed(*keys[:-1]):
                self.controller.press(keys[-1])
                self.controller.release(keys[-1])
        except Exception as e:
            logger.error(f"Failed to send hotkey: {e}")

    def backspace(self, count: int = 1) -> None:
        """
        Send backspace key.

        Args:
            count: Number of backspaces to send
        """
        for _ in range(count):
            self.send_key(Key.backspace)

    def delete_all(self) -> None:
        """Select all and delete (Ctrl+A, Delete)"""
        with self.controller.pressed(Key.ctrl_l):
            self.controller.press(KeyCode.from_char("a"))
            self.controller.release(KeyCode.from_char("a"))
        time.sleep(0.01)
        self.send_key(Key.delete)


class GlobalKeyListener:
    """Global keyboard event listener for hotkeys and ALT key trigger"""

    def __init__(self):
        self.listener: Optional[keyboard.Listener] = None
        self.is_running = False

        # ALT key state tracking
        self.alt_pressed = False
        self.on_alt_press: Optional[callable] = None
        self.on_alt_release: Optional[callable] = None

        # Hotkey handlers and key press tracking
        self._hotkey_handlers: dict[str, callable] = {}
        self._pressed_keys: set = set()  # Track currently pressed keys

        # Debounce mechanism to prevent duplicate triggers
        self._last_trigger_time: float = 0
        self._debounce_delay: float = 0.3  # 300ms debounce

    def start(self) -> None:
        """Start the global keyboard listener"""
        if self.is_running:
            return

        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        self.is_running = True
        logger.info("Global keyboard listener started")

    def stop(self) -> None:
        """Stop the keyboard listener"""
        if not self.is_running:
            return

        if self.listener:
            self.listener.stop()
            self.listener = None

        self.is_running = False
        logger.info("Global keyboard listener stopped")

    def _trigger_hotkey(self, key_str: str) -> None:
        """Trigger hotkey with debounce protection"""
        import time
        current_time = time.time()

        # Check debounce
        if current_time - self._last_trigger_time < self._debounce_delay:
            logger.debug(f"Hotkey '{key_str}' debounced (too soon)")
            return

        self._last_trigger_time = current_time

        # Trigger the handler
        if key_str in self._hotkey_handlers:
            self._hotkey_handlers[key_str]()

    def _on_press(self, key: Union[Key, KeyCode]) -> None:
        """Handle key press events"""
        try:
            # Check for ALT key press
            if key in (Key.alt_l, Key.alt_r, Key.alt):
                if not self.alt_pressed:
                    self.alt_pressed = True
                    logger.debug("ALT key pressed")
                    if self.on_alt_press:
                        self.on_alt_press()
            # Track hotkey presses (don't trigger yet)
            elif not self.alt_pressed:
                key_str = self._key_to_string(key)
                if key_str in self._hotkey_handlers:
                    if key_str not in self._pressed_keys:
                        self._pressed_keys.add(key_str)
                        logger.debug(f"Key pressed (will trigger on release): {key_str}")

        except Exception as e:
            logger.error(f"Error in on_press: {e}")

    def _on_release(self, key: Union[Key, KeyCode]) -> None:
        """Handle key release events"""
        try:
            # Check for ALT key release
            if key in (Key.alt_l, Key.alt_r, Key.alt):
                if self.alt_pressed:
                    self.alt_pressed = False
                    logger.debug("ALT key released")
                    if self.on_alt_release:
                        self.on_alt_release()
            # Trigger hotkey on release
            else:
                key_str = self._key_to_string(key)
                if key_str in self._pressed_keys:
                    self._pressed_keys.discard(key_str)
                    # Trigger the hotkey with debounce
                    if key_str in self._hotkey_handlers:
                        # Only trigger if command window is focused (for 'c' key)
                        if key_str == 'c':
                            if is_command_window_focused():
                                logger.info(f"Hotkey '{key_str}' triggered on release")
                                self._trigger_hotkey(key_str)
                            else:
                                logger.debug(f"Ignoring hotkey '{key_str}' - command window not focused")
                        else:
                            # Other hotkeys work regardless of focus
                            logger.info(f"Hotkey '{key_str}' triggered on release")
                            self._trigger_hotkey(key_str)

        except Exception as e:
            logger.error(f"Error in on_release: {e}")

    def _key_to_string(self, key: Union[Key, KeyCode]) -> str:
        """Convert a key object to string representation"""
        if isinstance(key, KeyCode):
            if key.char:
                return key.char
            return f"Key.{key.name or 'unknown'}"
        elif isinstance(key, Key):
            return f"Key.{key.name or 'unknown'}"
        return str(key)

    def register_hotkey(self, key_str: str, handler: callable) -> None:
        """
        Register a hotkey handler.

        Args:
            key_str: Key string (e.g., "r" for R key)
            handler: Callback function
        """
        self._hotkey_handlers[key_str] = handler
        logger.debug(f"Registered hotkey: {key_str}")

    def unregister_hotkey(self, key_str: str) -> None:
        """Unregister a hotkey handler"""
        if key_str in self._hotkey_handlers:
            del self._hotkey_handlers[key_str]


# Singleton instances
_emulator_instance: Optional[KeyboardEmulator] = None
_listener_instance: Optional[GlobalKeyListener] = None


def get_emulator() -> KeyboardEmulator:
    """Get singleton keyboard emulator instance"""
    global _emulator_instance
    if _emulator_instance is None:
        _emulator_instance = KeyboardEmulator()
    return _emulator_instance


def get_listener() -> GlobalKeyListener:
    """Get singleton global key listener instance"""
    global _listener_instance
    if _listener_instance is None:
        _listener_instance = GlobalKeyListener()
    return _listener_instance


# =============================================================================
# Global Mouse Listener for left-button long-press trigger
# =============================================================================

class GlobalMouseListener:
    """
    Global mouse listener for left-button long-press trigger.
    Only triggers when an editable cursor is present in the focused window.
    """

    def __init__(self, long_press_delay: float = 0.2):
        """
        Args:
            long_press_delay: Minimum press duration (seconds) to trigger recording
        """
        self.listener: Optional[keyboard.Listener] = None
        self.mouse_listener: Optional["mouse.Listener"] = None
        self.is_running = False

        # Mouse button state tracking
        self.left_button_pressed = False
        self.press_start_time: Optional[float] = None
        self.has_triggered = False
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_timer = threading.Event()

        # Callbacks
        self.on_long_press: Optional[callable] = None
        self.on_release: Optional[callable] = None

        # Configuration
        self.long_press_delay = long_press_delay

        # Import mouse controller
        try:
            from pynput import mouse
            self.mouse = mouse
        except ImportError:
            self.mouse = None
            logger.error("pynput.mouse not available")

    def start(self) -> None:
        """Start the global mouse listener"""
        if self.is_running:
            return

        if not self.mouse:
            logger.error("Cannot start mouse listener: pynput.mouse not available")
            return

        self.mouse_listener = self.mouse.Listener(
            on_click=self._on_click
        )
        self.mouse_listener.start()
        self.is_running = True
        logger.info("Global mouse listener started")

    def stop(self) -> None:
        """Stop the mouse listener"""
        if not self.is_running:
            return

        self._stop_timer.set()

        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener = None

        # Wait for timer thread to finish
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=1.0)

        self.is_running = False
        self._stop_timer.clear()
        logger.info("Global mouse listener stopped")

    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        """Handle mouse click events"""
        try:
            # Only interested in left button
            if button != self.mouse.Button.left:
                return

            if pressed:
                # Left button pressed
                self.left_button_pressed = True
                self.press_start_time = time.time()
                self.has_triggered = False

                # Start timer to check for long press
                self._stop_timer.clear()
                self._timer_thread = threading.Thread(
                    target=self._check_long_press,
                    daemon=True
                )
                self._timer_thread.start()

            else:
                # Left button released
                was_pressed = self.left_button_pressed
                did_trigger = self.has_triggered

                self.left_button_pressed = False
                self.press_start_time = None
                self._stop_timer.set()

                # Trigger release callback if we had triggered recording
                if did_trigger and self.on_release:
                    logger.debug("Mouse long-press released")
                    self.on_release()

        except Exception as e:
            logger.error(f"Error in mouse on_click: {e}")

    def _check_long_press(self) -> None:
        """Check if left button has been pressed long enough"""
        # Wait for the delay
        self._stop_timer.wait(self.long_press_delay)

        if self._stop_timer.is_set():
            return

        if not self.left_button_pressed:
            return

        # Check how long we've been pressing
        if self.press_start_time:
            press_duration = time.time() - self.press_start_time
            if press_duration >= self.long_press_delay:
                # Check if there's an editable cursor
                if has_editable_cursor():
                    # Long press detected!
                    self.has_triggered = True
                    logger.debug(f"Mouse long-press detected ({press_duration:.2f}s)")
                    if self.on_long_press:
                        self.on_long_press()
                else:
                    logger.debug("No editable cursor, ignoring mouse press")


# Singleton instance
_mouse_listener_instance: Optional[GlobalMouseListener] = None


def get_mouse_listener(long_press_delay: float = 0.2) -> GlobalMouseListener:
    """Get singleton global mouse listener instance"""
    global _mouse_listener_instance
    if _mouse_listener_instance is None:
        _mouse_listener_instance = GlobalMouseListener(long_press_delay=long_press_delay)
    return _mouse_listener_instance
