# ai-tools-hub — Referencia de funciones para agentes de IA

> **Propósito de este documento:**  
> Contexto completo de la librería `ai-tools-hub` para que una IA agéntica pueda implementar, integrar o extender esta biblioteca en otro proyecto.  
> Cada función está documentada con: firma, parámetros, valor de retorno, comportamiento, errores posibles y ejemplo de uso.

---

## Información general del paquete

| Campo | Valor |
|---|---|
| Nombre del paquete | `ai-tools-hub` |
| Versión | `0.1.0` |
| Python mínimo | 3.9 |
| Licencia | MIT |
| Repositorio | https://github.com/EL-SICRIO-R3/ia-tools |

### Instalación

```bash
# Solo la librería base
pip install -e .

# Base + SDK de Google Gemini
pip install -e ".[gemini]"
```

### Import rápido (todas las herramientas)

```python
from ai_tools_hub import ALL_TOOLS
```

`ALL_TOOLS` es una lista plana de todas las funciones callable; se pasa directamente al parámetro `tools=` de un modelo de Gemini (o cualquier LLM compatible con function calling).

### Dependencias

| Paquete | Propósito |
|---|---|
| `pyperclip` | Acceso al portapapeles |
| `requests` | Descargas HTTP |
| `beautifulsoup4` | Parseo HTML |
| `pypdf` | Extracción de texto de PDFs |
| `psutil` | Inspección de procesos y red |
| `opencv-python` | Captura de webcam |
| `plyer` *(opcional)* | Notificaciones nativas del SO |
| `google-generativeai` *(opcional)* | SDK de Gemini |

---

## Estructura de módulos

```
ai_tools_hub/
├── __init__.py          # API pública y lista ALL_TOOLS
├── system_tools.py      # SO, portapapeles, comandos de terminal
├── web_tools.py         # Navegador, extracción de texto de URLs
├── file_tools.py        # Leer / crear archivos, listar directorios
├── vision_tools.py      # Captura de webcam
├── dev_tools.py         # Gestión de puertos, árbol de directorios, Docker
└── interaction_tools.py # Notificaciones de escritorio, cliente de correo
```

---

## Módulo `system_tools`

### `get_clipboard_content() -> str`

**Descripción:** Lee el texto actualmente copiado en el portapapeles del sistema.

**Parámetros:** Ninguno.

**Retorna:**
- El texto del portapapeles como `str`.
- `"The clipboard is currently empty."` si el portapapeles está vacío.
- Un mensaje de error `str` si `pyperclip` no está instalado o si ocurre un fallo.

**Comportamiento:** Nunca lanza excepciones; siempre retorna una cadena.

**Ejemplo:**
```python
from ai_tools_hub.system_tools import get_clipboard_content

resultado = get_clipboard_content()
# → "Texto que el usuario copió" o "The clipboard is currently empty."
```

---

### `get_os_info() -> str`

**Descripción:** Devuelve un resumen del sistema operativo y el hardware del host.

**Parámetros:** Ninguno.

**Retorna:** Un `str` multilínea con los siguientes campos:
- `OS`: cadena completa de la plataforma (e.g. `Linux-6.1.0-x86_64-with-glibc2.36`)
- `System`: nombre del SO (e.g. `Linux`, `Windows`, `Darwin`)
- `Release`: versión del kernel/SO
- `Version`: versión detallada
- `Machine`: arquitectura de hardware (e.g. `x86_64`)
- `Processor`: nombre del procesador (puede ser `N/A`)
- `Python`: versión de Python en uso
- `Architecture`: bits del intérprete y formato ELF/EXE

**Ejemplo:**
```python
from ai_tools_hub.system_tools import get_os_info

print(get_os_info())
# OS: Linux-6.1.0-x86_64-with-glibc2.36
# System: Linux
# Release: 6.1.0
# ...
```

---

### `run_terminal_command(command_name: str, argument: str = "") -> str`

**Descripción:** Ejecuta un comando de terminal de una lista de permitidos (solo lectura/informativos) y devuelve su salida.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `command_name` | `str` | ✅ | Clave del comando a ejecutar (ver lista de permitidos). |
| `argument` | `str` | ❌ (default `""`) | Argumento de ruta opcional, usado únicamente por `ls` y `dir`. |

