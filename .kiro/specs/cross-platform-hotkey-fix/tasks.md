# Implementation Plan

## Overview

This task list follows the exploratory bugfix workflow to fix the cross-platform hotkey, clipboard, notification, and startup feedback issues. The approach is: (1) write exploration tests to confirm the bug exists, (2) write preservation tests to capture existing correct behavior, (3) implement the fix, and (4) validate everything passes.

## Tasks

- [ ] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Cross-Platform Hotkey Detection Failure
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists across all four bug scenarios
  - **Scoped PBT Approach**: Scope the property to concrete failing cases:
    - Right-side modifier keys (ctrl_r, alt_r) with any registered character key
    - Windows-style key representations (vk-based KeyCode) with registered hotkeys
    - Clipboard detection on Windows (no xclip/xsel available)
    - Notification dispatch on Windows (no notify-send available)
    - pynput import failure with no visible user feedback
  - Test that `HotkeyManager` triggers callback when right Ctrl + right Alt + 'c' is pressed (from Bug Condition: `input.modifier IN [Key.ctrl_r, Key.alt_r] AND hotkey_set only contains [Key.ctrl_l, Key.alt_l]`)
  - Test that `HotkeyManager` triggers callback when Windows vk-based key objects are in `_active_keys` (from Bug Condition: `platform == "win32" AND pynput_key_representation != KeyCode.from_char(expected)`)
  - Test that `_detect_clipboard_backend()` returns a working backend on Windows without xclip/xsel (from Bug Condition: `platform == "win32" AND NOT shutil.which("xclip") AND NOT shutil.which("xsel")`)
  - Test that `NotificationManager._send_notification()` delivers notification on Windows without notify-send (from Bug Condition: `platform == "win32" AND NOT shutil.which("notify-send")`)
  - Test that when pynput import fails, visible feedback is provided to the user (from Bug Condition: `pynput_import_fails AND no_visible_feedback_provided`)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g., "Right Ctrl+Alt+C does not invoke callback", "Windows clipboard raises CaptureError", "No visible feedback on pynput failure")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Linux Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: Write these tests BEFORE implementing the fix
  - Observe behavior on UNFIXED code for non-buggy inputs (cases where isBugCondition returns false):
    - Observe: Left Ctrl + left Alt + 'c' on Linux triggers analyze callback
    - Observe: `_detect_clipboard_backend()` returns XCLIP when xclip is available on Linux
    - Observe: `_send_notification()` calls notify-send with correct arguments on Linux
    - Observe: Clipboard monitor detects changes, filters by length, prevents feedback loops
    - Observe: Unrelated key combinations do not trigger any callbacks
    - Observe: API Gateway unreachable → error notification + ERROR status without crash
  - Write property-based tests capturing observed behavior patterns:
    - For all left-modifier key combinations with registered character keys, callback is triggered (from Preservation Requirements: left Ctrl + left Alt + C continues to trigger analyze callback)
    - For all non-registered key combinations, no callback is triggered (from Preservation Requirements: unrelated key presses are ignored)
    - For clipboard operations on Linux with xclip available, xclip is used as backend (from Preservation Requirements: xclip/xsel remains primary on Linux)
    - For notifications on Linux with notify-send available, notify-send is called (from Preservation Requirements: notify-send continues to be used on Linux)
    - For clipboard text within valid length range, monitoring callback fires; outside range, it does not (from Preservation Requirements: clipboard monitoring unchanged)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3. Fix for cross-platform hotkey, clipboard, notification, and startup feedback

  - [ ] 3.1 Normalize modifier key matching in HotkeyManager
    - Modify `_parse_hotkey` in `HotkeyManager.start()` to include both left and right variants for each modifier
    - Map `"ctrl"` to both `Key.ctrl_l` and `Key.ctrl_r`
    - Map `"alt"` to both `Key.alt_l` and `Key.alt_r`
    - Map `"shift"` to both `Key.shift_l` and `Key.shift_r`
    - Alternatively, implement `_normalize_key()` helper that maps right variants to left variants in `on_press`/`on_release`
    - Implement platform-aware key comparison using `.char` or `.vk` attributes for character keys on Windows
    - _Bug_Condition: isBugCondition(input) where input.modifier IN [Key.ctrl_r, Key.alt_r] OR platform == "win32" with vk-based key representation_
    - _Expected_Behavior: Hotkey callback is triggered regardless of which physical modifier key (left or right) is used and regardless of platform key representation_
    - _Preservation: Left-modifier hotkeys on Linux continue to work identically; unrelated key combinations continue to be ignored_
    - _Requirements: 2.1, 2.2, 3.3, 3.5_

  - [ ] 3.2 Add Windows-compatible clipboard backend detection
    - Modify `_detect_clipboard_backend()` in `app/text_capture.py` to check `sys.platform`
    - On Windows (`sys.platform == "win32"`), skip xclip/xsel detection and use pyperclip directly (which uses win32 APIs internally)
    - Optionally add `ClipboardBackend.WIN32` enum value with ctypes-based fallback using `OpenClipboard`/`GetClipboardData`/`CloseClipboard`
    - Ensure pyperclip is listed as a project dependency
    - On Linux, preserve existing detection order: xclip → xsel → pyperclip
    - _Bug_Condition: isBugCondition(input) where platform == "win32" AND NOT shutil.which("xclip") AND NOT shutil.which("xsel")_
    - _Expected_Behavior: Clipboard read/write succeeds on Windows via pyperclip or win32 API_
    - _Preservation: On Linux with xclip/xsel installed, xclip/xsel remains the primary clipboard backend_
    - _Requirements: 2.3, 3.1_

  - [ ] 3.3 Add cross-platform notification dispatch
    - Modify `NotificationManager._send_notification()` in `app/main.py` to detect platform
    - On Windows, use `plyer.notification`, `win10toast`, or Windows toast notifications via ctypes
    - On Linux, continue using `notify-send` (existing behavior)
    - Add graceful degradation: if no notification backend is available, fall back to `print()` to stderr
    - _Bug_Condition: isBugCondition(input) where platform == "win32" AND NOT shutil.which("notify-send")_
    - _Expected_Behavior: User receives visible notification on Windows via platform-appropriate mechanism_
    - _Preservation: On Linux with notify-send available, notify-send continues to be used with same arguments_
    - _Requirements: 2.4, 3.2_

  - [ ] 3.4 Add visible feedback on pynput initialization failure
    - When pynput import fails or listener start fails in `HotkeyManager.start()`:
      - Set a `hotkeys_available` property to False
      - Print a message to stderr: "WARNING: Hotkeys are not available. Install pynput for hotkey support."
    - In `SystemTrayApp.run()`, after calling `self._hotkey_manager.start()`:
      - Check `self._hotkey_manager.hotkeys_available`
      - If False, call `self._update_status(AppStatus.ERROR)` and send a notification via `NotificationManager`
    - _Bug_Condition: isBugCondition(input) where pynput_import_fails OR listener_start_fails AND no_visible_feedback_provided_
    - _Expected_Behavior: User receives visible indication (notification, tray icon ERROR status, or console message) that hotkeys are disabled_
    - _Preservation: When pynput is available and listener starts successfully, no additional feedback is shown_
    - _Requirements: 2.5_

  - [ ] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Cross-Platform Hotkey Detection
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied:
      - Right-side modifier keys trigger callbacks
      - Windows key representations are matched correctly
      - Clipboard operations succeed on Windows
      - Notifications are delivered on Windows
      - pynput failure provides visible feedback
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing Linux Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix:
      - Left-modifier hotkeys on Linux still work
      - xclip/xsel still used on Linux
      - notify-send still used on Linux
      - Clipboard monitoring unchanged
      - Unrelated keys still ignored
      - API error handling unchanged

- [ ] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite (exploration + preservation + any existing tests)
  - Ensure all tests pass with no regressions
  - Verify the fix addresses all five bug scenarios from the requirements
  - Ask the user if questions arise

## Task Dependency Graph

```json
{
  "waves": [
    ["1", "2"],
    ["3.1", "3.2", "3.3", "3.4"],
    ["3.5", "3.6"],
    ["4"]
  ]
}
```

## Notes

- The exploration test (task 1) is expected to FAIL on unfixed code — this confirms the bug exists. Do not attempt to fix the code when it fails.
- The preservation tests (task 2) are expected to PASS on unfixed code — this captures the baseline behavior that must be preserved.
- After implementing the fix (tasks 3.1–3.4), re-running both test suites should show all tests passing.
- Property-based testing is recommended for both exploration and preservation to provide stronger guarantees across the input domain.
- The fix uses a normalization approach for modifier keys rather than expanding the hotkey set, to keep the comparison logic simple and maintainable.
- Platform detection uses `sys.platform` checks to route to the appropriate backend for clipboard and notification operations.
