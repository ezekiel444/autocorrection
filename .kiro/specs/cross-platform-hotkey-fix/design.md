# Cross-Platform Hotkey Fix - Bugfix Design

## Overview

The autocorrection-tw system tray application is non-functional on Windows and partially broken on Linux when right-side modifier keys are used. The bug stems from four interrelated issues: (1) hotkey matching only recognizes left-side modifier keys, (2) clipboard operations depend on Linux-only tools, (3) notifications use a Linux-only command, and (4) no visible feedback is provided when the hotkey system fails to initialize. The fix will introduce platform-aware logic across the hotkey manager, clipboard backend, and notification system while preserving all existing Linux behavior.

## Glossary

- **Bug_Condition (C)**: The set of conditions under which the hotkey system fails — right-side modifier keys, Windows platform without xclip/xsel, Windows platform without notify-send, or pynput import failure
- **Property (P)**: The desired behavior — hotkeys trigger callbacks regardless of modifier side or platform, clipboard operations succeed on all platforms, notifications display on all platforms, and failures are visibly reported
- **Preservation**: Existing Linux behavior (xclip/xsel clipboard, notify-send notifications, left-modifier hotkeys) must remain unchanged
- **HotkeyManager**: The class in `app/main.py` that registers and listens for global keyboard shortcuts using pynput
- **ClipboardBackend**: The enum in `app/text_capture.py` that determines which clipboard tool is used
- **NotificationManager**: The class in `app/main.py` that sends desktop notifications via subprocess

## Bug Details

### Bug Condition

The bug manifests in four scenarios: (1) when the user presses a hotkey using right-side Ctrl or Alt keys, (2) when the application runs on Windows and pynput reports key codes differently, (3) when the application runs on Windows and attempts clipboard or notification operations using Linux-only tools, and (4) when pynput fails to load with no user feedback.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SystemEvent (key press, clipboard operation, notification, or startup)
  OUTPUT: boolean

  RETURN (input.type == "key_press"
          AND input.modifier IN [Key.ctrl_r, Key.alt_r]
          AND hotkey_set only contains [Key.ctrl_l, Key.alt_l])
         OR (input.type == "key_press"
             AND platform == "win32"
             AND pynput_key_representation != KeyCode.from_char(expected))
         OR (input.type == "clipboard_operation"
             AND platform == "win32"
             AND NOT shutil.which("xclip")
             AND NOT shutil.which("xsel")
             AND pyperclip_not_configured_for_windows)
         OR (input.type == "notification"
             AND platform == "win32"
             AND NOT shutil.which("notify-send"))
         OR (input.type == "startup"
             AND (pynput_import_fails OR listener_start_fails)
             AND no_visible_feedback_provided)
