"""
tools.py
--------
Funciones locales que el agente de IA puede invocar mediante Function Calling.
Cada función representa una acción concreta que Jarvis puede ejecutar en el
sistema operativo del usuario.

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
# Herramientas del portapapeles
# ---------------------------------------------------------------------------

def obtener_portapapeles() -> str:
    """
    Lee y retorna el texto actual del portapapeles del sistema.

    Returns:
        str: El texto copiado o un mensaje de error si el portapapeles
             está vacío o no contiene texto.
    """
    try:
        texto = pyperclip.paste()
        if not texto or not texto.strip():
            return "[Portapapeles vacío o sin texto]"
        return texto
    except Exception as exc:  # noqa: BLE001
        return f"[Error al leer el portapapeles: {exc}]"


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
# Herramientas del sistema
# ---------------------------------------------------------------------------

def obtener_info_sistema() -> str:
    """
    Retorna información básica del sistema operativo.

    Returns:
        str: Cadena con el nombre del SO, versión y arquitectura.
    """
    return (
        f"Sistema: {platform.system()} {platform.release()} "
        f"({platform.machine()}) | Python {platform.python_version()}"
    )


# ---------------------------------------------------------------------------
# Registro de herramientas disponibles para el agente
# ---------------------------------------------------------------------------

TOOLS_MAP: dict[str, Callable[..., str]] = {
    "obtener_portapapeles": obtener_portapapeles,
    "copiar_al_portapapeles": copiar_al_portapapeles,
    "abrir_vscode": abrir_vscode,
    "abrir_aplicacion": abrir_aplicacion,
    "guardar_nota": guardar_nota,
    "guardar_documento": guardar_documento,
    "obtener_info_sistema": obtener_info_sistema,
}