**Comandos permitidos (allow-list):**

| Clave | Comando real | Plataforma |
|---|---|---|
| `python` | `python --version` | Todas |
| `pip` | `pip list` | Todas |
| `ls` | `ls -lh [ruta]` | POSIX |
| `pwd` | `pwd` | POSIX |
| `whoami` | `whoami` | POSIX |
| `df` | `df -h` | POSIX |
| `free` | `free -h` | POSIX |
| `uname` | `uname -a` | POSIX |
| `uptime` | `uptime` | POSIX |
| `ps` | `ps aux` | POSIX |
| `env` | `env` | POSIX |
| `date` | `date` | POSIX |
| `dir` | `dir` | Windows |
| `systeminfo` | `systeminfo` | Windows |
| `tasklist` | `tasklist` | Windows |
| `ipconfig` | `ipconfig` | Windows |
| `ver` | `ver` | Windows |

**Retorna:**
- `stdout` del comando (y `stderr` si existe), como `str`.
- Mensaje de error descriptivo si el comando no está en la allow-list, no se encuentra en el sistema, o excede 30 segundos de ejecución.

**Seguridad:** Los comandos destructivos (`rm`, `del`, `format`, etc.) son imposibles. Los comandos se pasan como lista a `subprocess.run` — sin interpolación de shell.

**Ejemplo:**
```python
from ai_tools_hub.system_tools import run_terminal_command

print(run_terminal_command("ls", "/tmp"))
print(run_terminal_command("df"))
print(run_terminal_command("pip"))
```

---

## Módulo `web_tools`

### `open_browser(url: str) -> str`

**Descripción:** Abre una URL en el navegador predeterminado del sistema.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `url` | `str` | ✅ | La URL a abrir. Si no tiene esquema, se añade `https://` automáticamente. |

**Retorna:**
- `"Browser opened successfully for: <url>"` si la operación fue exitosa.
- Mensaje de error `str` si la URL está vacía, el sistema no pudo abrir el navegador, o ocurre una excepción.

**Comportamiento:**
- Si `url` no empieza por `http://`, `https://` o `file://`, antepone `https://`.
- Usa `webbrowser.open()` de la biblioteca estándar de Python.

**Ejemplo:**
```python
from ai_tools_hub.web_tools import open_browser

open_browser("python.org")           # abre https://python.org
open_browser("https://github.com")
```

---

### `extract_text_from_url(url: str, max_chars: int = 8000) -> str`

**Descripción:** Descarga una página web y devuelve su texto plano limpio (scripts y estilos eliminados).

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `url` | `str` | ✅ | URL de la página a scrapear. |
| `max_chars` | `int` | ❌ (default `8000`) | Límite de caracteres del texto devuelto. |

**Retorna:**
- El texto plano de la página como `str`, con líneas en blanco consecutivas colapsadas.
- Si el texto supera `max_chars`, se trunca y se añade `[... content truncated at N characters ...]`.
- Mensaje de error `str` en caso de timeout, error HTTP, fallo de conexión o librería faltante.

**Comportamiento:**
- Elimina etiquetas `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>`, `<aside>`, `<noscript>`.
- Timeout de red: **15 segundos**.
- Requiere: `requests`, `beautifulsoup4`.

**Ejemplo:**
```python
from ai_tools_hub.web_tools import extract_text_from_url

texto = extract_text_from_url("https://en.wikipedia.org/wiki/Python_(programming_language)")
print(texto[:500])

# Limitar a 3000 caracteres
resumen = extract_text_from_url("https://example.com", max_chars=3000)
```

---

## Módulo `file_tools`

### `read_file(file_path: str, encoding: str = "utf-8") -> str`

**Descripción:** Lee y devuelve el contenido completo de un archivo de texto o PDF.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `file_path` | `str` | ✅ | Ruta al archivo. Acepta `~` (tilde expansion). |
| `encoding` | `str` | ❌ (default `"utf-8"`) | Codificación para archivos de texto plano. |

**Retorna:**
- El contenido del archivo como `str`.
- Para archivos `.pdf`: el texto extraído de todas las páginas, separadas por `\n\n`.
- Mensajes de error descriptivos en caso de: archivo no encontrado, es un directorio, error de decodificación, permiso denegado, o `pypdf` no instalado para PDFs.

