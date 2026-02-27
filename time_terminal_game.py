import os
import json
import time
import base64
import hashlib
import hmac
import random
import tkinter as tk
from tkinter import ttk, messagebox

# ----------------------------
# Simple "encryption" for saves
# ----------------------------
# This is not military-grade crypto, but it prevents casual tampering.
# It derives a key from the password and XORs with a SHA256-based keystream.
# If you want strong crypto later, swap this for cryptography.Fernet.

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
# Node + Game framework
# ----------------------------

class GameBase:
    game_id = "base"
    title = "Base Game"
    description = ""

    def __init__(self, app):
        self.app = app

    def mount(self, parent):
        """Create UI in right panel."""
        for w in parent.winfo_children():
            w.destroy()
        lbl = ttk.Label(parent, text="No game UI implemented.", wraplength=360)
        lbl.pack(padx=12, pady=12, anchor="nw")

    def start(self):
        """Called when game starts."""
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
# Node 1: Colored objects puzzle (right panel)
# ----------------------------

class ColorShapesGame(GameBase):
    game_id = "colors"
    title = "Chromatic Drift"
    description = "Observe moving shapes; infer rules from a poem + hints."

    def __init__(self, app):
        super().__init__(app)
        self.canvas = None
        self.running = False
        self.shapes = []
        self.colors = ["#ff3355", "#ff7a00", "#ffd000", "#33dd66", "#33aaff", "#9b5cff"]
        self.tick = 0

    def mount(self, parent):
        super().mount(parent)
        for w in parent.winfo_children():
            w.destroy()

        header = ttk.Label(parent, text="Chromatic Drift (Node 1)", font=("Segoe UI", 11, "bold"))
        header.pack(padx=12, pady=(12, 6), anchor="nw")

        poem = (
            "Roses are red, violets are… not quite the same,\n"
            "In Jack’s first jump, colors play a shifting game.\n"
            "Triangles drift—never twice the same hue,\n"
            "Rectangles may swap… but two anchors stay true.\n"
            "One burns like dawn, one glows like embered night;\n"
            "Count the whole spectrum—then speak it in light.\n\n"
            "Hint: watch the triangles. The rectangles lie."
        )
        ttk.Label(parent, text=poem, wraplength=360, justify="left").pack(padx=12, pady=(0, 10), anchor="nw")

        self.canvas = tk.Canvas(parent, width=380, height=240, bg="#0a0f1a", highlightthickness=1, highlightbackground="#00ff88")
        self.canvas.pack(padx=12, pady=(0, 10), anchor="nw")

        controls = ttk.Frame(parent)
        controls.pack(padx=12, pady=(0, 12), fill="x")

        ttk.Button(controls, text="Start", command=self._start_anim).pack(side="left")
        ttk.Button(controls, text="Stop", command=self._stop_anim).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Claim Hint", command=self._claim_hint).pack(side="left", padx=(8, 0))

        ttk.Label(parent, text="To solve: in terminal, type:  solve colors <NUMBER>", foreground="#666").pack(padx=12, anchor="nw")

    def _claim_hint(self):
        self.app.print_line("[HINT] Two rectangles are 'anchors' (they keep their colors). Triangles always change.")

    def _start_anim(self):
        if self.running:
            return
        self.running = True
        self._init_shapes()
        self._tick()

    def _stop_anim(self):
        self.running = False

    def _init_shapes(self):
        self.canvas.delete("all")
        self.shapes = []
        # Two anchor rectangles: red & orange never change
        r1 = self.canvas.create_rectangle(20, 30, 110, 90, fill="#ff3355", outline="")
        r2 = self.canvas.create_rectangle(130, 30, 220, 90, fill="#ff7a00", outline="")
        self.canvas.create_text(65, 20, text="RECT-A", fill="#cfe", font=("Segoe UI", 9, "bold"))
        self.canvas.create_text(175, 20, text="RECT-B", fill="#cfe", font=("Segoe UI", 9, "bold"))

        # Two swappable rectangles (can change)
        r3 = self.canvas.create_rectangle(240, 30, 330, 90, fill="#33aaff", outline="")
        r4 = self.canvas.create_rectangle(20, 110, 110, 170, fill="#33dd66", outline="")

        # Three triangles that always change
        t1 = self.canvas.create_polygon(150, 140, 190, 200, 110, 200, fill="#ffd000", outline="")
        t2 = self.canvas.create_polygon(260, 140, 300, 200, 220, 200, fill="#9b5cff", outline="")
        t3 = self.canvas.create_polygon(340, 120, 370, 170, 310, 170, fill="#33dd66", outline="")

        self.shapes = [
            ("anchor_rect", r1),
            ("anchor_rect", r2),
            ("rect", r3),
            ("rect", r4),
            ("tri", t1),
            ("tri", t2),
            ("tri", t3),
        ]
        self.tick = 0

    def _tick(self):
        if not self.running:
            return

        self.tick += 1

        # Triangles always change color
        for kind, sid in self.shapes:
            if kind == "tri":
                self.canvas.itemconfig(sid, fill=random.choice(self.colors))

        # Non-anchor rectangles may swap color occasionally
        if self.tick % 12 == 0:
            rects = [sid for kind, sid in self.shapes if kind == "rect"]
            if len(rects) == 2:
                c1 = self.canvas.itemcget(rects[0], "fill")
                c2 = self.canvas.itemcget(rects[1], "fill")
                self.canvas.itemconfig(rects[0], fill=c2)
                self.canvas.itemconfig(rects[1], fill=c1)

        # Move shapes slightly
        for kind, sid in self.shapes:
            dx = random.choice([-2, -1, 0, 1, 2])
            dy = random.choice([-2, -1, 0, 1, 2])
            self.canvas.move(sid, dx, dy)

        self.app.root.after(120, self._tick)