END FUNCTION
```

### Examples

- **Right Ctrl+Alt+C on Linux**: User presses right Ctrl + right Alt + C. The `_active_keys` set contains `Key.ctrl_r` and `Key.alt_r`, but the hotkey set expects `Key.ctrl_l` and `Key.alt_l`. The subset check fails, callback is never invoked.
- **Ctrl+Alt+C on Windows**: User presses left Ctrl + left Alt + C on Windows. Pynput reports the key as a platform-specific virtual key code that does not match the `KeyCode.from_char('c')` object stored in the hotkey set. Callback is never invoked.
- **Clipboard read on Windows**: Application calls `capture_and_validate()`. `shutil.which("xclip")` returns None, `shutil.which("xsel")` returns None, pyperclip import may succeed but paste returns empty or raises. User gets a CaptureError with no working fallback.
- **Notification on Windows**: Application calls `_send_notification()`. `subprocess.run(["notify-send", ...])` raises `FileNotFoundError`. The exception is caught and logged, but user sees nothing.
- **pynput unavailable**: pynput is not installed. `ImportError` is caught, `logger.warning()` is called, but no notification, no tray icon change, and no console output reaches the user.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- On Linux with xclip or xsel installed, the system continues to use xclip/xsel as the primary clipboard backend
- On Linux with notify-send available, the system continues to use notify-send for desktop notifications
- Left Ctrl + left Alt + C on Linux continues to trigger the analyze callback exactly as before
- Clipboard monitoring continues to detect changes, filter by length, and prevent feedback loops from self-originated writes
- Unrelated key combinations continue to be ignored without triggering callbacks
- When the API Gateway is unreachable, the system continues to show an error notification and set status to ERROR without crashing

**Scope:**
All inputs that do NOT involve right-side modifier keys, Windows-specific platform detection, or pynput initialization failure should be completely unaffected by this fix. This includes:
- Left-modifier hotkey presses on Linux (existing working path)
- Clipboard operations on Linux with xclip/xsel available
- Notification delivery on Linux with notify-send available
- All API communication logic
- All clipboard monitoring logic (polling, length filtering, self-originated detection)

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Restrictive Modifier Key Matching**: In `HotkeyManager.start()`, the `_parse_hotkey` function maps `"ctrl"` to `keyboard.Key.ctrl_l` and `"alt"` to `keyboard.Key.alt_l` exclusively. When the user presses `Key.ctrl_r` or `Key.alt_r`, these keys are added to `_active_keys` but never match the hotkey set because `Key.ctrl_l != Key.ctrl_r`.

2. **Platform-Specific Key Representation**: On Windows, pynput may report key presses using `vk` (virtual key code) attributes rather than matching `KeyCode.from_char()` objects directly. The equality check in `key_set.issubset(self._active_keys)` fails because the key objects are not equal even though they represent the same logical key.

3. **Linux-Only Clipboard Detection**: `_detect_clipboard_backend()` in `text_capture.py` checks for `xclip` and `xsel` first (Linux tools), then falls back to pyperclip import. On Windows, neither xclip nor xsel exists, and pyperclip may not be installed or configured, resulting in `CaptureError`.

4. **Linux-Only Notification Command**: `NotificationManager._send_notification()` hardcodes `notify-send` as the notification command. On Windows, this binary does not exist, causing `FileNotFoundError` which is silently caught.

5. **Silent Failure on Initialization**: When pynput import fails or the listener fails to start, only `logger.warning()` or `logger.error()` is called. No notification is sent, no tray icon status change occurs, and no console message is printed.

## Correctness Properties

Property 1: Bug Condition - Cross-Platform Hotkey Detection

_For any_ key press event where the user presses a registered hotkey combination using either left or right modifier keys on any supported platform (Linux, Windows), the fixed `HotkeyManager` SHALL trigger the registered callback function, regardless of which physical modifier key (left or right) is used and regardless of the platform's key representation format.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Existing Linux Behavior Unchanged

_For any_ input that does NOT involve right-side modifier keys, Windows platform operations, or pynput initialization failure, the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing Linux clipboard operations (xclip/xsel), Linux notifications (notify-send), left-modifier hotkey detection, clipboard monitoring, and API communication.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `app/main.py`

**Function**: `HotkeyManager.start()` → `_parse_hotkey` inner function

**Specific Changes**:
1. **Normalize Modifier Keys**: Map both left and right variants to a canonical form. When building the hotkey set, include both `Key.ctrl_l` and `Key.ctrl_r` for `"ctrl"`, both `Key.alt_l` and `Key.alt_r` for `"alt"`, and both `Key.shift_l` and `Key.shift_r` for `"shift"`. Alternatively, normalize pressed keys in `on_press`/`on_release` to their left variant before adding to `_active_keys`.

2. **Platform-Aware Key Comparison**: In the `on_press` handler, normalize key objects before comparison. For character keys, compare using the `.char` attribute (if available) or `.vk` attribute to handle Windows virtual key codes. Implement a `_normalize_key()` helper that returns a canonical representation.

3. **Visible Failure Feedback**: When pynput import fails or listener start fails, call `self._update_status(AppStatus.ERROR)` (if tray icon exists) and print a message to stderr. Add a `hotkeys_available` property to `HotkeyManager` so the `SystemTrayApp` can check and notify the user.

---

**File**: `app/text_capture.py`

**Function**: `_detect_clipboard_backend()`

**Specific Changes**:
4. **Platform-Aware Backend Detection**: Add `sys.platform` check at the top of `_detect_clipboard_backend()`. On Windows (`sys.platform == "win32"`), skip xclip/xsel detection and go directly to pyperclip (which uses win32 APIs on Windows). Ensure pyperclip is listed as a dependency. Optionally add a `WIN32` backend that uses `ctypes` to call Windows clipboard APIs directly as a fallback.

5. **Add Windows Clipboard Backend**: Add a `ClipboardBackend.WIN32` enum value. Implement `_read_from_backend` and `_write_to_backend` cases for WIN32 using either pyperclip (which internally uses win32 clipboard) or direct ctypes calls to `OpenClipboard`/`GetClipboardData`/`CloseClipboard`.

---

**File**: `app/main.py`

**Function**: `NotificationManager._send_notification()`

**Specific Changes**:
6. **Cross-Platform Notification Dispatch**: Add platform detection to `_send_notification()`. On Windows, use either `plyer.notification` (cross-platform library), `win10toast`, or the built-in `ctypes` approach with Windows toast notifications. On Linux, continue using `notify-send`. On macOS (future), use `osascript`.

7. **Graceful Degradation**: If no notification backend is available on any platform, fall back to `print()` to stderr so the user gets at least console feedback.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write unit tests that simulate key press events with right-side modifiers and verify callback invocation. Mock pynput key objects to simulate Windows key representations. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **Right Ctrl+Alt+C Test**: Simulate pressing `Key.ctrl_r` + `Key.alt_r` + `KeyCode('c')` and assert the analyze callback is invoked (will fail on unfixed code)
2. **Windows Key Representation Test**: Simulate a key press where pynput reports a `vk`-based KeyCode instead of `from_char()` and assert matching works (will fail on unfixed code)
3. **Windows Clipboard Test**: Mock `shutil.which` to return None for xclip/xsel and verify clipboard read succeeds via pyperclip (will fail on unfixed code if pyperclip not properly detected)
4. **Windows Notification Test**: Mock `subprocess.run` to raise FileNotFoundError for notify-send and verify notification still reaches user (will fail on unfixed code)
5. **pynput Import Failure Test**: Mock pynput import to raise ImportError and verify visible feedback is provided (will fail on unfixed code)

**Expected Counterexamples**:
- Hotkey callbacks are not invoked when right-side modifiers are used
- Hotkey callbacks are not invoked when Windows-style key objects are in `_active_keys`
- CaptureError raised on Windows with no working clipboard backend
- Notifications silently fail on Windows
- Possible causes: restrictive key matching, platform-specific key representation, Linux-only tool dependencies

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedSystem(input)
  ASSERT expectedBehavior(result)
END FOR
```