**Comportamiento:**
- Detecta automáticamente archivos PDF por extensión (`.pdf`, case-insensitive).
- Expande `~` a la carpeta home del usuario.
- Resuelve rutas relativas a absolutas.

**Ejemplo:**
```python
from ai_tools_hub.file_tools import read_file

# Texto plano
contenido = read_file("/home/user/notas.txt")

# PDF
texto_pdf = read_file("~/documentos/informe.pdf")

# Encoding alternativo
contenido_latin = read_file("/tmp/legacy.txt", encoding="latin-1")
```

---

### `create_file(file_path: str, content: str, overwrite: bool = False) -> str`

**Descripción:** Crea un archivo de texto UTF-8 en la ruta especificada.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `file_path` | `str` | ✅ | Ruta del archivo a crear. Acepta `~`. |
| `content` | `str` | ✅ | Contenido a escribir en el archivo. |
| `overwrite` | `bool` | ❌ (default `False`) | Si `True`, reemplaza el archivo si ya existe. |

**Retorna:**
- `"File created successfully: <ruta> (<bytes> bytes)"` al crear.
- `"File updated successfully: <ruta> (<bytes> bytes)"` al sobreescribir.
- Mensaje de error `str` si el archivo ya existe y `overwrite=False`, permiso denegado, u otra excepción.

**Comportamiento:**
- Crea directorios padre automáticamente (`mkdir -p` equivalente).
- Siempre escribe en UTF-8.

**Ejemplo:**
```python
from ai_tools_hub.file_tools import create_file

create_file("/tmp/saludo.txt", "Hola, mundo!")
create_file("/tmp/saludo.txt", "Nuevo contenido", overwrite=True)
create_file("~/proyecto/config/settings.json", '{"debug": true}')
```

---

### `list_directory(directory_path: str = ".", show_hidden: bool = False) -> str`

**Descripción:** Lista los archivos y subdirectorios de una ruta con sus tamaños.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `directory_path` | `str` | ❌ (default `"."`) | Ruta del directorio a listar. |
| `show_hidden` | `bool` | ❌ (default `False`) | Si `True`, incluye archivos y carpetas ocultos (que empiezan con `.`). |

**Retorna:**
- Un `str` multilínea formateado con:
  - Cabecera con la ruta absoluta resuelta.
  - Cada entrada con icono (`📁` directorio, `📄` archivo) y tamaño legible (B, KB, MB…).
  - Resumen con conteo total de archivos y directorios.
- Mensaje de error si el directorio no existe, es un archivo, o hay permiso denegado.

**Comportamiento:**
- Ordena: primero directorios, luego archivos (alfabéticamente dentro de cada grupo).
- Los tamaños se expresan en la unidad más compacta (B, KB, MB, GB, TB, PB).

**Ejemplo:**
```python
from ai_tools_hub.file_tools import list_directory

print(list_directory("/tmp"))
print(list_directory(".", show_hidden=True))  # incluye archivos ocultos
```

---

## Módulo `vision_tools`

### `capturar_foto_webcam() -> str`

**Descripción:** Captura una foto con la webcam principal del sistema y la guarda como JPEG.

**Parámetros:** Ninguno.

**Retorna:**
- La ruta absoluta del archivo de imagen generado (`str`), e.g. `/tmp/webcam_snapshot.jpg`.
- Mensaje de error `str` si la cámara no está disponible, OpenCV no está instalado, o la captura falla.

**Comportamiento:**
- Usa la cámara con índice `0` (primera webcam).
- Guarda el archivo en el directorio temporal del sistema como `webcam_snapshot.jpg`.
- Libera el recurso de la cámara (`cap.release()`) incluso si ocurre un error.
- Requiere: `opencv-python`.

**Ejemplo:**
```python
from ai_tools_hub.vision_tools import capturar_foto_webcam

ruta = capturar_foto_webcam()
print(ruta)  # → /tmp/webcam_snapshot.jpg
```

---

## Módulo `dev_tools`

### `liberar_puerto(puerto: int) -> str`

**Descripción:** Termina el proceso que está escuchando en el puerto TCP especificado.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `puerto` | `int` | ✅ | Número de puerto TCP (e.g. `8080`, `4200`, `3000`). |

