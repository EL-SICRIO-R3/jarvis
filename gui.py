"""
gui.py
------
Ventana flotante de Jarvis implementada con CustomTkinter.

Características:
  - Sin bordes del SO (``overrideredirect`` en Windows, equivalente en macOS).
  - Centrada en la pantalla al mostrarse.
  - Campo de texto para introducir comandos.
  - Área de respuesta con scroll.
  - Soporte para mostrar/ocultar mediante el método ``toggle()``.
  - Se integra con ``JarvisAgent`` para procesar las respuestas del LLM.
  - Esquema de color oscuro moderno inspirado en Spotlight / Alfred.
"""

from __future__ import annotations

import platform
import threading
from typing import TYPE_CHECKING, Optional

import customtkinter as ctk

if TYPE_CHECKING:
    from ai_agent import JarvisAgent

# ---------------------------------------------------------------------------
# Configuración global de CustomTkinter
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------------------------------------------------------------------------
# Colores y dimensiones
# ---------------------------------------------------------------------------
_BG_COLOR = "#1C1C1E"          # Fondo principal (gris muy oscuro)
_INPUT_BG = "#2C2C2E"          # Fondo del campo de entrada
_RESPONSE_BG = "#1C1C1E"       # Fondo del área de respuesta
_ACCENT = "#0A84FF"            # Azul acento (estilo Apple)
_TEXT_PRIMARY = "#F2F2F7"      # Texto principal
_TEXT_SECONDARY = "#8E8E93"    # Texto secundario / placeholder

_WINDOW_WIDTH = 680
_WINDOW_HEIGHT = 420
_BORDER_RADIUS = 16
_PADDING = 20


