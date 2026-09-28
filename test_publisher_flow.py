"""Run with: python test_publisher_flow.py"""

from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import xiaoluohao_publisher as publisher

Publisher = publisher.Publisher


app = Publisher()
try:
    app.root.update()
    assert app.current_page == "login"
    assert set(app.status) == {"抖音", "小红书", "快手", "视频号", "B站"}
    app.show_page("editor")
    assert app.current_page == "editor"
    app.set_kind("文章")
    assert set(app.target_vars) == {"公众号", "知乎", "头条", "B站专栏"}
    with TemporaryDirectory() as tmp, patch.object(publisher, "DATA", Path(tmp)), patch.object(publisher, "urlopen"):
        port_file = Path(tmp) / "login_browser" / "DevToolsActivePort"
        port_file.parent.mkdir()
        port_file.write_text("12345\n")
        assert app._login_browser_url() == "http://127.0.0.1:12345"
    failed = CompletedProcess([], 1, "", "(node:1) [DEP0169] DeprecationWarning: url.parse()\nLocator.count: Target page, context or browser has been closed")
    with patch.object(app, "_login_browser_url", return_value="http://127.0.0.1:12345"), patch.object(publisher.subprocess, "run", return_value=failed):
        app._account_command("抖音", ["test"], True)
        app.root.update()
        assert "标签页已关闭" in app.login_notice.get()
finally:
    app.root.destroy()
