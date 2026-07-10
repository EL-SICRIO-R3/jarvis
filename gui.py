"""
gui.py
------
Interfaz de Jarvis: fondo negro con red molecular animada.
Entrada y salida totalmente por voz.
"""

from __future__ import annotations

import math
import platform
import random
import subprocess
import threading
import time
import os
import tkinter as tk
from dotenv import load_dotenv

load_dotenv()

try:
    from tkinterdnd2 import DND_FILES as _DND_FILES, TkinterDnD as _TkDnD
    _DND_BASE: type = _TkDnD.Tk
    _HAS_DND = True
except ImportError:
    _DND_BASE = tk.Tk  # type: ignore[assignment,misc]
    _HAS_DND = False
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_agent import JarvisAgent

_SO = platform.system().lower()

# ── Estados ────────────────────────────────────────────────────────────────
_IDLE      = "idle"
_LISTENING = "listening"
_THINKING  = "thinking"
_SPEAKING  = "speaking"
_PAUSED    = "paused"

_STATE_COLOR = {
    _IDLE:      "#1A6FFF",
    _LISTENING: "#00FFCC",
    _THINKING:  "#FF9500",
    _SPEAKING:  "#30D158",
    _PAUSED:    "#3A3A3C",
}
_STATE_LABEL = {
    _IDLE:      "Inicializando voz…",
    _LISTENING: "En escucha…  (di «Jarvis» para activar)",
    _THINKING:  "Procesando…",
    _SPEAKING:  "Hablando  ·  clic o Esc para interrumpir",
    _PAUSED:    "Conversación pausada",
}

# ── Dimensiones ─────────────────────────────────────────────────────────────
_W, _H        = 860, 620
_BOTTOM_H     = 120
_N_PARTICLES  = 72    # puntos distribuidos en la esfera (Fibonacci)
_SPHERE_R     = 0.26  # radio como fraccion de min(W,H)
_CONNECT_D3   = 0.68  # umbral de conexion en distancia de cuerda 3D
_FPS          = 30

_WIDGET_W, _WIDGET_H = 220, 220        # dimensiones del modo widget
_LOCAL_VOICES = [                      # voces disponibles en la configuración local
    ("Jorge · México  (Neural)", "es-MX-JorgeNeural"),
    ("Dalia · México  (Neural)", "es-MX-DaliaNeural"),
    ("Álvaro · España (Neural)", "es-ES-AlvaroNeural"),
    ("Elvira · España (Neural)", "es-ES-ElviraNeural"),
    ("Elena · Argentina (Neural)", "es-AR-ElenaNeural"),
    ("Tomás · Argentina (Neural)", "es-AR-TomasNeural"),
]

def _open_path(path: str) -> None:
    """Abre un archivo con la aplicación predeterminada del sistema."""
    if _SO == "darwin":
        command = ["open", path]
    elif _SO == "windows":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    else:
        command = ["xdg-open", path]
    subprocess.Popen(command)


class _Particle:
    """Punto en la superficie de una esfera unitaria — distribucion Fibonacci."""
    __slots__ = ("x0", "y0", "z0", "phase", "disp_cur")

    def __init__(self, index: int, total: int) -> None:
        golden     = (1.0 + math.sqrt(5.0)) / 2.0
        theta      = math.acos(1.0 - 2.0 * (index + 0.5) / total)
        phi        = 2.0 * math.pi * index / golden
        self.x0    = math.sin(theta) * math.cos(phi)
        self.y0    = math.sin(theta) * math.sin(phi)
        self.z0    = math.cos(theta)
        self.phase = random.uniform(0.0, 2.0 * math.pi)
        self.disp_cur: float = 1.0   # desplazamiento radial suavizado (lerp)

