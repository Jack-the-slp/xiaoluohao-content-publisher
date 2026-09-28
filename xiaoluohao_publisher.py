"""小螺号个人内容发布入口。运行：python xiaoluohao_publisher.py"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
from datetime import datetime
from pathlib import Path
from tkinter import END, Button, Checkbutton, Entry, Frame, Label, StringVar, Text, Tk, filedialog, messagebox
from conf import LOCAL_CHROME_PATH


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "xiaoluohao_data"
PLATFORMS = {
    "图片": {"抖音": "douyin", "小红书": "xiaohongshu", "快手": "kuaishou"},
    "视频": {"抖音": "douyin", "小红书": "xiaohongshu", "快手": "kuaishou", "视频号": "tencent", "B站": "bilibili"},
    "文章": {"公众号": "weixin", "知乎": "zhihu", "头条": "toutiao", "B站专栏": "bilibili"},
}
COLORS = {"bg": "#f5f7fb", "card": "#ffffff", "ink": "#17243b", "muted": "#64748b",
          "blue": "#315de5", "line": "#dfe5ee"}


def build_commands(kind: str, targets: list[str], account: str, title: str, body: str,
                   files: list[Path], tags: str, category: str, article: Path | None = None) -> list[list[str]]:
    if not targets or not title.strip():
        raise ValueError("请填写标题并选择至少一个平台")
    if kind != "文章" and not files:
        raise ValueError("请先选择图片或视频")
    if kind == "图片" and any(p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} for p in files):
        raise ValueError("图片仅支持 JPG、PNG、WebP")
    if kind == "视频" and len(files) != 1:
        raise ValueError("每次请选择一个视频文件")
    if kind != "文章" and not all(p.is_file() for p in files):
        raise ValueError("所选素材文件不存在")
    if kind != "文章" and not account.strip():
        raise ValueError("请填写自己的账号名称；各平台登录时使用同一名称")
    if kind == "视频" and "B站" in targets and not category.strip().isdigit():
        raise ValueError("发布到 B站前请填写数字分区 ID")
    if kind == "文章" and (not body.strip() or article is None):
        raise ValueError("请填写正文并保存文章草稿")

    commands = []
    for target in targets:
        platform = PLATFORMS[kind][target]
        if kind == "文章":
            local_cli = ROOT / ".wechatsync" / "node_modules" / ".bin" / "wechatsync.cmd"
            cli = str(local_cli) if local_cli.exists() else (shutil.which("wechatsync") or shutil.which("wechatsync.cmd"))
            if not cli:
                raise ValueError("文章同步需要先安装 Wechatsync CLI 和浏览器扩展；草稿已保存在本地")
            commands.append([cli, "sync", str(article), "-t", title.strip(), "-p", platform])
            continue
        command = [sys.executable, str(ROOT / "sau_cli.py"), platform,
                   "upload-note" if kind == "图片" else "upload-video",
                   "--account", account.strip()]
        if kind == "图片":
            command += ["--images", *(str(p) for p in files), "--title", title.strip(), "--note", body]
        else:
            command += ["--file", str(files[0]), "--title", title.strip(), "--desc", body]
            if platform == "bilibili":
                command += ["--tid", category.strip()]
            else:
                command += ["--headed"]
        if tags.strip():
            command += ["--tags", tags.strip()]
        commands.append(command)
    return commands


class Publisher:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("小螺号 · 内容发布")
        self.root.geometry("900x760")
        self.root.minsize(780, 650)
        self.root.configure(bg=COLORS["bg"])
        self.kind = StringVar(value="图片")
        self.title = StringVar()
        self.account = StringVar(value="主账号")
        self.tags = StringVar()
        self.category = StringVar()
        self.files: list[Path] = []
        self.target_vars: dict[str, StringVar] = {}
        self.busy = False
        self.status: dict[str, StringVar] = {}
        self.browser_lock = threading.Lock()
        self._make_ui()
        self.account.trace_add("write", lambda *_: [state.set("未检查") for state in self.status.values()])

    def _make_ui(self) -> None:
        header = Frame(self.root, bg=COLORS["ink"], padx=28, pady=17)
        header.pack(fill="x")
        Label(header, text="小螺号  /  内容发布", font=("Microsoft YaHei UI", 19, "bold"),
              fg="white", bg=COLORS["ink"]).pack(side="left")
        self.nav_login = self._button(header, "① 登录账号", lambda: self.show_page("login"), secondary=True)
        self.nav_login.pack(side="right", padx=(8, 0))
        self.nav_editor = self._button(header, "② 内容创作", lambda: self.show_page("editor"), secondary=True)
        self.nav_editor.pack(side="right")

        self.login_page = Frame(self.root, bg=COLORS["bg"], padx=32, pady=24)
        Label(self.login_page, text="先连接你的账号", font=("Microsoft YaHei UI", 23, "bold"),
              fg=COLORS["ink"], bg=COLORS["bg"]).pack(anchor="w")
        Label(self.login_page, text="各平台在同一个浏览器窗口中打开标签页。扫码后点“检查状态”；B站仍使用终端扫码。",
              fg=COLORS["muted"], bg=COLORS["bg"], font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(5, 21))
        self.login_notice = StringVar(value="")
        Label(self.login_page, textvariable=self.login_notice, fg="#b42318", bg=COLORS["bg"],
              wraplength=780, justify="left", anchor="w").pack(fill="x")
        account_row = Frame(self.login_page, bg=COLORS["bg"])
        account_row.pack(fill="x", pady=(0, 16))
        Label(account_row, text="账号名称", fg=COLORS["ink"], bg=COLORS["bg"], width=10,
              anchor="w", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        Entry(account_row, textvariable=self.account, font=("Microsoft YaHei UI", 11),
              relief="solid", bd=1).pack(side="left", fill="x", expand=True, ipady=7)
        Label(account_row, text="本机别名，各平台共用", fg=COLORS["muted"], bg=COLORS["bg"]).pack(side="left", padx=12)
        for name, platform in PLATFORMS["视频"].items():
            row = Frame(self.login_page, bg=COLORS["card"], highlightbackground=COLORS["line"],
                        highlightthickness=1, padx=17, pady=10)
            row.pack(fill="x", pady=4)
            Label(row, text=name, font=("Microsoft YaHei UI", 12, "bold"), fg=COLORS["ink"],
                  bg=COLORS["card"], width=12, anchor="w").pack(side="left")
            state = StringVar(value="未检查")
            self.status[name] = state
            Label(row, textvariable=state, fg=COLORS["muted"], bg=COLORS["card"],
                  width=14, anchor="w").pack(side="left")
            self._button(row, "检查状态", lambda n=name, p=platform: self.check_login(n, p), secondary=True).pack(side="right")
            self._button(row, "登录", lambda n=name, p=platform: self.login_platform(n, p)).pack(side="right", padx=8)
        article = Frame(self.login_page, bg=COLORS["card"], highlightbackground=COLORS["line"],
                        highlightthickness=1, padx=17, pady=13)
        article.pack(fill="x", pady=(12, 4))
        Label(article, text="文章平台", font=("Microsoft YaHei UI", 12, "bold"), fg=COLORS["ink"],
              bg=COLORS["card"]).pack(anchor="w")
        Label(article, text="公众号、知乎、头条、B站专栏：在浏览器扩展中登录，发布时同步为草稿。",
              fg=COLORS["muted"], bg=COLORS["card"]).pack(anchor="w", pady=(3, 0))
        self._button(self.login_page, "进入内容创作  →", lambda: self.show_page("editor")).pack(anchor="e", pady=18)

        self.editor_page = Frame(self.root, bg=COLORS["bg"], padx=32, pady=16)
        Label(self.editor_page, text="创作与发布", font=("Microsoft YaHei UI", 22, "bold"),
              fg=COLORS["ink"], bg=COLORS["bg"]).pack(anchor="w")
        Label(self.editor_page, text="写一次内容，选择平台，确认后逐个提交。",
              fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor="w", pady=(2, 12))
        kinds = Frame(self.editor_page, bg=COLORS["bg"])
        kinds.pack(anchor="w")
        for kind in PLATFORMS:
            self._button(kinds, kind, lambda k=kind: self.set_kind(k), secondary=True).pack(side="left", padx=(0, 8))
        self.kind_label = Label(self.editor_page, text="当前：图片", fg=COLORS["muted"], bg=COLORS["bg"])
        self.kind_label.pack(anchor="w", pady=(7, 10))
        form = Frame(self.editor_page, bg=COLORS["card"], padx=18, pady=12,
                     highlightbackground=COLORS["line"], highlightthickness=1)
        form.pack(fill="both", expand=True)
        for label, var in (("标题", self.title), ("话题，逗号分隔", self.tags), ("B站视频分区 ID", self.category)):
            Label(form, text=label, fg=COLORS["ink"], bg=COLORS["card"], anchor="w").pack(fill="x")
            Entry(form, textvariable=var, relief="solid", bd=1).pack(fill="x", ipady=5, pady=(3, 8))
        Label(form, text="正文 / 图片说明 / 视频简介", fg=COLORS["ink"], bg=COLORS["card"]).pack(anchor="w")
        self.body = Text(form, height=6, wrap="word", relief="solid", bd=1)
        self.body.pack(fill="both", expand=True, pady=(3, 8))
        self._button(form, "选择素材", self.choose_files, secondary=True).pack(anchor="w")
        self.file_label = Label(form, text="未选择素材", anchor="w", fg=COLORS["muted"], bg=COLORS["card"])
        self.file_label.pack(fill="x", pady=(5, 0))
        Label(form, text="目标平台", fg=COLORS["ink"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 0))
        self.targets = Frame(form, bg=COLORS["card"])
        self.targets.pack(anchor="w")
        actions = Frame(self.editor_page, bg=COLORS["bg"])
        actions.pack(fill="x", pady=11)
        self._button(actions, "打开草稿", self.open_draft, secondary=True).pack(side="left")
        self._button(actions, "保存草稿", self.save_draft, secondary=True).pack(side="left", padx=8)
        self.publish_button = self._button(actions, "确认后发布", self.publish)
        self.publish_button.pack(side="right")
        Label(self.editor_page, text="运行记录 · 最终状态以各平台后台为准", fg=COLORS["muted"],
              bg=COLORS["bg"]).pack(anchor="w")
        self.log = Text(self.editor_page, height=5, state="disabled", wrap="word", relief="solid", bd=1)
        self.log.pack(fill="x", pady=(5, 0))
        self.set_kind("图片")
        self.show_page("login")

    def _button(self, parent: Frame, label: str, action, secondary: bool = False) -> Button:
        return Button(parent, text=label, command=action, font=("Microsoft YaHei UI", 10),
                      bg=COLORS["card"] if secondary else COLORS["blue"],
                      fg=COLORS["ink"] if secondary else "white", activebackground=COLORS["line"],
                      relief="flat", bd=0, padx=16, pady=7, cursor="hand2")

    def show_page(self, page: str) -> None:
        self.login_page.pack_forget()
        self.editor_page.pack_forget()
        (self.login_page if page == "login" else self.editor_page).pack(fill="both", expand=True)
        self.current_page = page

    def set_kind(self, kind: str) -> None:
        self.kind.set(kind)
        self.kind_label.config(text=f"当前：{kind}")
        for child in self.targets.winfo_children():
            child.destroy()
        self.target_vars = {}
        for name in PLATFORMS[kind]:
            var = StringVar(value="")
            self.target_vars[name] = var
            Checkbutton(self.targets, text=name, variable=var, onvalue="1", offvalue="",
                        bg=COLORS["card"], activebackground=COLORS["card"]).pack(side="left", padx=5)
        self.files = []
        self.file_label.config(text="文章直接填写正文" if kind == "文章" else "未选择素材")

    def choose_files(self) -> None:
        if self.kind.get() == "文章":
            return
        paths = filedialog.askopenfilenames(title="选择素材") if self.kind.get() == "图片" else [filedialog.askopenfilename(title="选择视频")]
        self.files = [Path(p) for p in paths if p]
        self.file_label.config(text="；".join(p.name for p in self.files) or "未选择素材")

    def selected(self) -> list[str]:
        return [name for name, var in self.target_vars.items() if var.get()]

    def save_draft(self) -> None:
        try:
            self._save_draft()
        except ValueError as exc:
            messagebox.showerror("无法保存", str(exc))

    def _save_draft(self) -> Path:
        title = self.title.get().strip()
        body = self.body.get("1.0", END).strip()
        if not title or not body:
            raise ValueError("保存草稿需要标题和正文")
        DATA.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = DATA / f"{stamp}-{self.kind.get()}.md"
        path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        (DATA / f"{stamp}-{self.kind.get()}.json").write_text(json.dumps({
            "title": title, "type": self.kind.get(), "files": [str(p) for p in self.files],
            "targets": self.selected(), "tags": self.tags.get(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self.write_log(f"草稿已保存：{path}")
        return path

    def open_draft(self) -> None:
        path = filedialog.askopenfilename(title="打开小螺号草稿", initialdir=DATA,
                                          filetypes=[("草稿信息", "*.json")])
        if not path:
            return
        info_path = Path(path)
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            body = info_path.with_suffix(".md").read_text(encoding="utf-8")
            self.set_kind(info["type"])
            self.title.set(info["title"])
            self.tags.set(info.get("tags", ""))
            self.body.delete("1.0", END)
            self.body.insert("1.0", body.split("\n\n", 1)[1].strip())
            self.files = [Path(p) for p in info.get("files", [])]
            self.file_label.config(text="；".join(p.name for p in self.files) or "未选择素材")
            for target in info.get("targets", []):
                if target in self.target_vars:
                    self.target_vars[target].set("1")
        except (OSError, ValueError, KeyError, IndexError) as exc:
            messagebox.showerror("无法打开草稿", str(exc))

    def login_platform(self, name: str, platform: str) -> None:
        account = self.account.get().strip()
        if not account:
            messagebox.showerror("无法登录", "请先填写账号名称")
            return
        command = [sys.executable, str(ROOT / "sau_cli.py"), platform, "login", "--account", account]
        self.status[name].set("登录中…")
        self.login_notice.set("")
        if platform == "bilibili":
            try:
                subprocess.Popen(command, cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)
                self.status[name].set("扫码后点检查")
            except OSError as exc:
                self.status[name].set("启动失败")
                messagebox.showerror("无法登录", str(exc))
            return
        threading.Thread(target=self._account_command, args=(name, command + ["--headed"], True), daemon=True).start()

    def check_login(self, name: str, platform: str) -> None:
        account = self.account.get().strip()
        if not account:
            messagebox.showerror("无法检查", "请先填写账号名称")
            return
        self.status[name].set("检查中…")
        self.login_notice.set("")
        command = [sys.executable, str(ROOT / "sau_cli.py"), platform, "check", "--account", account]
        threading.Thread(target=self._account_command, args=(name, command, False), daemon=True).start()

    def _account_command(self, name: str, command: list[str], login: bool) -> None:
        try:
            env = os.environ.copy()
            if login:
                env["XIAOLUOHAO_LOGIN_CDP"] = self._login_browser_url()
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
                                    env=env)
            state = "扫码后点检查" if login and result.returncode == 0 else (
                "登录失败" if login else "已登录" if result.returncode == 0 else "需登录")
            self.root.after(0, self.status[name].set, state)
            if result.returncode:
                output = (result.stderr or result.stdout).strip()
                detail = output.splitlines()[0] if output else "请检查本机浏览器和网络"
                self.root.after(0, self.write_log, f"{name}：{state} {output[-1800:]}")
                self.root.after(0, self.login_notice.set, f"{name}：{state}。{detail}")
        except (OSError, RuntimeError) as exc:
            self.root.after(0, self.status[name].set, "启动失败")
            self.root.after(0, self.write_log, f"{name}：{exc}")
            self.root.after(0, self.login_notice.set, f"{name}：启动失败。{exc}")

    def _login_browser_url(self) -> str:
        with self.browser_lock:
            profile = DATA / "login_browser"
            port_file = profile / "DevToolsActivePort"
            if port_file.exists():
                try:
                    port = port_file.read_text().splitlines()[0]
                    url = f"http://127.0.0.1:{int(port)}"
                    with urlopen(url + "/json/version", timeout=1):
                        return url
                except (OSError, ValueError, IndexError):
                    port_file.unlink(missing_ok=True)
            if not LOCAL_CHROME_PATH or not Path(LOCAL_CHROME_PATH).is_file():
                raise RuntimeError("请先安装 Chrome 或 Edge 浏览器")
            profile.mkdir(parents=True, exist_ok=True)
            subprocess.Popen([LOCAL_CHROME_PATH, "--remote-debugging-port=0",
                              f"--user-data-dir={profile}", "--no-first-run", "about:blank"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(100):
                if port_file.exists():
                    try:
                        port = int(port_file.read_text().splitlines()[0])
                        return f"http://127.0.0.1:{port}"
                    except (ValueError, IndexError):
                        pass
                time.sleep(0.1)
            raise RuntimeError("浏览器窗口未能启动，请检查本机 Chrome 或 Edge")

    def write_log(self, message: str) -> None:
        self.log.config(state="normal")
        self.log.insert(END, message + "\n")
        self.log.see(END)
        self.log.config(state="disabled")

    def publish(self) -> None:
        if self.busy:
            return
        try:
            article = self._save_draft()
            commands = build_commands(self.kind.get(), self.selected(), self.account.get(),
                                      self.title.get(), self.body.get("1.0", END).strip(),
                                      self.files, self.tags.get(), self.category.get(), article)
        except ValueError as exc:
            messagebox.showerror("无法发布", str(exc))
            return
        if not messagebox.askyesno("确认发布", f"将向 {', '.join(self.selected())} 提交内容。确认继续？"):
            return
        self.busy = True
        self.publish_button.config(state="disabled")
        threading.Thread(target=self._run, args=(commands,), daemon=True).start()

    def _run(self, commands: list[list[str]]) -> None:
        for command in commands:
            target = command[2] if command[1] == str(ROOT / "sau_cli.py") else command[-1]
            self.root.after(0, self.write_log, f"开始：{target}")
            try:
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                        encoding="utf-8", errors="replace")
                output = (result.stdout + "\n" + result.stderr).strip()
                self.root.after(0, self.write_log, f"{target}：{'命令完成' if result.returncode == 0 else '失败'}\n{output[-1800:]}")
            except OSError as exc:
                self.root.after(0, self.write_log, f"{target}：启动失败：{exc}")
        self.root.after(0, self._done)

    def _done(self) -> None:
        self.busy = False
        self.publish_button.config(state="normal")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    Publisher().run()