**Retorna:**
- `"✅ Proceso '<nombre>' (PID <n>) en puerto <puerto> terminado."` si se mató el proceso.
- `"ℹ️  El puerto <puerto> ya estaba libre."` si no había proceso escuchando.
- Mensaje de error si el proceso ya no existe, el acceso fue denegado (sin permisos de admin), o falla la operación.

**Comportamiento:**
- Itera todas las conexiones TCP activas con estado `LISTEN`.
- Usa `psutil.Process.terminate()` seguido de `wait(timeout=5)`.
- Requiere: `psutil`.

**Ejemplo:**
```python
from ai_tools_hub.dev_tools import liberar_puerto

print(liberar_puerto(4200))   # Libera el servidor Angular
print(liberar_puerto(8080))   # Libera el servidor Spring Boot
```

---

### `obtener_arbol_directorios(ruta: str, profundidad: int = 2) -> str`

**Descripción:** Genera un árbol de directorios de estilo visual hasta el nivel de profundidad indicado.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ruta` | `str` | ✅ | Ruta raíz del árbol. Acepta `~`. |
| `profundidad` | `int` | ❌ (default `2`) | Máximo de niveles a mostrar (1 = solo hijos directos). |

**Retorna:**
- Un `str` multilínea con el árbol visual usando conectores (`├──`, `└──`, `│`).
- Mensaje de error si la ruta no existe, es un archivo, o hay permiso denegado.

**Directorios ignorados automáticamente:**
`node_modules`, `.git`, `venv`, `.venv`, `__pycache__`, `dist`, `target`, `build`, `.idea`, `.vscode`, `.mypy_cache`, `.pytest_cache`, `.tox`, `coverage`, `.angular`, `.gradle`, `.mvn`

**Comportamiento:**
- Muestra primero directorios, luego archivos (ordenados alfabéticamente).
- Usa recursión interna para construir el árbol.

**Ejemplo:**
```python
from ai_tools_hub.dev_tools import obtener_arbol_directorios

print(obtener_arbol_directorios("/home/user/mi-proyecto", profundidad=3))
# mi-proyecto/
# ├── src/
# │   ├── main.py
# │   └── utils.py
# └── README.md
```

---

### `listar_contenedores_activos() -> str`

**Descripción:** Lista todos los contenedores Docker que están en ejecución.

**Parámetros:** Ninguno.

**Retorna:**
- Una cadena formateada con cada contenedor en línea: `<ID>: <nombre> - <estado>`.
- `"ℹ️  No hay contenedores activos en este momento."` si Docker está corriendo pero no hay contenedores.
- Mensaje de error si Docker no está instalado/en PATH, el comando falla, o excede 15 segundos.

**Comportamiento:**
- Ejecuta `docker ps --format "{{.ID}}: {{.Names}} - {{.Status}}"`.
- Timeout: **15 segundos**.

**Ejemplo:**
```python
from ai_tools_hub.dev_tools import listar_contenedores_activos

print(listar_contenedores_activos())
# abc123def456: mi-app - Up 2 hours
# 789xyz012ghi: postgres-db - Up 3 days
```

---

### `reiniciar_contenedor(nombre_o_id: str) -> str`

**Descripción:** Reinicia un contenedor Docker identificado por su nombre o ID.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `nombre_o_id` | `str` | ✅ | Nombre o ID (completo o parcial) del contenedor Docker. |

**Retorna:**
- `"✅ Contenedor '<nombre_o_id>' reiniciado correctamente."` si tuvo éxito.
- Mensaje de error si el nombre/ID está vacío, el contenedor no existe, Docker no está instalado, el comando falla, o excede 60 segundos.

**Comportamiento:**
- Ejecuta `docker restart <nombre_o_id>`.
- Timeout: **60 segundos**.
- Valida que `nombre_o_id` no sea una cadena vacía antes de ejecutar.

**Ejemplo:**
```python
from ai_tools_hub.dev_tools import reiniciar_contenedor

