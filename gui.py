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
import tkinter as tk
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
_N_PARTICLES  = 30    # puntos distribuidos en la esfera (Fibonacci)
_SPHERE_R     = 0.26  # radio como fraccion de min(W,H)
_CONNECT_D3   = 0.80  # umbral de conexion en distancia de cuerda 3D
_FPS          = 30


class _Particle:
    """Punto en la superficie de una esfera unitaria — distribucion Fibonacci."""
    __slots__ = ("x0", "y0", "z0", "phase")

    def __init__(self, index: int, total: int) -> None:
        golden  = (1.0 + math.sqrt(5.0)) / 2.0
        theta   = math.acos(1.0 - 2.0 * (index + 0.5) / total)
        phi     = 2.0 * math.pi * index / golden
        self.x0 = math.sin(theta) * math.cos(phi)
        self.y0 = math.sin(theta) * math.sin(phi)
        self.z0 = math.cos(theta)
        self.phase = random.uniform(0.0, 2.0 * math.pi)

class JarvisWindow(tk.Tk):
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

        bottom = tk.Frame(self, bg="black", height=_BOTTOM_H)
        bottom.pack(side="bottom", fill="x")
        bottom.pack_propagate(False)

        self._lbl_response = tk.Label(
            bottom, text="",
            fg="#777777", bg="black",
            font=("Helvetica Neue", 12),
            wraplength=_W - 60, justify="center",
        )
        self._lbl_response.pack(pady=(10, 2))

        self._lbl_status = tk.Label(
            bottom, text=_STATE_LABEL[_IDLE],
            fg="#3A3A3A", bg="black",
            font=("Helvetica Neue", 10),
        )
        self._lbl_status.pack(pady=(0, 4))

        # ── Botón pausa (pill canvas) ──────────────────────────────────────
        _PW, _PH = 170, 36
        self._pill_w, self._pill_h = _PW, _PH
        self._pill = tk.Canvas(
            bottom, width=_PW, height=_PH,
            bg="black", highlightthickness=0, cursor="hand2",
        )
        self._pill.pack(pady=(0, 8))
        self._pill.bind("<Button-1>", lambda _e: self._toggle_pause())
        self._draw_pill()

        # Interrumpir habla con clic en canvas principal o Escape
        self._canvas.bind("<Button-1>", lambda _e: self._interrupt())
        self.bind("<Escape>", lambda _e: self._interrupt())

        self._particles = [_Particle(i, _N_PARTICLES) for i in range(_N_PARTICLES)]

    # ── Animación ──────────────────────────────────────────────────────────────
    def _schedule_frame(self) -> None:
        self._draw_frame()
        self.after(1000 // _FPS, self._schedule_frame)

    def _draw_frame(self) -> None:
        c    = self._canvas
        t    = time.time() - self._t0
        col  = _STATE_COLOR[self._state]
        W, H = _W, self._canvas_h
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
            # Vibracion radial segun estado
            if self._state == _LISTENING:
                disp = 1.0 + 0.16 * math.sin(t * 14 + p.phase)
            elif self._state == _SPEAKING:
                disp = 1.0 + 0.20 * math.sin(t * 9 + p.x0 * 1.6 + p.y0 * 1.6)
            elif self._state == _THINKING:
                disp = 1.0 + 0.06 * math.sin(t * 4 + p.phase)
            elif self._state == _PAUSED:
                disp = 1.0 + 0.015 * math.sin(t * 0.7 + p.phase)
            else:
                disp = 1.0 + 0.04 * math.sin(t * 1.8 + p.phase)

            px, py, pz = p.x0 * disp, p.y0 * disp, p.z0 * disp

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

    # ── Voz ────────────────────────────────────────────────────────────────────
    def _init_voice(self) -> None:
        def _setup() -> None:
            try:
                import speech_recognition as sr
                self._recognizer = sr.Recognizer()
                self._recognizer.pause_threshold       = 0.8
                self._recognizer.non_speaking_duration = 0.6
                self._mic = sr.Microphone()
                with self._mic as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=1.0)
                # Arrancar el loop continuo
                threading.Thread(target=self._continuous_loop, daemon=True).start()
            except Exception as e:
                self.after(0, lambda: self._set_status(f"Voz no disponible: {e}"))
        threading.Thread(target=_setup, daemon=True).start()

    def _continuous_loop(self) -> None:
        """Loop de escucha con wake word.
        Solo llama a la IA tras detectar 'jarvis'.
        """
        import re as _re
        import speech_recognition as sr

        _WAKE = _re.compile(
            r"^(?:hey\s+|oye\s+|ok\s+)?jarvis[,\s:!?.]*(.*)$", _re.IGNORECASE
        )
        waiting_command = False

        # Esperar init
        while self._state != _IDLE and self._voice_active:
            time.sleep(0.05)

        while self._voice_active:
            # Pausa: esperar y limpiar activacion pendiente
            if self._paused:
                while self._paused and self._voice_active:
                    time.sleep(0.05)
                waiting_command = False
                if not self._voice_active:
                    break

            # Mantener LISTENING (nunca volver a IDLE entre ciclos)
            if self._state not in (_SPEAKING, _THINKING, _PAUSED, _LISTENING):
                self._transition(_LISTENING)

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
                continue
            except Exception as exc:
                self._show_response(f"Error de red: {exc}")
                self._transition(_LISTENING)
                continue

            text = text.strip()
            if not text:
                self._transition(_LISTENING)
                continue

            # Wake word o modo activado
            command: str | None = None
            if waiting_command:
                command = text
                waiting_command = False
            else:
                m = _WAKE.match(text)
                if m:
                    cmd = m.group(1).strip()
                    if cmd:
                        command = cmd
                    else:
                        # Solo "jarvis" -> activado, esperar siguiente frase
                        self._set_status("Dime…")
                        self._state = _LISTENING
                        waiting_command = True
                        continue
                # Sin wake word -> ignorar silenciosamente

            if command is None:
                self._transition(_LISTENING)
                continue

            # Enviar a la IA
            self._show_response(f"Tú: {command}")
            try:
                reply = (
                    self._agent.send_message(command)
                    if self._agent else "[Modo demo]"
                )
            except Exception as exc:
                reply = f"[Error: {exc}]"

            self._show_response(f"Jarvis: {reply}")
            self._transition(_SPEAKING)
            self._speak(reply)

            if self._state == _SPEAKING:
                self._transition(_LISTENING)
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

    def _speak_neural(self, text: str) -> None:
        """TTS con edge-tts (voz neural Microsoft) + afplay. Fallback a say."""
        import asyncio
        import os
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

            async def _gen():
                comm = edge_tts.Communicate(text, "es-MX-JorgeNeural")
                await comm.save(self._tts_tmpfile)

            asyncio.run(_gen())
        except Exception:
            self._tts_tmpfile = None
            return

        # Reproducir con afplay (interruptible vía _interrupt)
        if self._tts_tmpfile and os.path.exists(self._tts_tmpfile):
            self._say_proc = subprocess.Popen(["afplay", self._tts_tmpfile])
            self._say_proc.wait()
            self._say_proc = None
            try:
                os.unlink(self._tts_tmpfile)
            except Exception:
                pass
            self._tts_tmpfile = None

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
        icon = "▶  REANUDAR" if paused else "⏸  PAUSAR"
        fg   = "#FF453A" if paused else "#EBEBF5"

        # Píldora: dos óvalos en los extremos + rectángulo central
        c.create_oval(0, 0, H, H, fill=bg, outline=bdr)          # tapa izq
        c.create_oval(W - H, 0, W - 1, H, fill=bg, outline=bdr)  # tapa der
        c.create_rectangle(R, 1, W - R, H - 1, fill=bg, outline="")  # cubre interior
        c.create_line(R, 0,   W - R, 0,   fill=bdr, width=1)     # borde superior
        c.create_line(R, H-1, W - R, H-1, fill=bdr, width=1)     # borde inferior
        c.create_text(W // 2, H // 2, text=icon, fill=fg,
                      font=("Helvetica Neue", 12))

    # ── Helpers thread-safe ──────────────────────────────────────────────
    def _transition(self, state: str) -> None:
        self._state = state
        label = _STATE_LABEL[state]
        self.after(0, lambda: self._lbl_status.configure(text=label))

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._lbl_status.configure(text=text))

    def _show_response(self, text: str) -> None:
        display = text[:150] + "…" if len(text) > 150 else text
        self.after(0, lambda: self._lbl_response.configure(text=display))

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

