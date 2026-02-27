import os
import json
import base64
import hashlib
import hmac
import random
import tkinter as tk
from tkinter import ttk, messagebox

# ----------------------------
# Simple "encryption" for saves (KEEP)
# ----------------------------
SAVE_DIR = os.path.join(os.path.expanduser("~"), ".time_terminal_game")
SAVE_PATH = os.path.join(SAVE_DIR, "save.dat")


def _pbkdf2_key(password: str, salt: bytes, rounds: int = 150_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds, dklen=32)


def _keystream(key: bytes, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        msg = counter.to_bytes(8, "big")
        out.extend(hashlib.sha256(key + msg).digest())
        counter += 1
    return bytes(out[:nbytes])


def encrypt_bytes(plaintext: bytes, password: str) -> bytes:
    salt = os.urandom(16)
    key = _pbkdf2_key(password, salt)
    ks = _keystream(key, len(plaintext))
    ct = bytes([p ^ k for p, k in zip(plaintext, ks)])
    mac = hmac.new(key, salt + ct, hashlib.sha256).digest()
    blob = salt + mac + ct
    return base64.urlsafe_b64encode(blob)


def decrypt_bytes(ciphertext_b64: bytes, password: str) -> bytes:
    blob = base64.urlsafe_b64decode(ciphertext_b64)
    if len(blob) < 16 + 32:
        raise ValueError("Corrupt save")
    salt = blob[:16]
    mac = blob[16:48]
    ct = blob[48:]
    key = _pbkdf2_key(password, salt)
    mac2 = hmac.new(key, salt + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, mac2):
        raise ValueError("Wrong password or tampered save")
    ks = _keystream(key, len(ct))
    pt = bytes([c ^ k for c, k in zip(ct, ks)])
    return pt


# ----------------------------
# Optional TTS (safe)
# ----------------------------
try:
    import pyttsx3
except Exception:
    pyttsx3 = None


# ----------------------------
# Node + Game framework
# ----------------------------

class GameBase:
    game_id = "base"
    title = "Base Game"
    description = ""

    def __init__(self, app):
        self.app = app

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()
        ttk.Label(parent, text="No game UI implemented.", wraplength=360).pack(padx=12, pady=12, anchor="nw")

    def start(self):
        self.app.print_line(f"[GAME] {self.title} started.")


class NodeBase:
    node_id = "NODE"
    title = "Node"
    intro = "..."
    godskip_code = "CODE"
    games = []  # list of GameBase classes

    def __init__(self, app):
        self.app = app

    def on_enter(self):
        self.app.print_line(f"\n=== {self.node_id}: {self.title} ===")
        self.app.print_line(self.intro)
        self.app.narrate(self.intro)

    def available_games(self):
        return self.games


# ----------------------------
# Node 1: Colored objects puzzle (clock/minutes = palette size)
# ----------------------------

class ColorShapesGame(GameBase):
    game_id = "colors"
    title = "Chromatic Drift"
    description = "Clock-coded palette; triangles never repeat; anchors stay true."

    SAFE_MINUTES = [6, 7, 8, 9, 10, 11, 12]  # minutes == number of colors (playable range)

    def __init__(self, app):
        super().__init__(app)
        self.canvas = None
        self.running = False
        self.shapes = []
        self.tick = 0

        # minutes/palette size is a node state value
        self.minutes = None
        self.palette = []
        self.tri_color_queue = []

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Chromatic Drift (Node 1)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")

        poem = (
            "Roses are red—violets refuse to agree,\n"
            "Jack steps through static into a lab that shouldn’t be.\n"
            "A clock without a second hand watches him breathe;\n"
            "The MINUTES decide the spectrum you’ll see.\n\n"
            "Triangles drift—each hue used once before it returns.\n"
            "Rectangles barter colors, but two anchors never learn:\n"
            "One burns like dawn, one glows like embered night.\n"
            "Count by time, not by sight.\n\n"
            "Command: solve colors <MINUTES>"
        )
        ttk.Label(parent, text=poem, wraplength=380, justify="left").pack(padx=12, pady=(0, 10), anchor="nw")

        self.canvas = tk.Canvas(parent, width=400, height=280, bg="#0a0f1a",
                                highlightthickness=1, highlightbackground="#00ff88")
        self.canvas.pack(padx=12, pady=(0, 10), anchor="nw")

        controls = ttk.Frame(parent)
        controls.pack(padx=12, pady=(0, 12), fill="x")

        ttk.Button(controls, text="Start", command=self._start_anim).pack(side="left")
        ttk.Button(controls, text="Stop", command=self._stop_anim).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Hint", command=self._hint).pack(side="left", padx=(8, 0))

        ttk.Label(parent, text="(The clock minutes = number of colors in the palette.)", foreground="#666").pack(padx=12, anchor="nw")

    def _hint(self):
        self.app.print_line("[HINT] Read the clock. The MINUTES are the palette size. Triangles don’t repeat until they exhaust it.")
        self.app.print_line("[HINT] Two rectangles are anchors: red & orange never change.")

    def _start_anim(self):
        if self.running:
            return
        self.running = True
        self._init_scene()
        self._tick()

    def _stop_anim(self):
        self.running = False

    def _init_scene(self):
        self.canvas.delete("all")
        self.shapes = []
        self.tick = 0

        # Generate clock time: hour is flavor, minutes is puzzle
        hour = random.choice([1, 3, 7, 9, 11, 12])
        minutes = random.choice(self.SAFE_MINUTES)
        self.minutes = minutes

        # store the answer in state so solve can validate
        self.app.state["node1_minutes_answer"] = minutes

        # Build palette of size == minutes (within safe list)
        # Always include anchors (red/orange) but anchors are not part of "palette size" logic;
        # palette is for non-anchors + triangles.
        base_colors = [
            "#ffd000", "#33dd66", "#33aaff", "#9b5cff", "#ff66cc", "#00ffd5",
            "#c0ff00", "#ff4444", "#ffb000", "#66a3ff", "#b88cff", "#44ffaa"
        ]
        random.shuffle(base_colors)
        self.palette = base_colors[:minutes]

        # triangle queue enforces "no repeat until palette exhausted"
        self.tri_color_queue = self.palette.copy()
        random.shuffle(self.tri_color_queue)

        # Draw a simple analog clock top-left
        self._draw_clock(cx=70, cy=70, r=48, hour=hour, minute=minutes)

        # Anchors: red/orange rectangles (no labels)
        r1 = self.canvas.create_rectangle(160, 30, 260, 90, fill="#ff3355", outline="")
        r2 = self.canvas.create_rectangle(280, 30, 380, 90, fill="#ff7a00", outline="")

        # Swappable rectangles (from palette)
        c3 = random.choice(self.palette)
        c4 = random.choice(self.palette)
        r3 = self.canvas.create_rectangle(160, 110, 260, 170, fill=c3, outline="")
        r4 = self.canvas.create_rectangle(280, 110, 380, 170, fill=c4, outline="")

        # Triangles (colors from queue)
        t1 = self.canvas.create_polygon(170, 210, 210, 260, 130, 260, fill=self._next_tri_color(), outline="")
        t2 = self.canvas.create_polygon(270, 210, 310, 260, 230, 260, fill=self._next_tri_color(), outline="")
        t3 = self.canvas.create_polygon(370, 200, 390, 245, 330, 245, fill=self._next_tri_color(), outline="")

        self.shapes = [
            ("anchor_rect", r1),
            ("anchor_rect", r2),
            ("rect", r3),
            ("rect", r4),
            ("tri", t1),
            ("tri", t2),
            ("tri", t3),
        ]

        self.app.print_line(f"[NODE1] The clock flickers: {hour:02d}:{minutes:02d}.")
        self.app.print_line("[NODE1] The terminal whispers: 'Minutes decide the spectrum.'")

    def _draw_clock(self, cx, cy, r, hour, minute):
        # clock face
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#00ff88", width=2)
        # tick marks (12)
        for i in range(12):
            angle = (i / 12) * 6.28318530718
            x1 = cx + (r - 4) * (0.0 + __import__("math").sin(angle))
            y1 = cy - (r - 4) * (0.0 + __import__("math").cos(angle))
            x2 = cx + (r - 14) * (0.0 + __import__("math").sin(angle))
            y2 = cy - (r - 14) * (0.0 + __import__("math").cos(angle))
            self.canvas.create_line(x1, y1, x2, y2, fill="#00ff88")

        # hands
        import math
        # minute hand
        m_angle = (minute / 60) * 2 * math.pi
        mx = cx + (r - 16) * math.sin(m_angle)
        my = cy - (r - 16) * math.cos(m_angle)
        self.canvas.create_line(cx, cy, mx, my, fill="#cfe", width=2)

        # hour hand (approx)
        h = hour % 12
        h_angle = ((h + minute / 60) / 12) * 2 * math.pi
        hx = cx + (r - 26) * math.sin(h_angle)
        hy = cy - (r - 26) * math.cos(h_angle)
        self.canvas.create_line(cx, cy, hx, hy, fill="#cfe", width=3)

        # digital readout small
        self.canvas.create_text(cx, cy + r + 14, text=f"{hour:02d}:{minute:02d}", fill="#00ff88", font=("Segoe UI", 10, "bold"))

    def _next_tri_color(self):
        if not self.tri_color_queue:
            self.tri_color_queue = self.palette.copy()
            random.shuffle(self.tri_color_queue)
        return self.tri_color_queue.pop()

    def _tick(self):
        if not self.running:
            return

        self.tick += 1

        # Triangles: update using non-repeating queue
        if self.tick % 2 == 0:
            for kind, sid in self.shapes:
                if kind == "tri":
                    self.canvas.itemconfig(sid, fill=self._next_tri_color())

        # Non-anchor rectangles swap occasionally and may change to palette colors
        if self.tick % 12 == 0:
            rects = [sid for kind, sid in self.shapes if kind == "rect"]
            if len(rects) == 2:
                if random.random() < 0.5:
                    # swap fills
                    c1 = self.canvas.itemcget(rects[0], "fill")
                    c2 = self.canvas.itemcget(rects[1], "fill")
                    self.canvas.itemconfig(rects[0], fill=c2)
                    self.canvas.itemconfig(rects[1], fill=c1)
                else:
                    # re-roll from palette
                    self.canvas.itemconfig(rects[0], fill=random.choice(self.palette))
                    self.canvas.itemconfig(rects[1], fill=random.choice(self.palette))

        # Move shapes slightly
        for kind, sid in self.shapes:
            dx = random.choice([-2, -1, 0, 1, 2])
            dy = random.choice([-2, -1, 0, 1, 2])
            self.canvas.move(sid, dx, dy)

        self.app.root.after(120, self._tick)


class Node1_ColorLab(NodeBase):
    node_id = "N1"
    title = "Color Lab (Present)"
    intro = (
        "Jack opens his eyes to a lab that smells like ozone and old coffee.\n"
        "The monitor doesn’t boot— it *breathes*.\n"
        "A clock hangs above the console with no second hand, as if time itself is shy.\n"
        "The screen writes: “MINUTES decide the spectrum. Count what never lies.”"
    )
    godskip_code = "GOD-N1-4412"
    games = [ColorShapesGame]


# ----------------------------
# Node 2: Actual chessboard UI (canvas) + scenario move answer
# ----------------------------

UNICODE_PIECES = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}


