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

# ---------------------------------------------------------------------------
# Importaciones locales
# ---------------------------------------------------------------------------
from ai_agent import JarvisAgent
from gui import JarvisWindow
from telegram_bot import start_telegram_bot

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
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

    def _quit(self) -> None:
        """Cierra la aplicación completamente."""
        print("[Jarvis] Cerrando aplicación…")
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
        self._window.show()  # Mostrar directamente al arrancar con foco

        print("[Jarvis] Listo.")
        if self._agent is not None and start_telegram_bot(self._agent):
            print("[Jarvis] Telegram activado.")

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
