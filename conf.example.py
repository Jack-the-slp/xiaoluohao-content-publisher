from pathlib import Path
import os

BASE_DIR = Path(__file__).parent.resolve()
XHS_SERVER = "http://127.0.0.1:11901"  # only used by xhs-related flows
_browsers = [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
             Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")]
_browsers += sorted(Path("C:/Program Files (x86)/Microsoft/EdgeCore").glob("*/msedge.exe"), reverse=True)
LOCAL_CHROME_PATH = os.getenv("LOCAL_CHROME_PATH") or str(next((p for p in _browsers if p.is_file()), ""))
LOCAL_CHROME_HEADLESS = True  # default headless behavior for uploader/examples
DEBUG_MODE = True  # default debug behavior
# Optional proxy for the YouTube uploader. Where youtube.com is blocked, direct
# connections time out and the (patchright) chromium does NOT use the system proxy.
# Point this at your local proxy port, e.g. "http://127.0.0.1:7890". None = no proxy.
YT_PROXY = None