class Node1_ColorLab(NodeBase):
    node_id = "N1"
    title = "Color Lab (Present)"
    intro = "Jack wakes in a lab where colors refuse to stay put. The console flickers: 'Count what never lies.'"
    godskip_code = "GOD-N1-4412"
    games = [ColorShapesGame]

# ----------------------------
# Node 2: Chess riddle (CS students)
# ----------------------------

class ChessRiddleGame(GameBase):
    game_id = "chess"
    title = "Forked Timeline"
    description = "A chess puzzle framed as a search problem."

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Forked Timeline (Chess Riddle)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        text = (
            "Jack sees a board state (abstracted).\n\n"
            "Question:\n"
            "A knight at f5 can fork two major pieces.\n"
            "Which move is the fork?\n\n"
            "A) N(d4)\n"
            "B) N(g7)\n"
            "C) N(h6)\n"
            "D) N(e7)\n\n"
            "In terminal: solve chess <A|B|C|D>\n"
            "(CS hint: think in graph moves: each knight move is an edge.)"
        )
        ttk.Label(parent, text=text, wraplength=360, justify="left").pack(padx=12, pady=(0, 10), anchor="nw")

class Node2_Chess(NodeBase):
    node_id = "N2"
    title = "Chess Switchyard (1930)"
    intro = "Jack lands in a switchyard of decisions. Each move branches time like a search tree."
    godskip_code = "GOD-N2-9901"
    games = [ChessRiddleGame]

# ----------------------------
# Node 3: Tricky code scroll (predict where Jack goes)
# ----------------------------

