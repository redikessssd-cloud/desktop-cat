# -*- coding: utf-8 -*-
"""Desktop Cat — autonomous pixel cat pet.
Walks left/right, climbs onto your windows and scratches them, sleeps,
follows the mouse with its eyes, reacts to typing, can be dragged
(mochi-stretch), and poops a 💩 emoji.
Needs: pip install pillow pynput   (pynput optional, for typing reaction)
Keep cat.py together with the cat_*.png sprite files.
"""
import os
import sys
import math
import random
import time
import tkinter as tk

try:
    from PIL import Image, ImageTk
except Exception:
    raise SystemExit("Pillow is required:  pip install pillow")

try:
    from pynput import keyboard as _kb
    HAVE_PYNPUT = True
except Exception:
    HAVE_PYNPUT = False

DIR = os.path.dirname(os.path.abspath(__file__))
TRANSPARENT = "#ff4dff"   # magic color that becomes click-through / invisible
DISPLAY_H = 120           # on-screen cat height in px
TICK = 33                 # ms per frame (~30 fps)
BUBBLE_SPACE = 28         # px reserved above the cat for speech bubbles
FOOT_PAD = 14             # px reserved below the cat

SPRITE_FILES = {
    "sit":     "cat.png",
    "stretch": "cat_stretch.png",
    "scratch": "cat_scratch.png",
    "play":    "cat_play.png",
    "stand":   "cat_stand.png",
    "walk":    "cat_walk.png",
    "sleep":   "cat_sleep.png",
    "type":    "cat_type.png",
}

WINDOWS = sys.platform.startswith("win")

# ---------------------------------------------------------------------------
# Windows: enumerate other top-level windows so the cat can climb on them.
# ---------------------------------------------------------------------------
if WINDOWS:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def list_windows(own_title):
        out = []
        def cb(hwnd, lparam):
            try:
                if not _user32.IsWindowVisible(hwnd):
                    return True
                if _user32.IsIconic(hwnd):
                    return True
                n = _user32.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                _user32.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value
                if not title or title == own_title:
                    return True
                if title in ("Program Manager", "Windows Input Experience",
                             "Setup", "Default IME"):
                    return True
                rc = wintypes.RECT()
                if not _user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                    return True
                w = rc.right - rc.left
                h = rc.bottom - rc.top
                if w < 220 or h < 130:
                    return True
                out.append((rc.left, rc.top, rc.right, rc.bottom))
            except Exception:
                return True
            return True
        try:
            _user32.EnumWindows(_ENUMPROC(cb), 0)
        except Exception:
            return []
        return out
else:
    def list_windows(own_title):
        return []


def make_fallback_cat():
    """Tiny drawn cat used only if cat.png is missing."""
    from PIL import ImageDraw
    s = 160
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    body = (32, 32, 38, 255)
    d.ellipse((30, 60, 130, 150), fill=body)
    d.ellipse((40, 20, 120, 100), fill=body)
    d.polygon((48, 40, 40, 8, 70, 30), fill=body)
    d.polygon((112, 40, 120, 8, 90, 30), fill=body)
    d.ellipse((60, 55, 74, 72), fill=(120, 220, 120, 255))
    d.ellipse((86, 55, 100, 72), fill=(120, 220, 120, 255))
    d.polygon((76, 70, 84, 70, 80, 78), fill=(240, 150, 160, 255))
    return img


def detect_eyes(img):
    """Find the two green eyes; return ([(x, y), ...], pupil_radius)."""
    px = img.load()
    W, H = img.size
    pts = []
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if a > 40 and g > 110 and g > r + 35 and g > b + 35:
                pts.append((x, y))
    if len(pts) < 6:
        return [], 3
    midx = sum(p[0] for p in pts) / len(pts)
    groups = [[p for p in pts if p[0] < midx], [p for p in pts if p[0] >= midx]]
    eyes = []
    for grp in groups:
        if grp:
            cx = sum(p[0] for p in grp) / len(grp)
            cy = sum(p[1] for p in grp) / len(grp)
            eyes.append((cx, cy))
    pr = max(2, min(5, (len(pts) / max(1, len(eyes))) ** 0.5 * 0.35))
    return eyes, pr


