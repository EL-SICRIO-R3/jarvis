"""
ai_tools_hub.py
---------------
Implementación local de todas las herramientas que Jarvis puede invocar
mediante Function Calling.  Expone ``ALL_TOOLS`` — la lista de callables
que se pasa directamente a Gemini (auto-esquemas desde type hints/docstrings)
y se usa para construir ``TOOLS_MAP`` en ai_agent.py.

Todas las funciones:
  - Aceptan parámetros tipados.
  - Devuelven siempre ``str`` (éxito o mensaje de error entre corchetes).
  - Manejan diferencias entre macOS, Linux y Windows cuando sea necesario.
"""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from typing import Callable


# ---------------------------------------------------------------------------
# Utilidad interna
# ---------------------------------------------------------------------------

def _so() -> str:
    """Devuelve 'macos', 'windows' o 'linux'."""
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


# ---------------------------------------------------------------------------
# system_tools
# ---------------------------------------------------------------------------

def get_clipboard_content() -> str:
    """Lee y retorna el texto actual del portapapeles del sistema."""
    try:
        import pyperclip  # type: ignore
        text = pyperclip.paste()
        return text if text else "El portapapeles está vacío."
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
    _POSIX: dict[str, list[str]] = {
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
    _WIN: dict[str, list[str]] = {
        "python": ["python", "--version"],
        "pip": ["pip", "list"],
        "dir": ["dir"],
        "systeminfo": ["systeminfo"],
        "tasklist": ["tasklist"],
        "ipconfig": ["ipconfig"],
        "ver": ["ver"],
    }

    allow_list = _WIN if platform.system().lower() == "windows" else _POSIX
    if command_name not in allow_list:
        return (
            f"[Error: comando '{command_name}' no permitido. "
            f"Disponibles: {', '.join(sorted(allow_list))}]"
        )

    cmd = allow_list[command_name][:]
    if command_name in ("ls", "dir") and argument:
        cmd.append(argument)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + ("\n" + result.stderr if result.stderr else "")
        return output.strip() or "(sin salida)"
    except FileNotFoundError:
        return f"[Error: '{command_name}' no encontrado en el sistema.]"
    except subprocess.TimeoutExpired:
        return f"[Error: '{command_name}' superó el tiempo límite de 30 s.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al ejecutar '{command_name}': {exc}]"


# ---------------------------------------------------------------------------
# web_tools
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
        return f"Navegador abierto en: {url}"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al abrir el navegador: {exc}]"


def extract_text_from_url(url: str, max_chars: int = 8000) -> str:
    """
    Descarga una página web y devuelve su texto plano limpio (scripts y estilos eliminados).

    Args:
        url: URL de la página a extraer.
        max_chars: Límite de caracteres del texto devuelto (por defecto 8000).
    """
    try:
        import requests  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError as exc:
        return f"[Error: dependencia faltante — {exc}]"

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return f"[Error al descargar la página: {exc}]"

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()

    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines()]
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False

    text = "\n".join(cleaned).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n[... contenido truncado a {max_chars} caracteres ...]"
    return text


