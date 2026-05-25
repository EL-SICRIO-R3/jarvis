"""
ai_agent.py
-----------
Clase ``JarvisAgent`` que gestiona:
  - La conexión con la API de Google Gemini (con fallback a OpenAI).
  - El historial de conversación en memoria.
  - El System Prompt que define la personalidad y capacidades de Jarvis.
  - La ejecución del ciclo de Function Calling: detecta cuándo el LLM quiere
    invocar una herramienta local, la ejecuta y devuelve el resultado.

Variables de entorno necesarias (al menos una):
  - GEMINI_API_KEY  → clave para Google Gemini
  - OPENAI_API_KEY  → clave para OpenAI (fallback)
"""

from __future__ import annotations

import os
from typing import Optional

from ai_tools_hub import ALL_TOOLS
from tools import TOOLS_MAP, JARVIS_CUSTOM_CALLABLES
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Lista combinada de herramientas para Gemini (callables con type hints y
# docstrings — Gemini genera el esquema automáticamente).
# ---------------------------------------------------------------------------

GEMINI_TOOLS = JARVIS_CUSTOM_CALLABLES + ALL_TOOLS

# ---------------------------------------------------------------------------
# Esquema de herramientas para OpenAI (Function Calling manual)
# ---------------------------------------------------------------------------

OPENAI_TOOLS = [
    # ── Jarvis-específicas ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "copiar_al_portapapeles",
            "description": "Copia un texto al portapapeles del sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto que se copiará al portapapeles."}
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_vscode",
            "description": "Abre Visual Studio Code, opcionalmente en una ruta específica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del directorio o archivo a abrir en VSCode."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_aplicacion",
            "description": "Abre una aplicación del sistema por nombre (p. ej. 'Safari', 'Notepad').",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre de la aplicación a abrir."}
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_navegador",
            "description": (
                "Abre el navegador predeterminado en una URL o dominio, o realiza una búsqueda en Google. "
                "Usa esta herramienta cuando el usuario pida: abrir una página web, navegar a un sitio, "
                "buscar algo en internet, abrir una pestaña nueva con X, ver algo en YouTube, "
                "visitar un sitio, buscar en Google, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL o dominio a abrir. Omitir si se usa el parámetro buscar.",
                    },
                    "buscar": {
                        "type": "string",
                        "description": "Término o frase para buscar en Google.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardar_nota",
            "description": "Guarda texto en un archivo de notas en el escritorio del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Contenido de la nota."},
                    "nombre_archivo": {"type": "string", "description": "Nombre del archivo de destino (opcional)."},
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardar_documento",
            "description": "Genera y guarda un documento de texto (informe, reporte, resumen, carta, lista, etc.) en el escritorio del usuario. Úsala siempre que el usuario pida 'genera un documento', 'crea un informe', 'escribe un reporte', 'guarda un resumen', 'hazme una carta', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "contenido": {"type": "string", "description": "Contenido completo del documento."},
                    "nombre_archivo": {"type": "string", "description": "Nombre del archivo con extensión."},
                    "ruta_carpeta": {"type": "string", "description": "Carpeta de destino. Si se omite, se guarda en el escritorio."},
                },
                "required": ["contenido"],
            },
        },
    },
    # ── ai-tools-hub / system ─────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_clipboard_content",
            "description": "Lee y retorna el texto actual del portapapeles del sistema.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_os_info",
            "description": "Devuelve un resumen detallado del sistema operativo y el hardware del host.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Ejecuta un comando de terminal de una lista de permitidos (solo lectura/informativos) y devuelve su salida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command_name": {"type": "string", "description": "Clave del comando a ejecutar (e.g. 'ls', 'df', 'pip', 'ps')."},
                    "argument": {"type": "string", "description": "Argumento de ruta opcional (solo para 'ls' y 'dir')."},
                },
                "required": ["command_name"],
            },
        },
    },
    # ── ai-tools-hub / web ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Abre una URL en el navegador predeterminado del sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "La URL a abrir. Si no tiene esquema, se añade https:// automáticamente."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_text_from_url",
            "description": "Descarga una página web y devuelve su texto plano limpio (scripts y estilos eliminados).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL de la página a extraer."},
                    "max_chars": {"type": "integer", "description": "Límite de caracteres del texto devuelto (por defecto 8000)."},
                },
                "required": ["url"],
            },
        },
    },
    # ── ai-tools-hub / file ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee y devuelve el contenido completo de un archivo de texto o PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Ruta al archivo. Acepta ~ (tilde expansion)."},
                    "encoding": {"type": "string", "description": "Codificación (por defecto utf-8)."},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Crea un archivo de texto UTF-8 en la ruta especificada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Ruta del archivo a crear. Acepta ~."},
                    "content": {"type": "string", "description": "Contenido a escribir en el archivo."},
                    "overwrite": {"type": "boolean", "description": "Si True, reemplaza el archivo si ya existe."},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Lista los archivos y subdirectorios de una ruta con sus tamaños.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory_path": {"type": "string", "description": "Ruta del directorio a listar (por defecto el directorio actual)."},
                    "show_hidden": {"type": "boolean", "description": "Si True, incluye archivos y carpetas ocultos."},
                },
                "required": [],
            },
        },
    },
    # ── ai-tools-hub / vision ─────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "capturar_foto_webcam",
            "description": "Captura una foto con la webcam principal del sistema y la guarda como JPEG. Retorna la ruta del archivo.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── ai-tools-hub / dev ────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "liberar_puerto",
            "description": "Termina el proceso que está escuchando en el puerto TCP especificado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "puerto": {"type": "integer", "description": "Número de puerto TCP (e.g. 8080, 4200, 3000)."}
                },
                "required": ["puerto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_arbol_directorios",
            "description": "Genera un árbol visual de directorios hasta el nivel de profundidad indicado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta raíz del árbol. Acepta ~."},
                    "profundidad": {"type": "integer", "description": "Máximo de niveles a mostrar (por defecto 2)."},
                },
                "required": ["ruta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_contenedores_activos",
            "description": "Lista todos los contenedores Docker que están en ejecución.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reiniciar_contenedor",
            "description": "Reinicia un contenedor Docker identificado por su nombre o ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_o_id": {"type": "string", "description": "Nombre o ID del contenedor Docker."}
                },
                "required": ["nombre_o_id"],
            },
        },
    },
    # ── ai-tools-hub / interaction ────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "mostrar_notificacion",
            "description": "Muestra una notificación nativa del sistema operativo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título de la notificación."},
                    "mensaje": {"type": "string", "description": "Cuerpo / texto de la notificación."},
                },
                "required": ["titulo", "mensaje"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redactar_email",
            "description": "Abre el cliente de correo electrónico predeterminado con un borrador prellenado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destinatario": {"type": "string", "description": "Dirección de correo del destinatario."},
                    "asunto": {"type": "string", "description": "Asunto del correo."},
                    "cuerpo": {"type": "string", "description": "Cuerpo del mensaje."},
                },
                "required": ["destinatario", "asunto", "cuerpo"],
            },
        },
    },
]