class DesktopCat:
    def __init__(self):
        self.root = tk.Tk()
        self.title = "DesktopCatPet"
        self.root.title(self.title)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except Exception:
            pass

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        # ---- load sprites ----
        self.images = {}
        self.sizes = {}
        maxw = 80
        for name, fn in SPRITE_FILES.items():
            path = os.path.join(DIR, fn)
            try:
                im = Image.open(path).convert("RGBA")
            except Exception:
                if name == "sit":
                    im = make_fallback_cat()
                else:
                    continue
            r = DISPLAY_H / im.height
            im = im.resize((max(1, int(im.width * r)), DISPLAY_H), Image.NEAREST)
            flip = im.transpose(Image.FLIP_LEFT_RIGHT)
            self.images[name] = {1: ImageTk.PhotoImage(im), -1: ImageTk.PhotoImage(flip)}
            self.sizes[name] = (im.width, im.height)
            maxw = max(maxw, im.width)
        if "sit" not in self.images:
            im = make_fallback_cat().resize((DISPLAY_H, DISPLAY_H), Image.NEAREST)
            self.images["sit"] = {1: ImageTk.PhotoImage(im), -1: ImageTk.PhotoImage(im)}
            self.sizes["sit"] = (DISPLAY_H, DISPLAY_H)
            maxw = max(maxw, DISPLAY_H)

        # detect eyes on the sit sprite (for mouse-following pupils)
        self.eyes = []
        self.pupil_r = 3
        try:
            _sp = Image.open(os.path.join(DIR, SPRITE_FILES["sit"])).convert("RGBA")
            _r = DISPLAY_H / _sp.height
            _sp = _sp.resize((max(1, int(_sp.width * _r)), DISPLAY_H), Image.NEAREST)
            self.eyes, self.pupil_r = detect_eyes(_sp)
        except Exception:
            self.eyes = []

        self.winw = maxw + 40
        self.winh = BUBBLE_SPACE + DISPLAY_H + FOOT_PAD
        self.cx = self.winw // 2
        self.cy = BUBBLE_SPACE + DISPLAY_H // 2

        self.canvas = tk.Canvas(self.root, width=self.winw, height=self.winh,
                                 bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.sprite_id = self.canvas.create_image(self.cx, self.cy,
                                                   image=self.images["sit"][1])
        self.bubble_ids = []
        self.pupil_ids = []
        for _ in self.eyes:
            self.pupil_ids.append(self.canvas.create_oval(0, 0, 0, 0,
                                                          fill="#0d0d14", outline=""))

        # ---- position / motion state ----
        self.ground_y = self.sh - self.winh - 60
        self.x = random.randint(40, max(60, self.sw - self.winw - 40))
        self.y = self.ground_y
        self.facing = -1
        self.target = None
        self.state = "idle"
        self.state_until = 0.0
        self.next_decision = time.time() + random.uniform(2, 4)
        self.next_meow = time.time() + random.uniform(8, 18)
        self.cur_sprite = "sit"
        self.anim_phase = 0.0
        self.type_until = 0.0
        self._was_typing = False
        self.poops = []
        self.scratch_target = None
        self.cooldown_window = 0.0

        # ---- dragging ----
        self.drag = False
        self.drag_dx = 0
        self.drag_dy = 0
        self.press_xy = None
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_menu)
        self.canvas.bind("<Double-Button-1>", lambda e: self.start_walk())

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Гулять", command=self.start_walk)
        self.menu.add_command(label="Поспать", command=self.start_sleep)
        self.menu.add_command(label="Поцарапать окно", command=self.start_window_hunt)
        self.menu.add_command(label="Покакать", command=self.drop_poop)
        self.menu.add_separator()
        self.menu.add_command(label="Закрыть", command=self.quit)

        if HAVE_PYNPUT:
            try:
                self._listener = _kb.Listener(on_press=self._on_key)
                self._listener.daemon = True
                self._listener.start()
            except Exception:
                pass

        self.apply_geometry()
        self.tick()

    # ------------------------------------------------------------------
    def apply_geometry(self):
        self.x = max(-20, min(self.sw - self.winw + 20, int(self.x)))
        self.y = max(-10, min(self.sh - self.winh + 10, int(self.y)))
        self.root.geometry("%dx%d+%d+%d" % (self.winw, self.winh, self.x, self.y))

    def set_sprite(self, name):
        if name not in self.images:
            name = "sit"
        self.cur_sprite = name
        self.canvas.itemconfig(self.sprite_id, image=self.images[name][self.facing])
        w, h = self.sizes[name]
        self.canvas.coords(self.sprite_id, self.cx, BUBBLE_SPACE + h // 2)

    def _update_pupils(self, mx, my):
        if not self.pupil_ids:
            return
        if self.cur_sprite != "sit" or self.drag:
            for pid in self.pupil_ids:
                self.canvas.coords(pid, -20, -20, -19, -19)
            return
        w, h = self.sizes["sit"]
        left_x = self.cx - w // 2
        for i, (ex, ey) in enumerate(self.eyes):
            if i >= len(self.pupil_ids):
                break
            sx = (w - ex) if self.facing == -1 else ex
            canvas_x = left_x + sx
            canvas_y = BUBBLE_SPACE + ey
            gx = self.x + canvas_x
            gy = self.y + canvas_y
            dx = mx - gx
            dy = my - gy
            d = max(1.0, (dx * dx + dy * dy) ** 0.5)
            off = min(self.pupil_r * 0.9, d)
            ox = dx / d * off
            oy = dy / d * off
            r = self.pupil_r
            self.canvas.coords(self.pupil_ids[i],
                               canvas_x + ox - r, canvas_y + oy - r,
                               canvas_x + ox + r, canvas_y + oy + r)
            self.canvas.tag_raise(self.pupil_ids[i])

    # ------------------------------------------------------------------
    def say(self, text, kind="text"):
        for i in self.bubble_ids:
            self.canvas.delete(i)
        self.bubble_ids = []
        x, y = self.cx, 14
        if kind == "emoji":
            t = self.canvas.create_text(x, y, text=text, font=("Segoe UI Emoji", 16))
            self.bubble_ids.append(t)
        else:
            t = self.canvas.create_text(x, y, text=text, font=("Segoe UI", 11, "bold"),
                                        fill="#33235a")
            bb = self.canvas.bbox(t)
            if bb:
                pad = 4
                r = self.canvas.create_rectangle(bb[0]-pad, bb[1]-pad, bb[2]+pad, bb[3]+pad,
                                                 fill="#ffffff", outline="#d8cff0")
                self.canvas.tag_lower(r, t)
                self.bubble_ids.append(r)
            self.bubble_ids.append(t)
        self._bubble_until = time.time() + 1.6

    def clear_bubble(self):
        for i in self.bubble_ids:
            self.canvas.delete(i)
        self.bubble_ids = []

    # ------------------------------------------------------------------
    def drop_poop(self):
        fx = self.x + self.cx
        fy = self.y + BUBBLE_SPACE + DISPLAY_H - 18
        try:
            p = tk.Toplevel(self.root)
            p.overrideredirect(True)
            p.attributes("-topmost", True)
            try:
                p.attributes("-transparentcolor", TRANSPARENT)
            except Exception:
                pass
            p.configure(bg=TRANSPARENT)
            tk.Label(p, text="💩", font=("Segoe UI Emoji", 20), bg=TRANSPARENT).pack()
            p.update_idletasks()
            p.geometry("+%d+%d" % (int(fx), int(fy)))
            self.poops.append(p)
            if len(self.poops) > 8:
                old = self.poops.pop(0)
                try:
                    old.destroy()
                except Exception:
                    pass
            self.root.after(15000, lambda w=p: self._kill_poop(w))
        except Exception:
            pass
        self.say("💩", kind="emoji")

    def _kill_poop(self, w):
        try:
            if w in self.poops:
                self.poops.remove(w)
            w.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def start_walk(self):
        self.target = (random.randint(0, max(1, self.sw - self.winw)), self.ground_y)
        self.state = "walk"

    def start_sleep(self):
        self.state = "sleep"
        self.state_until = time.time() + random.uniform(6, 11)
        self.set_sprite("sleep")
        self.say("z z z")

    def start_scratch_air(self):
        self.state = "scratch"
        self.state_until = time.time() + 1.8
        self.set_sprite("scratch")
        self.say(random.choice(["царап!", "мяу!", "~"]))

    def start_window_hunt(self):
        wins = list_windows(self.title)
        if not wins:
            self.start_scratch_air()
            return
        random.shuffle(wins)
        l, t, r, b = wins[0]
        tx = max(0, min(self.sw - self.winw, l + (r - l) // 2 - self.winw // 2))
        ty = max(0, t - (BUBBLE_SPACE + DISPLAY_H) + 24)
        self.scratch_target = (tx, ty)
        self.target = (tx, self.ground_y)
        self.state = "goto_window"

    # ------------------------------------------------------------------
    def _approach(self, cur, tgt, step):
        if abs(tgt - cur) <= step:
            return tgt, True
        return cur + step * (1 if tgt > cur else -1), False

    def tick(self):
        now = time.time()
        try:
            mx, my = self.root.winfo_pointerxy()
        except Exception:
            mx, my = self.x + self.cx, self.y

        if self.bubble_ids and now > getattr(self, "_bubble_until", 0):
            self.clear_bubble()

        typing = now < self.type_until

        if self.drag:
            self._render_drag()
            self._update_pupils(mx, my)
            self._was_typing = typing
            self.root.after(TICK, self.tick)
            return

        st = self.state

        if st == "idle":
            if typing:
                self.set_sprite("type")
                self.anim_phase += 0.6
                bob = abs(math.sin(self.anim_phase)) * 4
                w, h = self.sizes["type"]
                self.canvas.coords(self.sprite_id, self.cx, BUBBLE_SPACE + h // 2 + bob)
                if not self._was_typing:
                    self.say("тык-тык!")
                elif random.random() < 0.03:
                    self.say(random.choice(["мяу", "мур", "тык-тык"]))
            else:
                self.facing = -1 if mx < self.x + self.cx else 1
                self.set_sprite("sit")
                if now > self.next_meow:
                    self.say(random.choice(["мяу", "мяу~", "мур", "ня"]))
                    self.next_meow = now + random.uniform(8, 20)
                if now > self.next_decision:
                    self._decide()

        elif st == "walk":
            self.set_sprite("walk")
            tx, ty = self.target
            self.facing = -1 if tx < self.x else 1
            self.x, dx_done = self._approach(self.x, tx, 4.0)
            self.y, dy_done = self._approach(self.y, ty, 4.0)
            self.anim_phase += 0.3
            self.y += math.sin(self.anim_phase) * 1.2
            if dx_done and dy_done:
                self.state = "idle"
                self.next_decision = now + random.uniform(2, 5)
            if now > self.next_meow and random.random() < 0.3:
                self.say(random.choice(["мяу", "мур~"]))
                self.next_meow = now + random.uniform(8, 20)

        elif st == "goto_window":
            self.set_sprite("walk")
            tx, ty = self.target
            self.facing = -1 if tx < self.x else 1
            self.x, dxd = self._approach(self.x, tx, 4.5)
            if dxd:
                self.target = self.scratch_target
                self.state = "climb"

        elif st == "climb":
            self.set_sprite("stand")
            tx, ty = self.target
            self.x, dxd = self._approach(self.x, tx, 4.0)
            self.y, dyd = self._approach(self.y, ty, 4.0)
            if dxd and dyd:
                self.state = "scratch_window"
                self.state_until = now + 2.4
                self.set_sprite("scratch")
                self.say("царап-царап!")

        elif st == "scratch_window":
            self.set_sprite("scratch")
            self.x += math.sin(now * 22) * 1.5
            if random.random() < 0.03:
                self.say(random.choice(["царап!", "мяу!", "мур"]))
            if now > self.state_until:
                self.drop_poop()
                self.state = "idle"
                self.next_decision = now + random.uniform(3, 6)
                self.cooldown_window = now + random.uniform(15, 30)

        elif st == "sleep":
            self.set_sprite("sleep")
            if random.random() < 0.01:
                self.say("z z z")
            if now > self.state_until:
                self.state = "idle"
                self.next_decision = now + random.uniform(2, 4)

        elif st == "scratch":
            self.set_sprite("scratch")
            self.x += math.sin(now * 22) * 1.2
            if now > self.state_until:
                if random.random() < 0.5:
                    self.drop_poop()
                self.state = "idle"
                self.next_decision = now + random.uniform(2, 5)

        self._update_pupils(mx, my)
        self.apply_geometry()
        self._was_typing = typing
        self.root.after(TICK, self.tick)

    def _decide(self):
        now = time.time()
        choices = ["walk", "walk", "sleep", "scratch"]
        if now > self.cooldown_window and (not WINDOWS or list_windows(self.title)):
            choices += ["window", "window"]
        pick = random.choice(choices)
        if pick == "walk":
            self.start_walk()
        elif pick == "sleep":
            self.start_sleep()
        elif pick == "scratch":
            self.start_scratch_air()
        elif pick == "window":
            self.start_window_hunt()

    # ------------------------------------------------------------------
    def _render_drag(self):
        base = self.images.get("stretch", self.images["sit"])
        self.canvas.itemconfig(self.sprite_id, image=base[self.facing])
        w, h = self.sizes.get("stretch", self.sizes["sit"])
        self.canvas.coords(self.sprite_id, self.cx, BUBBLE_SPACE + h // 2)
        self.cur_sprite = "stretch"

    def on_press(self, e):
        self.drag = True
        self.press_xy = (e.x_root, e.y_root)
        self.drag_dx = e.x_root - self.x
        self.drag_dy = e.y_root - self.y
        self.set_sprite("stretch")

    def on_drag(self, e):
        if not self.drag:
            return
        self.x = e.x_root - self.drag_dx
        self.y = e.y_root - self.drag_dy
        self.apply_geometry()

    def on_release(self, e):
        self.drag = False
        moved = 0
        if self.press_xy:
            moved = abs(e.x_root - self.press_xy[0]) + abs(e.y_root - self.press_xy[1])
        self.state = "idle"
        self.next_decision = time.time() + random.uniform(1, 3)
        if moved < 4:
            self.say(random.choice(["мяу~", "мур", "❤", "ня"]))

    def on_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _on_key(self, key):
        self.type_until = time.time() + 1.3

    def quit(self):
        for p in list(self.poops):
            try:
                p.destroy()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if HAVE_PYNPUT:
        print("[cat] typing reaction: ON")
    else:
        print("[cat] pynput NOT installed -> typing reaction OFF."
              "  Install with:  pip install pynput")
    DesktopCat().run()