class ChessScenarioGame(GameBase):
    game_id = "chess"
    title = "Forked Timeline"
    description = "A real board. Find the move that forks."

    def __init__(self, app):
        super().__init__(app)
        self.canvas = None

        # A simple scenario: White to move.
        # We'll design a position where Ne7+ is the intended fork (example).
        # Board is encoded as dict: squares like "e4": "N"
        self.position = {
            "f5": "N",   # white knight
            "e8": "k",   # black king
            "d6": "q",   # black queen (fork target)
            "c7": "r",   # black rook (fork target)
            "g8": "r",
            "a1": "K"
        }
        self.expected = "Ne7"  # player types "solve chess Ne7"

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Forked Timeline (Chess)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")

        story = (
            "Jack arrives in 1930. Switchboards click like chess clocks.\n"
            "A diagram flashes: a single knight move splits the future.\n\n"
            "Goal: find the fork move.\n"
            "Terminal: solve chess <MOVE>\n"
            "Example: solve chess Ne7\n"
        )
        ttk.Label(parent, text=story, wraplength=380, justify="left").pack(padx=12, pady=(0, 8), anchor="nw")

        self.canvas = tk.Canvas(parent, width=400, height=400, bg="#0a0f1a",
                                highlightthickness=1, highlightbackground="#00ff88")
        self.canvas.pack(padx=12, pady=(0, 10), anchor="nw")

        self._draw_board()
        self.app.print_line("[NODE2] White to move. Find the knight fork.")

    def _draw_board(self):
        self.canvas.delete("all")
        tile = 48
        ox, oy = 8, 8
        light = "#1a2438"
        dark = "#0f182b"

        # Draw squares
        for r in range(8):
            for c in range(8):
                x1 = ox + c * tile
                y1 = oy + r * tile
                x2 = x1 + tile
                y2 = y1 + tile
                color = light if (r + c) % 2 == 0 else dark
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="#0a0f1a")

        # Coordinates helper (small)
        for i, file_ in enumerate("abcdefgh"):
            self.canvas.create_text(ox + i * tile + 24, oy + 8 * tile + 10, text=file_, fill="#00ff88", font=("Segoe UI", 9))
        for i, rank in enumerate("87654321"):
            self.canvas.create_text(ox - 10, oy + i * tile + 24, text=rank, fill="#00ff88", font=("Segoe UI", 9))

        # Draw pieces
        for sq, p in self.position.items():
            file_ = sq[0]
            rank = int(sq[1])
            c = ord(file_) - ord("a")
            r = 8 - rank
            x = ox + c * tile + 24
            y = oy + r * tile + 24
            glyph = UNICODE_PIECES.get(p, p)
            self.canvas.create_text(x, y, text=glyph, fill="#cfe", font=("Segoe UI Symbol", 22, "bold"))

        # Caption
        self.canvas.create_text(210, 392, text="White to move", fill="#00ff88", font=("Segoe UI", 10, "bold"))