# ---------------------------------------------------------------------------
# file_tools
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
            return "[Error: 'pypdf' no está instalado. Instala con: pip install pypdf]"
        try:
            reader = PdfReader(path)
            return "\n\n".join(p.extract_text() or "" for p in reader.pages).strip()
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
        return f"[Error: el archivo '{path}' ya existe. Usa overwrite=True para sobreescribir.]"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        size = os.path.getsize(path)
        action = "actualizado" if os.path.exists(path) else "creado"
        return f"Archivo {action}: {path} ({size} bytes)"
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

    def _human(n: float) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(n) < 1024.0:
                return f"{n:,.1f} {unit}"
            n /= 1024.0
        return f"{n:.1f} PB"

    try:
        entries = os.listdir(path)
    except PermissionError:
        return f"[Error: permiso denegado para listar '{path}'.]"

    if not show_hidden:
        entries = [e for e in entries if not e.startswith(".")]

    dirs  = sorted(e for e in entries if os.path.isdir(os.path.join(path, e)))
    files = sorted(e for e in entries if os.path.isfile(os.path.join(path, e)))

    lines = [f"Directorio: {path}", ""]
    for d in dirs:
        lines.append(f"📁 {d}/")
    for fn in files:
        size = os.path.getsize(os.path.join(path, fn))
        lines.append(f"📄 {fn}  ({_human(size)})")
    lines += ["", f"{len(dirs)} directorio(s), {len(files)} archivo(s)"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# vision_tools
# ---------------------------------------------------------------------------

def capturar_foto_webcam() -> str:
    """
    Captura una foto con la webcam principal del sistema y la guarda como JPEG.
    Retorna la ruta absoluta del archivo generado o un mensaje de error.
    """
    try:
        import cv2  # type: ignore
    except ImportError:
        return "[Error: 'opencv-python' no está instalado. Instala con: pip install opencv-python]"

    cap = cv2.VideoCapture(0)
    try:
        if not cap.isOpened():
            return "[Error: no se pudo abrir la webcam (índice 0).]"
        ret, frame = cap.read()
        if not ret or frame is None:
            return "[Error: la webcam devolvió un frame vacío.]"
        output_path = os.path.join(tempfile.gettempdir(), "webcam_snapshot.jpg")
        cv2.imwrite(output_path, frame)
        return output_path
    finally:
        cap.release()


def tomar_captura_pantalla() -> str:
    """
    Toma un screenshot de la pantalla principal del sistema y lo guarda como PNG
    en un archivo temporal. Retorna la ruta absoluta del archivo generado.
    """
    try:
        import mss  # type: ignore
        import mss.tools  # type: ignore
    except ImportError:
        return "[Error: 'mss' no está instalado. Instala con: pip install mss]"

    try:
        import time as _time
        ts = int(_time.time() * 1_000_000)  # microseconds — avoids same-second collisions
        output_path = os.path.join(tempfile.gettempdir(), f"screenshot_{ts}.png")
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # monitor principal
            screenshot = sct.grab(monitor)
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
        return output_path
    except Exception as exc:  # noqa: BLE001
        return f"[Error al tomar la captura de pantalla: {exc}]"


# ---------------------------------------------------------------------------
# dev_tools
# ---------------------------------------------------------------------------

def liberar_puerto(puerto: int) -> str:
    """
    Termina el proceso que está escuchando en el puerto TCP especificado.

    Args:
        puerto: Número de puerto TCP (e.g. 8080, 4200, 3000).
    """
    sistema = _so()
    try:
        if sistema == "windows":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10
            )
            pids = set()
            for line in result.stdout.splitlines():
                if f":{puerto}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        pids.add(parts[-1])
            if not pids:
                return f"No se encontró ningún proceso escuchando en el puerto {puerto}."
            for pid in pids:
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            return f"Proceso(s) {', '.join(pids)} en puerto {puerto} terminados."
        else:
            result = subprocess.run(
                ["lsof", "-ti", f":{puerto}"],
                capture_output=True, text=True, timeout=10
            )
            pids_str = result.stdout.strip()
            if not pids_str:
                return f"No se encontró ningún proceso escuchando en el puerto {puerto}."
            pids = pids_str.split()
            for pid in pids:
                subprocess.run(["kill", "-9", pid], capture_output=True)
            return f"Proceso(s) {', '.join(pids)} en puerto {puerto} terminados."
    except Exception as exc:  # noqa: BLE001
        return f"[Error al liberar el puerto {puerto}: {exc}]"


