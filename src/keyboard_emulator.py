"""
Keyboard emulation module for sending text to target applications.
Supports both direct typing and clipboard-based input for Chinese text.
"""

import logging
import time
from typing import Optional, List, Union
from enum import Enum

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from config import KeyboardConfig, get_config


logger = logging.getLogger(__name__)


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

        # Hotkey handlers
        self._hotkey_handlers: dict[str, callable] = {}

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
            # Check for hotkeys (only when ALT is not pressed)
            elif not self.alt_pressed:
                key_str = self._key_to_string(key)
                if key_str in self._hotkey_handlers:
                    self._hotkey_handlers[key_str]()

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