class Node2_Chess(NodeBase):
    node_id = "N2"
    title = "Chess Switchyard (1930)"
    intro = (
        "Jack lands inside a station that hums with relays and radio chatter.\n"
        "A paper chessboard is pinned beside the console.\n"
        "Someone wrote: “Fork the king, steal the queen, and time will listen.”"
    )
    godskip_code = "GOD-N2-9901"
    games = [ChessScenarioGame]


# ----------------------------
# Node 3/4/5/6: keep your originals for now (still usable)
# (You can ask me next to fully wire Node3 answers + real iterated dilemma.)
# ----------------------------

class CodeScrollGame(GameBase):
    game_id = "codes"
    title = "Where Will Jack Go?"
    description = "Read tricky code; predict the destination."

    CODE_SNIPPETS = [
        ("Snippet A", """\
jack = {"x": 0, "t": "N1"}
for i in range(1, 6):
    if i % 2 == 0:
        jack["x"] += i
    else:
        jack["x"] -= (i+1)
    if jack["x"] % 3 == 0:
        jack["t"] = "N2"
    elif jack["x"] % 5 == 0:
        jack["t"] = "N3"
    else:
        jack["t"] = "N4"
print(jack["t"], jack["x"])
"""),
        ("Snippet B", """\
path = ["N1","N2","N3","N4","N5","N6"]
p = 0
for step in range(9):
    p = (p + step) % len(path)
    if step % 4 == 0:
        p = (p * 2) % len(path)
print(path[p])
"""),
        ("Snippet C", """\
def jump(s):
    return (s*7 + 3) % 6
s = 1
for _ in range(4):
    s = jump(s)
print("N" + str(s+1))
"""),
    ]

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Where Will Jack Go? (Code Scroll)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        ttk.Label(parent, text="Commands:\n  showcode <A|B|C>\n  (Next step: solve code ... fully validated)", wraplength=380, justify="left").pack(padx=12, pady=(0, 8), anchor="nw")

        scroller = tk.Text(parent, height=16, width=48, bg="#0a0f1a", fg="#00ff88", insertbackground="#00ff88", wrap="none")
        scroller.pack(padx=12, pady=(0, 10), anchor="nw", fill="both", expand=True)
        scroller.insert("end", "Use terminal command: showcode A  (or B/C)\n")
        scroller.config(state="disabled")


