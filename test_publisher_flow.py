"""Run with: python test_publisher_flow.py"""

from xiaoluohao_publisher import Publisher


app = Publisher()
try:
    app.root.update()
    assert app.current_page == "login"
    assert set(app.status) == {"抖音", "小红书", "快手", "视频号", "B站"}
    app.show_page("editor")
    assert app.current_page == "editor"
    app.set_kind("文章")
    assert set(app.target_vars) == {"公众号", "知乎", "头条", "B站专栏"}
finally:
    app.root.destroy()