SYSTEM_PROMPT = """Eres Jarvis, asistente personal de IA con carácter propio.

Personalidad:
- Directo e inteligente. No eres servil ni dices frases vacías como "¡Por supuesto!"
  o "¡Claro que sí!". Vas al grano.
- Tienes un punto de ironía sutil cuando el contexto lo permite, pero sin pasarte.
- Culto y articulado: hablas como una persona real, no como un manual de instrucciones.
- Opinas cuando es relevante, con tacto pero sin adulación.
- Adaptas el tono: formal si el usuario lo es, más relajado si la conversación lo pide.

Capacidades:
- Leer y escribir en el portapapeles del sistema.
- Abrir aplicaciones y proyectos en VS Code.
- Abrir el navegador en cualquier URL y realizar búsquedas en Google.
- Extraer el texto de cualquier página web.
- Guardar notas rápidas en el escritorio.
- Generar y guardar documentos (informes, reportes, resúmenes, cartas, listas) en el escritorio.
- Leer archivos de texto y PDFs.
- Crear archivos y listar directorios.
- Obtener información del sistema operativo (básica y detallada).
- Ejecutar comandos de terminal de solo lectura (ls, df, ps, pip, etc.).
- Capturar fotos con la webcam.
- Liberar puertos TCP ocupados.
- Mostrar el árbol de directorios de un proyecto.
- Gestionar contenedores Docker (listar y reiniciar).
- Mostrar notificaciones nativas del sistema operativo.
- Redactar y abrir borradores de correo en el cliente de email predeterminado.

=== REGLA OBLIGATORIA: GENERACIÓN DE DOCUMENTOS ===
Si el usuario pide crear, generar, escribir, elaborar, redactar o preparar cualquier tipo
de documento, informe, reporte, resumen, carta, lista, análisis, plan o texto estructurado:
  1. DEBES llamar a la herramienta `guardar_documento` con el contenido COMPLETO.
  2. NUNCA incluyas el contenido del documento en tu respuesta de texto.
  3. Tras guardar, responde solo con una confirmación breve del nombre del archivo.

Ejemplo CORRECTO:    → llamas a guardar_documento({contenido: "...", nombre_archivo: "informe.txt"})
                     → respondes: "Guardado como informe.txt en el escritorio."
Ejemplo INCORRECTO:  → responder el texto del documento sin llamar a guardar_documento.
=====================================================

Reglas operativas:
1. Responde en el idioma del usuario (normalmente español).
2. Respuestas cortas por defecto; desarrolla solo cuando la complejidad lo exige.
3. Usa la herramienta apropiada cuando el usuario pide ejecutar algo en la computadora.
4. Si no sabes algo, dilo claramente. Nunca inventes información.
"""


