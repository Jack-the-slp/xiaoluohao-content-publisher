"""小螺号个人内容发布入口。运行：python xiaoluohao_publisher.py"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import END, Button, Checkbutton, Entry, Frame, Label, StringVar, Text, Tk, filedialog, messagebox


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "xiaoluohao_data"
PLATFORMS = {
    "图片": {"抖音": "douyin", "小红书": "xiaohongshu", "快手": "kuaishou"},
    "视频": {"抖音": "douyin", "小红书": "xiaohongshu", "快手": "kuaishou", "视频号": "tencent", "B站": "bilibili"},
    "文章": {"公众号": "weixin", "知乎": "zhihu", "头条": "toutiao", "B站专栏": "bilibili"},
}


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
        self.root.geometry("740x720")
        self.kind = StringVar(value="图片")
        self.title = StringVar()
        self.account = StringVar(value="我的账号")
        self.tags = StringVar()
        self.category = StringVar()
        self.files: list[Path] = []
        self.target_vars: dict[str, StringVar] = {}
        self.busy = False
        self._make_ui()

    def _make_ui(self) -> None:
        Label(self.root, text="小螺号内容发布", font=("Microsoft YaHei UI", 19, "bold")).pack(pady=12)
        kinds = Frame(self.root)
        kinds.pack()
        for kind in PLATFORMS:
            Button(kinds, text=kind, width=13, command=lambda k=kind: self.set_kind(k)).pack(side="left", padx=8)
        self.kind_label = Label(self.root, text="当前：图片")
        self.kind_label.pack(pady=6)
        for label, var in (("标题", self.title), ("账号名称（图片、视频）", self.account),
                           ("话题，逗号分隔", self.tags), ("B站视频分区 ID", self.category)):
            Label(self.root, text=label).pack(anchor="w", padx=18)
            Entry(self.root, textvariable=var).pack(fill="x", padx=18, pady=(0, 7))
        Label(self.root, text="正文 / 图片说明 / 视频简介").pack(anchor="w", padx=18)
        self.body = Text(self.root, height=10, wrap="word")
        self.body.pack(fill="both", expand=True, padx=18)
        Button(self.root, text="选择素材", command=self.choose_files).pack(anchor="w", padx=18, pady=8)
        self.file_label = Label(self.root, text="未选择素材", anchor="w")
        self.file_label.pack(fill="x", padx=18)
        Label(self.root, text="目标平台").pack(anchor="w", padx=18, pady=(9, 0))
        self.targets = Frame(self.root)
        self.targets.pack(anchor="w", padx=18)
        actions = Frame(self.root)
        actions.pack(pady=12)
        Button(actions, text="打开草稿", command=self.open_draft, width=12).pack(side="left", padx=5)
        Button(actions, text="保存草稿", command=self.save_draft, width=15).pack(side="left", padx=10)
        Button(actions, text="登录所选平台", command=self.login, width=14).pack(side="left", padx=5)
        self.publish_button = Button(actions, text="确认后发布", command=self.publish, width=15)
        self.publish_button.pack(side="left", padx=5)
        Label(self.root, text="运行记录（结果以各平台后台为准）").pack(anchor="w", padx=18)
        self.log = Text(self.root, height=9, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self.set_kind("图片")

    def set_kind(self, kind: str) -> None:
        self.kind.set(kind)
        self.kind_label.config(text=f"当前：{kind}")
        for child in self.targets.winfo_children():
            child.destroy()
        self.target_vars = {}
        for name in PLATFORMS[kind]:
            var = StringVar(value="")
            self.target_vars[name] = var
            Checkbutton(self.targets, text=name, variable=var, onvalue="1", offvalue="").pack(side="left", padx=5)
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

    def login(self) -> None:
        targets = self.selected()
        if self.kind.get() == "文章":
            messagebox.showinfo("文章登录", "请在 Chrome 或 Edge 中安装文章同步助手扩展，并在浏览器里登录目标平台。")
            return
        if not targets or not self.account.get().strip():
            messagebox.showerror("无法登录", "请先选择平台并填写账号名称")
            return
        if "B站" in targets:
            messagebox.showinfo("B站登录", "B站首次登录需要在本文件夹的终端中运行：.venv\\Scripts\\python.exe sau_cli.py bilibili login --account 你的账号名称")
            targets = [t for t in targets if t != "B站"]
        commands = [[sys.executable, str(ROOT / "sau_cli.py"), PLATFORMS[self.kind.get()][t],
                     "login", "--account", self.account.get().strip(), "--headed"] for t in targets]
        if commands:
            self.busy = True
            self.publish_button.config(state="disabled")
            threading.Thread(target=self._run, args=(commands,), daemon=True).start()

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
