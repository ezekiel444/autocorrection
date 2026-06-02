"""Build script for creating AutoCorrect.exe using PyInstaller."""
import PyInstaller.__main__
import os
import sys

project_root = os.path.dirname(os.path.abspath(__file__))
icon_path = os.path.join(project_root, "assets", "tray_icon.ico")

args = [
    os.path.join(project_root, "app", "__main__.py"),
    "--name=AutoCorrect",
    "--onefile",
    "--windowed",  # No console window
    "--add-data", f"{os.path.join(project_root, 'app')}:app",
    "--add-data", f"{os.path.join(project_root, '.env')}:.",
    "--add-data", f"{os.path.join(project_root, 'config')}:config",
    "--hidden-import=app",
    "--hidden-import=app.main",
    "--hidden-import=app.text_capture",
    "--hidden-import=app.history",
    "--hidden-import=app.history_window",
    "--hidden-import=app.review_window",
    "--hidden-import=app.settings_window",
    "--hidden-import=app.theme",
    "--hidden-import=pynput",
    "--hidden-import=pynput.keyboard",
    "--hidden-import=pynput.keyboard._win32",
    "--hidden-import=pystray",
    "--hidden-import=pystray._win32",
    "--hidden-import=PIL",
    "--hidden-import=plyer",
    "--hidden-import=plyer.platforms.win",
    "--hidden-import=plyer.platforms.win.notification",
    "--hidden-import=pyperclip",
    "--hidden-import=httpx",
]

# Add icon if it exists
if os.path.exists(icon_path):
    args.append(f"--icon={icon_path}")

print("Building AutoCorrect.exe...")
PyInstaller.__main__.run(args)
print("\nDone! Find AutoCorrect.exe in the dist/ folder.")
