"""
tools.py
--------
Funciones locales que el agente de IA puede invocar mediante Function Calling.
Cada función representa una acción concreta que Jarvis puede ejecutar en el
sistema operativo del usuario.

Incluye implementaciones directas de las herramientas descritas en
doc-ia-tools.md (system, web, file y vision) más las herramientas
específicas de Jarvis.

Todas las funciones deben:
  - Aceptar parámetros tipados.
  - Devolver siempre una cadena de texto con el resultado (éxito o error).
  - Manejar las diferencias entre macOS, Linux y Windows cuando sea necesario.
"""

import os
import platform
import subprocess
import tempfile
from typing import Callable


# ---------------------------------------------------------------------------
# Herramientas de sistema (system_tools)
# ---------------------------------------------------------------------------

def get_clipboard_content() -> str:
    """Lee y retorna el texto actual del portapapeles del sistema."""
    try:
        import pyperclip  # type: ignore
        text = pyperclip.paste()
        if not text:
            return "The clipboard is currently empty."
        return text
    except ImportError:
        return "[Error: 'pyperclip' no está instalado.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al leer el portapapeles: {exc}]"


def get_os_info() -> str:
    """Devuelve un resumen detallado del sistema operativo y el hardware del host."""
    fields = {
        "OS": platform.platform(),
        "System": platform.system(),
        "Release": platform.release(),
        "Version": platform.version(),
        "Machine": platform.machine(),
        "Processor": platform.processor() or "N/A",
        "Python": platform.python_version(),
        "Architecture": " / ".join(platform.architecture()),
    }
    return "\n".join(f"{k}: {v}" for k, v in fields.items())


def run_terminal_command(command_name: str, argument: str = "") -> str:
    """
    Ejecuta un comando de terminal de una lista de permitidos (solo lectura/informativos)
    y devuelve su salida.

    Args:
        command_name: Clave del comando a ejecutar (e.g. 'ls', 'df', 'pip', 'ps').
        argument: Argumento de ruta opcional (solo para 'ls' y 'dir').
    """
    _POSIX_COMMANDS: dict[str, list[str]] = {
        "python": ["python", "--version"],
        "pip": ["pip", "list"],
        "ls": ["ls", "-lh"],
        "pwd": ["pwd"],
        "whoami": ["whoami"],
        "df": ["df", "-h"],
        "free": ["free", "-h"],
        "uname": ["uname", "-a"],
        "uptime": ["uptime"],
        "ps": ["ps", "aux"],
        "env": ["env"],
        "date": ["date"],
    }
    _WINDOWS_COMMANDS: dict[str, list[str]] = {
        "python": ["python", "--version"],
        "pip": ["pip", "list"],
        "dir": ["dir"],
        "systeminfo": ["systeminfo"],
        "tasklist": ["tasklist"],
        "ipconfig": ["ipconfig"],
        "ver": ["ver"],
    }

    is_windows = platform.system().lower() == "windows"
    allow_list = _WINDOWS_COMMANDS if is_windows else _POSIX_COMMANDS

    if command_name not in allow_list:
        return (
            f"[Error: comando '{command_name}' no está en la lista de comandos permitidos. "
            f"Comandos disponibles: {', '.join(sorted(allow_list))}]"
        )

    cmd = allow_list[command_name][:]
    if command_name in ("ls", "dir") and argument:
        cmd.append(argument)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output.strip() or "(sin salida)"
    except FileNotFoundError:
        return f"[Error: comando '{command_name}' no encontrado en el sistema.]"
    except subprocess.TimeoutExpired:
        return f"[Error: el comando '{command_name}' superó el tiempo límite de 30 segundos.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al ejecutar '{command_name}': {exc}]"


# ---------------------------------------------------------------------------
# Herramientas web (web_tools)
# ---------------------------------------------------------------------------

def open_browser(url: str) -> str:
    """
    Abre una URL en el navegador predeterminado del sistema.

    Args:
        url: La URL a abrir. Si no tiene esquema, se añade https:// automáticamente.
    """
    import webbrowser

    if not url or not url.strip():
        return "[Error: URL vacía.]"
    url = url.strip()
    if not url.startswith(("http://", "https://", "file://")):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"Browser opened successfully for: {url}"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al abrir el navegador: {exc}]"


def extract_text_from_url(url: str, max_chars: int = 8000) -> str:
    """
    Descarga una página web y devuelve su texto plano limpio (scripts y estilos eliminados).

    Args:
        url: URL de la página a scrapear.
        max_chars: Límite de caracteres del texto devuelto (por defecto 8000).
    """
    try:
        import requests  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError as exc:
        return f"[Error: dependencia faltante — {exc}]"

    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return "[Error: la solicitud superó el tiempo límite de 15 segundos.]"
    except requests.exceptions.HTTPError as exc:
        return f"[Error HTTP: {exc}]"
    except requests.exceptions.RequestException as exc:
        return f"[Error de conexión: {exc}]"

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()

    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
    # Colapsar líneas en blanco consecutivas
    cleaned_lines: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned_lines.append("")
            prev_blank = True
        else:
            cleaned_lines.append(line)
            prev_blank = False

    text = "\n".join(cleaned_lines).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n[... content truncated at {max_chars} characters ...]"
    return text


# ---------------------------------------------------------------------------
# Herramientas de archivos (file_tools)
# ---------------------------------------------------------------------------