Specifically:
- For all modifier key combinations (left/right Ctrl × left/right Alt × character key), assert callback is triggered
- For all Windows key representations, assert matching succeeds
- For clipboard operations on Windows, assert read/write succeeds via pyperclip or win32
- For notifications on Windows, assert user receives visible feedback
- For pynput failure, assert user receives visible indication

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for left-modifier hotkeys on Linux, clipboard operations with xclip/xsel, and notify-send notifications, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Left-Modifier Hotkey Preservation**: Verify that left Ctrl + left Alt + registered key continues to trigger callbacks exactly as before
2. **Linux Clipboard Preservation**: Verify that on Linux with xclip available, clipboard read/write uses xclip and returns identical results
3. **Linux Notification Preservation**: Verify that on Linux with notify-send, notifications are sent with the same arguments
4. **Clipboard Monitor Preservation**: Verify that clipboard monitoring (polling, length filtering, self-originated detection) continues to work identically
5. **Unrelated Key Preservation**: Verify that pressing non-hotkey combinations does not trigger any callbacks
6. **API Error Handling Preservation**: Verify that API failures continue to produce error notifications and ERROR status

### Unit Tests

- Test `_parse_hotkey` with both left and right modifier variants
- Test `_normalize_key` helper with various pynput key objects (Linux and Windows representations)
- Test `_detect_clipboard_backend` on mocked Windows platform (no xclip/xsel)
- Test `_detect_clipboard_backend` on mocked Linux platform (xclip available)
- Test `_send_notification` on mocked Windows platform (no notify-send)
- Test `_send_notification` on mocked Linux platform (notify-send available)
- Test `HotkeyManager.start()` when pynput import fails — verify visible feedback
- Test `validate_hotkey` unchanged behavior

### Property-Based Tests

- Generate random modifier combinations (left/right × ctrl/alt/shift) and verify all trigger the callback when combined with the registered character key
- Generate random key press sequences and verify only registered hotkeys trigger callbacks (no false positives)
- Generate random text strings and verify clipboard round-trip (write then read) preserves content on all platforms
- Generate random notification parameters and verify they reach the platform-appropriate backend

### Integration Tests

- Test full correction flow with right-modifier hotkey press → clipboard read → API call → notification
- Test full correction flow on mocked Windows environment end-to-end
- Test application startup with pynput unavailable → verify user feedback and graceful degradation
- Test clipboard monitoring continues to work after hotkey system initialization failure
