"""
tools.py
--------
Funciones locales que el agente de IA puede invocar mediante Function Calling.
Cada función representa una acción concreta que Jarvis puede ejecutar en el
sistema operativo del usuario.

Las herramientas genéricas (portapapeles, sistema, web, archivos, dev,
interacción) provienen de la librería ``ai-tools-hub``.
Las herramientas específicas de Jarvis se definen aquí.

Todas las funciones deben:
  - Aceptar parámetros tipados.
  - Devolver siempre una cadena de texto con el resultado (éxito o error).
  - Manejar las diferencias entre macOS y Windows cuando sea necesario.
"""

import os
import platform
import subprocess
from typing import Callable

import pyperclip

# ---------------------------------------------------------------------------
# Importaciones de ai-tools-hub
# ---------------------------------------------------------------------------

from ai_tools_hub import ALL_TOOLS
from ai_tools_hub.system_tools import (
    get_clipboard_content,
    get_os_info,
    run_terminal_command,
)
from ai_tools_hub.web_tools import open_browser, extract_text_from_url
from ai_tools_hub.file_tools import read_file, create_file, list_directory
from ai_tools_hub.vision_tools import capturar_foto_webcam
from ai_tools_hub.dev_tools import (
    liberar_puerto,
    obtener_arbol_directorios,
    listar_contenedores_activos,
    reiniciar_contenedor,
)
from ai_tools_hub.interaction_tools import mostrar_notificacion, redactar_email


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _sistema_operativo() -> str:
    """Devuelve 'windows', 'macos' o 'linux' según el SO actual."""
    sistema = platform.system().lower()
    if sistema == "darwin":
        return "macos"
    if sistema == "windows":
        return "windows"
    return "linux"


# ---------------------------------------------------------------------------
# Herramientas del portapapeles (Jarvis-específicas)
# ---------------------------------------------------------------------------

def copiar_al_portapapeles(texto: str) -> str:
    """
    Copia el texto recibido al portapapeles del sistema.

    Args:
        texto: Cadena que se copiará al portapapeles.

    Returns:
        str: Confirmación de la operación o mensaje de error.
    """
    try:
        pyperclip.copy(texto)
        return f"Texto copiado al portapapeles: '{texto[:80]}{'...' if len(texto) > 80 else ''}'"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al copiar al portapapeles: {exc}]"


# ---------------------------------------------------------------------------
# Herramientas de aplicaciones
# ---------------------------------------------------------------------------

def abrir_vscode(ruta: str = "") -> str:
    """
    Abre Visual Studio Code, opcionalmente en una ruta específica.

    Args:
        ruta: Ruta del directorio o archivo a abrir en VSCode.
              Si está vacía, abre VSCode sin proyecto.

    Returns:
        str: Confirmación de la operación o mensaje de error.
    """
    try:
        cmd = ["code"]

        if ruta:
            ruta_expandida = os.path.expanduser(ruta)
            cmd.append(ruta_expandida)

        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        destino = f" en '{ruta}'" if ruta else ""
        return f"VSCode abierto{destino}."
    except FileNotFoundError:
        return "[Error: 'code' no encontrado. Verifica que VSCode esté en el PATH.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al abrir VSCode: {exc}]"