class CodeScrollGame(GameBase):
    game_id = "codes"
    title = "Where Will Jack Go?"
    description = "Read tricky code; predict the destination."

    CODE_SNIPPETS = [
        ("Snippet A", """\njack = {"x": 0, "t": "N1"}
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
        ("Snippet B", """\npath = ["N1","N2","N3","N4","N5","N6"]
p = 0
for step in range(9):
    p = (p + step) % len(path)
    if step % 4 == 0:
        p = (p * 2) % len(path)
print(path[p])
"""),
        ("Snippet C", """\ndef jump(s):
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
        ttk.Label(parent, text="Pick a snippet in terminal then answer.\nCommands:\n  showcode <A|B|C>\n  solve code <A|B|C> <NODE_ID>", wraplength=360, justify="left").pack(padx=12, pady=(0, 8), anchor="nw")

        self.scroller = tk.Text(parent, height=14, width=46, bg="#0a0f1a", fg="#00ff88", insertbackground="#00ff88", wrap="none")
        self.scroller.pack(padx=12, pady=(0, 10), anchor="nw", fill="both", expand=True)
        self.scroller.insert("end", "Use terminal command: showcode A  (or B/C)\n")
        self.scroller.config(state="disabled")

class Node3_Code(NodeBase):
    node_id = "N3"
    title = "Code Observatory (2030)"
    intro = "Jack finds code etched into glass. The future asks: where will he go next?"
    godskip_code = "GOD-N3-1209"
    games = [CodeScrollGame]

# ----------------------------
# Node 4: Regex generator (changes every few seconds)
# ----------------------------

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

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Pattern Storm (Regex)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        ttk.Label(parent, text="Text changes every ~3 seconds.\nChoose the correct regex option.\nTerminal:\n  solve regex <1|2|3|4>", wraplength=360, justify="left").pack(padx=12, pady=(0, 8), anchor="nw")

        self.lbl = ttk.Label(parent, text="(generating...)", wraplength=360, justify="left")
        self.lbl.pack(padx=12, pady=(0, 10), anchor="nw")

        box = ttk.Frame(parent)
        box.pack(padx=12, pady=(0, 12), fill="x")

        self.opts = []
        for i in range(4):
            l = ttk.Label(box, text=f"{i+1}) ...", wraplength=360, justify="left")
            l.pack(anchor="nw", pady=2)
            self.opts.append(l)

        self.running = True
        self._tick()

    def _tick(self):
        if not self.running:
            return

        # generate a target string
        prefix = random.choice(["TIME", "NODE", "JACK", "ECHO"])
        digits = random.randint(10, 9999)
        suffix = random.choice(["A", "B", "C"])
        s = f"{prefix}-{digits}{suffix}"

        # correct regex among options (simple patterns)
        correct_patterns = [
            r"^(TIME|NODE|JACK|ECHO)-\d+[ABC]$",
            r"^[A-Z]{4}-\d{2,4}[ABC]$",
            r"^(TIME|NODE)-\d+[A-C]$",
            r"^[A-Z]+-\d+[A-Z]$",
        ]
        # pick one as correct and shuffle distractors
        self.correct = random.choice(correct_patterns)
        choices = [self.correct]

        distractors = [
            r"^(TIME|NODE|JACK|ECHO)\d+[ABC]$",         # missing hyphen
            r"^[A-Z]{4}-\d{5}[ABC]$",                   # too many digits fixed
            r"^(TIME|NODE|JACK|ECHO)-[A-Z]+[ABC]$",     # letters instead of digits
            r"^\d+-[A-Z]{4}[ABC]$",                     # reversed
            r"^[A-Z]{4}-\d{2,4}$",                      # missing suffix
        ]
        random.shuffle(distractors)
        for d in distractors[:3]:
            choices.append(d)
        random.shuffle(choices)

        self.lbl.config(text=f"TEXT:  {s}")
        for i, pat in enumerate(choices):
            self.opts[i].config(text=f"{i+1}) {pat}")

        # store index for answer checking (1..4)
        self._choice_map = {str(i+1): choices[i] for i in range(4)}

        self.app.root.after(3000, self._tick)

    def stop(self):
        self.running = False

class Node4_Regex(NodeBase):
    node_id = "N4"
    title = "Regex Drift (Timeless)"
    intro = "Jack sees symbols reforming. Patterns decide which doors stay open."
    godskip_code = "GOD-N4-7770"
    games = [RegexChoiceGame]

# ----------------------------
# Node 5: Repeated game theory (Prisoner's Dilemma style)
# ----------------------------

class GameTheoryGame(GameBase):
    game_id = "dilemma"
    title = "Iterated Dilemma"
    description = "Beat the opponent 6 rounds; includes training mode."

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Iterated Dilemma (Game Theory)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        txt = (
            "You play 6 rounds against a strategy.\n"
            "Actions: C (cooperate) or D (defect)\n\n"
            "Payoffs (you, opponent):\n"
            "  C/C = (3,3)\n"
            "  D/C = (5,0)\n"
            "  C/D = (0,5)\n"
            "  D/D = (1,1)\n\n"
            "Terminal:\n"
            "  train dilemma   (explains strategy)\n"
            "  play dilemma    (starts rounds; you answer each round)\n"
        )
        ttk.Label(parent, text=txt, wraplength=360, justify="left").pack(padx=12, pady=(0, 12), anchor="nw")

class Node5_GameTheory(NodeBase):
    node_id = "N5"
    title = "Strategic Loop (3000)"
    intro = "Jack meets an algorithm that rewards trust—until it doesn’t."
    godskip_code = "GOD-N5-6606"
    games = [GameTheoryGame]

# ----------------------------
# Node 6: Final (password fragments / end riddle placeholder)
# ----------------------------

class FinalRiddleGame(GameBase):
    game_id = "final"
    title = "Axis Lock"
    description = "Final password gate (placeholder in prototype)."

    def mount(self, parent):
        for w in parent.winfo_children():
            w.destroy()

        ttk.Label(parent, text="Axis Lock (Final)", font=("Segoe UI", 11, "bold")).pack(padx=12, pady=(12, 6), anchor="nw")
        txt = (
            "Jack stands before the Axis.\n"
            "The final password is assembled from earlier nodes.\n\n"
            "Terminal:\n"
            "  unlock <PASSWORD>\n"
            "  godskip <CODE>\n"
        )
        ttk.Label(parent, text=txt, wraplength=360, justify="left").pack(padx=12, pady=(0, 12), anchor="nw")

class Node6_Final(NodeBase):
    node_id = "N6"
    title = "The Axis (Final)"
    intro = "This is the end of the loop—or the start of the real one."
    godskip_code = "GOD-N6-0420"
    games = [FinalRiddleGame]

# ----------------------------
# App
# ----------------------------

class TimeTerminalApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Jack’s Time Terminal")
        self.root.geometry("1100x650")
        self.root.minsize(900, 540)

        self.password = None
        self.state = {
            "player_name": None,
            "score": 0,
            "current_node": "N1",
            "unlocked_nodes": ["N1"],
            "solved": {},      # game_id -> bool or metadata
        }

        # Node registry (exactly 6)
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
        self._boot()

    # ---------- UI ----------
    def _build_ui(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)

        # left: terminal
        left = ttk.Frame(outer)
        left.pack(side="left", fill="both", expand=True)

        # right: game panel
        right = ttk.Frame(outer, width=420)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        # terminal output
        self.output = tk.Text(left, bg="#0a0f1a", fg="#00ff88", insertbackground="#00ff88", wrap="word")
        self.output.pack(fill="both", expand=True, padx=10, pady=(10, 6))
        self.output.config(state="disabled")

        # input
        inp_row = ttk.Frame(left)
        inp_row.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(inp_row, text="> ").pack(side="left")
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(inp_row, textvariable=self.input_var)
        self.input_entry.pack(side="left", fill="x", expand=True)
        self.input_entry.bind("<Return>", lambda e: self._on_enter())

        ttk.Button(inp_row, text="Send", command=self._on_enter).pack(side="left", padx=(8, 0))

        # game panel container
        self.game_panel = ttk.Frame(right)
        self.game_panel.pack(fill="both", expand=True, padx=10, pady=10)

        # status bar
        self.status = ttk.Label(self.root, text="Ready", anchor="w")
        self.status.pack(fill="x")

    # ---------- Boot / Save ----------
    def _boot(self):
        self.print_line("Welcome to Jack’s Time Terminal.")
        self.print_line("A story of time, puzzles, and one stubborn console.\n")

        # ask password (first-time gate)
        self._prompt_password()

    def _prompt_password(self):
        win = tk.Toplevel(self.root)
        win.title("Enter Game Password")
        win.geometry("420x180")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Enter a password to start.\n(Used to encrypt your save file.)", justify="left").pack(padx=14, pady=(14, 8), anchor="w")

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
            # try load existing save
            self._try_load_save()
            # ask player name if missing
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
        win.geometry("420x180")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Hey traveler… what is your name?", justify="left").pack(padx=14, pady=(14, 8), anchor="w")
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
            # basic validation
            if "current_node" in data and "unlocked_nodes" in data:
                self.state.update(data)
                self.print_line("[SAVE] Loaded.")
        except Exception as e:
            self.print_line("[SAVE] Could not load (wrong password or tampered save). Starting fresh.")
            # keep fresh state

    def _save(self):
        if not self.password:
            return
        os.makedirs(SAVE_DIR, exist_ok=True)
        data = json.dumps(self.state, ensure_ascii=False).encode("utf-8")
        blob = encrypt_bytes(data, self.password)
        with open(SAVE_PATH, "wb") as f:
            f.write(blob)

    # ---------- Terminal IO ----------
    def print_line(self, s: str):
        self.output.config(state="normal")
        self.output.insert("end", s + "\n")
        self.output.see("end")
        self.output.config(state="disabled")

    def narrate(self, text: str):
        # Optional TTS; safe if missing.
        # pip install pyttsx3 (optional)
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
        self._save()

        self.current_node_obj = self.node_classes[node_id](self)
        self.current_node_obj.on_enter()

        # auto-mount first game UI if exists (or clear panel)
        self._clear_game_panel()
        self.status.config(text=f"{self.state['player_name']} | Node {node_id} | Score {self.state['score']}")

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
        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("help", "?"):
            self._cmd_help()
            return

        if cmd == "exit":
            self.print_line("This is the terminal app. Use 'travel' to move nodes. (Or close the window.)")
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
            # solve colors <NUMBER>
            # solve chess <A|B|C|D>
            # solve code <A|B|C> <NODE_ID>
            # solve regex <1|2|3|4>
            self._cmd_solve(args)
            return

        if cmd == "showcode":
            self._cmd_showcode(args)
            return

        if cmd == "train":
            self._cmd_train(args)
            return

        if cmd == "unlock":
            # final password (prototype placeholder)
            self._cmd_unlock(args)
            return

        if cmd == "godskip":
            self._cmd_godskip(args)
            return

        self.print_line("Unknown command. Type 'help'.")

    def _cmd_help(self):
        self.print_line("Commands:")
        self.print_line("  help                     - show commands")
        self.print_line("  node                     - show current node")
        self.print_line("  nodes                    - list nodes + unlocked")
        self.print_line("  routes                   - show Chrono Routes")
        self.print_line("  travel <N1..N6>           - move (if unlocked)")
        self.print_line("  games                    - list node games")
        self.print_line("  play <game_id>           - open game UI on right")
        self.print_line("  solve ...                - solve puzzles")
        self.print_line("  showcode <A|B|C>          - show a code snippet (Node3)")
        self.print_line("  train dilemma            - training for game theory (Node5)")
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
            self._save()
        self.print_line(f"[UNLOCK] {node_id} unlocked ({reason}).")

    def _cmd_solve(self, args):
        if not args:
            self.print_line("Usage examples:")
            self.print_line("  solve colors 6")
            self.print_line("  solve chess D")
            self.print_line("  solve regex 2")
            return

        kind = args[0].lower()
        cur = self.state["current_node"]

        # Node1 colors: the "total colors" is 6 in this prototype
        if kind == "colors" and cur == "N1":
            if len(args) < 2:
                self.print_line("Usage: solve colors <NUMBER>")
                return
            ans = args[1].strip()
            if ans == "6":
                self.state["score"] += 10
                self._save()
                self.print_line("[OK] You counted the spectrum correctly.")
                self._unlock_node("N2", "Chromatic Drift solved")
            else:
                self.print_line("[NO] Not quite. Watch the triangles vs anchor rectangles.")
            return

        # Node2 chess: in this prototype, correct is D) Ne7 (example)
        if kind == "chess" and cur == "N2":
            if len(args) < 2:
                self.print_line("Usage: solve chess <A|B|C|D>")
                return
            ans = args[1].strip().upper()
            if ans == "D":
                self.state["score"] += 10
                self._save()
                self.print_line("[OK] Fork found. Timeline branches.")
                self._unlock_node("N3", "Chess riddle solved")
            else:
                self.print_line("[NO] Not that one. Think like a BFS over knight moves.")
            return

        # Node4 regex: correctness depends on current generated correct pattern (not fully wired here)
        if kind == "regex" and cur == "N4":
            if len(args) < 2:
                self.print_line("Usage: solve regex <1|2|3|4>")
                return
            # This prototype: allow unlock even if wrong, but score only if "2"
            pick = args[1].strip()
            if pick == "2":
                self.state["score"] += 5
                self.print_line("[OK] Correct regex. Score awarded.")
            else:
                self.print_line("[OK] Node unlock granted, but no score for incorrect regex.")
            self._save()
            self._unlock_node("N5", "Pattern Storm attempt")
            return

        self.print_line("[ERR] That solve command doesn’t apply here (wrong node or wrong format).")

    def _cmd_showcode(self, args):
        if self.state["current_node"] != "N3":
            self.print_line("[ERR] showcode only works in Node3.")
            return
        if not args:
            self.print_line("Usage: showcode <A|B|C>")
            return
        key = args[0].strip().upper()
        # find the CodeScrollGame in right panel (if mounted)
        # This is just terminal output for now:
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
            self.print_line("Tip: Pure D gives fast points but triggers retaliation; plan 6 rounds.")
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
        # Prototype final password:
        if pw.lower() == "jackisunstuck":
            self.state["score"] += 50
            self._save()
            self.print_line("[OK] The Axis opens. Jack steps out of the loop.")
            self.print_line("ENDING: Time exhales. The console goes quiet.")
        else:
            self.print_line("[NO] The Axis rejects it. The loop tightens.")

    def _cmd_godskip(self, args):
        if not args:
            self.print_line("Usage: godskip <CODE>")
            return
        code = args[0].strip()
        node = self.current_node_obj
        if code == node.godskip_code:
            # unlock next reachable nodes from this node
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
    # ttk theme (optional)
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except:
        pass

    app = TimeTerminalApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