class Node3_Code(NodeBase):
    node_id = "N3"
    title = "Code Observatory (2030)"
    intro = (
        "The glass walls reflect Jack like debug output.\n"
        "Code is etched where advertisements should be.\n"
        "A line repeats: “If you can predict the branch, you can escape the loop.”"
    )
    godskip_code = "GOD-N3-1209"
    games = [CodeScrollGame]


class RegexChoiceGame(GameBase):
    game_id = "regex"
    title = "Pattern Storm"
    description = "Pick the regex that matches the changing text."

    def __init__(self, app):
        super().__init__(app)
        self.lbl = None
        self.opts = []
        self.correct = None
        self.running = False
        self._choice_map = {}

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Pattern Storm (Regex)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        ttk.Label(parent, text="Text changes every ~3 seconds.\nPick the correct regex.\nTerminal: solve regex <1|2|3|4>",
                  wraplength=380, justify="left").pack(padx=12, pady=(0, 8), anchor="nw")

        self.lbl = ttk.Label(parent, text="(generating...)", wraplength=380, justify="left")
        self.lbl.pack(padx=12, pady=(0, 10), anchor="nw")

        box = ttk.Frame(parent)
        box.pack(padx=12, pady=(0, 12), fill="x")

        self.opts = []
        for i in range(4):
            l = ttk.Label(box, text=f"{i+1}) ...", wraplength=380, justify="left")
            l.pack(anchor="nw", pady=2)
            self.opts.append(l)

        self.running = True
        self._tick()

    def _tick(self):
        if not self.running:
            return

        prefix = random.choice(["TIME", "NODE", "JACK", "ECHO"])
        digits = random.randint(10, 9999)
        suffix = random.choice(["A", "B", "C"])
        s = f"{prefix}-{digits}{suffix}"

        correct_patterns = [
            r"^(TIME|NODE|JACK|ECHO)-\d+[ABC]$",
            r"^[A-Z]{4}-\d{2,4}[ABC]$",
            r"^(TIME|NODE)-\d+[A-C]$",
            r"^[A-Z]+-\d+[A-Z]$",
        ]
        self.correct = random.choice(correct_patterns)
        choices = [self.correct]

        distractors = [
            r"^(TIME|NODE|JACK|ECHO)\d+[ABC]$",
            r"^[A-Z]{4}-\d{5}[ABC]$",
            r"^(TIME|NODE|JACK|ECHO)-[A-Z]+[ABC]$",
            r"^\d+-[A-Z]{4}[ABC]$",
            r"^[A-Z]{4}-\d{2,4}$",
        ]
        random.shuffle(distractors)
        for d in distractors[:3]:
            choices.append(d)
        random.shuffle(choices)

        self.lbl.config(text=f"TEXT:  {s}")
        for i, pat in enumerate(choices):
            self.opts[i].config(text=f"{i+1}) {pat}")

        self._choice_map = {str(i+1): choices[i] for i in range(4)}
        self.app.state["regex_correct_pattern"] = self.correct  # store for validation if you want later

        self.app.root.after(3000, self._tick)

    def stop(self):
        self.running = False