class JarvisAgent:
    """
    Agente de IA de Jarvis.

    Gestiona la comunicación con el LLM seleccionado (Gemini o OpenAI),
    mantiene el historial de conversación y ejecuta el ciclo de
    Function Calling cuando el modelo solicita invocar herramientas locales.

    Args:
        provider: Motor LLM a utilizar. Valores válidos: ``'gemini'``, ``'openai'``.
                  Si no se especifica, se detecta automáticamente según las claves
                  de entorno disponibles.
    """

    SUPPORTED_PROVIDERS = ("gemini", "openai")

    def __init__(self, provider: Optional[str] = None) -> None:
        self._provider = self._resolve_provider(provider)
        self._history: list[dict] = []
        self.last_saved_path: Optional[str] = None  # última ruta de doc/nota guardada

        if self._provider == "gemini":
            self._init_gemini()
        else:
            self._init_openai()

    # ------------------------------------------------------------------
    # Inicialización de proveedores
    # ------------------------------------------------------------------

    def _resolve_provider(self, provider: Optional[str]) -> str:
        """
        Determina qué proveedor LLM usar.

        Orden de prioridad:
          1. Parámetro ``provider`` explícito.
          2. Variable de entorno ``GEMINI_API_KEY`` disponible → ``'gemini'``.
          3. Variable de entorno ``OPENAI_API_KEY`` disponible → ``'openai'``.

        Raises:
            EnvironmentError: Si no se encuentra ninguna clave de API válida.
        """
        if provider and provider in self.SUPPORTED_PROVIDERS:
            return provider

        if os.getenv("GEMINI_API_KEY"):
            return "gemini"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"

        raise EnvironmentError(
            "No se encontró ninguna clave de API. "
            "Define GEMINI_API_KEY o OPENAI_API_KEY como variable de entorno."
        )

    def _init_gemini(self) -> None:
        """Inicializa el cliente de Google Gemini."""
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self._client = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction=SYSTEM_PROMPT,
            tools=GEMINI_TOOLS,
        )
        self._chat = self._client.start_chat(history=[])

    def _init_openai(self) -> None:
        """Inicializa el cliente de OpenAI."""
        from openai import OpenAI  # type: ignore

        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    @property
    def provider(self) -> str:
        """Retorna el nombre del proveedor LLM activo."""
        return self._provider

    def reset_history(self) -> None:
        """Reinicia el historial de conversación."""
        self._history = []
        if self._provider == "gemini":
            self._chat = self._client.start_chat(history=[])

    def send_message(self, user_message: str) -> str:
        """
        Envía un mensaje del usuario al LLM y devuelve la respuesta final.

        Ejecuta el ciclo completo de Function Calling si el modelo solicita
        invocar herramientas locales.

        Args:
            user_message: Texto del usuario.

        Returns:
            str: Respuesta textual final del asistente.
        """
        if self._provider == "gemini":
            return self._send_gemini(user_message)
        return self._send_openai(user_message)

    def send_message_with_image(self, user_message: str, image_path: str) -> str:
        """Envía un mensaje con imagen al LLM (visión multimodal).

        Args:
            user_message: Texto del usuario describiendo qué hacer con la imagen.
            image_path: Ruta absoluta al archivo de imagen.

        Returns:
            str: Respuesta textual del asistente.
        """
        if self._provider == "gemini":
            return self._send_gemini_with_image(user_message, image_path)
        # OpenAI vision fallback — si no hay soporte, degradar a texto
        return self._send_openai(f"[El usuario adjuntó una imagen: {image_path}]\n{user_message}")

    # ------------------------------------------------------------------
    # Implementación por proveedor
    # ------------------------------------------------------------------

    def _send_gemini(self, user_message: str) -> str:
        """
        Ciclo de mensajes para Google Gemini con Function Calling.

        Args:
            user_message: Texto del usuario.

        Returns:
            str: Respuesta textual final del asistente.
        """
        import google.generativeai as genai  # type: ignore

        response = self._chat.send_message(user_message)

        # Ciclo de function calling
        while True:
            # Recolectar todas las llamadas a herramientas de la respuesta
            tool_calls = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if hasattr(part, "function_call") and part.function_call.name
            ]

            if not tool_calls:
                break

            # Ejecutar cada herramienta y construir las respuestas
            tool_responses = []
            for call in tool_calls:
                resultado = self._execute_tool(call.name, dict(call.args))
                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=call.name,
                            response={"result": resultado},
                        )
                    )
                )

            response = self._chat.send_message(tool_responses)

        # Extraer texto de la respuesta final
        try:
            return response.text
        except ValueError:
            return "[No se pudo obtener una respuesta textual del modelo.]"

    def _send_gemini_with_image(self, user_message: str, image_path: str) -> str:
        """Envía texto + imagen a Gemini (visión multimodal)."""
        import google.generativeai as genai  # type: ignore
        from PIL import Image  # type: ignore

        try:
            img = Image.open(image_path)
        except Exception as exc:
            return f"[No se pudo abrir la imagen: {exc}]"

        response = self._chat.send_message([user_message, img])

        # Ciclo de function calling (igual que _send_gemini)
        while True:
            tool_calls = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if hasattr(part, "function_call") and part.function_call.name
            ]
            if not tool_calls:
                break
            tool_responses = []
            for call in tool_calls:
                resultado = self._execute_tool(call.name, dict(call.args))
                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=call.name,
                            response={"result": resultado},
                        )
                    )
                )
            response = self._chat.send_message(tool_responses)

        try:
            return response.text
        except ValueError:
            return "[No se pudo obtener una respuesta textual del modelo.]"

    def _send_openai(self, user_message: str) -> str:
        """
        Ciclo de mensajes para OpenAI con Function Calling.

        Args:
            user_message: Texto del usuario.

        Returns:
            str: Respuesta textual final del asistente.
        """
        import json

        # Agregar mensaje del usuario al historial
        self._history.append({"role": "user", "content": user_message})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._history

        # Ciclo de function calling
        while True:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
            )

            message = response.choices[0].message

            if not message.tool_calls:
                # Respuesta textual final
                assistant_text = message.content or ""
                self._history.append({"role": "assistant", "content": assistant_text})
                return assistant_text

            # Agregar la respuesta del asistente con las tool_calls
            messages.append(message)

            # Ejecutar cada herramienta
            for tool_call in message.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                resultado = self._execute_tool(tool_call.function.name, args)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": resultado,
                    }
                )

    # ------------------------------------------------------------------
    # Ejecución de herramientas
    # ------------------------------------------------------------------

    def _execute_tool(self, nombre: str, args: dict) -> str:
        """
        Busca y ejecuta una herramienta local por nombre.

        Args:
            nombre: Nombre de la función a invocar (debe existir en ``TOOLS_MAP``).
            args:   Argumentos de la función como diccionario.

        Returns:
            str: Resultado de la ejecución o mensaje de error.
        """
        func = TOOLS_MAP.get(nombre)
        if func is None:
            return f"[Herramienta '{nombre}' no encontrada.]"
        try:
            resultado = str(func(**args))
            if nombre in ("guardar_nota", "guardar_documento") and "en: " in resultado:
                self.last_saved_path = resultado.split("en: ", 1)[1].strip()
            return resultado
        except TypeError as exc:
            return f"[Error de argumentos en '{nombre}': {exc}]"
        except Exception as exc:  # noqa: BLE001
            return f"[Error al ejecutar '{nombre}': {exc}]"
