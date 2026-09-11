# -*- coding: utf-8 -*-
"""Qt 版谷歌猪桌宠。

透明无边框窗口由 Qt 的 WA_TranslucentBackground 处理，支持真正的逐像素
alpha、柔和阴影和稳定动画。
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import (
    APP_NAME,
    ASSETS,
    PHRASES,
    PROP_BY_STATE,
    THEMES,
    load_manifest,
    load_settings,
    save_settings,
)
from single_instance import acquire_single_instance


def set_startup(enabled: bool) -> bool:
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


class SwitchButton(QAbstractButton):
    def __init__(self, checked: bool, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(52, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.accent = QColor("#34C759")
        self.off = QColor("#C7C7CC")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.accent if self.isChecked() else self.off)
        painter.drawRoundedRect(QRectF(2, 5, 48, 22), 11, 11)
        x = 26 if self.isChecked() else 2
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(x, 2, 28, 28))


class PetWindow(QWidget):
    def __init__(self, no_walk=False, open_control=False):
        super().__init__()
        self.manifest = load_manifest()
        self.settings = load_settings()
        if no_walk:
            self.settings["auto_walk"] = False
        self.theme = THEMES["dark" if self.settings["dark_mode"] else "light"]
        self.size_name = (
            self.settings["size"]
            if self.settings["size"] in self.manifest["sizes"]
            else "medium"
        )
        self.win_w, self.win_h = self.manifest["sizes"][self.size_name]["canvas"]
        self.pixmaps: dict[str, dict[str, QPixmap]] = {}
        self.walk_frames: list[dict[str, QPixmap]] = []
        self.props: dict[str, QPixmap] = {}
        self.current_state = "idle"
        self.override_state = None
        self.override_until = 0.0
        self.bubble_text = ""
        self.bubble_until = 0.0
        self.prop_kind = ""
        self.prop_until = 0.0
        self.prop_phase = 0.0
        self.phase = 0.0
        self.direction = -1
        self.vx = 1.2
        self.walk_frame = 0
        self.walk_index = 0
        self.walk_elapsed = 0.0
        self.walk_interval = 0.055
        self.last_walk_toggle = time.monotonic()
        self.next_random_action = time.monotonic() + random.uniform(8, 15)
        self.dragging = False
        self.drag_offset = QPoint()
        self.drag_moved = False
        self.action_cycle = ["happy", "angry", "music", "sleepy"]
        self.control_panel = None
        self.tray = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.win_w, self.win_h)
        self._load_images()
        self._place_initial()
        self.show()
        if not self.settings.get("topmost"):
            self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
            self.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self._create_tray()
        self.current_state = "walk" if self.settings.get("auto_walk") else "idle"
        if open_control:
            QTimer.singleShot(250, self.open_control_panel)
        QTimer.singleShot(350, lambda: self.show_bubble("你好，我是谷歌猪", 2.8))

    # ---------------------------------------------------------------- assets

    def _load_images(self):
        entries = self.manifest["sizes"][self.size_name]["states"]
        self.pixmaps = {}
        dpr = self.devicePixelRatioF() or 1.0

        def prepare(pixmap: QPixmap, smooth: bool) -> QPixmap:
            if dpr != 1.0:
                pixmap = pixmap.scaled(
                    round(pixmap.width() * dpr),
                    round(pixmap.height() * dpr),
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation if smooth else Qt.FastTransformation,
                )
                pixmap.setDevicePixelRatio(dpr)
            return pixmap

        for state, variants in entries.items():
            self.pixmaps[state] = {
                key: prepare(QPixmap(str(ASSETS / relative)), True)
                for key, relative in variants.items()
            }
        # 飘动模式只使用静止高清猪身，不再加载 GIF 腿帧。
        self.walk_frames = []
        self.props = {
            name: QPixmap(str(ASSETS / "props" / f"{name}.png"))
            for name in ("coffee", "music", "sleep", "heart", "sparkle", "anger", "pig")
        }

    def _place_initial(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = int(self.settings.get("x") or 0)
        y = int(self.settings.get("y") or 0)
        if x <= 0 or y <= 0:
            x = screen.right() - self.win_w - 48
            y = screen.bottom() - self.win_h - 68
        self.move(self._clamp_pos(x, y))

    def _clamp_pos(self, x, y):
        screen = QApplication.primaryScreen().availableGeometry()
        x = max(-8, min(int(x), screen.right() - self.win_w + 8))
        y = max(screen.top(), min(int(y), screen.bottom() - self.win_h + 8))
        return QPoint(x, y)

    # ---------------------------------------------------------------- controls

    def _create_tray(self):
        icon = QIcon(str(ASSETS / "icon.ico"))
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        control = QAction("控制中心", self)
        control.triggered.connect(self.open_control_panel)
        corner = QAction("回到右下角", self)
        corner.triggered.connect(self.move_to_corner)
        self.walk_action = QAction("飘动模式", self)
        self.walk_action.setCheckable(True)
        self.walk_action.setChecked(bool(self.settings.get("auto_walk")))
        self.walk_action.toggled.connect(self.set_walk_enabled)
        quit_action = QAction("退出桌宠", self)
        quit_action.triggered.connect(self.quit)
        menu.addAction(control)
        menu.addAction(self.walk_action)
        menu.addAction(corner)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(APP_NAME)
        self.tray.show()

    def open_control_panel(self):
        if self.control_panel:
            self.control_panel.show()
            self.control_panel.raise_()
            return
        self.control_panel = ControlPanel(self)
        self.control_panel.show()

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
        self.update()

    def show_bubble(self, text, seconds=2.5):
        self.bubble_text = text
        self.bubble_until = time.monotonic() + seconds
        self.update()

    def move_to_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.win_w - 48, screen.bottom() - self.win_h - 68)
        self.save()
        self.show_bubble("回到角落啦", 2.0)

    def set_walk_enabled(self, enabled):
        self.settings["auto_walk"] = bool(enabled)
        self.current_state = "walk" if enabled else "idle"
        if self.walk_action:
            self.walk_action.blockSignals(True)
            self.walk_action.setChecked(bool(enabled))
            self.walk_action.blockSignals(False)
        self.save()
        self.update()
        if self.control_panel:
            QTimer.singleShot(0, self.control_panel.refresh)

    def set_size(self, size_name):
        if size_name not in self.manifest["sizes"]:
            return
        right = self.x() + self.win_w
        bottom = self.y() + self.win_h
        self.size_name = size_name
        self.settings["size"] = size_name
        self.win_w, self.win_h = self.manifest["sizes"][size_name]["canvas"]
        self.setFixedSize(self.win_w, self.win_h)
        self._load_images()
        self.move(self._clamp_pos(right - self.win_w, bottom - self.win_h))
        self.update()
        self.save()
        if self.control_panel:
            QTimer.singleShot(0, self.control_panel.refresh)

    def apply_theme(self):
        self.theme = THEMES["dark" if self.settings["dark_mode"] else "light"]
        self.update()
        if self.control_panel:
            QTimer.singleShot(0, self.control_panel.refresh)

    def save(self):
        self.settings.update(
            {
                "x": self.x(),
                "y": self.y(),
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
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    # ---------------------------------------------------------------- painting

    def _state_pixmap(self):
        state = self.current_state if self.current_state in self.pixmaps else "idle"
        variants = self.pixmaps.get(state, self.pixmaps["idle"])
        key = "normal" if self.direction < 0 else "flipped"
        return variants.get(key, variants["normal"])

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if self.bubble_text:
            bubble_w = min(self.win_w - 34, 302)
            bubble_h = 58
            left = (self.win_w - bubble_w) / 2
            top = 8
            rect = QRectF(left, top, bubble_w, bubble_h)
            path = QPainterPath()
            path.addRoundedRect(rect, 17, 17)
            tip = self.win_w / 2 + 28
            path.moveTo(tip - 12, top + bubble_h - 1)
            path.lineTo(tip, top + bubble_h + 15)
            path.lineTo(tip + 12, top + bubble_h - 1)
            painter.setBrush(QColor(self.theme["bubble"]))
            painter.setPen(QPen(QColor(self.theme["line"]), 1))
            painter.drawPath(path)
            painter.setPen(QColor(self.theme["bubble_text"]))
            painter.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, self.bubble_text)

        pixmap = self._state_pixmap()
        draw_w = pixmap.width() / (pixmap.devicePixelRatio() or 1.0)
        draw_h = pixmap.height() / (pixmap.devicePixelRatio() or 1.0)
        bob = math.sin(self.phase * 2.0) * 2.0
        if self.current_state == "walk":
            bob = math.sin(self.phase * 1.8) * 6.0 + math.sin(self.phase * 0.7) * 2.0
        shake = math.sin(self.phase * 16.0) * 3.3 if self.current_state == "angry" else 0
        bounce = abs(math.sin(self.phase * 5.0)) * 3.2 if self.current_state == "happy" else 0
        x = (self.win_w - draw_w) / 2 + shake
        y = self.win_h - draw_h - 8 + bob - bounce

        shadow = QRadialGradient(
            self.win_w / 2,
            self.win_h - 4,
            max(30, draw_w * 0.42),
        )
        shadow.setColorAt(0, QColor(0, 0, 0, 78))
        shadow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(shadow)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            QRectF(
                self.win_w / 2 - draw_w * 0.38,
                self.win_h - 18,
                draw_w * 0.76,
                24,
            )
        )
        painter.drawPixmap(int(x), int(y), pixmap)

        if self.prop_kind:
            prop = self.props.get(self.prop_kind)
            if prop:
                prop = prop.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                px = self.win_w - prop.width() - 26
                py = 102 + math.sin(self.prop_phase) * 5
                painter.drawPixmap(int(px), int(py), prop)

    # ---------------------------------------------------------------- events

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_moved = False
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
        elif event.button() == Qt.RightButton:
            self.open_control_panel()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            target = event.globalPosition().toPoint() - self.drag_offset
            if (target - self.pos()).manhattanLength() > 4:
                self.drag_moved = True
            self.move(self._clamp_pos(target.x(), target.y()))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            if self.drag_moved:
                self.save()
            else:
                self._click_action()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.do_action("music")

    def _click_action(self):
        if self.override_state in self.action_cycle:
            index = (self.action_cycle.index(self.override_state) + 1) % len(
                self.action_cycle
            )
        else:
            index = 0
        self.do_action(self.action_cycle[index])

    def _tick(self):
        now = time.monotonic()
        self.phase += 0.055
        self.prop_phase += 0.08
        if self.override_until and now >= self.override_until:
            self.override_state = None
            self.override_until = 0
        if self.bubble_until and now >= self.bubble_until:
            self.bubble_text = ""
        if self.prop_until and now >= self.prop_until:
            self.prop_kind = ""
        if (
            self.settings["random_actions"]
            and not self.dragging
            and now >= self.next_random_action
            and not self.override_state
        ):
            self.next_random_action = now + random.uniform(9, 18)
            self.do_action(random.choice(["sleepy", "music", "happy"]))

        walking = bool(
            self.settings["auto_walk"] and not self.dragging and not self.override_state
        )
        if walking:
            pos = self.pos()
            x = pos.x() + self.vx
            screen = QApplication.primaryScreen().availableGeometry()
            if x > screen.right() - self.win_w + 8:
                x = screen.right() - self.win_w + 8
                self.vx = -abs(self.vx)
            elif x < screen.left() - 8:
                x = screen.left() - 8
                self.vx = abs(self.vx)
            self.direction = 1 if self.vx > 0 else -1
            self.move(int(x), pos.y())
            self.current_state = "walk"
        elif self.override_state:
            self.current_state = self.override_state
        else:
            self.current_state = "idle"
        self.update()


class ControlPanel(QWidget):
    def __init__(self, pet: PetWindow):
        super().__init__(None)
        self.pet = pet
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(430)
        self._drag_pos = None
        self._build()

    def _build(self):
        if self.layout():
            QWidget().setLayout(self.layout())
        theme = self.pet.theme
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("控制中心")
        title.setStyleSheet(
            f"color:{theme['text']};font-size:25px;font-weight:700;"
        )
        subtitle = QLabel("让谷歌猪按你的习惯待在桌面上")
        subtitle.setStyleSheet(f"color:{theme['secondary']};font-size:11px;")
        status = QLabel(
            "飘动模式已开启" if self.pet.settings.get("auto_walk") else "飘动模式已关闭"
        )
        status.setStyleSheet(
            "QLabel{"
            f"color:{theme['accent'] if self.pet.settings.get('auto_walk') else theme['tertiary']};"
            f"background:{'rgba(10,132,255,40)' if self.pet.settings.get('auto_walk') else theme['card2']};"
            "border-radius:9px;padding:3px 8px;font-size:10px;"
            "}"
        )
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_box.addWidget(status)
        header.addLayout(title_box, 1)
        icon = QLabel()
        icon.setPixmap(
            self.pet.props["pig"].scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        header.addWidget(icon)
        root.addLayout(header)

        behavior = self._card()
        behavior_layout = QVBoxLayout(behavior)
        behavior_layout.setContentsMargins(14, 10, 14, 10)
        behavior_layout.setSpacing(0)
        rows = [
            ("飘动模式", "默认开启，可随时关闭", "auto_walk"),
            ("始终置顶", "保持在窗口最前", "topmost"),
            ("随机小动作", "偶尔切换表情", "random_actions"),
            ("深色外观", "控制中心使用深色", "dark_mode"),
            ("开机启动", "登录 Windows 后自动出现", "start_on_boot"),
        ]
        for index, (name, note, key) in enumerate(rows):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 5, 0, 5)
            text_box = QVBoxLayout()
            label = QLabel(name)
            label.setStyleSheet(f"color:{theme['text']};font-size:12px;font-weight:600;")
            detail = QLabel(note)
            detail.setStyleSheet(f"color:{theme['secondary']};font-size:9px;")
            text_box.addWidget(label)
            text_box.addWidget(detail)
            row_layout.addLayout(text_box, 1)
            switch = SwitchButton(bool(self.pet.settings[key]))
            switch.toggled.connect(lambda value, k=key: self._toggle(k, value))
            row_layout.addWidget(switch)
            behavior_layout.addWidget(row)
            if index != len(rows) - 1:
                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet(f"background:{theme['line']};")
                behavior_layout.addWidget(line)
        root.addWidget(behavior)

        size_card = self._card()
        size_layout = QVBoxLayout(size_card)
        size_layout.setContentsMargins(14, 10, 14, 10)
        size_title = QLabel("桌宠大小")
        size_title.setStyleSheet(f"color:{theme['text']};font-size:12px;font-weight:600;")
        size_layout.addWidget(size_title)
        segment = QHBoxLayout()
        group = QButtonGroup(self)
        labels = {"small": "小", "medium": "中", "large": "大"}
        for key, label in labels.items():
            button = QPushButton(label)
            button.setCheckable(True)
            button.setChecked(self.pet.size_name == key)
            button.setFixedHeight(34)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton{border:none;border-radius:8px;background:"
                + (theme["accent"] if self.pet.size_name == key else theme["card2"])
                + ";color:"
                + ("#FFFFFF" if self.pet.size_name == key else theme["text"])
                + ";font-size:12px;}"
            )
            button.clicked.connect(lambda _=False, k=key: self.pet.set_size(k))
            group.addButton(button)
            segment.addWidget(button)
        size_layout.addLayout(segment)
        root.addWidget(size_card)

        action_card = self._card()
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(14, 10, 14, 10)
        action_title = QLabel("快速动作")
        action_title.setStyleSheet(f"color:{theme['text']};font-size:12px;font-weight:600;")
        action_layout.addWidget(action_title)
        grid = QGridLayout()
        actions = [
            ("摸摸", lambda: self.pet.do_action("happy")),
            ("睡觉", lambda: self.pet.do_action("sleepy")),
            ("听歌", lambda: self.pet.do_action("music")),
            ("生气", lambda: self.pet.do_action("angry")),
            ("回角落", self.pet.move_to_corner),
        ]
        for i, (label, callback) in enumerate(actions):
            button = QPushButton(label)
            button.setFixedHeight(36)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton{{border:none;border-radius:10px;background:{theme['card2']};"
                f"color:{theme['accent']};font-size:11px;font-weight:600;}}"
            )
            button.clicked.connect(callback)
            grid.addWidget(button, i // 3, i % 3)
        action_layout.addLayout(grid)
        root.addWidget(action_card)

        footer = QHBoxLayout()
        quit_button = QPushButton("退出桌宠")
        quit_button.setFixedHeight(42)
        quit_button.setCursor(Qt.PointingHandCursor)
        quit_button.setStyleSheet(
            f"QPushButton{{border:1px solid {theme['line']};border-radius:12px;"
            f"background:{theme['card']};color:{theme['red']};font-weight:600;}}"
        )
        quit_button.clicked.connect(self.pet.quit)
        done = QPushButton("完成")
        done.setFixedHeight(42)
        done.setCursor(Qt.PointingHandCursor)
        done.setStyleSheet(
            f"QPushButton{{border:none;border-radius:12px;background:{theme['accent']};"
            "color:#FFFFFF;font-weight:600;}"
        )
        done.clicked.connect(self.close)
        footer.addWidget(quit_button)
        footer.addStretch()
        footer.addWidget(done)
        root.addLayout(footer)

        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 54, max(screen.top() + 20, (screen.height() - self.height()) // 2))

    def _card(self):
        card = QFrame()
        card.setStyleSheet(
            f"QFrame{{background:{self.pet.theme['card']};border:1px solid "
            f"{self.pet.theme['line']};border-radius:16px;}}"
        )
        return card

    def refresh(self):
        self._build()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(self.pet.theme["bg"]))
        painter.setPen(QPen(QColor(self.pet.theme["line"]), 1))
        painter.drawRoundedRect(QRectF(8, 8, self.width() - 16, self.height() - 16), 22, 22)

    def _toggle(self, key, value):
        self.pet.settings[key] = bool(value)
        if key == "auto_walk":
            self.pet.set_walk_enabled(bool(value))
            return
        if key == "topmost":
            self.pet.setWindowFlag(Qt.WindowStaysOnTopHint, bool(value))
            self.pet.show()
        if key == "start_on_boot":
            if not set_startup(bool(value)):
                self.pet.show_bubble("开机启动设置失败", 2.2)
        self.pet.save()
        if key == "dark_mode":
            self.pet.apply_theme()
        else:
            self.pet.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None


def main():
    if not acquire_single_instance():
        return
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--no-walk", action="store_true")
    parser.add_argument("--control-center", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = PetWindow(no_walk=args.no_walk, open_control=args.control_center)
    if args.smoke_test:
        pet.quit()
        print("qt smoke-test: OK")
        return
    app.exec()


if __name__ == "__main__":
    main()
