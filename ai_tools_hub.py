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
import ast
import json
import importlib.util
import logging
import re
from pathlib import Path
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)


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


def _img_dir() -> Path:
    """
    Devuelve la ruta ``<proyecto>/ia-tools/img`` y la crea si no existe.
    El directorio raíz del proyecto se determina por la ubicación de este módulo.
    """
    config = _config_path()
    try:
        configured = json.loads(config.read_text(encoding="utf-8")).get("image_directory")
    except (OSError, ValueError, AttributeError):
        configured = None
    img_dir = Path(os.path.expanduser(configured)) if configured else Path(__file__).parent / "ia-tools" / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def _config_path() -> Path:
    """Devuelve el archivo de configuración persistente de Jarvis."""
    return Path.home() / ".config" / "jarvis" / "config.json"


def configurar_ruta_imagenes(ruta: str, autorizado: bool = False) -> str:
    """Cambia la carpeta de imágenes; requiere confirmación explícita del usuario."""
    if not autorizado:
        return "[AUTORIZACIÓN REQUERIDA: cambiar la carpeta de imágenes modifica el comportamiento de Jarvis.]"
    destino = Path(os.path.expanduser(ruta))
    if not destino.is_absolute():
        return "[Error: la ruta debe ser absoluta o empezar por ~.]"
    try:
        config = _config_path()
        config.parent.mkdir(parents=True, exist_ok=True)
        values = {}
        if config.exists():
            values = json.loads(config.read_text(encoding="utf-8"))
            if not isinstance(values, dict):
                values = {}
        values["image_directory"] = str(destino)
        config.write_text(json.dumps(values, indent=2), encoding="utf-8")
        destino.mkdir(parents=True, exist_ok=True)
        return f"Ruta de imágenes configurada en: {destino}"
    except (OSError, ValueError) as exc:
        return f"[Error al configurar la ruta de imágenes: {exc}]"


def crear_tool(nombre: str, codigo: str, autorizado: bool = False) -> str:
    """Crea una herramienta Python personalizada para cargarla al reiniciar Jarvis."""
    if not autorizado:
        return "[AUTORIZACIÓN REQUERIDA: crear una tool ejecutará código local al reiniciar Jarvis.]"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nombre):
        return "[Error: el nombre de la tool no es un identificador Python válido.]"
    if not codigo.strip():
        return "[Error: debes proporcionar el código de la tool.]"
    try:
        tree = ast.parse(codigo)
    except SyntaxError as exc:
        return f"[Error: el código de la tool no es válido: {exc}]"
    if not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == nombre
        for node in tree.body
    ):
        return f"[Error: el código debe definir una función llamada '{nombre}'.]"
    try:
        tools_dir = Path.home() / ".config" / "jarvis" / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        tool_path = tools_dir / f"{nombre}.py"
        tool_path.write_text(codigo.rstrip() + "\n", encoding="utf-8")
        return f"Tool '{nombre}' creada en {tool_path}. Reinicia Jarvis para cargarla."
    except OSError as exc:
        return f"[Error al crear la tool: {exc}]"