class Node4_Regex(NodeBase):
    node_id = "N4"
    title = "Regex Drift (Timeless)"
    intro = (
        "Jack watches text rewrite itself like a memory trying to stabilize.\n"
        "The console says: “Patterns are gates. Choose wrong and the story continues—without reward.”"
    )
    godskip_code = "GOD-N4-7770"
    games = [RegexChoiceGame]


class GameTheoryGame(GameBase):
    game_id = "dilemma"
    title = "Iterated Dilemma"
    description = "Prototype rules shown; full 6-round interactive mode next."

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Iterated Dilemma (Game Theory)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        txt = (
            "You will play 6 rounds.\n"
            "Actions: C (cooperate) or D (defect)\n\n"
            "Payoffs (you, opponent):\n"
            "  C/C = (3,3)\n"
            "  D/C = (5,0)\n"
            "  C/D = (0,5)\n"
            "  D/D = (1,1)\n\n"
            "Terminal:\n"
            "  train dilemma\n"
            "  (Next step: real interactive 6 rounds)\n"
        )
        ttk.Label(parent, text=txt, wraplength=380, justify="left").pack(padx=12, pady=(0, 12), anchor="nw")


class Node5_GameTheory(NodeBase):
    node_id = "N5"
    title = "Strategic Loop (3000)"
    intro = (
        "In a city of holograms, Jack meets a machine that negotiates with futures.\n"
        "It offers him a deal: “Win six exchanges. Or remain a line of output forever.”"
    )
    godskip_code = "GOD-N5-6606"
    games = [GameTheoryGame]


class FinalRiddleGame(GameBase):
    game_id = "final"
    title = "Axis Lock"
    description = "Final password gate (prototype)."

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Axis Lock (Final)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        txt = (
            "Jack stands before the Axis.\n"
            "The last lock wants a phrase that only a traveler would learn.\n\n"
            "Terminal:\n"
            "  unlock <PASSWORD>\n"
            "  godskip <CODE>\n"
        )
        ttk.Label(parent, text=txt, wraplength=380, justify="left").pack(padx=12, pady=(0, 12), anchor="nw")


class Node6_Final(NodeBase):
    node_id = "N6"
    title = "The Axis (Final)"
    intro = (
        "The final door is not a door.\n"
        "It is a choice written in a language time understands.\n"
        "Jack hears his own name echo from six different years."
    )
    godskip_code = "GOD-N6-0420"
    games = [FinalRiddleGame]


# ----------------------------
# App
# ----------------------------

class TimeTerminalApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Jack’s Time Terminal")
        self.root.geometry("1150x700")
        self.root.minsize(920, 560)

        self.password = None
        self.tts_enabled = True
        self.tts_engine = None
        if pyttsx3 is not None:
            try:
                self.tts_engine = pyttsx3.init()
            except Exception:
                self.tts_engine = None

        self.state = {
            "player_name": None,
            "score": 0,
            "current_node": "N1",
            "unlocked_nodes": ["N1"],
            "solved": {},

            # extra state used by puzzles (encrypted too)
            "node1_minutes_answer": None,
            "regex_correct_pattern": None,
        }

        self.node_classes = {
            "N1": Node1_ColorLab,
            "N2": Node2_Chess,
            "N3": Node3_Code,
            "N4": Node4_Regex,
            "N5": Node5_GameTheory,
            "N6": Node6_Final,
        }

        self.node_routes = {
            "N1": ["N2", "N3"],
            "N2": ["N3", "N4"],
            "N3": ["N4", "N5"],
            "N4": ["N5"],
            "N5": ["N6"],
            "N6": [],
        }

        self.current_node_obj = None
        self.current_game_obj = None

        self._build_ui()

        # Save on close (encrypted)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._boot()

    # ---------- UI ----------
    def _build_ui(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer)
        left.pack(side="left", fill="both", expand=True)

        right = ttk.Frame(outer, width=460)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        self.output = tk.Text(left, bg="#0a0f1a", fg="#00ff88", insertbackground="#00ff88", wrap="word")
        self.output.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.output.config(state="disabled")

        inp_row = ttk.Frame(left)
        inp_row.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(inp_row, text="> ").pack(side="left")
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(inp_row, textvariable=self.input_var)
        self.input_entry.pack(side="left", fill="x", expand=True)
        self.input_entry.bind("<Return>", lambda e: self._on_enter())

        ttk.Button(inp_row, text="Send", command=self._on_enter).pack(side="left", padx=(8, 0))

        self.game_panel = ttk.Frame(right)
        self.game_panel.pack(fill="both", expand=True, padx=10, pady=10)

        self.status = ttk.Label(self.root, text="Ready", anchor="w")
        self.status.pack(fill="x")

    # ---------- Boot / Save ----------
    def _boot(self):
        self.print_line("Welcome to Jack’s Time Terminal.")
        self.print_line("He’s stuck inside a loop where years behave like folders.")
        self.print_line("Some doors open with logic. Some open with time.\n")
        self._prompt_password()

    def _prompt_password(self):
        win = tk.Toplevel(self.root)
        win.title("Enter Game Password")
        win.geometry("460x200")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Enter a password to start.\n(Used to encrypt your save file.)",
                  justify="left").pack(padx=14, pady=(14, 8), anchor="w")

        pw_var = tk.StringVar()
        ent = ttk.Entry(win, textvariable=pw_var, show="*")
        ent.pack(padx=14, fill="x")
        ent.focus_set()

        def submit():
            pw = pw_var.get().strip()
            if len(pw) < 4:
                messagebox.showerror("Password", "Use at least 4 characters.")
                return
            self.password = pw
            self._try_load_save()

            if not self.state.get("player_name"):
                self._prompt_name()
            else:
                self.print_line(f"Welcome back, {self.state['player_name']}.")
                self._enter_node(self.state["current_node"])
            win.destroy()

        ttk.Button(win, text="Start", command=submit).pack(padx=14, pady=14, anchor="e")
        win.bind("<Return>", lambda e: submit())

    def _prompt_name(self):
        win = tk.Toplevel(self.root)
        win.title("Traveler Name")
        win.geometry("460x200")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Hey traveler… what is your name?\n(We’ll remember it — encrypted.)",
                  justify="left").pack(padx=14, pady=(14, 8), anchor="w")
        name_var = tk.StringVar()
        ent = ttk.Entry(win, textvariable=name_var)
        ent.pack(padx=14, fill="x")
        ent.focus_set()

        def submit():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Name", "Enter a name.")
                return
            self.state["player_name"] = name
            self._save()
            self.print_line(f"Welcome, {name}.")
            self._enter_node(self.state["current_node"])
            win.destroy()

        ttk.Button(win, text="Continue", command=submit).pack(padx=14, pady=14, anchor="e")
        win.bind("<Return>", lambda e: submit())

    def _try_load_save(self):
        try:
            if not os.path.exists(SAVE_PATH):
                return
            with open(SAVE_PATH, "rb") as f:
                blob = f.read()
            pt = decrypt_bytes(blob, self.password)
            data = json.loads(pt.decode("utf-8"))
            if "current_node" in data and "unlocked_nodes" in data:
                self.state.update(data)
                self.print_line("[SAVE] Loaded (encrypted).")
        except Exception:
            self.print_line("[SAVE] Could not load (wrong password or tampered). Starting fresh.")

    def _save(self):
        if not self.password:
            return
        os.makedirs(SAVE_DIR, exist_ok=True)
        data = json.dumps(self.state, ensure_ascii=False).encode("utf-8")
        blob = encrypt_bytes(data, self.password)
        with open(SAVE_PATH, "wb") as f:
            f.write(blob)

    def _on_close(self):
        try:
            self._save()
        except Exception:
            pass
        self.root.destroy()

    # ---------- Terminal IO ----------
    def print_line(self, s: str):
        self.output.config(state="normal")
        self.output.insert("end", s + "\n")
        self.output.see("end")
        self.output.config(state="disabled")

    def narrate(self, text: str):
        if not self.tts_enabled or self.tts_engine is None:
            return
        try:
            self.tts_engine.stop()
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
        except Exception:
            pass

    def _on_enter(self):
        cmd = self.input_var.get().strip()
        if not cmd:
            return
        self.input_var.set("")
        self.print_line(f"> {cmd}")
        self._handle_command(cmd)

    # ---------- Node / Game ----------
    def _enter_node(self, node_id: str):
        if node_id not in self.node_classes:
            self.print_line(f"[ERR] Unknown node {node_id}")
            return

        self.state["current_node"] = node_id
        self.current_node_obj = self.node_classes[node_id](self)
        self.current_node_obj.on_enter()

        self._clear_game_panel()

        # Auto-mount first node game
        games = self.current_node_obj.available_games()
        if games:
            self._mount_game(games[0].game_id)

        self.status.config(text=f"{self.state.get('player_name','?')} | Node {node_id} | Score {self.state['score']}")

    def _clear_game_panel(self):
        for w in self.game_panel.winfo_children():
            w.destroy()
        ttk.Label(self.game_panel, text="Right Panel: Node games appear here.", foreground="#666").pack(padx=12, pady=12, anchor="nw")

    def _mount_game(self, game_id: str):
        node = self.current_node_obj
        if not node:
            self.print_line("[ERR] No node active.")
            return

        game_cls = None
        for g in node.available_games():
            if g.game_id.lower() == game_id.lower():
                game_cls = g
                break

        if not game_cls:
            self.print_line(f"[ERR] Game '{game_id}' not available in this node.")
            self.print_line("Try: games")
            return

        self.current_game_obj = game_cls(self)
        self.current_game_obj.mount(self.game_panel)
        self.current_game_obj.start()

    # ---------- Commands ----------
    def _handle_command(self, raw: str):
        try:
            parts = raw.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("help", "?"):
                self._cmd_help()
                return

            if cmd == "narrate":
                # narrate on/off
                if not args:
                    self.print_line(f"narrate is {'ON' if self.tts_enabled else 'OFF'}")
                    return
                v = args[0].lower()
                if v in ("on", "1", "true"):
                    self.tts_enabled = True
                    self.print_line("Narration: ON")
                elif v in ("off", "0", "false"):
                    self.tts_enabled = False
                    self.print_line("Narration: OFF")
                else:
                    self.print_line("Usage: narrate on|off")
                return

            if cmd == "node":
                n = self.current_node_obj
                self.print_line(f"NODE {n.node_id}: {n.title}")
                return

            if cmd == "nodes":
                self.print_line("Nodes: " + ", ".join(sorted(self.node_classes.keys())))
                self.print_line(f"Unlocked: {', '.join(self.state['unlocked_nodes'])}")
                return

            if cmd in ("routes", "chronoroutes", "chrono"):
                self._cmd_routes()
                return

            if cmd == "travel":
                if not args:
                    self.print_line("Usage: travel <N1..N6>")
                    return
                self._cmd_travel(args[0].upper())
                return

            if cmd == "games":
                self._cmd_games()
                return

            if cmd == "play":
                if not args:
                    self.print_line("Usage: play <game_id>")
                    return
                self._mount_game(args[0])
                return

            if cmd == "solve":
                self._cmd_solve(args)
                return

            if cmd == "showcode":
                self._cmd_showcode(args)
                return

            if cmd == "train":
                self._cmd_train(args)
                return

            if cmd == "unlock":
                self._cmd_unlock(args)
                return

            if cmd == "godskip":
                self._cmd_godskip(args)
                return

            self.print_line("Unknown command. Type 'help'.")
        finally:
            # Always persist (encrypted)
            self._save()

    def _cmd_help(self):
        self.print_line("Commands:")
        self.print_line("  help                     - show commands")
        self.print_line("  narrate on|off            - voice narration toggle")
        self.print_line("  node                     - show current node")
        self.print_line("  nodes                    - list nodes + unlocked")
        self.print_line("  routes                   - show Chrono Routes")
        self.print_line("  travel <N1..N6>           - move (if unlocked)")
        self.print_line("  games                    - list node games")
        self.print_line("  play <game_id>           - open game UI on right")
        self.print_line("  solve ...                - solve puzzles")
        self.print_line("  showcode <A|B|C>          - show code snippet (Node3)")
        self.print_line("  train dilemma            - training (Node5)")
        self.print_line("  unlock <password>        - final lock (Node6)")
        self.print_line("  godskip <code>           - developer skip per node")

    def _cmd_routes(self):
        cur = self.state["current_node"]
        nxt = self.node_routes.get(cur, [])
        self.print_line("=== CHRONO ROUTES ===")
        for n in nxt:
            open_ = "YES" if n in self.state["unlocked_nodes"] else "NO"
            self.print_line(f"  -> {n}   OPEN: {open_}")
        self.print_line("Use: travel N2")

    def _cmd_travel(self, node_id: str):
        cur = self.state["current_node"]
        if node_id not in self.node_classes:
            self.print_line("[ERR] Unknown node.")
            return
        if node_id not in self.node_routes.get(cur, []) and node_id != cur:
            self.print_line("[LOCKED] No direct route from here. Try: routes")
            return
        if node_id not in self.state["unlocked_nodes"]:
            self.print_line("[LOCKED] Node not unlocked yet. Solve puzzles in earlier nodes.")
            return
        self._enter_node(node_id)

    def _cmd_games(self):
        node = self.current_node_obj
        gs = node.available_games()
        self.print_line(f"Games in {node.node_id}:")
        for g in gs:
            self.print_line(f"  - {g.game_id}: {g.title} ({g.description})")

    def _unlock_node(self, node_id: str, reason: str):
        if node_id not in self.state["unlocked_nodes"]:
            self.state["unlocked_nodes"].append(node_id)
        self.print_line(f"[UNLOCK] {node_id} unlocked ({reason}).")

    def _cmd_solve(self, args):
        if not args:
            self.print_line("Usage examples:")
            self.print_line("  solve colors <MINUTES>")
            self.print_line("  solve chess Ne7")
            self.print_line("  solve regex 2")
            return

        kind = args[0].lower()
        cur = self.state["current_node"]

        # Node 1: answer is the minutes shown by the clock
        if kind == "colors" and cur == "N1":
            if len(args) < 2:
                self.print_line("Usage: solve colors <MINUTES>")
                return
            ans = args[1].strip()
            correct = str(self.state.get("node1_minutes_answer") or "")
            if ans == correct:
                self.state["score"] += 12
                self.state["solved"]["colors"] = True
                self.print_line("[OK] Time was the key. The spectrum stabilizes.")
                self._unlock_node("N2", "Chromatic Drift solved")
            else:
                self.print_line("[NO] Not the minutes. Look at the clock display.")
            return

        # Node 2 chess: solve chess Ne7
        if kind == "chess" and cur == "N2":
            if len(args) < 2:
                self.print_line("Usage: solve chess <MOVE>   (example: Ne7)")
                return
            move = args[1].strip()
            # Expected move comes from the mounted chess game (if present), else default
            expected = "Ne7"
            if isinstance(self.current_game_obj, ChessScenarioGame):
                expected = self.current_game_obj.expected
            if move.lower() == expected.lower():
                self.state["score"] += 15
                self.state["solved"]["chess"] = True
                self.print_line("[OK] The fork lands. Two futures collapse into one.")
                self._unlock_node("N3", "Forked Timeline solved")
            else:
                self.print_line("[NO] Not that move. Think: a knight attacks in L-shapes, and forks king + queen/rook.")
            return

        # Node 4 regex: keep your “unlock even if wrong” behavior
        if kind == "regex" and cur == "N4":
            if len(args) < 2:
                self.print_line("Usage: solve regex <1|2|3|4>")
                return
            pick = args[1].strip()
            if pick == "2":
                self.state["score"] += 5
                self.print_line("[OK] Correct regex. Score awarded.")
            else:
                self.print_line("[OK] Gate opens, but the loop remembers the mistake. No score.")
            self._unlock_node("N5", "Pattern Storm attempt")
            return

        self.print_line("[ERR] That solve command doesn’t apply here.")

    def _cmd_showcode(self, args):
        if self.state["current_node"] != "N3":
            self.print_line("[ERR] showcode only works in Node3.")
            return
        if not args:
            self.print_line("Usage: showcode <A|B|C>")
            return
        key = args[0].strip().upper()
        for title, code in CodeScrollGame.CODE_SNIPPETS:
            if title.endswith(key):
                self.print_line(f"--- {title} ---")
                self.print_line(code)
                return
        self.print_line("[ERR] Choose A, B, or C.")

    def _cmd_train(self, args):
        if not args:
            self.print_line("Usage: train dilemma")
            return
        if args[0].lower() == "dilemma":
            self.print_line("[TRAIN] Opponent strategy (prototype): starts with C, then mirrors your last move.")
            self.print_line("Tip: If you defect forever you get short-term points but lose trust-based advantages later.")
            return
        self.print_line("[ERR] Unknown training module.")

    def _cmd_unlock(self, args):
        if self.state["current_node"] != "N6":
            self.print_line("[ERR] unlock is for the final node.")
            return
        if not args:
            self.print_line("Usage: unlock <PASSWORD>")
            return
        pw = " ".join(args).strip()
        if pw.lower() == "jackisunstuck":
            self.state["score"] += 50
            self.print_line("[OK] The Axis opens. Jack steps out of the loop.")
            self.print_line("ENDING: Time exhales. The console finally goes quiet.")
        else:
            self.print_line("[NO] The Axis rejects it. The loop tightens.")

    def _cmd_godskip(self, args):
        if not args:
            self.print_line("Usage: godskip <CODE>")
            return
        code = args[0].strip()
        node = self.current_node_obj
        if code == node.godskip_code:
            for nxt in self.node_routes.get(node.node_id, []):
                self._unlock_node(nxt, "GodSkip")
            self.print_line("[GOD] Routes unlocked from this node.")
        else:
            self.print_line("[GOD] Wrong code.")


# ----------------------------
# Main
# ----------------------------

def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    TimeTerminalApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
