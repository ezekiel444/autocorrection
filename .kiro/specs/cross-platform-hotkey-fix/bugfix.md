# Bugfix Requirements Document

## Introduction

The autocorrection-tw system tray application fails to respond to global hotkeys (Ctrl+Alt+C and Ctrl+Alt+A) on Windows, and has limited cross-platform support overall. The root causes are:

1. **Hotkey key matching is too restrictive**: The pynput listener only registers `ctrl_l` (left Ctrl) and `alt_l` (left Alt), so pressing the right-side modifier keys does not trigger the hotkey. Additionally, pynput reports key presses differently on Windows vs Linux (e.g., `Key.ctrl_l` vs the actual key object), causing subset matching to fail silently.
2. **Clipboard backend is Linux-only**: `text_capture.py` prioritizes `xclip`/`xsel` (Linux tools) and the pyperclip fallback detection may fail silently on Windows, leaving no working clipboard backend.
3. **Notifications are Linux-only**: `NotificationManager` shells out to `notify-send`, which does not exist on Windows, so the user gets no feedback even if the hotkey did fire.
4. **No startup feedback on failure**: If pynput fails to import or the listener fails to start, the application provides no visible indication to the user that hotkeys are disabled.

These issues combine to produce a completely non-functional experience on Windows and a fragile experience on Linux when right-side modifier keys are used.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the user presses Ctrl+Alt+C or Ctrl+Alt+A using the right Ctrl or right Alt key THEN the system does not trigger the hotkey callback because only `Key.ctrl_l` and `Key.alt_l` are matched

1.2 WHEN the application runs on Windows THEN the hotkey listener may fail to match key presses because pynput reports Windows virtual key codes differently than the `KeyCode.from_char()` objects stored in the hotkey set

1.3 WHEN the application runs on Windows and attempts to read the clipboard THEN the system raises a CaptureError because `xclip` and `xsel` are not available, and pyperclip fallback detection relies on `shutil.which()` which does not find a clipboard tool

1.4 WHEN the application runs on Windows and attempts to send a desktop notification THEN the system silently fails because `notify-send` is a Linux-only command and no Windows notification mechanism is provided

1.5 WHEN pynput fails to import or the keyboard listener fails to start THEN the system only logs a warning with no visible feedback to the user (no notification, no console message, no tray icon change)

### Expected Behavior (Correct)

2.1 WHEN the user presses Ctrl+Alt+C or Ctrl+Alt+A using either left or right Ctrl/Alt keys THEN the system SHALL trigger the corresponding hotkey callback regardless of which physical modifier key is used

2.2 WHEN the application runs on Windows THEN the hotkey listener SHALL correctly detect and match key combinations using platform-appropriate key comparison logic

2.3 WHEN the application runs on Windows and attempts to read or write the clipboard THEN the system SHALL use a Windows-compatible clipboard backend (pyperclip or win32 API) without requiring xclip or xsel

2.4 WHEN the application runs on Windows and needs to send a desktop notification THEN the system SHALL use a Windows-native notification mechanism (e.g., win10toast, plyer, or Windows toast notifications) to display the notification

2.5 WHEN pynput fails to import or the keyboard listener fails to start THEN the system SHALL provide visible feedback to the user via a notification, tray icon status change to ERROR, or a printed console message indicating that hotkeys are not available

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the application runs on Linux with xclip or xsel installed THEN the system SHALL CONTINUE TO use xclip/xsel as the primary clipboard backend

3.2 WHEN the application runs on Linux with notify-send available THEN the system SHALL CONTINUE TO use notify-send for desktop notifications

3.3 WHEN the user presses Ctrl+Alt+C using the left Ctrl and left Alt keys on Linux THEN the system SHALL CONTINUE TO trigger the analyze callback as before

3.4 WHEN clipboard monitoring is enabled THEN the system SHALL CONTINUE TO detect clipboard changes, filter by length, and prevent feedback loops from self-originated writes

3.5 WHEN the hotkey listener is running and the user presses unrelated key combinations THEN the system SHALL CONTINUE TO ignore those key presses without triggering any callbacks

3.6 WHEN the API Gateway is unreachable THEN the system SHALL CONTINUE TO show an error notification and set status to ERROR without crashing
