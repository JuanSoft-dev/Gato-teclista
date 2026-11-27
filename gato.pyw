"""Gato teclista: un gato en el escritorio que teclea cuando tú tecleas
y mueve el mouse cuando tú lo mueves.

- Arrástralo con clic izquierdo para cambiarlo de sitio.
- Rueda del mouse sobre el gato: más grande / más pequeño.
- Clic derecho: tamaño, micrófono y Salir.
- Con el micrófono activado, el gato mueve la boca cuando hablas. Solo se mide
  el volumen, en tu PC; no se graba ni se envía nada.
Solo Windows. Sin dependencias (Python + tkinter).
"""
import array
import ctypes
import json
from ctypes import wintypes as wt
import math
import os
import random
import time
import tkinter as tk

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor():
    p = POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


# ------------------------------------------------------------------ mouse crudo
# Los juegos suelen bloquear el cursor en el centro, así que su posición no
# cambia. Raw Input da el movimiento físico del mouse aunque el cursor esté quieto.
import threading

kernel32 = ctypes.windll.kernel32
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT),
                ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD),
                ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wt.USHORT), ("ulButtons", wt.ULONG), ("ulRawButtons", wt.ULONG),
                ("lLastX", wt.LONG), ("lLastY", wt.LONG), ("ulExtraInformation", wt.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND,
                                   wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wt.UINT, wt.UINT]
user32.GetRawInputData.argtypes = [wt.HANDLE, wt.UINT, wt.LPVOID,
                                   ctypes.POINTER(wt.UINT), wt.UINT]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
kernel32.GetModuleHandleW.restype = wt.HMODULE
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]


class RawMouse:
    """Acumula el movimiento físico del mouse en un hilo aparte."""

    def __init__(self):
        self.dx = self.dy = 0
        self.lock = threading.Lock()
        self._proc = WNDPROC(self._wndproc)  # guardar referencia: si no, Python la libera
        threading.Thread(target=self._run, daemon=True).start()

    def take(self):
        with self.lock:
            d = (self.dx, self.dy)
            self.dx = self.dy = 0
        return d

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == 0x00FF:  # WM_INPUT
            raw = RAWINPUT()
            size = wt.UINT(ctypes.sizeof(raw))
            if user32.GetRawInputData(lparam, 0x10000003, ctypes.byref(raw), ctypes.byref(size),
                                      ctypes.sizeof(RAWINPUTHEADER)) != 0xFFFFFFFF:
                if raw.header.dwType == 0 and not raw.mouse.usFlags & 1:  # mouse, relativo
                    with self.lock:
                        self.dx += raw.mouse.lLastX
                        self.dy += raw.mouse.lLastY
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = f"GatoTeclistaRawInput{id(self)}"
        user32.RegisterClassW(ctypes.byref(wc))
        hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "", 0, 0, 0, 0, 0,
                                      wt.HWND(-3), None, hinst, None)  # ventana invisible
        rid = RAWINPUTDEVICE(1, 2, 0x100, hwnd)  # mouse, recibir aunque no tenga el foco
        user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# ------------------------------------------------------------------ micrófono
winmm = ctypes.windll.winmm


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wt.WORD), ("nChannels", wt.WORD),
                ("nSamplesPerSec", wt.DWORD), ("nAvgBytesPerSec", wt.DWORD),
                ("nBlockAlign", wt.WORD), ("wBitsPerSample", wt.WORD), ("cbSize", wt.WORD)]


class WAVEHDR(ctypes.Structure):
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wt.DWORD),
                ("dwBytesRecorded", wt.DWORD), ("dwUser", ctypes.c_size_t),
                ("dwFlags", wt.DWORD), ("dwLoops", wt.DWORD),
                ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_size_t)]


winmm.waveInOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wt.UINT,
                             ctypes.POINTER(WAVEFORMATEX), ctypes.c_size_t,
                             ctypes.c_size_t, wt.DWORD]
for _fn in ("waveInPrepareHeader", "waveInUnprepareHeader", "waveInAddBuffer"):
    getattr(winmm, _fn).argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wt.UINT]
