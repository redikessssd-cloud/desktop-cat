# -*- coding: utf-8 -*-
"""Desktop Cat — autonomous pixel cat pet (v4: smooth squash & stretch).

What's new in v4 ("juice", inspired by the technique behind desktop pets):
  * Procedural squash-and-stretch on every action (breathing idle, walk bob,
    landing spring after you drop it, typing tap) — rendered live with Pillow.
  * Eased walking (smooth accelerate / decelerate) instead of robotic steps.
  * Robust reactions: the cat now reacts to typing from ANY state, and its
    pupils always follow the mouse (with a fallback if eyes aren't detected).

Still here: climbs your windows and scratches them, sleeps, can be dragged
(mochi-stretch), poops a 💩 emoji, right-click menu.

Needs:  pip install pillow pynput      (pynput = global typing/mouse reaction)
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
BUBBLE_SPACE = 36         # px reserved above the cat for speech bubbles + stretch
FOOT_PAD = 16             # px reserved below the cat

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


def ease(t):
    """Smoothstep easing 0..1 (ease-in-out)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


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

        # ---- load sprites as PIL images (kept for live squash/stretch) ----
        self.base = {}     # name -> {1: PIL Image, -1: flipped PIL Image}
        self.sizes = {}    # name -> (w, h) at nominal display height
        self._frame_cache = {}   # (name, facing, qsx, qsy) -> PhotoImage
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
            self.base[name] = {1: im, -1: flip}
            self.sizes[name] = (im.width, im.height)
            maxw = max(maxw, im.width)
        if "sit" not in self.base:
            im = make_fallback_cat().resize((DISPLAY_H, DISPLAY_H), Image.NEAREST)
            self.base["sit"] = {1: im, -1: im.transpose(Image.FLIP_LEFT_RIGHT)}
            self.sizes["sit"] = (DISPLAY_H, DISPLAY_H)
            maxw = max(maxw, DISPLAY_H)

        # detect eyes on the sit sprite (for mouse-following pupils)
        self.eyes, self.pupil_r = detect_eyes(self.base["sit"][1])
        if not self.eyes:
            w0, h0 = self.sizes["sit"]
            self.eyes = [(w0 * 0.42, h0 * 0.34), (w0 * 0.58, h0 * 0.34)]
            self.pupil_r = 3

        self.winw = maxw + 60
        self.winh = BUBBLE_SPACE + DISPLAY_H + FOOT_PAD
        self.cx = self.winw // 2
        self.foot_y = BUBBLE_SPACE + DISPLAY_H   # ground line inside the window

        self.canvas = tk.Canvas(self.root, width=self.winw, height=self.winh,
                                 bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.sprite_id = self.canvas.create_image(self.cx, self.foot_y - DISPLAY_H // 2,
                                                  image=self._get_frame("sit", 1, 1.0, 1.0))
        self._rinfo = (self.cx, self.foot_y - DISPLAY_H / 2.0,
                       self.sizes["sit"][0], self.sizes["sit"][1])
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
        self.walk_phase = 0.0
        self.type_phase = 0.0
        self.walk_from = self.x
        self.walk_to = self.x
        self.walk_start = 0.0
        self.walk_dur = 1.0
        self.land_t = -10.0
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
        self.menu.add_command(label="Потянуться", command=self.start_stretch)
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
    # Live sprite rendering with squash & stretch (volume-aware).
    # ------------------------------------------------------------------
    def _get_frame(self, name, facing, sx, sy):
        if name not in self.base:
            name = "sit"
        qsx = max(0.55, min(1.6, round(sx, 2)))
        qsy = max(0.55, min(1.6, round(sy, 2)))
        key = (name, facing, qsx, qsy)
        ph = self._frame_cache.get(key)
        if ph is None:
            base = self.base[name][facing]
            w, h = base.size
            nw = max(1, int(round(w * qsx)))
            nh = max(1, int(round(h * qsy)))
            im = base if (nw == w and nh == h) else base.resize((nw, nh), Image.NEAREST)
            ph = ImageTk.PhotoImage(im)
            if len(self._frame_cache) > 600:
                self._frame_cache.clear()
            self._frame_cache[key] = ph
        return ph

    def _render(self, name, sx=1.0, sy=1.0, dx=0.0, dy=0.0):
        if name not in self.base:
            name = "sit"
        img = self._get_frame(name, self.facing, sx, sy)
        nw = img.width()
        nh = img.height()
        cx = self.cx + dx
        cy = self.foot_y - nh / 2.0 + dy
        self.canvas.itemconfig(self.sprite_id, image=img)
        self.canvas.coords(self.sprite_id, cx, cy)
        self.cur_sprite = name
        self._rinfo = (cx, cy, nw, nh)

    def set_sprite(self, name):
        """Render a sprite at neutral scale (compat helper)."""
        self._render(name, 1.0, 1.0)

    def _update_pupils(self, mx, my):
        if not self.pupil_ids:
            return
        if self.cur_sprite != "sit" or self.drag:
            for pid in self.pupil_ids:
                self.canvas.coords(pid, -20, -20, -19, -19)
            return
        cx, cy, nw, nh = self._rinfo
        w0, h0 = self.sizes["sit"]
        scale_x = nw / float(w0)
        scale_y = nh / float(h0)
        left = cx - nw / 2.0
        top = cy - nh / 2.0
        for i, (ex, ey) in enumerate(self.eyes):
            if i >= len(self.pupil_ids):
                break
            ex2 = (w0 - ex) if self.facing == -1 else ex
            canvas_x = left + ex2 * scale_x
            canvas_y = top + ey * scale_y
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
        x, y = self.cx, 16
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
        fy = self.y + self.foot_y - 18
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
        tx = random.randint(0, max(1, self.sw - self.winw))
        self.walk_from = self.x
        self.walk_to = tx
        self.walk_start = time.time()
        self.walk_dur = max(0.6, abs(tx - self.x) / 120.0)
        self.facing = -1 if tx < self.x else 1
        self.y = self.ground_y
        self.state = "walk"

    def start_stretch(self):
        self.state = "stretch"
        self.state_until = time.time() + 1.6
        self.say(random.choice(["ня~", "мрр", "х-хаа"]))

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

    def _step(self):
        now = time.time()
        try:
            mx, my = self.root.winfo_pointerxy()
        except Exception:
            mx, my = self.x + self.cx, self.y

        if self.bubble_ids and now > getattr(self, "_bubble_until", 0):
            self.clear_bubble()

        typing = now < self.type_until

        # --- being dragged: mochi stretch following the cursor ---
        if self.drag:
            self._render_drag()
            self._update_pupils(mx, my)
            self._was_typing = typing
            return

        # --- typing reaction overrides everything (except sleep) ---
        if typing and self.state != "sleep":
            self.type_phase += 0.45
            s = abs(math.sin(self.type_phase))
            self._face_toward(mx)
            self._render("type", 1.0 + 0.012 * s, 1.0 - 0.018 * s, 0.0, 1.0 * s)
            if not self._was_typing:
                self.say(random.choice(["мяу!", "тык-тык!", "мур?"]))
            elif random.random() < 0.02:
                self.say(random.choice(["мяу", "мур", "ня", "тык-тык"]))
            self._update_pupils(mx, my)
            self.apply_geometry()
            self._was_typing = typing
            return

        # hover-to-pause: when the cursor is over the cat, hold still so
        # it's easy to grab and drag (the transparent padding counts too)
        over = (self.x <= mx <= self.x + self.winw and
                self.y <= my <= self.y + self.winh)
        if over and self.state in ("idle", "walk"):
            self.state = "idle"
            self.next_decision = now + random.uniform(1.5, 3.0)
            self._face_toward(mx)
            self._render("sit", 1.0, 1.0)
            self._update_pupils(mx, my)
            self.apply_geometry()
            self._was_typing = typing
            return

        st = self.state

        if st == "idle":
            self._face_toward(mx)
            if now - self.land_t < 0.5:
                # landing spring after being dropped
                e = (now - self.land_t) / 0.5
                sy = 1.0 - 0.32 * math.cos(e * 10.0) * math.exp(-3.2 * e)
                sx = (1.0 / max(0.45, sy)) ** 0.5
                self._render("sit", sx, sy)
            else:
                # gentle breathing
                br = math.sin(now * 2.2)
                self._render("sit", 1.0 - 0.025 * br, 1.0 + 0.03 * br)
                if now > self.next_meow:
                    self.say(random.choice(["мяу", "мяу~", "мур", "ня"]))
                    self.next_meow = now + random.uniform(8, 20)
                if now > self.next_decision:
                    self._decide()

        elif st == "walk":
            e = (now - self.walk_start) / self.walk_dur
            if e >= 1.0:
                self.x = self.walk_to
                self.state = "idle"
                self.next_decision = now + random.uniform(2, 5)
                self.set_sprite("sit")
            else:
                self.x = self.walk_from + (self.walk_to - self.walk_from) * ease(e)
                self.walk_phase += 0.35
                lift = abs(math.sin(self.walk_phase))
                sy = 1.0 + 0.05 * math.sin(self.walk_phase * 2.0)
                sx = 1.0 - 0.04 * math.sin(self.walk_phase * 2.0)
                self._render("walk", sx, sy, 0.0, -4.0 * lift)
                if now > self.next_meow and random.random() < 0.2:
                    self.say(random.choice(["мяу", "мур~"]))
                    self.next_meow = now + random.uniform(8, 20)

        elif st == "stretch":
            e = (now - (self.state_until - 1.6)) / 1.6
            # ease into a big vertical stretch, then settle back
            k = math.sin(min(1.0, max(0.0, e)) * math.pi)
            self._render("stretch", 1.0 - 0.12 * k, 1.0 + 0.22 * k, 0.0, -6.0 * k)
            if now > self.state_until:
                self.state = "idle"
                self.next_decision = now + random.uniform(2, 5)

        elif st == "goto_window":
            tx, ty = self.target
            self.facing = -1 if tx < self.x else 1
            self.x, dxd = self._approach(self.x, tx, 4.5)
            self.walk_phase += 0.35
            lift = abs(math.sin(self.walk_phase))
            self._render("walk", 1.0, 1.0, 0.0, -4.0 * lift)
            if dxd:
                self.target = self.scratch_target
                self.state = "climb"

        elif st == "climb":
            tx, ty = self.target
            self.x, dxd = self._approach(self.x, tx, 4.0)
            self.y, dyd = self._approach(self.y, ty, 4.0)
            self.set_sprite("stand")
            if dxd and dyd:
                self.state = "scratch_window"
                self.state_until = now + 2.4
                self.set_sprite("scratch")
                self.say("царап-царап!")

        elif st == "scratch_window":
            self._render("scratch", 1.0, 1.0, math.sin(now * 22) * 1.5, 0.0)
            if random.random() < 0.03:
                self.say(random.choice(["царап!", "мяу!", "мур"]))
            if now > self.state_until:
                self.drop_poop()
                self.state = "idle"
                self.y = self.ground_y
                self.next_decision = now + random.uniform(3, 6)
                self.cooldown_window = now + random.uniform(15, 30)

        elif st == "sleep":
            br = math.sin(now * 1.4)
            self._render("sleep", 1.0 - 0.02 * br, 1.0 + 0.025 * br)
            if random.random() < 0.01:
                self.say("z z z")
            if now > self.state_until:
                self.state = "idle"
                self.next_decision = now + random.uniform(2, 4)

        elif st == "scratch":
            self._render("scratch", 1.0, 1.0, math.sin(now * 22) * 1.2, 0.0)
            if now > self.state_until:
                if random.random() < 0.5:
                    self.drop_poop()
                self.state = "idle"
                self.next_decision = now + random.uniform(2, 5)

        self._update_pupils(mx, my)
        self.apply_geometry()
        self._was_typing = typing

    def tick(self):
        # crash-safe loop: one bad frame must never freeze the cat
        try:
            self._step()
        except Exception:
            pass
        self.root.after(TICK, self.tick)

    def _face_toward(self, mx):
        # 40px deadzone so the cat doesn't flip left/right on tiny mouse jitter
        center = self.x + self.cx
        if mx < center - 40:
            self.facing = -1
        elif mx > center + 40:
            self.facing = 1

    def _decide(self):
        now = time.time()
        choices = ["walk", "walk", "stretch", "sleep", "scratch"]
        if now > self.cooldown_window and (not WINDOWS or list_windows(self.title)):
            choices += ["window", "window"]
        pick = random.choice(choices)
        if pick == "walk":
            self.start_walk()
        elif pick == "stretch":
            self.start_stretch()
        elif pick == "sleep":
            self.start_sleep()
        elif pick == "scratch":
            self.start_scratch_air()
        elif pick == "window":
            self.start_window_hunt()

    def apply_geometry(self):
        self.x = max(-20, min(self.sw - self.winw + 20, int(self.x)))
        self.y = max(-10, min(self.sh - self.winh + 10, int(self.y)))
        self.root.geometry("%dx%d+%d+%d" % (self.winw, self.winh, self.x, self.y))

    # ------------------------------------------------------------------
    def _render_drag(self):
        # vertical mochi stretch based on how fast it's pulled
        vy = 0.0
        if self.press_xy is not None:
            vy = abs(self.y - getattr(self, "_last_drag_y", self.y))
        self._last_drag_y = self.y
        stretch = min(0.28, vy / 60.0)
        self._render("stretch", 1.0 - 0.6 * stretch, 1.0 + stretch)

    def on_press(self, e):
        self.drag = True
        self.press_xy = (e.x_root, e.y_root)
        self._last_drag_y = self.y
        self.drag_dx = e.x_root - self.x
        self.drag_dy = e.y_root - self.y
        self._render("stretch", 1.0, 1.0)

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
        self.y = self.ground_y
        self.state = "idle"
        self.land_t = time.time()    # trigger landing spring
        self.next_decision = time.time() + random.uniform(1, 3)
        if moved < 4:
            self.say(random.choice(["мяу~", "мур", "❤", "ня"]))

    def on_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _on_key(self, key):
        # runs on the pynput listener thread; a single float store is GIL-safe
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
        print("[cat] typing/mouse reaction: ON")
    else:
        print("[cat] pynput NOT installed -> typing reaction OFF."
              "  Install with:  pip install pynput")
    DesktopCat().run()
