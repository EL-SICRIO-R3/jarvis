"""
main.py
-------
Punto de entrada de Jarvis Personal.

Responsabilidades:
  1. Inicializar el agente de IA (``JarvisAgent``).
  2. Crear la ventana gráfica (``JarvisWindow``) oculta.
  3. Registrar el ícono en la bandeja del sistema (``pystray``).
  4. Escuchar el atajo de teclado global (Ctrl+Espacio / Cmd+Espacio)
     para mostrar/ocultar la ventana.
  5. Coordinar el ciclo de vida completo de la aplicación.

Uso:
    python main.py
"""

from __future__ import annotations

import os
import platform
import sys
import threading
from pathlib import Path

import keyboard
import pystray
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Importaciones locales
# ---------------------------------------------------------------------------
from ai_agent import JarvisAgent
from gui import JarvisWindow

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_SO = platform.system().lower()

# Atajo global: Cmd+Espacio en macOS, Ctrl+Espacio en Windows/Linux
_HOTKEY = "command+space" if _SO == "darwin" else "ctrl+space"

# Tamaño del ícono de bandeja
_ICON_SIZE = (64, 64)


# ---------------------------------------------------------------------------
# Generación del ícono de bandeja (sin archivo externo)
# ---------------------------------------------------------------------------

def _crear_icono_imagen() -> Image.Image:
    """
    Genera una imagen PIL simple para el ícono de la bandeja del sistema.

    Crea un círculo azul con la letra 'J' en blanco, sin necesidad de
    ningún archivo de imagen externo.

    Returns:
        Image.Image: Imagen PIL de 64×64 píxeles.
    """
    img = Image.new("RGBA", _ICON_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo circular azul
    draw.ellipse([4, 4, 60, 60], fill="#0A84FF")

    # Letra 'J' centrada
    draw.text((22, 14), "J", fill="white")

    return img


# ---------------------------------------------------------------------------
# Clase principal de la aplicación
# ---------------------------------------------------------------------------

class JarvisApp:
    """
    Orquestador principal de Jarvis Personal.

    Gestiona el ciclo de vida de la aplicación: agente de IA, ventana
    gráfica, ícono en bandeja y atajo de teclado global.
    """

    def __init__(self) -> None:
        self._window: JarvisWindow | None = None
        self._tray: pystray.Icon | None = None
        self._agent: JarvisAgent | None = None

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------

    def _init_agent(self) -> None:
        """
        Intenta inicializar el agente de IA.

        Si no hay claves de API disponibles, continúa en modo demo
        (la ventana funcionará pero sin respuestas del LLM).
        """
        try:
            self._agent = JarvisAgent()
            print(f"[Jarvis] Agente iniciado con proveedor: {self._agent.provider}")
        except EnvironmentError as exc:
            print(f"[Jarvis] Modo demo activo – {exc}")
            self._agent = None

    def _init_window(self) -> None:
        """
        Crea e inicializa la ventana gráfica en el hilo principal.

        La ventana se crea oculta; el atajo de teclado la mostrará.
        """
        self._window = JarvisWindow(agent=self._agent)

    def _init_tray(self) -> None:
        """
        Configura e inicia el ícono de la bandeja del sistema.

        El ícono se ejecuta en un hilo daemon separado para no bloquear
        el bucle principal de Tkinter.
        """
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar / Ocultar", self._toggle_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self._quit),
        )

        self._tray = pystray.Icon(
            name="Jarvis",
            icon=_crear_icono_imagen(),
            title="Jarvis Personal",
            menu=menu,
        )

        tray_thread = threading.Thread(target=self._tray.run, daemon=True)
        tray_thread.start()

    def _register_hotkey(self) -> None:
        """
        Registra el atajo de teclado global para mostrar/ocultar la ventana.

        Usa la librería ``keyboard``. En macOS puede requerir permisos de
        accesibilidad (Preferencias del Sistema → Seguridad y Privacidad).
        """
        try:
            keyboard.add_hotkey(_HOTKEY, self._toggle_window)
            print(f"[Jarvis] Atajo global registrado: {_HOTKEY}")
        except Exception as exc:  # noqa: BLE001
            print(f"[Jarvis] No se pudo registrar el atajo '{_HOTKEY}': {exc}")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _toggle_window(self) -> None:
        """
        Llama al método ``toggle()`` de la ventana de forma segura
        desde cualquier hilo.
        """
        if self._window is not None:
            # after(0) garantiza que se ejecute en el hilo de Tkinter
            self._window.after(0, self._window.toggle)

    def _quit(self) -> None:
        """Cierra la aplicación completamente."""
        print("[Jarvis] Cerrando aplicación…")
        keyboard.unhook_all()
        if self._tray is not None:
            self._tray.stop()
        if self._window is not None:
            self._window.quit()

    # ------------------------------------------------------------------
    # Punto de entrada
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Inicia Jarvis Personal.

        Orden de inicialización:
          1. Agente de IA (hilo de inicialización separado para no
             bloquear la UI mientras carga el modelo).
          2. Ventana gráfica (debe crearse en el hilo principal).
          3. Ícono de bandeja (hilo daemon).
          4. Atajo de teclado global.
          5. Bucle principal de eventos de Tkinter.
        """
        print("[Jarvis] Iniciando…")

        # El agente puede tardar en inicializar; lo hacemos antes de la UI
        self._init_agent()

        # La ventana DEBE crearse en el hilo principal de Tkinter
        self._init_window()

        # Bandeja e ícono global (hilos secundarios)
        self._init_tray()
        self._register_hotkey()

        print("[Jarvis] Listo. Usa el atajo de teclado o el ícono de la bandeja.")

        # Bucle de eventos (bloquea hasta que se llame a quit())
        try:
            self._window.mainloop()
        except KeyboardInterrupt:
            self._quit()


# ---------------------------------------------------------------------------
# Punto de entrada del script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = JarvisApp()
    app.run()