print(reiniciar_contenedor("mi-app"))
print(reiniciar_contenedor("abc123def456"))
```

---

## Módulo `interaction_tools`

### `mostrar_notificacion(titulo: str, mensaje: str) -> str`

**Descripción:** Muestra una notificación nativa del sistema operativo.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `titulo` | `str` | ✅ | Título de la notificación. |
| `mensaje` | `str` | ✅ | Cuerpo / texto de la notificación. |

**Retorna:**
- `"Notificación enviada correctamente."` si se mostró la notificación.
- `"Error: La dependencia 'plyer' no está instalada."` si falta la librería.
- Mensaje de error `str` en caso de excepción.

**Comportamiento:**
- Usa la librería `plyer` (debe instalarse aparte: `pip install plyer`).
- La notificación permanece visible durante **10 segundos**.
- El nombre de la app en la notificación es `"AI Tools Hub"`.
- Compatible con macOS, Linux (con soporte de notificaciones), y Windows.

**Ejemplo:**
```python
from ai_tools_hub.interaction_tools import mostrar_notificacion

mostrar_notificacion("Tarea completada", "El análisis de datos ha finalizado.")
mostrar_notificacion("Alerta", "Se detectó un error en el proceso.")
```

---

### `redactar_email(destinatario: str, asunto: str, cuerpo: str) -> str`

**Descripción:** Abre el cliente de correo electrónico predeterminado con un borrador prellenado.

**Parámetros:**
| Nombre | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `destinatario` | `str` | ✅ | Dirección de correo del destinatario (e.g. `"usuario@empresa.com"`). |
| `asunto` | `str` | ✅ | Asunto del correo. Se codifica automáticamente para la URI. |
| `cuerpo` | `str` | ✅ | Cuerpo del mensaje. Se codifica automáticamente para la URI. |

**Retorna:**
- `"Cliente de correo abierto correctamente."` si el cliente se abrió.
- `"Error: No se pudo abrir el cliente de correo..."` si `webbrowser.open` devolvió `False`.
- Mensaje de error `str` en caso de excepción.

**Comportamiento:**
- Construye una URI `mailto:` con los parámetros `subject` y `body` codificados con `urllib.parse.quote`.
- Usa `webbrowser.open()` de la biblioteca estándar de Python.
- El cliente de correo se abre con todos los campos prellenados, pero el usuario debe enviar el mensaje manualmente.

**Ejemplo:**
```python
from ai_tools_hub.interaction_tools import redactar_email

redactar_email(
    destinatario="equipo@empresa.com",
    asunto="Reporte diario de análisis",
    cuerpo="Adjunto el informe del día. Saludos."
)
```

---

## Principios de diseño

| Principio | Descripción |
|---|---|
| **Docstrings-first** | Cada función tiene una docstring concisa (estilo telegráfico) que el LLM usa para decidir cuándo y cómo invocar la herramienta. |
| **Type hints estrictos** | Todos los parámetros y valores de retorno están anotados (`str`, `int`, `bool`). |
| **Error-safe** | Las excepciones siempre son capturadas y retornadas como `str` descriptivo — el agente nunca crashea la aplicación. |
| **Cross-platform** | Maneja diferencias entre macOS, Linux y Windows de forma transparente. |
| **Zero config** | Importar y usar — no requiere API keys ni archivos de configuración para las herramientas base. |

---

## Seguridad

- **Allow-list de terminal**: `run_terminal_command` solo ejecuta un conjunto pequeño de comandos de solo lectura. Operaciones destructivas son imposibles.
- **Sin inyección de shell**: Los comandos se pasan como listas a `subprocess.run` — sin interpolación de cadenas en shell.
- **Timeouts**: Peticiones de red: 15 s. Subprocesos: 30–60 s según la función.
- **Retornos graciosos**: Toda función retorna `str` en caso de fallo — el agente siempre puede reportar el problema al usuario.

---

## Uso completo con Gemini

```python
import os
import google.generativeai as genai
from ai_tools_hub import ALL_TOOLS

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

model = genai.GenerativeModel(
    model_name="models/gemini-2.5-flash-lite",
    tools=ALL_TOOLS,
)

chat = model.start_chat(enable_automatic_function_calling=True)
response = chat.send_message("¿Qué archivos hay en mi directorio actual?")
print(response.text)
```

> **Nota para la IA agéntica:** Cada función en `ALL_TOOLS` puede ser registrada como tool en cualquier LLM compatible (OpenAI, Anthropic, Gemini, etc.) que soporte function calling / tool use. Las funciones son callables de Python con type hints y docstrings, que muchos SDKs inspeccionan automáticamente para generar el esquema de herramienta.