class JarvisWindow(_DND_BASE):
    """Ventana principal de Jarvis: red molecular animada + voz."""

    def __init__(self, agent: Optional["JarvisAgent"] = None) -> None:
        super().__init__()
        self._agent       = agent
        self._state       = _IDLE
        self._t0          = time.time()
        self._recognizer   = None
        self._mic          = None
        self._say_proc     = None   # proceso TTS activo (afplay)
        self._tts_tmpfile  = None   # mp3 temporal de edge-tts
        self._voice_active = True   # flag para detener el loop
        self._paused       = False  # pausa manual
        self._pause_t0     = 0.0   # instante en que se pausó
        self._ring_factor  = 1.0   # factor de radio del anillo (muelle)

        self._pending_image_path: str | None = None  # ruta imagen arrastrada
        self._pending_image_tk   = None              # ImageTk para canvas
        self._image_needs_cmd    = False             # esperando voz para imagen
        self._img_close_rect     = None              # bounds del × de cierre
        self._img_drop_rect      = None              # bounds del + de carga

        self._doc_preview_path: str | None = None  # ruta último doc generado
        self._doc_preview_t0: float        = 0.0   # timestamp absoluto (time.time())
        self._doc_preview_rect             = None  # bounds para clic-to-open

        self._capture_preview_path: str | None = None  # ruta imagen capturada (webcam/pantalla)
        self._capture_preview_tk           = None       # ImageTk para el thumbnail
        self._capture_preview_t0: float    = 0.0
        self._capture_preview_rect         = None

        self._video_preview_path: str | None = None  # ruta video generado
        self._video_preview_t0: float        = 0.0
        self._video_preview_rect             = None

        # ── Ajustes ──────────────────────────────────────────────────────────
        self._selected_voice: str = _LOCAL_VOICES[0][1]
        self._text_mode: bool     = False
        self._widget_mode: bool   = False
        self._restore_geometry: str = f"{_W}x{_H}"
        self._drag_x: int = 0
        self._drag_y: int = 0
        self._widget_restore_rect  = None
        self._settings_win         = None
        self._bottom_frame         = None   # asignado en _build_ui
        self._btns_row             = None   # asignado en _build_ui

        self._configure_window()
        self._build_ui()
        self._init_voice()
        self._schedule_frame()

    # ── Ventana ──────────────────────────────────────────────────────────────────
    def _configure_window(self) -> None:
        self.title("Jarvis")
        self.configure(bg="black")
        self.resizable(False, False)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - _W) // 2
        y  = (sh - _H) // 3
        self.geometry(f"{_W}x{_H}+{x}+{y}")

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        canvas_h = _H - _BOTTOM_H
        self._canvas_h = canvas_h

        self._canvas = tk.Canvas(
            self, width=_W, height=canvas_h,
            bg="black", highlightthickness=0
        )
        self._canvas.pack(side="top", fill="both", expand=True)

        bottom = tk.Frame(self, bg="black")
        bottom.pack(side="bottom", fill="x")
        self._bottom_frame = bottom

        response_frame = tk.Frame(bottom, bg="black")
        response_frame.pack(fill="x", padx=24, pady=(10, 2))
        self._response_text = tk.Text(
            response_frame, height=4, wrap="word",
            fg="#777777", bg="black",
            insertbackground="#777777",
            font=("Helvetica Neue", 12),
            relief="flat", bd=0, highlightthickness=0,
            padx=0, pady=0,
        )
        self._response_text.pack(side="left", fill="both", expand=True)
        response_scroll = tk.Scrollbar(
            response_frame, orient="vertical",
            command=self._response_text.yview,
        )
        response_scroll.pack(side="right", fill="y")
        self._response_text.configure(yscrollcommand=response_scroll.set)
        self._response_text.configure(state="disabled")

        self._lbl_status = tk.Label(
            bottom, text=_STATE_LABEL[_IDLE],
            fg="#3A3A3A", bg="black",
            font=("Helvetica Neue", 10),
        )
        self._lbl_status.pack(pady=(0, 4))

        # ── Cuadro de diálogo de texto (oculto por defecto) ───────────────
        self._text_input_frame = tk.Frame(bottom, bg="black")
        self._text_dialog_canvas = tk.Canvas(
            self._text_input_frame, height=58, bg="black",
            highlightthickness=0,
        )
        self._text_dialog_canvas.pack(
            side="left", fill="x", expand=True, padx=(24, 8), pady=(0, 12)
        )
        self._text_dialog_content = tk.Frame(
            self._text_dialog_canvas, bg="#111214", height=52
        )
        self._text_dialog_window = self._text_dialog_canvas.create_window(
            3, 3, anchor="nw", window=self._text_dialog_content,
            width=1, height=52,
        )
        self._text_dialog_canvas.bind(
            "<Configure>", self._draw_text_dialog, add="+"
        )
        self._text_entry = tk.Entry(
            self._text_dialog_content,
            bg="#17181B", fg="#EBEBF5", insertbackground="#5B9BFF",
            font=("Helvetica Neue", 13), relief="flat", bd=0,
            highlightthickness=1, highlightbackground="#2A2D33",
            highlightcolor="#3A6EA5",
        )
        self._text_entry.pack(side="left", padx=(12, 8), ipady=6, pady=9,
                              expand=True, fill="x")
        self._text_entry.bind("<Return>", lambda _e: self._send_text_input())
        _sPW, _sPH = 34, 34
        self._send_pill = tk.Canvas(
            self._text_input_frame, width=_sPW, height=_sPH,
            bg="black", highlightthickness=0, cursor="hand2",
        )
        self._send_pill.pack(side="left", padx=(0, 8), pady=(12, 12))
        self._send_pill.bind("<Button-1>", lambda _e: self._send_text_input())
        self._draw_send_pill()

        # ── Pausa junto al botón enviar ───────────────────────────────────
        self._btns_row = self._text_dialog_content
        _PW, _PH = 36, 34
        self._pill_w, self._pill_h = _PW, _PH
        self._pill = tk.Canvas(
            self._text_input_frame, width=_PW, height=_PH,
            bg="black", highlightthickness=0, cursor="hand2",
        )
        self._pill.pack(side="left", padx=(0, 24), pady=(12, 12))
        self._pill.bind("<Button-1>", lambda _e: self._toggle_pause())
        self._draw_pill()

        # ── Botón de ajustes en esquina superior izquierda ────────────────
        _GPW, _GPH = 36, 36
        self._gear_pill = tk.Canvas(
            self, width=_GPW, height=_GPH,
            bg="black", highlightthickness=0, cursor="hand2",
        )
        self._gear_pill.place(x=10, y=10)
        self._gear_pill.bind("<Button-1>", lambda _e: self._open_settings())
        self._draw_gear_pill()

        # Interrumpir habla con clic en canvas principal o Escape
        self._canvas.bind("<Button-1>", self._canvas_click)
        self.bind("<Escape>", lambda _e: self._interrupt())

        # Drag-and-drop de imágenes (toda la ventana)
        if _HAS_DND:
            self.drop_target_register(_DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_image_drop)

        self._particles = [_Particle(i, _N_PARTICLES) for i in range(_N_PARTICLES)]

    # ── Animación ──────────────────────────────────────────────────────────────
    def _schedule_frame(self) -> None:
        self._draw_frame()
        self.after(1000 // _FPS, self._schedule_frame)

    def _draw_frame(self) -> None:
        c    = self._canvas
        t    = time.time() - self._t0
        col  = _STATE_COLOR[self._state]
        W = self._canvas.winfo_width()  or (_WIDGET_W if self._widget_mode else _W)
        H = self._canvas.winfo_height() or (_WIDGET_H if self._widget_mode else self._canvas_h)
        cx, cy = W // 2, H // 2

        c.delete("all")

        # Muelle: comprimir la esfera al pausar, expandir al reanudar
        target = 0.28 if self._state == _PAUSED else 1.0
        self._ring_factor += (target - self._ring_factor) * 0.07
        sphere_r = min(W, H) * _SPHERE_R * self._ring_factor

        # Velocidad de rotacion y tilt segun estado
        if self._state == _PAUSED:
            ry = t * 0.25;  rx = 0.30
        elif self._state == _LISTENING:
            ry = t * 1.4;   rx = 0.35 + 0.08 * math.sin(t * 2.1)
        elif self._state == _THINKING:
            ry = t * 0.8;   rx = 0.35
        elif self._state == _SPEAKING:
            ry = t * 1.1;   rx = 0.35 + 0.05 * math.sin(t * 3.2)
        else:
            ry = t * 0.45;  rx = 0.30

        sin_ry, cos_ry = math.sin(ry), math.cos(ry)
        sin_rx, cos_rx = math.sin(rx), math.cos(rx)

        # Proyectar particulas al plano 2D con perspectiva
        projected: list[tuple[float, float, float, object]] = []
        for p in self._particles:
            # Vibracion radial objetivo segun estado
            if self._state == _LISTENING:
                disp_target = 1.0 + 0.16 * math.sin(t * 14 + p.phase)
            elif self._state == _SPEAKING:
                disp_target = 1.0 + 0.20 * math.sin(t * 9 + p.x0 * 1.6 + p.y0 * 1.6)
            elif self._state == _THINKING:
                disp_target = 1.0 + 0.06 * math.sin(t * 4 + p.phase)
            elif self._state == _PAUSED:
                disp_target = 1.0 + 0.015 * math.sin(t * 0.7 + p.phase)
            else:
                disp_target = 1.0 + 0.04 * math.sin(t * 1.8 + p.phase)

            # Lerp: suaviza cambios de amplitud entre estados (coef 0.07 ≈ 140ms)
            p.disp_cur += (disp_target - p.disp_cur) * 0.07

            px, py, pz = p.x0 * p.disp_cur, p.y0 * p.disp_cur, p.z0 * p.disp_cur

            # Rotacion Y
            x1 =  px * cos_ry + pz * sin_ry
            z1 = -px * sin_ry + pz * cos_ry

            # Rotacion X (tilt)
            y2 =  py  * cos_rx - z1 * sin_rx
            z2 =  py  * sin_rx + z1 * cos_rx

            # Proyeccion perspectiva
            fov   = 3.2
            scale = sphere_r * fov / (fov + z2 * 0.4)
            sx    = cx + x1 * scale
            sy    = cy + y2 * scale
            depth = (z2 + 1.0) / 2.0  # 0 = atras, 1 = frente

            projected.append((sx, sy, depth, p))

        # Ordenar atras-primero (painter's algorithm)
        projected.sort(key=lambda item: item[2])

        # Conexiones entre particulas cercanas (topologia 3D)
        for i in range(len(projected)):
            sx1, sy1, d1, p1 = projected[i]
            for j in range(i + 1, len(projected)):
                sx2, sy2, d2, p2 = projected[j]
                dx = p1.x0 - p2.x0
                dy = p1.y0 - p2.y0
                dz = p1.z0 - p2.z0
                if dx*dx + dy*dy + dz*dz < _CONNECT_D3 ** 2:
                    avg_d = (d1 + d2) * 0.5
                    if self._state == _LISTENING:
                        la = avg_d * (0.35 + 0.50 * abs(math.sin(t * 10 + (i+j) * 0.25)))
                    elif self._state == _SPEAKING:
                        la = avg_d * (0.35 + 0.50 * abs(math.sin(t *  8 + (i+j) * 0.30)))
                    elif self._state == _PAUSED:
                        la = avg_d * 0.22
                    elif self._state == _THINKING:
                        la = avg_d * (0.40 + 0.25 * abs(math.sin(t * 3 + (i+j) * 0.15)))
                    else:
                        la = avg_d * 0.52
                    if la > 0.04:
                        c.create_line(sx1, sy1, sx2, sy2,
                                      fill=self._blend(col, la), width=1)

        # Nodos — size y alpha proporcionales a la profundidad
        for sx, sy, depth, p in projected:
            if self._state == _LISTENING:
                nr = (1.5 + 3.0 * depth) * (0.60 + 0.70 * abs(math.sin(t * 12 + p.phase)))
                na = 0.20 + 0.80 * depth * (0.55 + 0.45 * abs(math.sin(t *  9 + p.phase)))
            elif self._state == _SPEAKING:
                nr = (1.5 + 3.0 * depth) * (0.60 + 0.70 * abs(math.sin(t *  9 + p.phase)))
                na = 0.20 + 0.80 * depth * (0.50 + 0.50 * abs(math.sin(t * 11 + p.phase)))
            elif self._state == _THINKING:
                nr = (1.5 + 3.0 * depth) * (0.85 + 0.25 * math.sin(t * 5 + p.phase))
                na = 0.20 + 0.80 * depth * 0.80
            elif self._state == _PAUSED:
                nr = 1.2 + 1.6 * depth
                na = 0.10 + 0.28 * depth
            else:
                nr = 1.5 + 3.0 * depth
                na = 0.20 + 0.80 * depth * 0.82
            nr = max(0.5, nr)
            if na > 0.04:
                c.create_oval(sx - nr, sy - nr, sx + nr, sy + nr,
                              fill=self._blend(col, na), outline="")

        # Modo widget: solo partículas + botón de restaurar (sin overlays)
        if self._widget_mode:
            rx, ry = W - 14, 14
            rr     = 11
            rcol   = self._blend(col, 0.65)
            c.create_oval(rx - rr, ry - rr, rx + rr, ry + rr,
                          fill="#141414", outline=rcol, width=1)
            c.create_text(rx, ry, text="⊞", fill=rcol,
                          font=("Helvetica Neue", 11))
            self._widget_restore_rect = (rx - rr, ry - rr, rx + rr, ry + rr)
            return

        # ── Preview imagen arrastrada ─────────────────────────────────────────
        if self._pending_image_tk:
            iw = self._pending_image_tk.width()
            ih = self._pending_image_tk.height()
            pad, margin = 10, 16
            ix = W - margin - iw
            iy = margin
            ox, oy = ix - pad,      iy - pad        # esquina top-left del marco
            ex, ey = ix + iw + pad, iy + ih + pad   # esquina bottom-right del marco

            pulse = 0.72 + 0.28 * abs(math.sin(t * 1.3))

            # Sombra sólida (aisla el widget del canvas)
            c.create_rectangle(
                ox - 6, oy - 6, ex + 6, ey + 6,
                fill="#000000", outline="",
            )
            # Triple glow exterior difuso
            for gap, alpha in ((6, 0.06), (4, 0.13), (2, 0.22)):
                c.create_rectangle(
                    ox - gap, oy - gap, ex + gap, ey + gap,
                    outline=self._blend(col, alpha * pulse), width=1, fill="",
                )
            # Fondo oscuro del marco
            c.create_rectangle(ox, oy, ex, ey, fill="#080808", outline="")
            # Borde interior sutil
            c.create_rectangle(
                ox, oy, ex, ey,
                outline=self._blend(col, 0.40 * pulse), width=1, fill="",
            )
            # Esquinas HUD (L-shapes en los 4 vértices)
            clen = 13
            cc   = self._blend(col, pulse)
            for sx, sy, dx, dy in (
                (ox, oy, +1, +1), (ex, oy, -1, +1),
                (ox, ey, +1, -1), (ex, ey, -1, -1),
            ):
                c.create_line(sx, sy, sx + dx * clen, sy,  fill=cc, width=2)
                c.create_line(sx, sy, sx, sy + dy * clen,  fill=cc, width=2)

            # Imagen
            c.create_image(ix, iy, image=self._pending_image_tk, anchor="nw")

            # Botón × circular
            cr  = 10
            ccx = ex + cr - 1
            ccy = oy - cr + 1
            c.create_oval(
                ccx - cr, ccy - cr, ccx + cr, ccy + cr,
                fill="#111111", outline=self._blend(col, 0.65 * pulse), width=1,
            )
            c.create_text(
                ccx, ccy, text="×",
                fill=self._blend(col, 0.95),
                font=("Helvetica Neue", 12, "bold"),
            )
            self._img_close_rect = (ccx - cr, ccy - cr, ccx + cr, ccy + cr)
            self._img_drop_rect  = None

            # Etiqueta en píldora
            lx, ly = (ox + ex) // 2, ey + 17
            lw, lh = 58, 11
            c.create_rectangle(
                lx - lw, ly - lh, lx + lw, ly + lh,
                fill="#0C0C0C", outline=self._blend(col, 0.35 * pulse), width=1,
            )
            c.create_text(
                lx, ly, text="\u25cf  imagen activa",
                fill=self._blend(col, 0.65),
                font=("Helvetica Neue", 9),
            )
        else:
            self._img_close_rect = None
            # Zona de carga refinada (esquina superior derecha)
            bx1, by1, bx2, by2 = W - 52, 10, W - 10, 52
            bxc, byc = (bx1 + bx2) // 2, (by1 + by2) // 2
            pulse = 0.50 + 0.30 * abs(math.sin(t * 1.5))

            c.create_rectangle(bx1, by1, bx2, by2, fill="#070707", outline="")
            c.create_rectangle(
                bx1, by1, bx2, by2,
                outline=self._blend(col, 0.18 * pulse), width=1, fill="",
            )
            clen = 8
            cc   = self._blend(col, 0.55 * pulse)
            for sx, sy, dx, dy in (
                (bx1, by1, +1, +1), (bx2, by1, -1, +1),
                (bx1, by2, +1, -1), (bx2, by2, -1, -1),
            ):
                c.create_line(sx, sy, sx + dx * clen, sy, fill=cc, width=1)
                c.create_line(sx, sy, sx, sy + dy * clen, fill=cc, width=1)
            c.create_text(
                bxc, byc, text="+",
                fill=self._blend(col, 0.45 * pulse),
                font=("Helvetica Neue", 18),
            )
            self._img_drop_rect = (bx1, by1, bx2, by2)

        # ── Preview documento generado ────────────────────────────────────────
        if self._doc_preview_path:
            _DOC_SHOW, _DOC_FADE = 12.0, 4.0
            _age = time.time() - self._doc_preview_t0
            if _age >= _DOC_SHOW:
                self._doc_preview_path = None
                self._doc_preview_rect = None
            else:
                # Alpha: pleno durante los primeros segundos, luego fade-out
                if _age < _DOC_SHOW - _DOC_FADE:
                    _da = 1.0
                else:
                    _da = max(0.0, 1.0 - (_age - (_DOC_SHOW - _DOC_FADE)) / _DOC_FADE)
                # Desliz de entrada (primeros 0.45 s: baja desde abajo)
                _slide = int(18 * max(0.0, 1.0 - _age / 0.45))

                _dpath = self._doc_preview_path
                _fname = os.path.basename(_dpath)
                _ext   = os.path.splitext(_fname)[1].lower()
                _EXT_C = {
                    ".txt": "#32D74B", ".md": "#0A84FF", ".csv": "#FFD60A",
                    ".json": "#FF9F0A", ".pdf": "#FF453A", ".html": "#5E5CE6",
                }
                _tcol = _EXT_C.get(_ext, col)
                _dc   = lambda hx, a, _d=_da: self._blend(hx, a * _d)  # noqa: E731

                _cw, _ch = 268, 80
                _cx1, _cy1 = 12, H - _ch - 12 + _slide
                _cx2, _cy2 = _cx1 + _cw, _cy1 + _ch

                # Sombra sólida exterior
                c.create_rectangle(_cx1 - 4, _cy1 - 4, _cx2 + 4, _cy2 + 4,
                                   fill="#000000", outline="")
                # Triple glow
                for _g, _ga in ((5, 0.05), (3, 0.11), (1, 0.20)):
                    c.create_rectangle(_cx1 - _g, _cy1 - _g, _cx2 + _g, _cy2 + _g,
                                       outline=_dc(col, _ga), width=1, fill="")
                # Fondo oscuro
                c.create_rectangle(_cx1, _cy1, _cx2, _cy2,
                                   fill=self._blend("#090909", max(0.04, _da)), outline="")
                # Borde
                c.create_rectangle(_cx1, _cy1, _cx2, _cy2,
                                   outline=_dc(col, 0.38), width=1, fill="")
                # Esquinas HUD
                for _sx, _sy, _ddx, _ddy in (
                    (_cx1, _cy1, +1, +1), (_cx2, _cy1, -1, +1),
                    (_cx1, _cy2, +1, -1), (_cx2, _cy2, -1, -1),
                ):
                    c.create_line(_sx, _sy, _sx + _ddx * 10, _sy,       fill=_dc(col, 0.90), width=2)
                    c.create_line(_sx, _sy, _sx,              _sy + _ddy * 10, fill=_dc(col, 0.90), width=2)

                # Badge tipo archivo
                _bx1, _by1, _bx2, _by2 = _cx1 + 10, _cy1 + 13, _cx1 + 46, _cy1 + 29
                c.create_rectangle(_bx1, _by1, _bx2, _by2,
                                   fill=self._blend(_tcol, 0.15 * _da),
                                   outline=_dc(_tcol, 0.70), width=1)
                c.create_text((_bx1 + _bx2) // 2, (_by1 + _by2) // 2,
                              text=(_ext[1:].upper() if _ext else "DOC")[:4],
                              fill=_dc(_tcol, 0.92),
                              font=("Helvetica Neue", 8, "bold"))

                # Nombre de archivo
                _fn_s = _fname if len(_fname) <= 25 else _fname[:22] + "\u2026"
                c.create_text(_bx2 + 9, _by1 + 7, text=_fn_s, anchor="w",
                              fill=_dc("#EEEEEE", 0.92),
                              font=("Helvetica Neue", 11, "bold"))

                # Ruta corta
                _dir = os.path.dirname(_dpath)
                _hm  = os.path.expanduser("~")
                _dir = ("~" + _dir[len(_hm):]) if _dir.startswith(_hm) else _dir
                _dir_s = _dir if len(_dir) <= 30 else "\u2026" + _dir[-27:]
                c.create_text(_bx2 + 9, _by1 + 21, text=_dir_s, anchor="w",
                              fill=_dc("#888888", 0.80),
                              font=("Helvetica Neue", 8))

                # Barra de tiempo restante
                _pb_x, _pb_y, _pb_w = _cx1 + 10, _cy2 - 14, _cw - 20
                _pb_p = max(0.0, 1.0 - _age / _DOC_SHOW)
                c.create_rectangle(_pb_x, _pb_y, _pb_x + _pb_w, _pb_y + 2,
                                   fill=self._blend("#1A1A1A", max(0.04, _da)), outline="")
                if _pb_p > 0:
                    c.create_rectangle(_pb_x, _pb_y,
                                       _pb_x + int(_pb_w * _pb_p), _pb_y + 2,
                                       fill=_dc(col, 0.50), outline="")

                # Hint
                c.create_text(_cx1 + _cw // 2, _cy2 - 5,
                              text="\u00b7 clic para abrir \u00b7",
                              fill=_dc(col, 0.45),
                              font=("Helvetica Neue", 8))
                self._doc_preview_rect = (_cx1, _cy1, _cx2, _cy2)
        else:
            self._doc_preview_rect = None

        # ── Preview imagen capturada (webcam / pantalla) ──────────────────────
        if self._capture_preview_path:
            _CAP_SHOW, _CAP_FADE = 10.0, 3.0
            _age = time.time() - self._capture_preview_t0
            if _age >= _CAP_SHOW:
                self._capture_preview_path = None
                self._capture_preview_tk   = None
                self._capture_preview_rect = None
            else:
                if _age < _CAP_SHOW - _CAP_FADE:
                    _da = 1.0
                else:
                    _da = max(0.0, 1.0 - (_age - (_CAP_SHOW - _CAP_FADE)) / _CAP_FADE)
                _slide = int(18 * max(0.0, 1.0 - _age / 0.45))

                _dpath = self._capture_preview_path
                _fname = os.path.basename(_dpath)
                _dc    = lambda hx, a, _d=_da: self._blend(hx, a * _d)  # noqa: E731

                _cw, _ch = 210, 82
                _cx1 = W - _cw - 12
                _cy1 = H - _ch - 12 + _slide
                _cx2, _cy2 = _cx1 + _cw, _cy1 + _ch

                # Sombra sólida exterior
                c.create_rectangle(_cx1 - 4, _cy1 - 4, _cx2 + 4, _cy2 + 4,
                                    fill="#000000", outline="")
                # Triple glow
                for _g, _ga in ((5, 0.05), (3, 0.11), (1, 0.20)):
                    c.create_rectangle(_cx1 - _g, _cy1 - _g, _cx2 + _g, _cy2 + _g,
                                        outline=_dc(col, _ga), width=1, fill="")
                # Fondo oscuro
                c.create_rectangle(_cx1, _cy1, _cx2, _cy2,
                                    fill=self._blend("#090909", max(0.04, _da)), outline="")
                # Borde
                c.create_rectangle(_cx1, _cy1, _cx2, _cy2,
                                    outline=_dc(col, 0.38), width=1, fill="")
                # Esquinas HUD
                for _sx, _sy, _ddx, _ddy in (
                    (_cx1, _cy1, +1, +1), (_cx2, _cy1, -1, +1),
                    (_cx1, _cy2, +1, -1), (_cx2, _cy2, -1, -1),
                ):
                    c.create_line(_sx, _sy, _sx + _ddx * 10, _sy,
                                  fill=_dc(col, 0.90), width=2)
                    c.create_line(_sx, _sy, _sx, _sy + _ddy * 10,
                                  fill=_dc(col, 0.90), width=2)

                # Thumbnail de imagen (si está disponible)
                _text_x = _cx1 + 10
                if self._capture_preview_tk:
                    _iw = self._capture_preview_tk.width()
                    _ih = self._capture_preview_tk.height()
                    _ix = _cx1 + 8
                    _iy = _cy1 + (_ch - _ih) // 2
                    c.create_image(_ix, _iy, image=self._capture_preview_tk, anchor="nw")
                    _text_x = _ix + _iw + 8

                # Nombre de archivo
                _fn_s = _fname if len(_fname) <= 20 else _fname[:17] + "\u2026"
                c.create_text(_text_x, _cy1 + 16, text=_fn_s, anchor="w",
                              fill=_dc("#EEEEEE", 0.92),
                              font=("Helvetica Neue", 10, "bold"))

                # Subtítulo: tipo de captura
                _type_lbl = (
                    "Captura de pantalla" if "screenshot" in _fname
                    else "Imagen generada" if _fname.startswith("imagen_")
                    else "Foto webcam"
                )
                c.create_text(_text_x, _cy1 + 30, text=_type_lbl, anchor="w",
                              fill=_dc("#888888", 0.80),
                              font=("Helvetica Neue", 8))

                # Barra de tiempo restante
                _pb_x  = _cx1 + 8
                _pb_y  = _cy2 - 14
                _pb_w  = _cw - 16
                _pb_p  = max(0.0, 1.0 - _age / _CAP_SHOW)
                c.create_rectangle(_pb_x, _pb_y, _pb_x + _pb_w, _pb_y + 2,
                                    fill=self._blend("#1A1A1A", max(0.04, _da)), outline="")
                if _pb_p > 0:
                    c.create_rectangle(_pb_x, _pb_y,
                                        _pb_x + int(_pb_w * _pb_p), _pb_y + 2,
                                        fill=_dc(col, 0.50), outline="")

                # Hint
                c.create_text(_cx1 + _cw // 2, _cy2 - 4,
                              text="\u00b7 clic para abrir \u00b7",
                              fill=_dc(col, 0.45),
                              font=("Helvetica Neue", 8))
                self._capture_preview_rect = (_cx1, _cy1, _cx2, _cy2)
        else:
            self._capture_preview_rect = None

        # ── Preview video generado ────────────────────────────────────────────
        if self._video_preview_path:
            _VID_SHOW, _VID_FADE = 12.0, 3.0
            _age = time.time() - self._video_preview_t0
            if _age >= _VID_SHOW:
                self._video_preview_path = None
                self._video_preview_rect = None
            else:
                if _age < _VID_SHOW - _VID_FADE:
                    _da = 1.0
                else:
                    _da = max(0.0, 1.0 - (_age - (_VID_SHOW - _VID_FADE)) / _VID_FADE)
                _slide = int(18 * max(0.0, 1.0 - _age / 0.45))

                _dpath = self._video_preview_path
                _fname = os.path.basename(_dpath)
                _dc    = lambda hx, a, _d=_da: self._blend(hx, a * _d)  # noqa: E731

                _vw, _vh = 210, 82
                # Desplazada arriba respecto a la tarjeta de captura para no superponerse
                _vx1 = W - _vw - 12
                _vy1 = H - _vh - 12 + _slide - (_vh + 8 if self._capture_preview_path else 0)
                _vx2, _vy2 = _vx1 + _vw, _vy1 + _vh

                # Sombra sólida exterior
                c.create_rectangle(_vx1 - 4, _vy1 - 4, _vx2 + 4, _vy2 + 4,
                                    fill="#000000", outline="")
                # Triple glow (color azul-cian para diferenciar del preview de imagen)
                _vcol = "#00BFFF"
                for _g, _ga in ((5, 0.05), (3, 0.11), (1, 0.20)):
                    c.create_rectangle(_vx1 - _g, _vy1 - _g, _vx2 + _g, _vy2 + _g,
                                        outline=_dc(_vcol, _ga), width=1, fill="")
                # Fondo oscuro
                c.create_rectangle(_vx1, _vy1, _vx2, _vy2,
                                    fill=self._blend("#090909", max(0.04, _da)), outline="")
                # Borde
                c.create_rectangle(_vx1, _vy1, _vx2, _vy2,
                                    outline=_dc(_vcol, 0.38), width=1, fill="")
                # Esquinas HUD
                for _sx, _sy, _ddx, _ddy in (
                    (_vx1, _vy1, +1, +1), (_vx2, _vy1, -1, +1),
                    (_vx1, _vy2, +1, -1), (_vx2, _vy2, -1, -1),
                ):
                    c.create_line(_sx, _sy, _sx + _ddx * 10, _sy,
                                  fill=_dc(_vcol, 0.90), width=2)
                    c.create_line(_sx, _sy, _sx, _sy + _ddy * 10,
                                  fill=_dc(_vcol, 0.90), width=2)

                # Ícono de reproducción ▶
                _icon_x = _vx1 + 18
                _icon_y = _vy1 + _vh // 2
                c.create_text(_icon_x, _icon_y, text="\u25b6",
                              fill=_dc(_vcol, 0.85),
                              font=("Helvetica Neue", 22))

                # Nombre de archivo
                _fn_s = _fname if len(_fname) <= 20 else _fname[:17] + "\u2026"
                c.create_text(_vx1 + 44, _vy1 + 16, text=_fn_s, anchor="w",
                              fill=_dc("#EEEEEE", 0.92),
                              font=("Helvetica Neue", 10, "bold"))

                # Subtítulo
                c.create_text(_vx1 + 44, _vy1 + 30, text="Video generado",
                              anchor="w",
                              fill=_dc("#888888", 0.80),
                              font=("Helvetica Neue", 8))

                # Barra de tiempo restante
                _pb_x = _vx1 + 8
                _pb_y = _vy2 - 14
                _pb_w = _vw - 16
                _pb_p = max(0.0, 1.0 - _age / _VID_SHOW)
                c.create_rectangle(_pb_x, _pb_y, _pb_x + _pb_w, _pb_y + 2,
                                    fill=self._blend("#1A1A1A", max(0.04, _da)), outline="")
                if _pb_p > 0:
                    c.create_rectangle(_pb_x, _pb_y,
                                        _pb_x + int(_pb_w * _pb_p), _pb_y + 2,
                                        fill=_dc(_vcol, 0.50), outline="")

                # Hint
                c.create_text(_vx1 + _vw // 2, _vy2 - 4,
                              text="\u00b7 clic para abrir \u00b7",
                              fill=_dc(_vcol, 0.45),
                              font=("Helvetica Neue", 8))
                self._video_preview_rect = (_vx1, _vy1, _vx2, _vy2)
        else:
            self._video_preview_rect = None

    @staticmethod
    def _blend(hex_col: str, alpha: float) -> str:
        r = int(hex_col[1:3], 16)
        g = int(hex_col[3:5], 16)
        b = int(hex_col[5:7], 16)
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, int(r * alpha))),
            max(0, min(255, int(g * alpha))),
            max(0, min(255, int(b * alpha))),
        )

    # ── Imagen ─────────────────────────────────────────────────────────────────
    def _canvas_click(self, event) -> None:
        """Clic en canvas: cierra preview de imagen o interrumpe habla."""
        if self._widget_mode:
            # Registrar origen del arrastre y verificar botón restaurar
            self._drag_x = event.x_root
            self._drag_y = event.y_root
            if self._widget_restore_rect:
                x1, y1, x2, y2 = self._widget_restore_rect
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.after(0, self._exit_widget_mode)
            return
        if self._img_close_rect:
            x1, y1, x2, y2 = self._img_close_rect
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self._clear_image()
                return
        if self._img_drop_rect:
            x1, y1, x2, y2 = self._img_drop_rect
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.after(0, self._open_image_dialog)
                return
        if self._doc_preview_rect and self._doc_preview_path:
            x1, y1, x2, y2 = self._doc_preview_rect
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                _open_path(self._doc_preview_path)
                return
        if self._capture_preview_rect and self._capture_preview_path:
            x1, y1, x2, y2 = self._capture_preview_rect
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                _open_path(self._capture_preview_path)
                return
        if self._video_preview_rect and self._video_preview_path:
            x1, y1, x2, y2 = self._video_preview_rect
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                _open_path(self._video_preview_path)
                return
        self._interrupt()


    def _on_image_drop(self, event) -> None:
        """Maneja imagen arrastrada sobre la ventana."""
        raw = event.data.strip()
        if raw.startswith("{"):
            raw = raw[1:].split("}")[0]
        else:
            raw = raw.split()[0]
        self._load_image_preview(raw)

    def _load_image_preview(self, path: str) -> None:
        """Carga y redimensiona la imagen para mostrar en el canvas."""
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"):
            self._set_status("Formato no soportado (PNG, JPG, GIF…)")
            return
        try:
            from PIL import Image, ImageTk as _ITk
            img = Image.open(path)
            img.thumbnail((130, 130), Image.LANCZOS)
            self._pending_image_tk   = _ITk.PhotoImage(img)
            self._pending_image_path = path
            self._image_needs_cmd    = True
            self._set_status("Imagen lista · di qué hacer con ella")
            if self._state not in (_SPEAKING, _THINKING):
                self._transition(_LISTENING)
        except ImportError:
            self._set_status("Instala Pillow: pip install Pillow")
        except Exception as exc:
            self._set_status(f"Error al cargar imagen: {exc}")

    def _open_image_dialog(self) -> None:
        """Abre diálogo de archivo como alternativa al drag-and-drop."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Seleccionar imagen",
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff"),
                ("Todos", "*.*"),
            ],
        )
        if path:
            self._load_image_preview(path)

    def _clear_image(self) -> None:
        """Descarta la imagen activa y limpia el preview."""
        self._pending_image_path = None
        self._pending_image_tk   = None
        self._image_needs_cmd    = False
        self._img_close_rect     = None
    def _show_doc_preview(self, path: str) -> None:
        """Activa la tarjeta de preview del documento generado."""
        self._doc_preview_path = path
        self._doc_preview_t0   = time.time()
        self._doc_preview_rect = None

    def _show_capture_preview(self, path: str) -> None:
        """Activa la tarjeta de preview de imagen capturada (webcam / pantalla)."""
        try:
            from PIL import Image as _PILImg, ImageTk as _ITk  # type: ignore
            _img = _PILImg.open(path)
            _img.thumbnail((72, 56), _PILImg.LANCZOS)
            self._capture_preview_tk = _ITk.PhotoImage(_img)
        except Exception:
            self._capture_preview_tk = None
        self._capture_preview_path = path
        self._capture_preview_t0   = time.time()
        self._capture_preview_rect = None

    def _show_video_preview(self, path: str) -> None:
        """Activa la tarjeta de preview de video generado."""
        self._video_preview_path = path
        self._video_preview_t0   = time.time()
        self._video_preview_rect = None
    # ── Voz ────────────────────────────────────────────────────────────────────
    def _init_voice(self) -> None:
        def _setup() -> None:
            try:
                import speech_recognition as sr
                self._recognizer = sr.Recognizer()
                self._recognizer.pause_threshold       = 1.5
                self._recognizer.non_speaking_duration = 1.2
                self._mic = sr.Microphone()
                with self._mic as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
                # Arrancar el loop continuo
                threading.Thread(target=self._continuous_loop, daemon=True).start()
            except Exception as e:
                self.after(0, lambda: self._set_status(f"Voz no disponible: {e}"))
        threading.Thread(target=_setup, daemon=True).start()

    def _continuous_loop(self) -> None:
        """Loop de escucha con wake word y modo conversación persistente."""
        import re as _re
        import speech_recognition as sr

        _WAKE = _re.compile(
            r"^(?:hey\s+|oye\s+|ok\s+)?jarvis[,\s:!?.]*(.*)$", _re.IGNORECASE
        )
        # Frases para terminar la conversación
        _CONV_END = _re.compile(
            r"^\s*(?:ap[aá]gate|termina(?:r)?|cierra|para|fin(?:aliza(?:r)?)?|"
            r"hasta\s+luego|adi[oó]s|chau|bye|no\s+m[aá]s)\s*$",
            _re.IGNORECASE,
        )
        _OPEN_DOC = _re.compile(
            r"^(?:abre(?:lo|la)?|open|visualiza(?:r)?|muestra(?:me)?)"
            r"(?:\s+(?:el|la|ese|esa|este|esta))?\s*(?:archivo|documento|nota|fichero)?\s*$",
            _re.IGNORECASE,
        )
        # Detectar solicitudes de generación de documento para inyección de instrucción
        _DOC_CMD = _re.compile(
            r"\b(?:informe|reporte|resumen|carta|documento|an[aá]lisis|propuesta|plan|memo|"
            r"memorando|listado|elabora|redacta|genera(?:r)?|crear?)\b",
            _re.IGNORECASE,
        )
        _LABEL_CONV = "Conversación activa · di «apágate» para terminar"

        in_conversation = False  # True = no se necesita wake word entre frases

        # Esperar init
        while self._state != _IDLE and self._voice_active:
            time.sleep(0.05)

        while self._voice_active:
            # Pausa: esperar y salir del modo conversación
            if self._paused:
                while self._paused and self._voice_active:
                    time.sleep(0.05)
                in_conversation = False
                if not self._voice_active:
                    break

            # Mantener LISTENING
            if self._state not in (_SPEAKING, _THINKING, _PAUSED, _LISTENING):
                self._transition(_LISTENING)
                if in_conversation:
                    self._set_status(_LABEL_CONV)

            # Escuchar
            try:
                with self._mic as source:
                    audio = self._recognizer.listen(
                        source, timeout=3, phrase_time_limit=25
                    )
            except sr.WaitTimeoutError:
                continue
            except Exception as exc:
                if self._voice_active:
                    self._set_status(f"Error mic: {exc}")
                time.sleep(0.5)
                continue

            # Descartar audio mientras Jarvis habla
            if self._state == _SPEAKING:
                continue

            # Transcribir
            self._transition(_THINKING)
            try:
                text = self._recognizer.recognize_google(audio, language="es-ES")
            except sr.UnknownValueError:
                self._transition(_LISTENING)
                if in_conversation:
                    self._set_status(_LABEL_CONV)
                continue
            except Exception as exc:
                self._show_response(f"Error de red: {exc}")
                self._transition(_LISTENING)
                if in_conversation:
                    self._set_status(_LABEL_CONV)
                continue

            text = text.strip()
            if not text:
                self._transition(_LISTENING)
                if in_conversation:
                    self._set_status(_LABEL_CONV)
                continue

            # ── Determinar comando ─────────────────────────────────────────
            command: str | None = None

            if self._image_needs_cmd:
                # Imagen arrastrada: cualquier frase es el comando
                command = text
                self._image_needs_cmd = False

            elif in_conversation:
                # Verificar fin de conversación
                if _CONV_END.match(text):
                    in_conversation = False
                    self._show_response("Jarvis: Hasta luego.")
                    self._transition(_SPEAKING)
                    self._speak("Hasta luego.")
                    if self._state == _SPEAKING:
                        self._transition(_LISTENING)
                    continue
                command = text

            else:
                m = _WAKE.match(text)
                if m:
                    cmd = m.group(1).strip()
                    in_conversation = True   # activar modo conversación
                    self._set_status(_LABEL_CONV)
                    if cmd:
                        command = cmd
                    else:
                        # Solo "jarvis" → activado, esperar siguiente frase
                        self._set_status(_LABEL_CONV)
                        self._state = _LISTENING
                        continue
                # Sin wake word → ignorar silenciosamente

            if command is None:
                self._transition(_LISTENING)
                if in_conversation:
                    self._set_status(_LABEL_CONV)
                continue
            # ── Abrir documento con voz ───────────────────────────────────
            if self._doc_preview_path and _OPEN_DOC.match(command):
                _doc_p = self._doc_preview_path
                _open_path(_doc_p)
                _doc_fn = os.path.basename(_doc_p)
                self._show_response(f"Jarvis: Abriendo {_doc_fn}")
                self._transition(_SPEAKING)
                self._speak(f"Aquí tienes: {_doc_fn}")
                if self._state == _SPEAKING:
                    self._transition(_LISTENING)
                if in_conversation:
                    self._set_status(_LABEL_CONV)
                continue
            # ── Enviar a la IA ─────────────────────────────────────────────
            self._show_response(f"Tú: {command}")
            img_path = self._pending_image_path
            # Inyectar recordatorio de herramienta si se detecta solicitud de documento
            _ai_cmd = command
            if not img_path and _DOC_CMD.search(command):
                _ai_cmd = (
                    "[OBLIGATORIO: usa la herramienta guardar_documento para guardar el "
                    "contenido en un archivo. NO incluyas el documento en el texto de "
                    "respuesta. Solo confirma el nombre del archivo guardado.]\n" + command
                )
            try:
                if img_path and self._agent:
                    reply = self._agent.send_message_with_image(_ai_cmd, img_path)
                elif self._agent:
                    reply = self._agent.send_message(_ai_cmd)
                else:
                    reply = "[Modo demo]"
            except Exception as exc:
                reply = f"[Error: {exc}]"

            # ── Notificar documento guardado ─────────────────────────────────
            if self._agent and self._agent.last_saved_path:
                _saved = self._agent.last_saved_path
                self._agent.last_saved_path = None
                self.after(0, lambda p=_saved: self._show_doc_preview(p))

            # ── Notificar imagen capturada ────────────────────────────────────
            if self._agent and self._agent.last_captured_image_path:
                _cpath = self._agent.last_captured_image_path
                self._agent.last_captured_image_path = None
                self.after(0, lambda p=_cpath: self._show_capture_preview(p))

            # ── Notificar video generado ──────────────────────────────────────
            if self._agent and self._agent.last_generated_video_path:
                _vpath = self._agent.last_generated_video_path
                self._agent.last_generated_video_path = None
                self.after(0, lambda p=_vpath: self._show_video_preview(p))

            self._show_response(f"Jarvis: {reply}")
            self._transition(_SPEAKING)
            self._speak(reply)

            if self._state == _SPEAKING:
                self._transition(_LISTENING)
            if in_conversation:
                self._set_status(_LABEL_CONV)

    def _interrupt(self) -> None:
        """Interrumpe el habla de Jarvis y vuelve a escuchar de inmediato."""
        if self._state != _SPEAKING:
            return
        if self._say_proc and self._say_proc.poll() is None:
            self._say_proc.terminate()
            try:
                self._say_proc.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                self._say_proc.kill()
        self._say_proc = None
        # Limpiar MP3 temporal si existe
        if self._tts_tmpfile:
            import os
            try:
                os.unlink(self._tts_tmpfile)
            except Exception:
                pass
            self._tts_tmpfile = None
        self._transition(_LISTENING)

    def _speak(self, text: str) -> None:
        chunk = text[:400]
        # edge-tts usa las voces configuradas localmente; pyttsx3 es el fallback offline.
        if _SO == "darwin":
            self._speak_neural(chunk)
        else:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", 170)
                engine.say(chunk)
                engine.runAndWait()
                engine.stop()
            except Exception:
                pass

    def _play_tmpfile(self) -> None:
        """Reproduce self._tts_tmpfile con el reproductor disponible."""
        if not self._tts_tmpfile or not os.path.exists(self._tts_tmpfile):
            return
        # afplay en macOS; ffplay/aplay como fallback en Linux
        if _SO == "darwin":
            player = ["afplay", self._tts_tmpfile]
        else:
            # Intentar ffplay o aplay (sin ventana de video)
            import shutil
            if shutil.which("ffplay"):
                player = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                          self._tts_tmpfile]
            elif shutil.which("aplay"):
                player = ["aplay", self._tts_tmpfile]
            else:
                player = None
        if player:
            self._say_proc = subprocess.Popen(player)
            self._say_proc.wait()
            self._say_proc = None
        try:
            os.unlink(self._tts_tmpfile)
        except Exception:
            pass
        self._tts_tmpfile = None

    def _speak_neural(self, text: str) -> None:
        """TTS con edge-tts (voz neural Microsoft) + afplay. Fallback a say."""
        import asyncio
        import tempfile
        try:
            import truststore
            truststore.inject_into_ssl()
            import edge_tts
        except ImportError:
            # Fallback a voz del sistema si no están instalados
            self._say_proc = subprocess.Popen(
                ["say", "-v", "Reed (Español (México))", "-r", "175", text]
            )
            self._say_proc.wait()
            self._say_proc = None
            return

        # Generar MP3 con la voz neural
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                self._tts_tmpfile = f.name

            mood = getattr(self._agent, "current_mood", "neutral")
            prosody = {
                "alegre": ("+8%", "+10Hz"),
                "triste": ("-8%", "-10Hz"),
                "frustrado": ("+3%", "+0Hz"),
                "urgente": ("+14%", "+15Hz"),
                "cansado": ("-14%", "-15Hz"),
                "neutral": ("+0%", "+0Hz"),
            }.get(mood, ("+0%", "+0Hz"))

            async def _gen():
                comm = edge_tts.Communicate(
                    text,
                    self._selected_voice,
                    rate=prosody[0],
                    pitch=prosody[1],
                )
                await comm.save(self._tts_tmpfile)

            asyncio.run(_gen())
        except Exception:
            self._tts_tmpfile = None
            return

        self._play_tmpfile()

    def _toggle_pause(self) -> None:
        """Pausa o reanuda la conversación."""
        if self._paused:
            self._paused = False
            self._transition(_IDLE)  # el muelle en _draw_frame expande el anillo
        else:
            self._paused = True
            self._pause_t0 = time.time()
            # Cortar habla activa si la hay
            if self._say_proc and self._say_proc.poll() is None:
                self._say_proc.terminate()
                try:
                    self._say_proc.wait(timeout=0.3)
                except subprocess.TimeoutExpired:
                    self._say_proc.kill()
            self._say_proc = None
            if self._tts_tmpfile:
                import os
                try:
                    os.unlink(self._tts_tmpfile)
                except Exception:
                    pass
                self._tts_tmpfile = None
            self._transition(_PAUSED)
        self.after(0, self._draw_pill)

    def _draw_pill(self) -> None:
        """Redibuja el botón pausa en forma de píldora."""
        c = self._pill
        c.delete("all")
        W, H = self._pill_w, self._pill_h
        R    = H // 2
        paused = self._paused
        bg   = "#1C1C1E"
        bdr  = "#FF3B30" if paused else "#48484A"
        icon = "▶" if paused else "⏸"
        fg   = "#FF453A" if paused else "#EBEBF5"

        # Píldora: dos óvalos en los extremos + rectángulo central
        c.create_oval(0, 0, H, H, fill=bg, outline=bdr)          # tapa izq
        c.create_oval(W - H, 0, W - 1, H, fill=bg, outline=bdr)  # tapa der
        c.create_rectangle(R, 1, W - R, H - 1, fill=bg, outline="")  # cubre interior
        c.create_line(R, 0,   W - R, 0,   fill=bdr, width=1)     # borde superior
        c.create_line(R, H-1, W - R, H-1, fill=bdr, width=1)     # borde inferior
        c.create_text(W // 2, H // 2, text=icon, fill=fg,
                      font=("Helvetica Neue", 14, "bold"))

    def _draw_gear_pill(self) -> None:
        """Redibuja el botón de ajustes (ícono ⚙) como círculo."""
        c = self._gear_pill
        c.delete("all")
        W, H = 36, 36
        bg  = "#1C1C1E"
        bdr = "#48484A"
        c.create_oval(1, 1, W - 1, H - 1, fill=bg, outline=bdr)
        c.create_text(W // 2, H // 2, text="⚙", fill="#EBEBF5",
                      font=("Helvetica Neue", 16))

    def _draw_send_pill(self) -> None:
        """Redibuja el botón enviar del cuadro de texto."""
        c = self._send_pill
        c.delete("all")
        W, H = 34, 34
        R    = H // 2
        bg   = "#1A6FFF"
        bdr  = "#2A7FFF"
        c.create_oval(0, 0, H, H, fill=bg, outline=bdr)
        c.create_oval(W - H, 0, W - 1, H, fill=bg, outline=bdr)
        c.create_rectangle(R, 1, W - R, H - 1, fill=bg, outline="")
        c.create_line(R, 0, W - R, 0, fill=bdr, width=1)
        c.create_line(R, H - 1, W - R, H - 1, fill=bdr, width=1)
        # Paper-plane icon coordinates are relative to the 34x34 canvas.
        plane_points = (10, 17, 24, 10, 19, 24, 16, 18)
        c.create_polygon(
            *plane_points,
            fill="white", outline="",
        )
        plane_fold = (10, 17, 16, 18)
        c.create_line(*plane_fold, fill=bg, width=1)

    def _draw_text_dialog(self, event=None) -> None:
        """Dibuja el contenedor redondeado del cuadro de texto."""
        c = self._text_dialog_canvas
        width = c.winfo_width()
        if width < 10:
            return

        c.delete("dialog_background")
        x1, y1, x2, y2 = 1, 1, width - 2, 56
        radius = 14

        def _rounded_box(
            left: int, top: int, right: int, bottom: int,
            fill: str, tag: str,
        ) -> None:
            r = min(radius, (right - left) // 2, (bottom - top) // 2)
            c.create_rectangle(
                left + r, top, right - r, bottom,
                fill=fill, outline="", tags=tag,
            )
            c.create_rectangle(
                left, top + r, right, bottom - r,
                fill=fill, outline="", tags=tag,
            )
            for ax1, ay1, ax2, ay2, start in (
                (left, top, left + 2 * r, top + 2 * r, 90),
                (right - 2 * r, top, right, top + 2 * r, 0),
                (left, bottom - 2 * r, left + 2 * r, bottom, 180),
                (right - 2 * r, bottom - 2 * r, right, bottom, 270),
            ):
                c.create_arc(
                    ax1, ay1, ax2, ay2, start=start, extent=90,
                    fill=fill, outline="", tags=tag,
                )

        _rounded_box(x1, y1, x2, y2, "#2A2D33", "dialog_background")
        _rounded_box(x1 + 1, y1 + 1, x2 - 1, y2 - 1,
                     "#111214", "dialog_background")
        c.tag_lower("dialog_background")
        c.itemconfigure(
            self._text_dialog_window,
            width=max(1, width - 6),
            height=52,
        )

    # ── Modo texto ──────────────────────────────────────────────────────────
    def _set_text_mode(self, enabled: bool) -> None:
        """Muestra u oculta el cuadro de diálogo de texto."""
        self._text_mode = enabled
        if enabled:
            self._text_input_frame.pack(fill="x", pady=(4, 12))
            if not self._widget_mode:
                x, y = self.winfo_x(), self.winfo_y()
                self.geometry(f"{_W}x{_H + 76}+{x}+{y}")
            self._text_entry.focus_set()
        else:
            self._text_input_frame.pack_forget()
            if not self._widget_mode:
                x, y = self.winfo_x(), self.winfo_y()
                self.geometry(f"{_W}x{_H}+{x}+{y}")

    def _send_text_input(self) -> None:
        """Envía el texto escrito por el usuario al agente."""
        text = self._text_entry.get().strip()
        if not text:
            return
        self._text_entry.delete(0, "end")
        self._show_response(f"Tú: {text}")
        threading.Thread(
            target=self._process_text_command, args=(text,), daemon=True
        ).start()

    def _process_text_command(self, command: str) -> None:
        """Procesa un comando enviado por texto (hilo secundario)."""
        self._transition(_THINKING)
        img_path = self._pending_image_path
        if img_path:
            self._clear_image()
        try:
            if self._agent:
                if img_path:
                    reply = self._agent.send_message_with_image(command, img_path)
                else:
                    reply = self._agent.send_message(command)
            else:
                reply = "[Modo demo]"
        except Exception as exc:
            reply = f"[Error: {exc}]"
        if self._agent and self._agent.last_saved_path:
            _saved = self._agent.last_saved_path
            self._agent.last_saved_path = None
            self.after(0, lambda p=_saved: self._show_doc_preview(p))
        if self._agent and self._agent.last_captured_image_path:
            _cpath = self._agent.last_captured_image_path
            self._agent.last_captured_image_path = None
            self.after(0, lambda p=_cpath: self._show_capture_preview(p))
        if self._agent and self._agent.last_generated_video_path:
            _vpath = self._agent.last_generated_video_path
            self._agent.last_generated_video_path = None
            self.after(0, lambda p=_vpath: self._show_video_preview(p))
        self._show_response(f"Jarvis: {reply}")
        self._transition(_SPEAKING)
        self._speak(reply)
        if self._state == _SPEAKING:
            self._transition(_IDLE)

    # ── Panel de ajustes ────────────────────────────────────────────────────
    def _open_settings(self) -> None:
        """Abre el panel flotante de ajustes."""
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return

        _SW, _SH = 400, 360
        win = tk.Toplevel(self)
        win.title("Ajustes · Jarvis")
        win.configure(bg="#0C0C0C")
        win.resizable(False, False)
        win.transient(self)
        wx = self.winfo_x() + (_W - _SW) // 2
        wy = self.winfo_y() + (_H - _SH) // 2
        win.geometry(f"{_SW}x{_SH}+{wx}+{wy}")
        self._settings_win = win

        col = _STATE_COLOR[self._state]

        # Marco HUD decorativo
        frame_c = tk.Canvas(win, width=_SW, height=_SH,
                            bg="#0C0C0C", highlightthickness=0)
        frame_c.place(x=0, y=0)
        pad = 6
        for g, a in ((4, 0.06), (2, 0.14), (1, 0.30)):
            frame_c.create_rectangle(
                pad - g, pad - g, _SW - pad + g, _SH - pad + g,
                outline=self._blend(col, a), width=1, fill="",
            )
        clen = 16
        for sx, sy, dx, dy in (
            (pad, pad, +1, +1), (_SW - pad, pad, -1, +1),
            (pad, _SH - pad, +1, -1), (_SW - pad, _SH - pad, -1, -1),
        ):
            frame_c.create_line(sx, sy, sx + dx * clen, sy,
                                fill=self._blend(col, 0.90), width=2)
            frame_c.create_line(sx, sy, sx, sy + dy * clen,
                                fill=self._blend(col, 0.90), width=2)

        # ── Título ──────────────────────────────────────────────────────────
        tk.Label(win, text="⚙  AJUSTES", fg=self._blend(col, 0.90),
                 bg="#0C0C0C", font=("Helvetica Neue", 14, "bold")
                 ).place(x=22, y=18)

        def _sep(y: int) -> None:
            sc = tk.Canvas(win, width=_SW - 44, height=1,
                           bg="#0C0C0C", highlightthickness=0)
            sc.place(x=22, y=y)
            sc.create_line(0, 0, _SW - 44, 0, fill=self._blend(col, 0.22))
        _sep(50)

        # ── Voz del agente ───────────────────────────────────────────────
        _active_voices = _LOCAL_VOICES
        voice_label = "VOZ LOCAL DEL AGENTE"
        tk.Label(win, text=voice_label, fg=self._blend(col, 0.55),
                 bg="#0C0C0C", font=("Helvetica Neue", 9, "bold")
                 ).place(x=22, y=62)

        voice_names  = [n for n, _ in _active_voices]
        voice_values = [v for _, v in _active_voices]
        cur_idx = next(
            (i for i, v in enumerate(voice_values) if v == self._selected_voice), 0
        )
        voice_var = tk.StringVar(win, value=voice_names[cur_idx])
        vm = tk.OptionMenu(win, voice_var, *voice_names)
        vm.configure(
            bg="#1C1C1E", fg="#EBEBF5",
            activebackground="#2C2C2E", activeforeground="#EBEBF5",
            font=("Helvetica Neue", 12), relief="flat", bd=0,
            highlightthickness=1, highlightbackground=self._blend(col, 0.35),
            width=30,
        )
        vm["menu"].configure(
            bg="#1C1C1E", fg="#EBEBF5",
            activebackground="#2C2C2E", activeforeground="#EBEBF5",
            font=("Helvetica Neue", 12),
        )
        vm.place(x=20, y=80)
        _sep(152)

        # ── Comunicación ────────────────────────────────────────────────
        tk.Label(win, text="COMUNICACIÓN", fg=self._blend(col, 0.55),
                 bg="#0C0C0C", font=("Helvetica Neue", 9, "bold")
                 ).place(x=22, y=164)

        text_var = tk.BooleanVar(win, value=self._text_mode)
        chk_bg   = "#1C1C1E"
        chk_frame = tk.Frame(win, bg=chk_bg)
        chk_frame.place(x=20, y=182, width=_SW - 40, height=40)
        tk.Checkbutton(
            chk_frame,
            text="  Habilitar cuadro de diálogo de texto",
            variable=text_var,
            bg=chk_bg, fg="#EBEBF5",
            activebackground="#2C2C2E", activeforeground="#EBEBF5",
            selectcolor="#0C0C0C",
            font=("Helvetica Neue", 12), relief="flat", bd=0,
        ).pack(pady=6, padx=8, anchor="w")
        _sep(240)

        # ── Vista ───────────────────────────────────────────────────────
        tk.Label(win, text="VISTA", fg=self._blend(col, 0.55),
                 bg="#0C0C0C", font=("Helvetica Neue", 9, "bold")
                 ).place(x=22, y=252)

        _BW, _BH = _SW - 40, 38
        widget_btn = tk.Canvas(win, width=_BW, height=_BH,
                               bg="#0C0C0C", highlightthickness=0,
                               cursor="hand2")
        widget_btn.place(x=20, y=270)

        def _draw_wb() -> None:
            widget_btn.delete("all")
            R  = _BH // 2
            bg = "#1C1C1E"
            bd = self._blend(col, 0.50)
            widget_btn.create_oval(0, 0, _BH, _BH, fill=bg, outline=bd)
            widget_btn.create_oval(_BW - _BH, 0, _BW - 1, _BH, fill=bg, outline=bd)
            widget_btn.create_rectangle(R, 1, _BW - R, _BH - 1, fill=bg, outline="")
            widget_btn.create_line(R, 0, _BW - R, 0, fill=bd, width=1)
            widget_btn.create_line(R, _BH - 1, _BW - R, _BH - 1, fill=bd, width=1)
            lbl = ("✦  Salir del modo widget"
                   if self._widget_mode else "⊟  Minimizar a widget")
            widget_btn.create_text(_BW // 2, _BH // 2, text=lbl,
                                   fill=self._blend(col, 0.90),
                                   font=("Helvetica Neue", 12))
        _draw_wb()

        def _on_widget_btn(_e=None) -> None:
            win.destroy()
            self._settings_win = None
            if self._widget_mode:
                self._exit_widget_mode()
            else:
                self._enter_widget_mode()

        widget_btn.bind("<Button-1>", _on_widget_btn)

        # ── Botón APLICAR ───────────────────────────────────────────────
        _ABW, _ABH = 110, 34
        apply_btn = tk.Canvas(win, width=_ABW, height=_ABH,
                              bg="#0C0C0C", highlightthickness=0,
                              cursor="hand2")
        apply_btn.place(x=_SW - _ABW - 18, y=_SH - _ABH - 16)
        R  = _ABH // 2
        bg = "#1C1C1E"
        bd = self._blend(col, 0.55)
        apply_btn.create_oval(0, 0, _ABH, _ABH, fill=bg, outline=bd)
        apply_btn.create_oval(_ABW - _ABH, 0, _ABW - 1, _ABH, fill=bg, outline=bd)
        apply_btn.create_rectangle(R, 1, _ABW - R, _ABH - 1, fill=bg, outline="")
        apply_btn.create_line(R, 0, _ABW - R, 0, fill=bd, width=1)
        apply_btn.create_line(R, _ABH - 1, _ABW - R, _ABH - 1, fill=bd, width=1)
        apply_btn.create_text(_ABW // 2, _ABH // 2, text="APLICAR",
                              fill=self._blend(col, 0.90),
                              font=("Helvetica Neue", 11, "bold"))

        def _apply(_e=None) -> None:
            # Aplicar voz seleccionada (buscar en la lista activa)
            sel = voice_var.get()
            for n, v in _active_voices:
                if n == sel:
                    self._selected_voice = v
                    break
            # Aplicar modo texto
            new_tm = text_var.get()
            if new_tm != self._text_mode:
                self._set_text_mode(new_tm)
            win.destroy()
            self._settings_win = None

        apply_btn.bind("<Button-1>", _apply)
        win.bind("<Return>", _apply)

    # ── Modo widget ──────────────────────────────────────────────────────────
    def _enter_widget_mode(self) -> None:
        """Minimiza la ventana a un widget compacto mostrando solo partículas."""
        if self._widget_mode:
            return
        self._widget_mode    = True
        self._restore_geometry = self.geometry()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        wx = sw - _WIDGET_W - 24
        wy = sh - _WIDGET_H - 60
        self._bottom_frame.pack_forget()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{_WIDGET_W}x{_WIDGET_H}+{wx}+{wy}")
        self._canvas.bind("<B1-Motion>", self._widget_drag_move)
        self.lift()
        self.focus_force()

    def _exit_widget_mode(self) -> None:
        """Restaura la ventana completa desde el modo widget."""
        if not self._widget_mode:
            return
        self._widget_mode = False
        self._canvas.unbind("<B1-Motion>")
        self._widget_restore_rect = None
        self.overrideredirect(False)
        self.attributes("-topmost", False)
        self._bottom_frame.pack(side="bottom", fill="x")
        # Restaurar geometría y ajustar alto si el modo texto está activo
        geo = self._restore_geometry
        wh, *pos_parts = geo.replace('-', '+-').split('+')
        pos = '+' + '+'.join(p.replace('+-', '-') for p in pos_parts if p) if pos_parts else ''
        w_str, h_str = wh.split('x')
        h = _H + 50 if self._text_mode else _H
        self.geometry(f"{w_str}x{h}{pos}")
        self.lift()
        self.focus_force()

    def _widget_drag_move(self, event) -> None:
        """Arrastra el widget por la pantalla (coordenadas absolutas de pantalla)."""
        dx = event.x_root - self._drag_x
        dy = event.y_root - self._drag_y
        self._drag_x = event.x_root   # actualizar para el siguiente evento
        self._drag_y = event.y_root
        x  = self.winfo_x() + dx
        y  = self.winfo_y() + dy
        self.geometry(f"+{x}+{y}")

    # ── Helpers thread-safe ──────────────────────────────────────────────
    def _transition(self, state: str) -> None:
        self._state = state
        label = _STATE_LABEL[state]
        self.after(0, lambda: self._lbl_status.configure(text=label))

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._lbl_status.configure(text=text))

    def _show_response(self, text: str) -> None:
        def _update() -> None:
            self._response_text.configure(state="normal")
            self._response_text.delete("1.0", "end")
            self._response_text.insert("1.0", text)
            self._response_text.configure(state="disabled")
            self._response_text.see("1.0")

        self.after(0, _update)

    # ── Mostrar / ocultar ────────────────────────────────────────────────
    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self) -> None:
        self.withdraw()

    def toggle(self) -> None:
        if self.winfo_viewable():
            self.hide()
        else:
            self.show()