def _load_custom_tools() -> list[Callable[..., str]]:
    """Carga tools autorizadas previamente desde la carpeta de configuración."""
    tools_dir = Path.home() / ".config" / "jarvis" / "tools"
    loaded: list[Callable[..., str]] = []
    if not tools_dir.is_dir():
        return loaded
    for path in sorted(tools_dir.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"jarvis_custom_{path.stem}", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            _LOGGER.warning("No se pudo cargar la tool personalizada %s: %s", path, exc)
            continue
        function = getattr(module, path.stem, None)
        if callable(function):
            loaded.append(function)
    return loaded


def _video_dir() -> Path:
    """
    Devuelve la ruta ``<proyecto>/ia-tools/video`` y la crea si no existe.
    """
    video_dir = Path(__file__).parent / "ia-tools" / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    return video_dir


_VEO_SUPPORTED_DURATIONS = (4, 6, 8)


def _extract_generated_video_bytes(operation: Any) -> bytes:
    """Extrae bytes de respuestas ``response`` y ``result`` del SDK de Veo."""
    result = getattr(operation, "response", None)
    if result is None:
        result = getattr(operation, "result", None)
    generated_videos = getattr(result, "generated_videos", None)
    if not generated_videos:
        raise RuntimeError("La API no devolvió ningún video.")

    video = generated_videos[0].video
    video_bytes = getattr(video, "video_bytes", None)
    if video_bytes is None:
        video_bytes = getattr(video, "video", None)
    if video_bytes is None:
        raise RuntimeError("La API no devolvió los datos del video.")
    return video_bytes


# ---------------------------------------------------------------------------
# system_tools
# ---------------------------------------------------------------------------

def get_clipboard_content() -> str:
    """Retorna el texto actual del portapapeles."""
    try:
        import pyperclip  # type: ignore
        text = pyperclip.paste()
        return text if text else "El portapapeles está vacío."
    except ImportError:
        return "[Error: 'pyperclip' no está instalado.]"
    except Exception as exc:  # noqa: BLE001
        return f"[Error al leer el portapapeles: {exc}]"


def get_os_info() -> str:
    """Retorna resumen del SO, hardware y arquitectura del host."""
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
    Ejecuta un comando de solo lectura y retorna su salida.

    Args:
        command_name: Clave del comando: 'ls', 'df', 'pip', 'ps', 'whoami', etc.
        argument: Ruta opcional (solo 'ls' y 'dir').
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
    Abre una URL en el navegador predeterminado.

    Args:
        url: URL a abrir (se añade https:// si falta esquema).
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
    Descarga una URL y retorna su texto plano limpio.

    Args:
        url: URL de la página.
        max_chars: Límite de caracteres (por defecto 8000).
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
    Retorna el contenido de un archivo de texto o PDF.

    Args:
        file_path: Ruta al archivo; acepta ~.
        encoding: Codificación del archivo de texto (por defecto utf-8).
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
    Crea o sobreescribe un archivo de texto UTF-8.

    Args:
        file_path: Ruta del archivo; acepta ~.
        content: Contenido a escribir.
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
    Lista archivos y subdirectorios con sus tamaños.

    Args:
        directory_path: Ruta a listar (por defecto directorio actual).
        show_hidden: Si True, incluye entradas ocultas.
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
    """Captura foto con la webcam y retorna la ruta del JPEG guardado."""
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
        import time as _time
        ts = int(_time.time() * 1_000_000)
        output_path = str(_img_dir() / f"webcam_{ts}.jpg")
        cv2.imwrite(output_path, frame)
        return output_path
    finally:
        cap.release()


def tomar_captura_pantalla() -> str:
    """Captura la pantalla y retorna la ruta del PNG guardado."""
    try:
        import mss  # type: ignore
        import mss.tools  # type: ignore
    except ImportError:
        return "[Error: 'mss' no está instalado. Instala con: pip install mss]"

    try:
        import time as _time
        ts = int(_time.time() * 1_000_000)  # microseconds — avoids same-second collisions
        output_path = str(_img_dir() / f"screenshot_{ts}.png")
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
    Termina el proceso que escucha en el puerto TCP dado.

    Args:
        puerto: Número de puerto TCP (e.g. 8080, 3000).
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
    Genera árbol visual de directorios hasta la profundidad indicada.

    Args:
        ruta: Ruta raíz; acepta ~.
        profundidad: Niveles máximos a mostrar (por defecto 2).
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
    """Lista los contenedores Docker en ejecución."""
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
    Reinicia un contenedor Docker.

    Args:
        nombre_o_id: Nombre o ID del contenedor.
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
    Ejecuta git status en el directorio indicado y retorna la salida.

    Args:
        ruta_proyecto: Ruta al directorio raíz del repositorio; acepta ~.
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
    Retorna las últimas N líneas de un archivo de log.

    Args:
        ruta_archivo: Ruta al archivo de log; acepta ~.
        lineas: Cantidad de líneas finales a devolver (por defecto 50).
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
    Muestra una notificación nativa del SO.

    Args:
        titulo: Título de la notificación.
        mensaje: Texto del cuerpo.
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
    Abre el cliente de correo con un borrador prellenado.

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
    Guarda texto como archivo en el escritorio (o carpeta indicada). Retorna la ruta.

    Args:
        contenido: Texto completo del documento.
        nombre_archivo: Nombre con extensión (e.g. 'reporte.txt', 'resumen.md').
        ruta_carpeta: Carpeta destino; si vacía, usa el escritorio.
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
    Añade texto a un archivo de notas en el escritorio. Retorna la ruta.

    Args:
        texto: Contenido de la nota.
        nombre_archivo: Nombre del archivo (por defecto 'jarvis_nota.txt').
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
# image_gen_tools
# ---------------------------------------------------------------------------

def generar_imagen(descripcion: str, estilo: str = "") -> str:
    """
    Genera una imagen IA desde una descripción y la guarda en ia-tools/img/. Retorna la ruta del PNG.

    Args:
        descripcion: Descripción detallada de la imagen a generar.
        estilo: Estilo visual opcional (e.g. 'fotorrealista', 'anime', 'acuarela', 'pixel art').
    """
    import time as _time

    prompt = f"{descripcion}. Estilo: {estilo}" if estilo.strip() else descripcion
    ts = int(_time.time() * 1_000_000)
    output_path = str(_img_dir() / f"imagen_{ts}.png")

    # 1. Intentar con OpenAI DALL-E 3
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI  # type: ignore
            import requests as _req   # type: ignore

            client = OpenAI(api_key=openai_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            img_data = _req.get(image_url, timeout=30).content
            with open(output_path, "wb") as f:
                f.write(img_data)
            return output_path
        except Exception as exc:  # noqa: BLE001
            return f"[Error al generar imagen con DALL-E 3: {exc}]"

    # 2. Intentar con Google Imagen (requiere GEMINI_API_KEY de Google AI Studio)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai as _ggenai  # type: ignore
            from google.genai import types as _ggenai_types  # type: ignore

            client = _ggenai.Client(api_key=gemini_key)
            response = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=prompt,
                config=_ggenai_types.GenerateImagesConfig(number_of_images=1),
            )
            img_bytes = response.generated_images[0].image.image_bytes
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            return output_path
        except Exception as exc:  # noqa: BLE001
            return f"[Error al generar imagen con Imagen: {exc}]"

    return "[Error: se necesita OPENAI_API_KEY o GEMINI_API_KEY para generar imágenes.]"


def generar_video(descripcion: str, duracion: int = 5, estilo: str = "") -> str:
    """
    Genera un video IA desde una descripción y lo guarda en ia-tools/video/. Retorna la ruta del MP4.

    Args:
        descripcion: Descripción detallada del video a generar.
        duracion: Duración en segundos (por defecto 5; máximo 8 para Veo, 10 para RunwayML).
        estilo: Estilo visual opcional (e.g. 'cinemático', 'animado', 'documental').
    """
    import time as _time

    prompt = f"{descripcion}. Estilo: {estilo}" if estilo.strip() else descripcion
    try:
        requested_duration = int(duracion)
    except (TypeError, ValueError):
        return "[Error: la duración del video debe ser un número entero.]"
    ts = int(_time.time() * 1_000_000)
    output_path = str(_video_dir() / f"video_{ts}.mp4")

    # 1. Intentar con Google Veo (requiere GEMINI_API_KEY)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai as _ggenai  # type: ignore
            from google.genai import types as _ggenai_types  # type: ignore

            client = _ggenai.Client(api_key=gemini_key)
            veo_duration = min(
                _VEO_SUPPORTED_DURATIONS,
                key=lambda supported: abs(supported - requested_duration),
            )
            operation = client.models.generate_videos(
                model=os.getenv("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-preview"),
                prompt=prompt,
                config=_ggenai_types.GenerateVideosConfig(
                    duration_seconds=veo_duration,
                    aspect_ratio="16:9",
                ),
            )
            timeout = 300
            start = _time.time()
            while not operation.done:
                if _time.time() - start > timeout:
                    return "[Error: tiempo límite de 5 minutos superado al generar video con Veo.]"
                _time.sleep(10)
                operation = client.operations.get(operation)

            if operation.error:
                raise RuntimeError(str(operation.error))

            video_bytes = _extract_generated_video_bytes(operation)
            with open(output_path, "wb") as f:
                f.write(video_bytes)
            return output_path
        except Exception as exc:  # noqa: BLE001
            return f"[Error al generar video con Veo: {exc}]"

    # 2. Intentar con RunwayML (requiere RUNWAYML_API_KEY)
    runway_key = os.getenv("RUNWAYML_API_KEY")
    if runway_key:
        try:
            from runwayml import RunwayML  # type: ignore
            import requests as _req  # type: ignore

            client = RunwayML(api_key=runway_key)
            task = client.text_to_video.create(
                model="gen4_turbo",
                prompt_text=prompt,
                duration=min(max(int(duracion), 5), 10),
                ratio="1280:720",
            )
            timeout = 180
            start = _time.time()
            while task.status not in ("SUCCEEDED", "FAILED"):
                if _time.time() - start > timeout:
                    return "[Error: tiempo límite de 3 minutos superado al generar video con RunwayML.]"
                _time.sleep(8)
                task = client.tasks.retrieve(task.id)

            if task.status == "FAILED":
                raise RuntimeError(f"Tarea fallida: {task.failure}")

            video_url = task.output[0]
            video_response = _req.get(video_url, timeout=60)
            video_response.raise_for_status()
            video_data = video_response.content
            with open(output_path, "wb") as f:
                f.write(video_data)
            return output_path
        except Exception as exc:  # noqa: BLE001
            return f"[Error al generar video con RunwayML: {exc}]"

    return "[Error: se necesita GEMINI_API_KEY o RUNWAYML_API_KEY para generar videos.]"


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
    # image_gen_tools
    generar_imagen,
    # video_gen_tools
    generar_video,
    # Configuración y extensibilidad (requieren autorización en ai_agent.py)
    configurar_ruta_imagenes,
    crear_tool,
]

ALL_TOOLS.extend(_load_custom_tools())