def obtener_arbol_directorios(ruta: str, profundidad: int = 2) -> str:
    """
    Genera un árbol visual de directorios hasta el nivel de profundidad indicado.

    Args:
        ruta: Ruta raíz del árbol. Acepta ~.
        profundidad: Máximo de niveles a mostrar (por defecto 2).
    """
    path = os.path.realpath(os.path.expanduser(ruta))
    if not os.path.exists(path):
        return f"[Error: la ruta '{path}' no existe.]"

    lines: list[str] = [path]

    def _walk(current: str, prefix: str, depth: int) -> None:
        if depth > profundidad:
            return
        try:
            entries = sorted(os.listdir(current))
        except PermissionError:
            return
        entries = [e for e in entries if not e.startswith(".")]
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(prefix + connector + entry)
            full = os.path.join(current, entry)
            if os.path.isdir(full):
                extension = "    " if is_last else "│   "
                _walk(full, prefix + extension, depth + 1)

    _walk(path, "", 1)
    return "\n".join(lines)


def listar_contenedores_activos() -> str:
    """Lista todos los contenedores Docker que están en ejecución."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format",
             "table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"[Error de Docker: {result.stderr.strip()}]"
        return result.stdout.strip() or "No hay contenedores activos."
    except FileNotFoundError:
        return "[Error: Docker no está instalado o no está en el PATH.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al listar contenedores: {exc}]"


def reiniciar_contenedor(nombre_o_id: str) -> str:
    """
    Reinicia un contenedor Docker identificado por su nombre o ID.

    Args:
        nombre_o_id: Nombre o ID del contenedor Docker.
    """
    try:
        result = subprocess.run(
            ["docker", "restart", nombre_o_id],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return f"[Error al reiniciar '{nombre_o_id}': {result.stderr.strip()}]"
        return f"Contenedor '{nombre_o_id}' reiniciado correctamente."
    except FileNotFoundError:
        return "[Error: Docker no está instalado o no está en el PATH.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error: {exc}]"


def obtener_estado_git(ruta_proyecto: str) -> str:
    """
    Ejecuta git status en el directorio de proyecto indicado y devuelve la salida como texto plano.

    Args:
        ruta_proyecto: Ruta absoluta o relativa al directorio raíz del repositorio Git. Acepta ~.
    """
    path = os.path.realpath(os.path.expanduser(ruta_proyecto))
    if not os.path.exists(path):
        return f"[Error: la ruta '{path}' no existe.]"
    try:
        result = subprocess.run(
            ["git", "status"],
            cwd=path, capture_output=True, text=True, timeout=15
        )
        output = result.stdout + ("\n" + result.stderr if result.stderr else "")
        return output.strip() or "(sin salida)"
    except FileNotFoundError:
        return "[Error: Git no está instalado o no está en el PATH.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al ejecutar git status: {exc}]"


def analizar_ultimos_logs(ruta_archivo: str, lineas: int = 50) -> str:
    """
    Lee y devuelve las últimas N líneas de un archivo de log de forma eficiente.

    Args:
        ruta_archivo: Ruta absoluta o relativa al archivo de log. Acepta ~.
        lineas: Número de líneas finales a devolver (por defecto 50).
    """
    path = os.path.realpath(os.path.expanduser(ruta_archivo))
    if not os.path.exists(path):
        return f"[Error: el archivo '{path}' no existe.]"
    if os.path.isdir(path):
        return f"[Error: '{path}' es un directorio, no un archivo.]"
    try:
        with open(path, "rb") as f:
            # Leer las últimas N líneas sin cargar el archivo completo
            f.seek(0, 2)
            file_size = f.tell()
            block_size = 4096
            data = b""
            remaining = file_size
            while remaining > 0 and data.count(b"\n") < lineas + 1:
                read_size = min(block_size, remaining)
                remaining -= read_size
                f.seek(remaining)
                data = f.read(read_size) + data
            text_lines = data.decode("utf-8", errors="replace").splitlines()
        return "\n".join(text_lines[-lineas:])
    except Exception as exc:  # noqa: BLE001
        return f"[Error al leer el log: {exc}]"


# ---------------------------------------------------------------------------
# interaction_tools
# ---------------------------------------------------------------------------

def mostrar_notificacion(titulo: str, mensaje: str) -> str:
    """
    Muestra una notificación nativa del sistema operativo.

    Args:
        titulo: Título de la notificación.
        mensaje: Cuerpo / texto de la notificación.
    """
    sistema = _so()
    try:
        if sistema == "macos":
            script = (
                f'display notification "{mensaje}" with title "{titulo}"'
            )
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
            return f"Notificación mostrada: '{titulo}'"
        else:
            try:
                from plyer import notification  # type: ignore
                notification.notify(title=titulo, message=mensaje, timeout=5)
                return f"Notificación mostrada: '{titulo}'"
            except ImportError:
                return "[Error: 'plyer' no está instalado. Instala con: pip install plyer]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al mostrar la notificación: {exc}]"


def redactar_email(destinatario: str, asunto: str, cuerpo: str) -> str:
    """
    Abre el cliente de correo electrónico predeterminado con un borrador prellenado.

    Args:
        destinatario: Dirección de correo del destinatario.
        asunto: Asunto del correo.
        cuerpo: Cuerpo del mensaje.
    """
    import urllib.parse
    import webbrowser

    try:
        params = urllib.parse.urlencode(
            {"subject": asunto, "body": cuerpo}, quote_via=urllib.parse.quote
        )
        mailto = f"mailto:{urllib.parse.quote(destinatario)}?{params}"
        webbrowser.open(mailto)
        return f"Borrador de correo abierto para: {destinatario}"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al abrir el cliente de correo: {exc}]"


# ---------------------------------------------------------------------------
# Herramientas específicas de Jarvis
# ---------------------------------------------------------------------------

def guardar_documento(contenido: str, nombre_archivo: str = "documento.txt", ruta_carpeta: str = "") -> str:
    """
    Genera y guarda un documento de texto en el escritorio (o carpeta indicada).
    Úsala cuando el usuario pida crear un informe, reporte, resumen, carta, lista
    u otro documento con contenido estructurado.

    Args:
        contenido: Texto completo del documento.
        nombre_archivo: Nombre con extensión (p.ej. 'reporte.txt', 'resumen.md').
        ruta_carpeta: Carpeta destino; si vacía, usa el escritorio del usuario.
    """
    try:
        carpeta = os.path.expanduser(ruta_carpeta) if ruta_carpeta else os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(carpeta, exist_ok=True)
        ruta = os.path.join(carpeta, nombre_archivo)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"Documento guardado en: {ruta}"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al guardar el documento: {exc}]"


def guardar_nota(texto: str, nombre_archivo: str = "jarvis_nota.txt") -> str:
    """
    Guarda (o añade) texto en un archivo de notas en el escritorio del usuario.

    Args:
        texto: Contenido de la nota.
        nombre_archivo: Nombre del archivo de destino (por defecto 'jarvis_nota.txt').
    """
    try:
        escritorio = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(escritorio, exist_ok=True)
        ruta = os.path.join(escritorio, nombre_archivo)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(texto + "\n")
        return f"Nota guardada en: {ruta}"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al guardar la nota: {exc}]"


# ---------------------------------------------------------------------------
# Registro público — ALL_TOOLS es lo que importa ai_agent.py
# ---------------------------------------------------------------------------

ALL_TOOLS: list[Callable[..., str]] = [
    # system_tools
    get_clipboard_content,
    get_os_info,
    run_terminal_command,
    # web_tools
    open_browser,
    extract_text_from_url,
    # file_tools
    read_file,
    create_file,
    list_directory,
    # vision_tools
    capturar_foto_webcam,
    tomar_captura_pantalla,
    # dev_tools
    liberar_puerto,
    obtener_arbol_directorios,
    listar_contenedores_activos,
    reiniciar_contenedor,
    obtener_estado_git,
    analizar_ultimos_logs,
    # interaction_tools
    mostrar_notificacion,
    redactar_email,
    # Jarvis-specific
    guardar_documento,
    guardar_nota,
]