class JarvisWindow(ctk.CTk):
    """
    Ventana principal flotante de Jarvis.

    Gestiona la interfaz gráfica completa: campo de entrada, área de respuesta
    y la integración asíncrona con el agente de IA.

    Args:
        agent: Instancia de ``JarvisAgent`` ya inicializada. Si es ``None``,
               la ventana opera en modo demo (sin IA activa).
    """

    def __init__(self, agent: Optional["JarvisAgent"] = None) -> None:
        super().__init__()
        self._agent = agent
        self._is_visible = False
        self._so = platform.system().lower()

        self._configure_window()
        self._build_ui()
        self._bind_keys()

        # Ocultar al inicio (el tray la mostrará cuando corresponda)
        self.withdraw()

    # ------------------------------------------------------------------
    # Configuración de la ventana
    # ------------------------------------------------------------------

    def _configure_window(self) -> None:
        """Configura las propiedades base de la ventana flotante."""
        self.title("Jarvis")
        self.resizable(False, False)
        self.configure(fg_color=_BG_COLOR)

        # Eliminar bordes del SO
        if self._so == "windows":
            self.overrideredirect(True)
        elif self._so == "darwin":
            # En macOS eliminamos la barra de título pero conservamos
            # la funcionalidad de foco (overrideredirect tiene efectos
            # secundarios en macOS, por eso usamos wm_attributes).
            self.overrideredirect(True)
            self.wm_attributes("-topmost", True)
        else:
            self.overrideredirect(True)

        # Mantener la ventana siempre al frente
        self.wm_attributes("-topmost", True)

        # Transparencia de fondo en macOS
        if self._so == "darwin":
            self.wm_attributes("-transparent", True)

    def _center_window(self) -> None:
        """Centra la ventana en la pantalla activa."""
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - _WINDOW_WIDTH) // 2
        y = (screen_h - _WINDOW_HEIGHT) // 3  # Tercio superior, más natural
        self.geometry(f"{_WINDOW_WIDTH}x{_WINDOW_HEIGHT}+{x}+{y}")

    # ------------------------------------------------------------------
    # Construcción de la interfaz
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construye todos los widgets de la interfaz."""
        self.geometry(f"{_WINDOW_WIDTH}x{_WINDOW_HEIGHT}")

        # Contenedor principal con padding y esquinas redondeadas
        self._frame_main = ctk.CTkFrame(
            self,
            fg_color=_BG_COLOR,
            corner_radius=_BORDER_RADIUS,
            border_width=1,
            border_color="#3A3A3C",
        )
        self._frame_main.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Barra superior (título + botón cerrar) ──────────────────
        self._frame_topbar = ctk.CTkFrame(
            self._frame_main,
            fg_color="transparent",
            height=44,
        )
        self._frame_topbar.pack(fill="x", padx=_PADDING, pady=(12, 0))
        self._frame_topbar.pack_propagate(False)

        self._label_title = ctk.CTkLabel(
            self._frame_topbar,
            text="✦ Jarvis",
            font=ctk.CTkFont(family="SF Pro Display, Helvetica Neue, Arial", size=15, weight="bold"),
            text_color=_ACCENT,
        )
        self._label_title.pack(side="left", pady=4)

        self._btn_close = ctk.CTkButton(
            self._frame_topbar,
            text="✕",
            width=28,
            height=28,
            corner_radius=14,
            fg_color="#3A3A3C",
            hover_color="#FF453A",
            text_color=_TEXT_SECONDARY,
            font=ctk.CTkFont(size=11),
            command=self.hide,
        )
        self._btn_close.pack(side="right", pady=4)

        # ── Separador ──────────────────────────────────────────────
        ctk.CTkFrame(
            self._frame_main, height=1, fg_color="#3A3A3C"
        ).pack(fill="x", padx=_PADDING, pady=(8, 0))

        # ── Área de respuesta ───────────────────────────────────────
        self._textbox_response = ctk.CTkTextbox(
            self._frame_main,
            fg_color=_RESPONSE_BG,
            text_color=_TEXT_PRIMARY,
            font=ctk.CTkFont(family="SF Mono, Consolas, Menlo, monospace", size=13),
            corner_radius=10,
            border_width=0,
            wrap="word",
            state="disabled",
            activate_scrollbars=True,
        )
        self._textbox_response.pack(
            fill="both", expand=True, padx=_PADDING, pady=(12, 8)
        )

        # ── Mensaje de bienvenida ────────────────────────────────────
        self._append_response("Jarvis", "¿En qué puedo ayudarte hoy?")

        # ── Separador ──────────────────────────────────────────────
        ctk.CTkFrame(
            self._frame_main, height=1, fg_color="#3A3A3C"
        ).pack(fill="x", padx=_PADDING)

        # ── Fila de entrada ─────────────────────────────────────────
        self._frame_input = ctk.CTkFrame(
            self._frame_main, fg_color="transparent"
        )
        self._frame_input.pack(fill="x", padx=_PADDING, pady=(8, _PADDING))

        self._entry_input = ctk.CTkEntry(
            self._frame_input,
            placeholder_text="Escribe un comando o pregunta…",
            fg_color=_INPUT_BG,
            border_color="#3A3A3C",
            border_width=1,
            text_color=_TEXT_PRIMARY,
            placeholder_text_color=_TEXT_SECONDARY,
            font=ctk.CTkFont(size=14),
            corner_radius=10,
            height=42,
        )
        self._entry_input.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self._btn_send = ctk.CTkButton(
            self._frame_input,
            text="Enviar",
            width=84,
            height=42,
            corner_radius=10,
            fg_color=_ACCENT,
            hover_color="#0060CC",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_send,
        )
        self._btn_send.pack(side="right")

        # Drag para mover la ventana (arrastrando la barra superior)
        self._frame_topbar.bind("<ButtonPress-1>", self._on_drag_start)
        self._frame_topbar.bind("<B1-Motion>", self._on_drag_motion)
        self._label_title.bind("<ButtonPress-1>", self._on_drag_start)
        self._label_title.bind("<B1-Motion>", self._on_drag_motion)

    def _bind_keys(self) -> None:
        """Registra atajos de teclado dentro de la ventana."""
        self._entry_input.bind("<Return>", lambda _e: self._on_send())
        self._entry_input.bind("<Escape>", lambda _e: self.hide())

    # ------------------------------------------------------------------
    # Eventos de arrastre (mover ventana sin bordes)
    # ------------------------------------------------------------------

    def _on_drag_start(self, event) -> None:
        """Guarda la posición inicial del cursor al comenzar a arrastrar."""
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag_motion(self, event) -> None:
        """Mueve la ventana siguiendo el cursor."""
        delta_x = event.x - self._drag_x
        delta_y = event.y - self._drag_y
        new_x = self.winfo_x() + delta_x
        new_y = self.winfo_y() + delta_y
        self.geometry(f"+{new_x}+{new_y}")

    # ------------------------------------------------------------------
    # Lógica de envío y respuesta
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        """Captura el texto del campo de entrada y lanza el procesamiento."""
        texto = self._entry_input.get().strip()
        if not texto:
            return

        self._entry_input.delete(0, "end")
        self._append_response("Tú", texto)
        self._set_loading(True)

        # Procesar en hilo separado para no bloquear la UI
        threading.Thread(target=self._process_message, args=(texto,), daemon=True).start()

    def _process_message(self, mensaje: str) -> None:
        """
        Envía el mensaje al agente y actualiza la UI con la respuesta.

        Se ejecuta en un hilo secundario para mantener la interfaz fluida.

        Args:
            mensaje: Texto enviado por el usuario.
        """
        try:
            if self._agent is not None:
                respuesta = self._agent.send_message(mensaje)
            else:
                respuesta = (
                    "[Modo demo] Agente no configurado. "
                    "Define GEMINI_API_KEY o OPENAI_API_KEY."
                )
        except Exception as exc:  # noqa: BLE001
            respuesta = f"[Error: {exc}]"

        # Actualizar la UI desde el hilo principal
        self.after(0, self._append_response, "Jarvis", respuesta)
        self.after(0, self._set_loading, False)

    # ------------------------------------------------------------------
    # Utilidades de la interfaz
    # ------------------------------------------------------------------

    def _append_response(self, remitente: str, texto: str) -> None:
        """
        Agrega un bloque de mensaje al área de respuesta.

        Args:
            remitente: Nombre del emisor (p. ej. 'Tú' o 'Jarvis').
            texto:     Contenido del mensaje.
        """
        self._textbox_response.configure(state="normal")
        prefijo = f"\n[{remitente}]\n" if self._textbox_response.get("1.0", "end").strip() else f"[{remitente}]\n"
        self._textbox_response.insert("end", prefijo + texto + "\n")
        self._textbox_response.configure(state="disabled")
        self._textbox_response.see("end")

    def _set_loading(self, cargando: bool) -> None:
        """
        Activa o desactiva el estado de carga visual.

        Args:
            cargando: ``True`` para mostrar indicador de espera,
                      ``False`` para restaurar el estado normal.
        """
        if cargando:
            self._btn_send.configure(text="…", state="disabled")
            self._entry_input.configure(state="disabled")
        else:
            self._btn_send.configure(text="Enviar", state="normal")
            self._entry_input.configure(state="normal")
            self._entry_input.focus_set()

    # ------------------------------------------------------------------
    # Mostrar / ocultar
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Muestra la ventana centrada en pantalla y la enfoca."""
        self._center_window()
        self.deiconify()
        self.lift()
        self.focus_force()
        self._entry_input.focus_set()
        self._is_visible = True

    def hide(self) -> None:
        """Oculta la ventana sin cerrar la aplicación."""
        self.withdraw()
        self._is_visible = False

    def toggle(self) -> None:
        """Alterna entre mostrar y ocultar la ventana."""
        if self._is_visible:
            self.hide()
        else:
            self.show()