def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """
    Lee y devuelve el contenido completo de un archivo de texto o PDF.

    Args:
        file_path: Ruta al archivo. Acepta ~ (tilde expansion).
        encoding: Codificación para archivos de texto plano (por defecto utf-8).
    """
    path = os.path.realpath(os.path.expanduser(file_path))

    if not os.path.exists(path):
        return f"[Error: el archivo '{path}' no existe.]"
    if os.path.isdir(path):
        return f"[Error: '{path}' es un directorio, no un archivo.]"

    if path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            return "[Error: 'pypdf' no está instalado. Instálalo con: pip install pypdf]"
        try:
            reader = PdfReader(path)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages_text).strip()
        except Exception as exc:  # noqa: BLE001
            return f"[Error al leer el PDF: {exc}]"

    try:
        with open(path, encoding=encoding) as f:
            return f.read()
    except PermissionError:
        return f"[Error: permiso denegado para leer '{path}'.]"
    except UnicodeDecodeError:
        return f"[Error: no se pudo decodificar '{path}' con encoding '{encoding}'.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al leer el archivo: {exc}]"


def create_file(file_path: str, content: str, overwrite: bool = False) -> str:
    """
    Crea un archivo de texto UTF-8 en la ruta especificada.

    Args:
        file_path: Ruta del archivo a crear. Acepta ~.
        content: Contenido a escribir en el archivo.
        overwrite: Si True, reemplaza el archivo si ya existe.
    """
    path = os.path.realpath(os.path.expanduser(file_path))

    if os.path.exists(path) and not overwrite:
        return f"[Error: el archivo '{path}' ya existe. Usa overwrite=True para sobreescribirlo.]"

    action = "updated" if os.path.exists(path) else "created"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        size = os.path.getsize(path)
        return f"File {action} successfully: {path} ({size} bytes)"
    except PermissionError:
        return f"[Error: permiso denegado para escribir en '{path}'.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al crear el archivo: {exc}]"


def list_directory(directory_path: str = ".", show_hidden: bool = False) -> str:
    """
    Lista los archivos y subdirectorios de una ruta con sus tamaños.

    Args:
        directory_path: Ruta del directorio a listar (por defecto el directorio actual).
        show_hidden: Si True, incluye archivos y carpetas ocultos.
    """
    path = os.path.realpath(os.path.expanduser(directory_path))

    if not os.path.exists(path):
        return f"[Error: el directorio '{path}' no existe.]"
    if not os.path.isdir(path):
        return f"[Error: '{path}' es un archivo, no un directorio.]"

    def _human_size(num: float) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
            if abs(num) < 1024.0:
                return f"{num:,.1f} {unit}"
            num /= 1024.0
        return f"{num:.1f} EB"

    try:
        entries = os.listdir(path)
    except PermissionError:
        return f"[Error: permiso denegado para listar '{path}'.]"

    if not show_hidden:
        entries = [e for e in entries if not e.startswith(".")]

    dirs = sorted(e for e in entries if os.path.isdir(os.path.join(path, e)))
    files = sorted(e for e in entries if os.path.isfile(os.path.join(path, e)))

    lines = [f"Directory: {path}", ""]
    for d in dirs:
        lines.append(f"📁 {d}/")
    for f_name in files:
        size = os.path.getsize(os.path.join(path, f_name))
        lines.append(f"📄 {f_name}  ({_human_size(size)})")
    lines.append("")
    lines.append(f"{len(dirs)} director{'y' if len(dirs) == 1 else 'ies'}, {len(files)} file{'s' if len(files) != 1 else ''}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Herramientas de visión (vision_tools)
# ---------------------------------------------------------------------------

def capturar_foto_webcam() -> str:
    """
    Captura una foto con la webcam principal del sistema y la guarda como JPEG.
    Retorna la ruta absoluta del archivo generado o un mensaje de error.
    """
    try:
        import cv2  # type: ignore
    except ImportError:
        return "[Error: 'opencv-python' no está instalado. Instálalo con: pip install opencv-python]"

    cap = cv2.VideoCapture(0)
    try:
        if not cap.isOpened():
            return "[Error: no se pudo abrir la webcam (índice 0). Verifica que la cámara esté disponible.]"
        ret, frame = cap.read()
        if not ret or frame is None:
            return "[Error: la captura de imagen falló. La webcam devolvió un frame vacío.]"
        output_path = os.path.join(tempfile.gettempdir(), "webcam_snapshot.jpg")
        cv2.imwrite(output_path, frame)
        return output_path
    finally:
        cap.release()


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

# Lista de todos los callables disponibles para Gemini (se pasa a tools=)
JARVIS_CUSTOM_CALLABLES: list[Callable[..., str]] = [
    # Jarvis-específicas
    copiar_al_portapapeles,
    abrir_vscode,
    abrir_aplicacion,
    abrir_navegador,
    guardar_nota,
    guardar_documento,
    # system
    get_clipboard_content,
    get_os_info,
    run_terminal_command,
    # web
    open_browser,
    extract_text_from_url,
    # file
    read_file,
    create_file,
    list_directory,
    # vision
    capturar_foto_webcam,
]

TOOLS_MAP: dict[str, Callable[..., str]] = {
    # Jarvis-específicas
    "copiar_al_portapapeles": copiar_al_portapapeles,
    "abrir_vscode": abrir_vscode,
    "abrir_aplicacion": abrir_aplicacion,
    "abrir_navegador": abrir_navegador,
    "guardar_nota": guardar_nota,
    "guardar_documento": guardar_documento,
    # system
    "get_clipboard_content": get_clipboard_content,
    "get_os_info": get_os_info,
    "run_terminal_command": run_terminal_command,
    # web
    "open_browser": open_browser,
    "extract_text_from_url": extract_text_from_url,
    # file
    "read_file": read_file,
    "create_file": create_file,
    "list_directory": list_directory,
    # vision
    "capturar_foto_webcam": capturar_foto_webcam,
}