for _fn in ("waveInStart", "waveInReset", "waveInClose"):
    getattr(winmm, _fn).argtypes = [ctypes.c_void_p]


class Mic:
    """Lee el volumen del micrófono predeterminado (16 kHz, mono).
    No guarda el audio: cada bloque se convierte en un número y se descarta."""
    RATE, BLOCK, NBUF = 16000, 800, 4  # bloques de 50 ms

    def __init__(self):
        self.h = ctypes.c_void_p()
        fmt = WAVEFORMATEX(1, 1, self.RATE, self.RATE * 2, 2, 16, 0)
        if winmm.waveInOpen(ctypes.byref(self.h), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0):
            raise OSError("no hay micrófono disponible")
        self.bufs, self.hdrs = [], []
        for _ in range(self.NBUF):
            buf = ctypes.create_string_buffer(self.BLOCK * 2)
            hdr = WAVEHDR(ctypes.cast(buf, ctypes.c_void_p), self.BLOCK * 2, 0, 0, 0, 0, None, 0)
            winmm.waveInPrepareHeader(self.h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            winmm.waveInAddBuffer(self.h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            self.bufs.append(buf)
            self.hdrs.append(hdr)
        winmm.waveInStart(self.h)

    def level(self):
        """Volumen más reciente de 0 a 1 (None si no llegó audio nuevo)."""
        out = None
        for buf, hdr in zip(self.bufs, self.hdrs):
            if hdr.dwFlags & 1:  # WHDR_DONE
                samples = array.array("h", buf.raw[:hdr.dwBytesRecorded])
                if samples:
                    rms = math.sqrt(sum(x * x for x in samples) / len(samples))
                    db = 20 * math.log10(max(rms, 1) / 32768)
                    out = min(max((db + 48) / 28, 0.0), 1.0)  # -48 dB -> 0, -20 dB -> 1
                hdr.dwFlags &= ~1
                winmm.waveInAddBuffer(self.h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        return out

    def close(self):
        winmm.waveInReset(self.h)
        for hdr in self.hdrs:
            winmm.waveInUnprepareHeader(self.h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
        winmm.waveInClose(self.h)


# Teclas que se vigilan: todo menos botones del mouse y Shift/Ctrl/Alt genéricos
# (sus versiones izquierda/derecha ya se vigilan).
SKIP = {0x01, 0x02, 0x04, 0x05, 0x06, 0x10, 0x11, 0x12}
WATCH = [vk for vk in range(0x08, 0xFF) if vk not in SKIP]

MOUSE_HOLD = 2.0  # segundos que la pata se queda en el mouse tras usarlo

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gato_config.json")

# Colores
TRANSP = "#ff00fe"
BLACK = "#161616"
EDGE = "#6b6b6b"
WHITE = "#fbfaf5"
EYE = "#f2c12e"
KB_BODY = "#2b2b2b"
KEY = "#efece4"
KEY_ALT = "#c9c6bd"
KEY_HIT = "#ffb54d"
ACCENT = "#d9822b"
MUG = "#fbfaf5"
MUG_EDGE = "#b9b5aa"
COFFEE = "#5b3a22"
STEAM = "#c8c6c0"
HP_BAND = "#34343c"
HP_SHINE = "#5c5c68"
HP_CUP = "#d9822b"
HP_DARK = "#8a4f18"
MOUTH = "#4a1820"
MOUTH_LINE = "#8a8690"
TONGUE = "#e9788c"

W, H = 470, 370

# Teclado 75%. Cada tecla: (id, ancho en unidades, color).
# Las teclas de escritura usan el código de posición física (scan code), así
# funcionan con cualquier idioma de teclado (la Ñ cae donde está la Ñ).
# Las de navegación/modificadores usan 1000 + código virtual.
A, M, O = "key", "mod", "acc"
V = 1000


def _scan(first, n):
    return [(first + i, 1, A) for i in range(n)]


ROWS = [
    [(0x01, 1, O)] + [(sc, 1, M) for sc in range(0x3B, 0x45)] + [(0x57, 1, M), (0x58, 1, M),
     (V + 0x2C, 1, M), (V + 0x2D, 1, M), (V + 0x2E, 1, M)],
    [(0x29, 1, A)] + _scan(0x02, 12) + [(0x0E, 2, M), (V + 0x24, 1, M)],
    [(0x0F, 1.5, M)] + _scan(0x10, 12) + [(0x2B, 1.5, A), (V + 0x21, 1, M)],
    [(0x3A, 1.75, M)] + _scan(0x1E, 11) + [(0x1C, 2.25, O), (V + 0x22, 1, M)],
    [(0x2A, 2.25, M)] + _scan(0x2C, 10) + [(0x36, 1.75, M), (V + 0x26, 1, M), (V + 0x23, 1, M)],
    [(V + 0xA2, 1.25, M), (V + 0x5B, 1.25, M), (V + 0xA4, 1.25, M), (0x39, 6.25, A),
     (V + 0xA5, 1, M), (None, 1, M), (V + 0xA3, 1, M),
     (V + 0x25, 1, M), (V + 0x28, 1, M), (V + 0x27, 1, M)],
]
# Teclas que se identifican por código virtual (no por posición)
BY_VK = {0x2C, 0x2D, 0x2E, 0x24, 0x21, 0x22, 0x23, 0x26, 0x25, 0x28, 0x27,
         0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C, 0x5D}
EXTRA = {0x56: 0x2A}  # tecla < > de teclados ISO -> la contamos como Shift izq.

KB_X0, KB_Y0, KB_X1, KB_Y1 = 208, 276, 462, 358
KB_PAD, KB_GAP = 6, 2.0


def vk_to_id(vk):
    if vk in BY_VK:
        return V + vk
    sc = user32.MapVirtualKeyW(vk, 0)
    return EXTRA.get(sc, sc)


class Gato:
    def __init__(self):
        cfg = {}
        try:
            with open(CONFIG, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
        self.z = min(max(float(cfg.get("scale", 1.0)), 0.4), 2.5)

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=TRANSP)
        self.root.attributes("-transparentcolor", TRANSP)
        self.sw, self.sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = self.dims()
        pos = cfg.get("pos")
        if not (isinstance(pos, list) and len(pos) == 2):
            pos = [self.sw - w - 30, self.sh - h - 60]
        self.pos = [int(pos[0]), int(pos[1])]

        self.c = tk.Canvas(self.root, bg=TRANSP, highlightthickness=0)
        self.c.pack()
        self.apply_size()

        self.prev = set()
        self.lit = {}  # item -> (hora en que se apaga, color original)
        # cada pata: última tecla que tocó y cuándo
        self.key_pos = {"l": (275, 300), "r": (395, 300)}
        self.hit_at = {"l": 0.0, "r": 0.0}
        self.paw = {"l": [275.0, 280.0], "r": [395.0, 280.0]}  # posición animada
        self.last_key = 0.0
        self.last_mouse = 0.0
        self.last_cursor = cursor()
        self.vm = [self.last_cursor[0] / self.sw, self.last_cursor[1] / self.sh]
        self.locked_at = 0.0
        self.raw = RawMouse()
        self.next_blink = time.time() + 3
        self.keep_on_top()

        # micrófono: apagado salvo que lo actives desde el menú
        self.mic = None
        self.mouth_open = 0.0
        self.mic_var = tk.BooleanVar(value=False)
        if cfg.get("mic"):
            self.set_mic(True, quiet=True)

        c = self.c
        c.bind("<ButtonPress-1>", self.drag_start)
        c.bind("<B1-Motion>", self.drag_move)
        c.bind("<ButtonRelease-1>", lambda e: self.save())
        c.bind("<MouseWheel>", lambda e: self.set_scale(self.z + (0.1 if e.delta > 0 else -0.1)))
        menu = tk.Menu(self.root, tearoff=0)
        size = tk.Menu(menu, tearoff=0)
        for label, z in (("Mini (50%)", 0.5), ("Pequeño (75%)", 0.75), ("Normal (100%)", 1.0),
                         ("Grande (125%)", 1.25), ("Enorme (150%)", 1.5)):
            size.add_command(label=label, command=lambda z=z: self.set_scale(z))
        menu.add_cascade(label="Tamaño", menu=size)
        menu.add_checkbutton(label="Micrófono (mover la boca)", variable=self.mic_var,
                             command=lambda: self.set_mic(self.mic_var.get()))
        menu.add_separator()
        menu.add_command(label="Salir", command=self.quit)
        c.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

        self.tick()

    # ---------- tamaño ----------
    def dims(self):
        return round(W * self.z), round(H * self.z)

    def p(self, *v):
        """Escala coordenadas del dibujo base (470x370) al tamaño actual."""
        return [a * self.z for a in v]

    def lw(self, w):
        return max(1, w * self.z)

    def apply_size(self):
        w, h = self.dims()
        self.c.config(width=w, height=h)
        self.root.geometry(f"{w}x{h}+{self.pos[0]}+{self.pos[1]}")
        self.c.delete("all")
        self.lit = {}
        self.build()

    def set_scale(self, z):
        z = round(min(max(z, 0.4), 2.5), 2)
        if z == self.z:
            return
        ow, oh = self.dims()
        self.z = z
        w, h = self.dims()
        # mantener el gato anclado por abajo-centro
        self.pos = [self.pos[0] + (ow - w) // 2, self.pos[1] + oh - h]
        self.apply_size()
        self.save()

    def save(self):
        try:
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump({"scale": self.z, "pos": self.pos, "mic": self.mic is not None}, f)
        except Exception:
            pass

    def set_mic(self, on, quiet=False):
        if on and self.mic is None:
            try:
                self.mic = Mic()
            except Exception:
                self.mic = None
                if not quiet:
                    from tkinter import messagebox
                    messagebox.showinfo("Gato teclista",
                                        "No pude abrir el micrófono.\n\nRevisa que esté conectado y que "
                                        "Windows permita a las apps de escritorio usarlo "
                                        "(Configuración > Privacidad > Micrófono).")
        elif not on and self.mic is not None:
            self.mic.close()
            self.mic = None
        self.mic_var.set(self.mic is not None)
        self.save()

    def quit(self):
        self.save()
        if self.mic is not None:
            self.mic.close()
        self.root.destroy()

    # ---------- dibujo ----------
    def build(self):
        c, p, lw = self.c, self.p, self.lw
        # cola
        c.create_line(*p(320, 250, 390, 245, 420, 200, 445, 205, 455, 190),
                      smooth=True, width=lw(18), fill=BLACK, capstyle="round")
        # cuerpo
        c.create_oval(*p(140, 120, 340, 340), fill=BLACK, outline=EDGE, width=lw(3))

        # teclado
        c.create_rectangle(*p(KB_X0, KB_Y0, KB_X1, KB_Y1), fill=KB_BODY, outline="")
        self.keys = {}
        colors = {A: KEY, M: KEY_ALT, O: ACCENT}
        ux = (KB_X1 - KB_X0 - 2 * KB_PAD) / 16          # ancho de 1 unidad
        uy = (KB_Y1 - KB_Y0 - 2 * KB_PAD) / len(ROWS)   # alto de una fila

        for r, row in enumerate(ROWS):
            x = 0.0
            for kid, units, kind in row:
                x0 = KB_X0 + KB_PAD + x * ux
                y0 = KB_Y0 + KB_PAD + r * uy
                x1, y1 = x0 + units * ux - KB_GAP, y0 + uy - KB_GAP
                x += units
                # El gato está de frente a nosotros: el teclado mira hacia él (girado 180°)
                x0, x1 = KB_X0 + KB_X1 - x1, KB_X0 + KB_X1 - x0
                y0, y1 = KB_Y0 + KB_Y1 - y1, KB_Y0 + KB_Y1 - y0
                col = colors[kind]
                it = c.create_rectangle(*p(x0, y0, x1, y1), fill=col, outline="")
                if kid is not None:
                    self.keys[kid] = (it, col, ((x0 + x1) / 2, (y0 + y1) / 2))
        self.all_keys = list(self.keys.values())

        # taza de café (con vapor animado en tick)
        c.create_oval(*p(184, 307, 208, 329), outline=MUG, width=lw(5))  # asa
        c.create_rectangle(*p(162, 300, 196, 338), fill=MUG, outline="")
        c.create_oval(*p(162, 332, 196, 344), fill=MUG, outline="")
        c.create_oval(*p(162, 294, 196, 306), fill=MUG, outline=MUG_EDGE, width=lw(1.5))
        c.create_oval(*p(166, 296, 192, 304), fill=COFFEE, outline="")
        c.create_text(*p(179, 322), text="</>", fill=ACCENT,
                      font=("Consolas", -max(5, round(11 * self.z)), "bold"))
        self.steam = [c.create_line(0, 0, 1, 1, 0, 2, smooth=True, width=lw(2),
                                    fill=STEAM, capstyle="round") for _ in range(3)]

        # mouse
        self.mouse = c.create_oval(0, 0, 1, 1, fill=WHITE, outline="#9b988f", width=lw(2))
        # botones hacia nosotros; el clic izquierdo del gato queda a nuestra derecha
        self.mbtn_l = c.create_arc(0, 0, 1, 1, start=270, extent=90, fill=WHITE,
                                   outline="#9b988f", width=lw(2))
        self.mbtn_r = c.create_arc(0, 0, 1, 1, start=180, extent=90, fill=WHITE,
                                   outline="#9b988f", width=lw(2))

        # brazos y patitas
        self.arm_l = c.create_line(0, 0, 1, 1, width=lw(32), fill=BLACK, capstyle="round")
        self.arm_r = c.create_line(0, 0, 1, 1, width=lw(32), fill=BLACK, capstyle="round")
        self.paw_l = c.create_oval(0, 0, 1, 1, fill=WHITE, outline="")
        self.paw_r = c.create_oval(0, 0, 1, 1, fill=WHITE, outline="")

        # cabeza
        c.create_polygon(*p(160, 95, 165, 20, 215, 60), fill=BLACK, outline=EDGE, width=lw(3))
        c.create_polygon(*p(300, 95, 295, 20, 245, 60), fill=BLACK, outline=EDGE, width=lw(3))
        c.create_oval(*p(150, 40, 310, 170), fill=BLACK, outline=EDGE, width=lw(3))
        self.eyes = []
        for ex in (200, 262):
            c.create_oval(*p(ex - 19, 82, ex + 19, 120), fill=EYE, outline="")
            pu = c.create_oval(0, 0, 1, 1, fill=BLACK, outline="")
            self.eyes.append((ex, 101, pu))
        self.lids = [c.create_rectangle(*p(ex - 21, 80, ex + 21, 122), fill=BLACK,
                                        outline="", state="hidden") for ex in (200, 262)]

        # audífonos: diadema por encima de la cabeza y almohadillas a los lados
        c.create_arc(*p(146, 30, 314, 190), start=12, extent=156, style="arc",
                     outline=HP_BAND, width=lw(9))
        c.create_arc(*p(148, 32, 312, 188), start=30, extent=120, style="arc",
                     outline=HP_SHINE, width=lw(2))
        for x0 in (132, 296):
            c.create_oval(*p(x0, 84, x0 + 32, 136), fill=HP_CUP, outline=HP_BAND, width=lw(3))
            c.create_oval(*p(x0 + 9, 96, x0 + 23, 124), fill=HP_DARK, outline="")
        for y0, y1 in ((132, 126), (140, 140), (148, 154)):
            c.create_line(*p(178, y0, 140, y1), fill="#d9d6cc", width=lw(1.5))
            c.create_line(*p(282, y0, 320, y1), fill="#d9d6cc", width=lw(1.5))
        # boca cerrada (una "w") y boca abierta con lengua y colmillos
        self.mouth_closed = [
            c.create_arc(*p(222, 129, 231, 139), start=180, extent=180, style="arc",
                         outline=MOUTH_LINE, width=lw(1.5)),
            c.create_arc(*p(231, 129, 240, 139), start=180, extent=180, style="arc",
                         outline=MOUTH_LINE, width=lw(1.5))]
        self.mouth = c.create_oval(0, 0, 1, 1, fill=MOUTH, outline=MOUTH_LINE,
                                   width=lw(1.2), state="hidden")
        self.tongue = c.create_oval(0, 0, 1, 1, fill=TONGUE, outline="", state="hidden")
        self.fangs = [c.create_polygon(0, 0, 1, 1, 0, 1, fill=WHITE, outline="",
                                       state="hidden") for _ in range(2)]
        c.create_polygon(*p(225, 128, 237, 128, 231, 135), fill="#e98a9a", outline="")

    def drag_start(self, e):
        self._grab = (e.x_root - self.pos[0], e.y_root - self.pos[1])

    def drag_move(self, e):
        self.pos = [e.x_root - self._grab[0], e.y_root - self._grab[1]]
        self.root.geometry(f"+{self.pos[0]}+{self.pos[1]}")

    # ---------- bucle ----------
    def tick(self):
        now = time.time()
        c, p = self.c, self.p
        cx, cy = cursor()
        wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()

        # teclas: detectar pulsaciones nuevas
        pressed = {vk for vk in WATCH if down(vk)}
        for vk in pressed - self.prev:
            it, col, pos = self.keys.get(vk_to_id(vk)) or random.choice(self.all_keys)
            c.itemconfig(it, fill=KEY_HIT)
            self.lit[it] = (now + 0.12, col)
            # mitad izquierda del teclado (vista nuestra) -> pata izquierda; resto -> derecha.
            # Si la pata izquierda está en el mouse, la derecha escribe todo.
            on_mouse = now - self.last_mouse < MOUSE_HOLD
            side = "l" if pos[0] < (KB_X0 + KB_X1) / 2 and not on_mouse else "r"
            self.key_pos[side] = pos
            self.hit_at[side] = now
            self.last_key = now
        self.prev = pressed
        for it, (t, col) in list(self.lit.items()):
            if now > t:
                c.itemconfig(it, fill=col)
                del self.lit[it]

        # mouse: si el cursor se mueve, sigue su posición en la pantalla; si está
        # bloqueado (juegos), usa el movimiento físico del mouse.
        lbtn, rbtn = down(0x01), down(0x02)
        lx, ly = self.last_cursor
        rdx, rdy = self.raw.take()
        cursor_moved = (cx, cy) != (lx, ly)
        if cursor_moved:
            self.vm = [cx / self.sw, cy / self.sh]
        elif rdx or rdy:
            self.vm[0] = min(max(self.vm[0] + rdx / self.sw * 0.5, 0.0), 1.0)
            self.vm[1] = min(max(self.vm[1] + rdy / self.sh * 0.5, 0.0), 1.0)
            self.locked_at = now
        elif now - self.locked_at < 5 and now - self.last_mouse > 0.4:
            # cursor bloqueado y mouse quieto: vuelve despacio al centro
            self.vm[0] += (0.5 - self.vm[0]) * 0.03
            self.vm[1] += (0.5 - self.vm[1]) * 0.03
        if abs(cx - lx) + abs(cy - ly) > 3 or abs(rdx) + abs(rdy) > 3 or lbtn or rbtn:
            self.last_mouse = now  # ignora temblores mínimos
        self.last_cursor = (cx, cy)
        mx = 95 - (self.vm[0] - 0.5) * 70  # en espejo: su derecha es nuestra izquierda
        # el gato está de frente: si tu mouse va hacia arriba (lejos de ti),
        # el suyo va hacia abajo (lejos de él)
        my = 312 - (self.vm[1] - 0.5) * 36
        c.coords(self.mouse, *p(mx - 24, my - 30, mx + 24, my + 30))
        c.coords(self.mbtn_l, *p(mx - 24, my - 10, mx + 24, my + 30))
        c.coords(self.mbtn_r, *p(mx - 24, my - 10, mx + 24, my + 30))
        c.itemconfig(self.mbtn_l, fill=KEY_HIT if lbtn else WHITE)
        c.itemconfig(self.mbtn_r, fill=KEY_HIT if rbtn else WHITE)

        # Si usaste el mouse hace poco, una pata se queda en el mouse y la otra
        # escribe todo el teclado. Tras MOUSE_HOLD s sin mouse, vuelven las dos patas.
        on_mouse = now - self.last_mouse < MOUSE_HOLD

        # destino de cada pata: sobre su tecla (abajo si acaba de pulsar)
        targets = {}
        for side in ("l", "r"):
            kx, ky = self.key_pos[side]
            pressing = now - self.hit_at[side] < 0.1
            targets[side] = (kx, ky if pressing else ky - 22, pressing)
        if on_mouse:
            pdy = 4 if (lbtn or rbtn) else 0
            targets["l"] = (mx, my - 12 + pdy, True)

        for side, (sx, sy), arm, paw in (("l", (180, 200), self.arm_l, self.paw_l),
                                         ("r", (290, 200), self.arm_r, self.paw_r)):
            tx, ty, snap = targets[side]
            cur = self.paw[side]
            k = 0.7 if snap else 0.35
            cur[0] += (tx - cur[0]) * k
            cur[1] += (ty - cur[1]) * k
            px, py = cur
            c.coords(arm, *p(sx, sy, px, py - 4))
            c.coords(paw, *p(px - 15, py - 9, px + 15, py + 9))

        # boca: se abre según el volumen del micrófono
        level = self.mic.level() if self.mic is not None else 0.0
        if level is not None:
            k = 0.6 if level > self.mouth_open else 0.25  # abre rápido, cierra suave
            self.mouth_open += (level - self.mouth_open) * k
        self.draw_mouth(self.mouth_open)

        # vapor del café: tres hilos que ondulan
        for i, st in enumerate(self.steam):
            x0 = 171 + i * 8
            pts = []
            for j in range(5):
                y = 290 - j * 5.5 - (i % 2) * 4
                pts += [x0 + 2.5 * math.sin(now * 3 - j * 0.9 + i * 0.7), y]
            c.coords(st, *p(*pts))

        # ojos siguen el cursor
        for ex, ey, pu in self.eyes:
            dx, dy = cx - (wx + ex * self.z), cy - (wy + ey * self.z)
            d = max((dx * dx + dy * dy) ** 0.5, 1)
            k = min(d, 300) / 300 * 9
            ox, oy = dx / d * k, dy / d * k
            c.coords(pu, *p(ex + ox - 8, ey + oy - 12, ex + ox + 8, ey + oy + 12))

        # parpadeo
        if now > self.next_blink:
            for l in self.lids:
                c.itemconfig(l, state="normal")
            if now > self.next_blink + 0.12:
                for l in self.lids:
                    c.itemconfig(l, state="hidden")
                self.next_blink = now + random.uniform(2.5, 6)

        self.root.after(16, self.tick)

    def draw_mouth(self, a):
        c, p = self.c, self.p
        is_open = a > 0.08
        for it in self.mouth_closed:
            c.itemconfig(it, state="hidden" if is_open else "normal")
        for it in [self.mouth, self.tongue] + self.fangs:
            c.itemconfig(it, state="normal" if is_open else "hidden")
        if not is_open:
            return
        cx, top = 231, 133
        h = 6 + 20 * a
        w = 8 + 6 * a
        c.coords(self.mouth, *p(cx - w, top, cx + w, top + h))
        c.coords(self.tongue, *p(cx - w * 0.6, top + h * 0.5, cx + w * 0.6, top + h - 1))
        fl = 3.5 + 5 * a  # largo de los colmillos
        for sx, fang in zip((-1, 1), self.fangs):
            fx = cx + sx * w * 0.5
            c.coords(fang, *p(fx - 2.6, top + 1.5, fx + 2.6, top + 1.5, fx, top + 1.5 + fl))

    def keep_on_top(self):
        """Cada 2 s se vuelve a poner encima de todo (por si un juego lo tapa),
        sin robar el foco a la ventana que estás usando."""
        try:
            hwnd = user32.GetAncestor(ctypes.c_void_p(self.root.winfo_id()), 2)
            # HWND_TOPMOST, sin mover, sin cambiar tamaño, sin activar
            user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1), 0, 0, 0, 0,
                                0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass
        self.root.after(2000, self.keep_on_top)


if __name__ == "__main__":
    Gato().root.mainloop()
