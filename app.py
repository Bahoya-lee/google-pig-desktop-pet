# -*- coding: utf-8 -*-
"""谷歌猪桌宠。

一个不依赖第三方运行库的 Windows 桌面宠物：

- 透明、无边框、可拖动、可置顶；
- 会散步、眨眼、睡觉、听歌和随机做小动作；
- 点击切换表情，右键打开 iOS 风格控制中心；
- 设置保存在用户本地 AppData，不会上传。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import random
import sys
import time
import tkinter as tk
from pathlib import Path

from single_instance import acquire_single_instance


APP_NAME = "谷歌猪桌宠"
TRANSPARENT_COLOR = "#ff00ff"
ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PROPS = ASSETS / "props"
SETTINGS_PATH = (
    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GooglePigPet" / "settings.json"
)

THEMES = {
    "light": {
        "bg": "#F2F2F7",
        "card": "#FFFFFF",
        "card2": "#F2F2F7",
        "line": "#D1D1D6",
        "text": "#000000",
        "secondary": "#6C6C70",
        "tertiary": "#8E8E93",
        "accent": "#007AFF",
        "green": "#34C759",
        "orange": "#FF9500",
        "red": "#FF3B30",
        "bubble": "#FFFFFF",
        "bubble_text": "#111111",
    },
    "dark": {
        "bg": "#000000",
        "card": "#1C1C1E",
        "card2": "#2C2C2E",
        "line": "#38383A",
        "text": "#FFFFFF",
        "secondary": "#AEAEB2",
        "tertiary": "#8E8E93",
        "accent": "#0A84FF",
        "green": "#30D158",
        "orange": "#FF9F0A",
        "red": "#FF453A",
        "bubble": "#1C1C1E",
        "bubble_text": "#FFFFFF",
    },
}

DEFAULT_SETTINGS = {
    "auto_walk": True,
    "topmost": True,
    "random_actions": True,
    "dark_mode": True,
    "size": "medium",
    "fixed_action": "auto",
    "start_on_boot": False,
    "x": None,
    "y": None,
}

PHRASES = {
    "idle": ["今天也要元气满满", "猪乐", "好多猪啊", "记得看最新文献"],
    "walk": ["散步中…", "出发！", "去找好玩的"],
    "sleepy": ["你胆子真是肥嘟嘟的", "困了…", "先眯一会儿"],
    "happy": ["好！", "开心！", "被摸到了"],
    "angry": ["坏！", "哼！", "谁惹我了"],
    "music": ["听歌中…", "猪喝咖啡", "音乐时间"],
}


def enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

PROP_BY_STATE = {
    "happy": ["heart", "sparkle"],
    "sleepy": ["sleep"],
    "music": ["music", "coffee"],
    "angry": ["anger"],
}


def load_manifest() -> dict:
    path = ASSETS / "manifest.json"
    if not path.exists():
        raise SystemExit(
            f"缺少素材清单：{path}\n请先运行：python tools\\prepare_assets.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        settings.update(saved)
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class IOSSwitch(tk.Canvas):
    def __init__(self, master, value, command, *, bg, accent):
        super().__init__(
            master,
            width=52,
            height=32,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.value = bool(value)
        self.command = command
        self.accent = accent
        self.off = "#C7C7CC"
        self.bind("<Button-1>", self._toggle)
        self._render()

    def _render(self):
        self.delete("all")
        track = self.accent if self.value else self.off
        rounded_rect(self, 2, 4, 50, 28, 12, fill=track, outline="")
        x = 24 if self.value else 4
        self.create_oval(x, 4, x + 24, 28, fill="#FFFFFF", outline="")

    def _toggle(self, _event=None):
        self.value = not self.value
        self._render()
        if self.command:
            self.command(self.value)


class PillButton(tk.Canvas):
    def __init__(
        self,
        master,
        text,
        command,
        *,
        width=124,
        height=42,
        fill,
        fg,
        bg,
        font=("Microsoft YaHei UI", 12, "bold"),
        outline="",
    ):
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.command = command
        self.text = text
        self.fill = fill
        self.fg = fg
        self.font = font
        self.outline = outline
        self.width = width
        self.height = height
        self.bind("<Button-1>", self._pressed)
        self.bind("<ButtonRelease-1>", self._released)
        self._render(False)

    def _render(self, pressed=False):
        self.delete("all")
        fill = self.fill
        if pressed:
            fill = self._blend(fill, "#000000", 0.10)
        rounded_rect(
            self,
            1,
            1,
            self.width - 1,
            self.height - 1,
            self.height // 2,
            fill=fill,
            outline=self.outline,
            width=1,
        )
        self.create_text(
            self.width // 2,
            self.height // 2,
            text=self.text,
            fill=self.fg,
            font=self.font,
        )

    @staticmethod
    def _blend(color: str, other: str, amount: float) -> str:
        def rgb(value: str):
            value = value.lstrip("#")
            return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))

        a, b = rgb(color), rgb(other)
        return "#" + "".join(
            f"{round(a[i] + (b[i] - a[i]) * amount):02x}" for i in range(3)
        )

    def _pressed(self, _event=None):
        self._render(True)

    def _released(self, _event=None):
        self._render(False)
        if self.command:
            self.command()


class SegmentedControl(tk.Canvas):
    def __init__(self, master, values, selected, command, *, bg, card, accent, secondary):
        self.values = values
        self.selected = selected
        self.command = command
        self.card = card
        self.accent = accent
        self.secondary = secondary
        super().__init__(
            master,
            width=286,
            height=38,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.bind("<Button-1>", self._click)
        self._render()

    def _render(self):
        self.delete("all")
        rounded_rect(self, 1, 1, 285, 37, 10, fill=self.card, outline="")
        seg_w = 94
        for index, value in enumerate(self.values):
            x1 = 2 + index * seg_w
            x2 = x1 + seg_w
            if value == self.selected:
                rounded_rect(
                    self,
                    x1 + 2,
                    3,
                    x2 - 2,
                    35,
                    8,
                    fill=self.accent,
                    outline="",
                )
            color = "#FFFFFF" if value == self.selected else self.secondary
            self.create_text(
                (x1 + x2) // 2,
                19,
                text=value,
                fill=color,
                font=("Microsoft YaHei UI", 11, "bold"),
            )

    def _click(self, event):
        index = min(2, max(0, event.x // 94))
        self.selected = self.values[index]
        self._render()
        if self.command:
            self.command(self.selected)


class RoundedPanel(tk.Canvas):
    def __init__(self, master, width, height, *, bg, fill, outline, radius=18):
        super().__init__(
            master,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self.fill = fill
        rounded_rect(self, 1, 1, width - 1, height - 1, radius, fill=fill, outline=outline)
        self.body = tk.Frame(self, bg=fill)
        self.create_window(16, 12, anchor="nw", window=self.body, width=width - 32, height=height - 24)


class ControlCenter:
    def __init__(self, pet: "GooglePigPet"):
        self.pet = pet
        self.win = tk.Toplevel(pet.root)
        self.win.title("谷歌猪 · 控制中心")
        self.win.resizable(False, False)
        self.win.geometry(self._geometry())
        self.win.configure(bg=pet.theme["bg"])
        self.win.attributes("-topmost", True)
        try:
            self.win.iconbitmap(str(ASSETS / "icon.ico"))
        except tk.TclError:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda _e: self.close())
        self.render()
        self.win.focus_force()

    def _geometry(self) -> str:
        screen_w = self.pet.root.winfo_screenwidth()
        screen_h = self.pet.root.winfo_screenheight()
        width, height = 440, 748
        x = max(20, screen_w - width - 42)
        y = max(20, (screen_h - height) // 2)
        return f"{width}x{height}+{x}+{y}"

    def _row(self, parent, title, subtitle, value, command):
        theme = self.pet.theme
        row = tk.Frame(parent, bg=theme["card"], height=50)
        row.pack(fill="x")
        row.pack_propagate(False)
        left = tk.Frame(row, bg=theme["card"])
        left.pack(side="left", fill="both", expand=True)
        tk.Label(
            left,
            text=title,
            bg=theme["card"],
            fg=theme["text"],
            font=("PingFang SC", 12, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(6, 0))
        tk.Label(
            left,
            text=subtitle,
            bg=theme["card"],
            fg=theme["secondary"],
            font=("PingFang SC", 9),
            anchor="w",
        ).pack(fill="x")
        IOSSwitch(row, value, command, bg=theme["card"], accent=theme["green"]).pack(
            side="right", padx=(8, 0)
        )
        return row

    def _separator(self, parent):
        tk.Frame(parent, bg=self.pet.theme["line"], height=1).pack(fill="x", pady=1)

    def _header(self):
        theme = self.pet.theme
        header = tk.Frame(self.win, bg=theme["bg"])
        header.pack(fill="x", padx=22, pady=(20, 10))
        left = tk.Frame(header, bg=theme["bg"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text="控制中心",
            bg=theme["bg"],
            fg=theme["text"],
            font=("PingFang SC", 25, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            left,
            text="让谷歌猪按你的习惯待在桌面上",
            bg=theme["bg"],
            fg=theme["secondary"],
            font=("PingFang SC", 11),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            header,
            image=self.pet.prop_images["pig"],
            bg=theme["bg"],
            bd=0,
        ).pack(side="right", padx=(10, 2))

    def render(self):
        for child in self.win.winfo_children():
            child.destroy()
        self._header()

        theme = self.pet.theme
        behavior = RoundedPanel(
            self.win,
            396,
            290,
            bg=theme["bg"],
            fill=theme["card"],
            outline=theme["line"],
        )
        behavior.pack(padx=22)
        rows = [
            ("自动走动", "沿屏幕边缘散步", "auto_walk"),
            ("始终置顶", "保持在窗口最前", "topmost"),
            ("随机小动作", "偶尔切换表情", "random_actions"),
            ("深色外观", "控制中心使用深色", "dark_mode"),
            ("开机启动", "登录 Windows 后自动出现", "start_on_boot"),
        ]
        for index, (title, subtitle, key) in enumerate(rows):
            self._row(
                behavior.body,
                title,
                subtitle,
                self.pet.settings[key],
                lambda value, k=key: self._toggle_setting(k, value),
            )
            if index != len(rows) - 1:
                self._separator(behavior.body)

        appearance = RoundedPanel(
            self.win,
            396,
            102,
            bg=theme["bg"],
            fill=theme["card"],
            outline=theme["line"],
        )
        appearance.pack(padx=22, pady=(12, 0))
        tk.Label(
            appearance.body,
            text="桌宠大小",
            bg=theme["card"],
            fg=theme["text"],
            font=("PingFang SC", 12, "bold"),
            anchor="w",
        ).pack(anchor="w")
        sizes = ["小", "中", "大"]
        labels = {"small": "小", "medium": "中", "large": "大"}
        segmented = SegmentedControl(
            appearance.body,
            sizes,
            labels[self.pet.settings["size"]],
            self._set_size,
            bg=theme["card"],
            card=theme["card2"],
            accent=theme["accent"],
            secondary=theme["secondary"],
        )
        segmented.pack(anchor="w", pady=(5, 0))

        actions = RoundedPanel(
            self.win,
            396,
            126,
            bg=theme["bg"],
            fill=theme["card"],
            outline=theme["line"],
        )
        actions.pack(padx=22, pady=(12, 0))
        tk.Label(
            actions.body,
            text="快速动作",
            bg=theme["card"],
            fg=theme["text"],
            font=("PingFang SC", 12, "bold"),
            anchor="w",
        ).pack(anchor="w")
        buttons = tk.Frame(actions.body, bg=theme["card"])
        buttons.pack(fill="x", pady=(7, 0))
        specs = [
            ("摸摸", lambda: self.pet.do_action("happy"), theme["accent"]),
            ("睡觉", lambda: self.pet.do_action("sleepy"), "#5E5CE6"),
            ("听歌", lambda: self.pet.do_action("music"), "#AF52DE"),
            ("生气", lambda: self.pet.do_action("angry"), theme["orange"]),
            ("回角落", self.pet.move_to_corner, theme["card2"]),
        ]
        for text, command, fill in specs:
            fg = "#FFFFFF" if fill != theme["card2"] else theme["text"]
            PillButton(
                buttons,
                text,
                command,
                width=66,
                height=38,
                fill=fill,
                fg=fg,
                bg=theme["card"],
                font=("PingFang SC", 10, "bold"),
            ).pack(side="left", padx=(0, 5))

        footer = tk.Frame(self.win, bg=theme["bg"])
        footer.pack(fill="x", padx=22, pady=(16, 0))
        PillButton(
            footer,
            "完成",
            self.close,
            width=126,
            height=44,
            fill=theme["accent"],
            fg="#FFFFFF",
            bg=theme["bg"],
        ).pack(side="left")
        PillButton(
            footer,
            "退出桌宠",
            self.pet.quit,
            width=126,
            height=44,
            fill=theme["card"],
            fg=theme["red"],
            bg=theme["bg"],
            outline=theme["line"],
        ).pack(side="right")

    def _toggle_setting(self, key, value):
        self.pet.settings[key] = value
        if key == "topmost":
            self.pet.set_topmost(value)
        if key == "start_on_boot":
            ok = self.pet.set_startup(value)
            if not ok:
                self.pet.show_bubble("开机启动设置失败", 2.2)
        if key == "dark_mode":
            self.pet.save()
            self.pet.apply_theme()
            self.render()
        else:
            self.pet.save()

    def _set_size(self, label):
        key = {"小": "small", "中": "medium", "大": "large"}[label]
        self.pet.set_size(key)

    def close(self):
        self.pet.control_center = None
        self.win.destroy()


class GooglePigPet:
    def __init__(self, *, no_walk=False, open_control=False):
        self.manifest = load_manifest()
        self.settings = load_settings()
        if no_walk:
            self.settings["auto_walk"] = False
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT_COLOR)
        self.root.resizable(False, False)
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)
        except tk.TclError:
            pass
        try:
            self.root.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        self.root.attributes("-topmost", bool(self.settings["topmost"]))

        self.theme = THEMES["dark" if self.settings["dark_mode"] else "light"]
        self.images = {}
        self.prop_images = {}
        self.prop_item = None
        self.prop_kind = ""
        self.prop_until = 0.0
        self.prop_phase = 0.0
        self.size_name = self.settings["size"] if self.settings["size"] in self.manifest["sizes"] else "medium"
        self.win_w, self.win_h = self.manifest["sizes"][self.size_name]["canvas"]
        self.x = int(self.settings.get("x") or 0)
        self.y = int(self.settings.get("y") or 0)
        self.vx = 1.4
        self.direction = -1
        self.phase = 0.0
        self.current_key = None
        self.current_state = "idle"
        self.override_state = None
        self.override_until = 0.0
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.dragging = False
        self.drag_started = (0, 0)
        self.drag_window = (0, 0)
        self.drag_moved = False
        self.walk_frame = 0
        self.last_walk_toggle = time.monotonic()
        self.next_random_action = time.monotonic() + random.uniform(8, 15)
        self.control_center = None
        self.action_cycle = ["happy", "angry", "music", "sleepy"]

        self.canvas = tk.Canvas(
            self.root,
            width=self.win_w,
            height=self.win_h,
            bg=TRANSPARENT_COLOR,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()
        self._load_images()
        self._place_initial()
        self._draw_scene()
        self._bind_events()
        self._tick()

        if self.settings.get("start_on_boot"):
            self.set_startup(True)
        if open_control:
            self.root.after(350, self.open_control_center)
        self.root.after(350, lambda: self.show_bubble("你好，我是谷歌猪", 2.8))

    # ---------------------------------------------------------------- 素材与窗口

    def _load_images(self):
        self.images = {}
        entries = self.manifest["sizes"][self.size_name]["states"]
        for state, variants in entries.items():
            self.images[state] = {}
            for variant, relative in variants.items():
                self.images[state][variant] = tk.PhotoImage(file=str(ASSETS / relative))
        prop_zoom = {"small": 1, "medium": 1, "large": 2}.get(self.size_name, 1)
        self.prop_margin = 58 if prop_zoom == 1 else 82
        for name in ("coffee", "music", "sleep", "heart", "sparkle", "anger", "pig"):
            image = tk.PhotoImage(file=str(PROPS / f"{name}.png"))
            if prop_zoom > 1:
                image = image.zoom(prop_zoom, prop_zoom)
            self.prop_images[name] = image

    def _place_initial(self):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if self.x is None or self.y is None or self.x <= 0 or self.y <= 0:
            self.x = max(20, screen_w - self.win_w - 56)
            self.y = max(40, screen_h - self.win_h - 92)
        self._clamp_position()
        self._set_geometry()

    def _clamp_position(self):
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.x = max(-8, min(int(self.x), screen_w - self.win_w + 8))
        self.y = max(10, min(int(self.y), screen_h - self.win_h - 42))

    def _set_geometry(self):
        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.x)}+{int(self.y)}")

    def _draw_scene(self):
        self.canvas.delete("all")
        self._draw_bubble()
        self.image_item = self.canvas.create_image(
            self.win_w // 2,
            self.win_h - 14,
            anchor="s",
            image=self.current_image(),
            tags="pet",
        )
        self.prop_item = self.canvas.create_image(
            -200,
            -200,
            anchor="center",
            image=self.prop_images["sparkle"],
            state="hidden",
            tags="prop",
        )
        self.canvas.tag_raise(self.image_item)

    def current_image(self):
        state = self.current_state if self.current_state in self.images else "idle"
        if self.current_state == "walk" and self.walk_frame == 0:
            state = "idle"
        variant = "normal" if self.direction < 0 else "flipped"
        data = self.images.get(state, self.images["idle"])
        return data.get(variant, data["normal"])

    def _update_image(self):
        key = (self.current_state, self.direction, self.walk_frame)
        if key == self.current_key:
            return
        self.current_key = key
        self.canvas.itemconfigure(self.image_item, image=self.current_image())

    def _draw_bubble(self):
        self.canvas.delete("bubble")
        if not self.bubble_text:
            return
        theme = self.theme
        left = max(12, self.win_w // 2 - 150)
        right = min(self.win_w - 12, self.win_w // 2 + 150)
        top = 8
        bottom = 72
        rounded_rect(
            self.canvas,
            left,
            top,
            right,
            bottom,
            18,
            fill=theme["bubble"],
            outline=theme["line"],
            width=1,
            tags="bubble",
        )
        tip = self.win_w // 2 + 34
        self.canvas.create_polygon(
            tip - 12,
            bottom - 1,
            tip + 12,
            bottom - 1,
            tip,
            bottom + 16,
            fill=theme["bubble"],
            outline=theme["line"],
            width=1,
            tags="bubble",
        )
        self.canvas.create_text(
            (left + right) // 2,
            (top + bottom) // 2,
            text=self.bubble_text,
            width=right - left - 28,
            fill=theme["bubble_text"],
            font=("Microsoft YaHei UI", 11, "bold"),
            tags="bubble",
        )
        self.canvas.tag_raise("bubble")
        self.canvas.tag_raise("pet")
        if self.prop_item:
            self.canvas.tag_raise("prop")

    # ---------------------------------------------------------------- 交互

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind("<Button-3>", lambda _e: self.open_control_center())
        self.canvas.bind("<Double-Button-1>", lambda _e: self.do_action("music"))
        self.root.bind("<space>", lambda _e: self.pet_click())
        self.root.bind("m", lambda _e: self.do_action("music"))
        self.root.bind("s", lambda _e: self.do_action("sleepy"))
        self.root.bind("<Escape>", lambda _e: self.save())
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    def _drag_start(self, event):
        self.dragging = True
        self.drag_moved = False
        self.drag_started = (event.x_root, event.y_root)
        self.drag_window = (self.x, self.y)
        self.canvas.configure(cursor="fleur")

    def _drag_move(self, event):
        if not self.dragging:
            return
        dx = event.x_root - self.drag_started[0]
        dy = event.y_root - self.drag_started[1]
        if abs(dx) + abs(dy) > 4:
            self.drag_moved = True
        self.x = self.drag_window[0] + dx
        self.y = self.drag_window[1] + dy
        self._clamp_position()
        self._set_geometry()

    def _drag_end(self, _event=None):
        if not self.dragging:
            return
        self.dragging = False
        self.canvas.configure(cursor="")
        if not self.drag_moved:
            self.pet_click()
        else:
            self.save()

    def pet_click(self):
        state = self.action_cycle[self.action_cycle.index(self.override_state) + 1 if self.override_state in self.action_cycle else 0]
        self.do_action(state)

    def do_action(self, state):
        self.current_state = state
        self.override_state = state
        self.override_until = time.monotonic() + (5.0 if state == "music" else 3.2)
        choices = PROP_BY_STATE.get(state)
        if choices:
            self.prop_kind = random.choice(choices)
            self.prop_until = self.override_until
        else:
            self.prop_kind = ""
            self.prop_until = 0.0
        self.show_bubble(random.choice(PHRASES.get(state, ["你好"])), 2.8)
        self._update_image()

    def show_bubble(self, text, seconds=2.5):
        self.bubble_text = text
        self.bubble_until = time.monotonic() + seconds
        self._draw_bubble()

    def move_to_corner(self):
        self.x = self.root.winfo_screenwidth() - self.win_w - 56
        self.y = self.root.winfo_screenheight() - self.win_h - 92
        self._clamp_position()
        self._set_geometry()
        self.save()
        self.show_bubble("回到角落啦", 2.0)

    def open_control_center(self):
        if self.control_center:
            try:
                self.control_center.win.lift()
                return
            except tk.TclError:
                pass
        self.control_center = ControlCenter(self)

    # ---------------------------------------------------------------- 设置

    def set_size(self, size_name):
        if size_name not in self.manifest["sizes"]:
            return
        bottom = self.y + self.win_h
        center_x = self.x + self.win_w // 2
        self.size_name = size_name
        self.settings["size"] = size_name
        self.win_w, self.win_h = self.manifest["sizes"][size_name]["canvas"]
        self.x = center_x - self.win_w // 2
        self.y = bottom - self.win_h
        self._clamp_position()
        self._load_images()
        self.current_key = None
        self.canvas.configure(width=self.win_w, height=self.win_h)
        self.root.geometry(f"{self.win_w}x{self.win_h}+{int(self.x)}+{int(self.y)}")
        self._draw_scene()
        self.save()
        if self.control_center:
            self.control_center.render()

    def apply_theme(self):
        self.theme = THEMES["dark" if self.settings["dark_mode"] else "light"]
        self._draw_bubble()
        self.canvas.tag_raise("bubble")
        self.canvas.tag_raise("pet")

    def set_topmost(self, value: bool) -> None:
        self.root.attributes("-topmost", bool(value))

    def set_startup(self, enabled: bool) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            if getattr(sys, "frozen", False):
                command = f'"{Path(sys.executable)}"'
            else:
                python = Path(sys.executable)
                pythonw = python.with_name("pythonw.exe")
                executable = pythonw if pythonw.exists() else python
                command = f'"{executable}" "{Path(__file__).resolve()}"'
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, "GooglePigPet", 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, "GooglePigPet")
                    except FileNotFoundError:
                        pass
            return True
        except OSError:
            return False

    def save(self):
        self.settings.update(
            {
                "x": int(self.x),
                "y": int(self.y),
                "size": self.size_name,
                "dark_mode": bool(self.settings["dark_mode"]),
                "auto_walk": bool(self.settings["auto_walk"]),
                "topmost": bool(self.settings["topmost"]),
                "random_actions": bool(self.settings["random_actions"]),
            }
        )
        save_settings(self.settings)

    def quit(self):
        self.save()
        self.root.destroy()

    # ---------------------------------------------------------------- 主循环

    def _tick(self):
        now = time.monotonic()
        self.phase += 0.055
        if self.override_until and now >= self.override_until:
            self.override_state = None
            self.override_until = 0
        if self.bubble_until and now >= self.bubble_until:
            if self.bubble_text:
                self.bubble_text = ""
                self._draw_bubble()

        self.prop_phase += 0.08
        if self.prop_kind and now < self.prop_until:
            prop = self.prop_images.get(self.prop_kind)
            if prop:
                self.canvas.itemconfigure(self.prop_item, image=prop, state="normal")
                self.canvas.coords(
                    self.prop_item,
                    self.win_w - self.prop_margin,
                    112 + math.sin(self.prop_phase) * 5,
                )
                self.canvas.tag_raise("prop")
        else:
            self.prop_kind = ""
            self.canvas.itemconfigure(self.prop_item, state="hidden")

        if (
            self.settings["random_actions"]
            and not self.dragging
            and now >= self.next_random_action
            and not self.override_state
        ):
            self.next_random_action = now + random.uniform(9, 18)
            self.do_action(random.choice(["sleepy", "music", "happy"]))

        walking = bool(self.settings["auto_walk"] and not self.dragging and not self.override_state)
        if walking:
            self.x += self.vx
            right_limit = self.root.winfo_screenwidth() - self.win_w + 8
            if self.x > right_limit:
                self.x = right_limit
                self.vx = -abs(self.vx)
            elif self.x < -8:
                self.x = -8
                self.vx = abs(self.vx)
            self.direction = 1 if self.vx > 0 else -1
            if now - self.last_walk_toggle > 0.34:
                self.walk_frame = 1 - self.walk_frame
                self.last_walk_toggle = now
            self.current_state = "walk"
        elif self.override_state:
            self.current_state = self.override_state
        else:
            self.current_state = "idle"

        if walking:
            self._set_geometry()
        self._update_image()
        bob = math.sin(self.phase * 2.0) * 2.2
        if walking:
            bob += abs(math.sin(self.phase * 6.0)) * 3.0
        shake = math.sin(self.phase * 16.0) * 3.3 if self.current_state == "angry" else 0.0
        happy_bounce = (
            abs(math.sin(self.phase * 5.0)) * 3.2 if self.current_state == "happy" else 0.0
        )
        self.canvas.coords(
            self.image_item,
            self.win_w // 2 + shake,
            self.win_h - 12 + bob - happy_bounce,
        )
        self.root.after(16, self._tick)


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--no-walk", action="store_true", help="关闭自动走动")
    parser.add_argument("--control-center", action="store_true", help="启动时打开控制中心")
    parser.add_argument("--action", choices=("happy", "angry", "sleepy", "music"), help="启动后立即演示一个动作")
    parser.add_argument("--smoke-test", action="store_true", help="只检查素材和窗口，不进入主循环")
    parser.add_argument("--dpi-aware", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not acquire_single_instance():
        return
    if args.dpi_aware:
        enable_windows_dpi_awareness()
    pet = GooglePigPet(no_walk=args.no_walk, open_control=args.control_center)
    if args.action:
        pet.root.after(650, lambda: pet.do_action(args.action))
    if args.smoke_test:
        for state in ("idle", "walk", "sleepy", "happy", "angry", "music"):
            pet.current_state = state
            pet._draw_scene()
            pet.root.update_idletasks()
        print("smoke-test: OK")
        pet.root.destroy()
        return
    pet.root.mainloop()


if __name__ == "__main__":
    main()