def abrir_aplicacion(nombre: str) -> str:
    """
    Abre una aplicación del sistema por nombre.

    En macOS usa ``open -a``.
    En Windows usa ``start`` a través del shell.

    Args:
        nombre: Nombre de la aplicación (p. ej. 'Safari', 'Notepad', 'Calculator').

    Returns:
        str: Confirmación de la operación o mensaje de error.
    """
    so = _sistema_operativo()
    try:
        if so == "macos":
            subprocess.Popen(
                ["open", "-a", nombre],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif so == "windows":
            subprocess.Popen(
                f'start "" "{nombre}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [nombre],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return f"Aplicación '{nombre}' abierta."
    except Exception as exc:  # noqa: BLE001
        return f"[Error al abrir '{nombre}': {exc}]"


def abrir_navegador(url: str = "", buscar: str = "") -> str:
    """
    Abre el navegador predeterminado en una URL, dominio o realiza una búsqueda en Google.

    Args:
        url:    URL o dominio a abrir (p.ej. 'google.com', 'https://github.com').
                Si no tiene esquema, se añade 'https://' automáticamente.
        buscar: Término o frase para buscar en Google (cuando no se da una URL).

    Returns:
        str: Confirmación de la operación o mensaje de error.
    """
    import urllib.parse
    import webbrowser

    # Seguridad: bloquear esquemas no web
    _check = (url or "").lower().lstrip()
    if any(_check.startswith(s) for s in ("file://", "data:", "javascript:", "vbscript:")):
        return "[Error: esquema de URL no permitido.]"

    if url:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open_new_tab(url)
        return f"Abriendo {url} en el navegador."
    elif buscar:
        query = urllib.parse.quote_plus(buscar.strip())
        webbrowser.open_new_tab(f"https://www.google.com/search?q={query}")
        return f"Buscando '{buscar}' en Google."
    else:
        webbrowser.open_new_tab("https://www.google.com")
        return "Abriendo Google en el navegador."


# ---------------------------------------------------------------------------
# Herramientas de notas
# ---------------------------------------------------------------------------

def guardar_nota(texto: str, nombre_archivo: str = "jarvis_nota.txt") -> str:
    """
    Guarda texto en un archivo de notas en el escritorio del usuario.

    Args:
        texto:         Contenido de la nota.
        nombre_archivo: Nombre del archivo de destino (por defecto 'jarvis_nota.txt').

    Returns:
        str: Ruta completa del archivo guardado o mensaje de error.
    """
    so = _sistema_operativo()
    try:
        if so == "windows":
            escritorio = os.path.join(os.path.expanduser("~"), "Desktop")
        else:
            # macOS y Linux
            escritorio = os.path.join(os.path.expanduser("~"), "Desktop")

        os.makedirs(escritorio, exist_ok=True)
        ruta_archivo = os.path.join(escritorio, nombre_archivo)

        with open(ruta_archivo, "a", encoding="utf-8") as f:
            f.write(texto + "\n")

        return f"Nota guardada en: {ruta_archivo}"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al guardar la nota: {exc}]"


def guardar_documento(contenido: str, nombre_archivo: str = "documento.txt", ruta_carpeta: str = "") -> str:
    """
    Genera y guarda un documento de texto en el escritorio (o carpeta indicada).
    Úsala cuando el usuario pida crear un informe, reporte, resumen, carta, lista u otro
    documento con contenido estructurado.

    Args:
        contenido:      Texto completo del documento.
        nombre_archivo: Nombre con extensión (p.ej. 'reporte.txt', 'resumen.md', 'lista.csv').
        ruta_carpeta:   Carpeta destino; si vacía, usa el escritorio del usuario.

    Returns:
        str: Ruta completa del archivo guardado o mensaje de error.
    """
    try:
        if ruta_carpeta:
            carpeta = os.path.expanduser(ruta_carpeta)
        else:
            carpeta = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, nombre_archivo)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"Documento guardado en: {ruta}"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al guardar el documento: {exc}]"


# ---------------------------------------------------------------------------
# Registro de herramientas disponibles para el agente
# ---------------------------------------------------------------------------

# Herramientas propias de Jarvis (no incluidas en ai-tools-hub)
JARVIS_CUSTOM_CALLABLES: list[Callable[..., str]] = [
    copiar_al_portapapeles,
    abrir_vscode,
    abrir_aplicacion,
    abrir_navegador,
    guardar_nota,
    guardar_documento,
]

TOOLS_MAP: dict[str, Callable[..., str]] = {
    # Jarvis-específicas
    "copiar_al_portapapeles": copiar_al_portapapeles,
    "abrir_vscode": abrir_vscode,
    "abrir_aplicacion": abrir_aplicacion,
    "abrir_navegador": abrir_navegador,
    "guardar_nota": guardar_nota,
    "guardar_documento": guardar_documento,
    # ai-tools-hub / system
    "get_clipboard_content": get_clipboard_content,
    "get_os_info": get_os_info,
    "run_terminal_command": run_terminal_command,
    # ai-tools-hub / web
    "open_browser": open_browser,
    "extract_text_from_url": extract_text_from_url,
    # ai-tools-hub / file
    "read_file": read_file,
    "create_file": create_file,
    "list_directory": list_directory,
    # ai-tools-hub / vision
    "capturar_foto_webcam": capturar_foto_webcam,
    # ai-tools-hub / dev
    "liberar_puerto": liberar_puerto,
    "obtener_arbol_directorios": obtener_arbol_directorios,
    "listar_contenedores_activos": listar_contenedores_activos,
    "reiniciar_contenedor": reiniciar_contenedor,
    # ai-tools-hub / interaction
    "mostrar_notificacion": mostrar_notificacion,
    "redactar_email": redactar_email,
}
