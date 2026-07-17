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
import re
import threading
from typing import Callable, Optional

from ai_tools_hub import ALL_TOOLS
from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Herramientas para Gemini — ALL_TOOLS contiene todos los callables de
# ai_tools_hub; Gemini genera los esquemas automáticamente desde los
# type hints y docstrings.
# ---------------------------------------------------------------------------

GEMINI_TOOLS = ALL_TOOLS

# ---------------------------------------------------------------------------
# Mapa nombre → callable para la ejecución de herramientas
# ---------------------------------------------------------------------------

TOOLS_MAP: dict[str, Callable[..., str]] = {fn.__name__: fn for fn in ALL_TOOLS}

# ---------------------------------------------------------------------------
# Esquema de herramientas para OpenAI (Function Calling manual)
# ---------------------------------------------------------------------------

OPENAI_TOOLS = [
    # ── system_tools ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_clipboard_content",
            "description": "Retorna el texto actual del portapapeles.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_os_info",
            "description": "Retorna resumen del SO, hardware y arquitectura del host.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Ejecuta un comando de solo lectura y retorna su salida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command_name": {"type": "string", "description": "Clave del comando: 'ls', 'df', 'pip', 'ps', etc."},
                    "argument": {"type": "string", "description": "Ruta opcional (solo 'ls' y 'dir')."},
                },
                "required": ["command_name"],
            },
        },
    },
    # ── web_tools ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Abre una URL en el navegador predeterminado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL a abrir (se añade https:// si falta esquema)."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_text_from_url",
            "description": "Descarga una URL y retorna su texto plano limpio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL de la página."},
                    "max_chars": {"type": "integer", "description": "Límite de caracteres (por defecto 8000)."},
                },
                "required": ["url"],
            },
        },
    },
    # ── file_tools ────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Retorna el contenido de un archivo de texto o PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Ruta al archivo; acepta ~."},
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
            "description": "Crea o sobreescribe un archivo de texto UTF-8.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Ruta del archivo; acepta ~."},
                    "content": {"type": "string", "description": "Contenido a escribir."},
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
            "description": "Lista archivos y subdirectorios con sus tamaños.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory_path": {"type": "string", "description": "Ruta a listar (por defecto directorio actual)."},
                    "show_hidden": {"type": "boolean", "description": "Si True, incluye entradas ocultas."},
                },
                "required": [],
            },
        },
    },
    # ── vision_tools ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "capturar_foto_webcam",
            "description": "Captura foto con la webcam y retorna la ruta del JPEG guardado.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tomar_captura_pantalla",
            "description": "Captura la pantalla y retorna la ruta del PNG guardado.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    # ── image_gen_tools ───────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "generar_imagen",
            "description": "Genera una imagen IA desde una descripción y retorna la ruta del PNG guardado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string", "description": "Descripción detallada de la imagen."},
                    "estilo": {"type": "string", "description": "Estilo visual opcional (e.g. 'fotorrealista', 'anime', 'acuarela')."},
                },
                "required": ["descripcion"],
            },
        },
    },
    # ── video_gen_tools ───────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "generar_video",
            "description": "Genera un video IA desde una descripción de texto y retorna la ruta del MP4 guardado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {"type": "string", "description": "Descripción detallada del video a generar."},
                    "duracion": {"type": "integer", "description": "Duración en segundos (por defecto 5, máximo 8-10)."},
                    "estilo": {"type": "string", "description": "Estilo visual opcional (e.g. 'cinemático', 'animado', 'documental')."},
                },
                "required": ["descripcion"],
            },
        },
    },
    # ── dev_tools ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "liberar_puerto",
            "description": "Termina el proceso que escucha en el puerto TCP dado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "puerto": {"type": "integer", "description": "Número de puerto TCP (e.g. 8080, 3000)."}
                },
                "required": ["puerto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_arbol_directorios",
            "description": "Genera árbol visual de directorios hasta la profundidad indicada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta raíz; acepta ~."},
                    "profundidad": {"type": "integer", "description": "Niveles máximos a mostrar (por defecto 2)."},
                },
                "required": ["ruta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_contenedores_activos",
            "description": "Lista los contenedores Docker en ejecución.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reiniciar_contenedor",
            "description": "Reinicia un contenedor Docker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_o_id": {"type": "string", "description": "Nombre o ID del contenedor."}
                },
                "required": ["nombre_o_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_estado_git",
            "description": "Ejecuta git status en la ruta indicada y retorna la salida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta_proyecto": {"type": "string", "description": "Ruta al directorio raíz del repositorio; acepta ~."}
                },
                "required": ["ruta_proyecto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analizar_ultimos_logs",
            "description": "Retorna las últimas N líneas de un archivo de log.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta_archivo": {"type": "string", "description": "Ruta al archivo de log; acepta ~."},
                    "lineas": {"type": "integer", "description": "Cantidad de líneas finales (por defecto 50)."},
                },
                "required": ["ruta_archivo"],
            },
        },
    },
    # ── interaction_tools ─────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "mostrar_notificacion",
            "description": "Muestra una notificación nativa del SO.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título de la notificación."},
                    "mensaje": {"type": "string", "description": "Texto del cuerpo."},
                },
                "required": ["titulo", "mensaje"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redactar_email",
            "description": "Abre el cliente de correo con un borrador prellenado.",
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
    {
        "type": "function",
        "function": {
            "name": "configurar_ruta_imagenes",
            "description": "Cambia la carpeta persistente donde se guardan imágenes. Requiere autorización del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta absoluta o iniciada por ~."},
                    "autorizado": {"type": "boolean", "description": "Parámetro interno; solo se activa después de la confirmación del usuario."},
                },
                "required": ["ruta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_tool",
            "description": "Crea una nueva tool Python para cargarla al reiniciar. Requiere autorización del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre de función Python."},
                    "codigo": {"type": "string", "description": "Código completo de la función."},
                    "autorizado": {"type": "boolean", "description": "Parámetro interno; solo se activa después de la confirmación del usuario."},
                },
                "required": ["nombre", "codigo"],
            },
        },
    },
]

# Eight iterations allow normal tool chains while preventing provider-side loops.
_MAX_TOOL_CALL_ITERATIONS = 8
_GEMINI_EMPTY_RESPONSE = (
    "[El modelo terminó sin devolver texto. Intenta reformular la instrucción "
    "o verifica la conexión con el modelo.]"
)

_AUTH_CONFIRM_RE = re.compile(
    r"^\s*(?:s[ií]|autorizo|acepto|confirmo|adelante)(?:\s|[.!,:;]|$)"
)
_AUTH_REJECT_RE = re.compile(
    r"^\s*(?:no\s+(?:autorizo|quiero|lo hagas)|cancel(?:ar|o)|rechazo)(?:\s|[.!,:;]|$)"
)

_MOOD_KEYWORDS = {
    "triste": ("triste", "deprimido", "deprimida", "lloro", "llorar", "solo", "mal día", "mal dia", "pena"),
    "frustrado": ("frustrado", "frustrada", "frustración", "frustracion", "harto", "harta", "desesperado", "enojado", "cabreado", "error"),
    "alegre": ("feliz", "contento", "contenta", "genial", "increíble", "increible", "jaja", "gracias"),
    "urgente": ("urgente", "rápido", "rapido", "ya mismo", "emergencia", "asap"),
    "cansado": ("cansado", "cansada", "agotado", "agotada", "sueño", "sueno", "no puedo más", "no puedo mas"),
}
_MOOD_PRIORITY = ("urgente", "frustrado", "triste", "cansado", "alegre")
_MOOD_PATTERNS = {
    mood: tuple(
        re.compile(rf"\b{re.escape(keyword)}\b")
        for keyword in keywords
    )
    for mood, keywords in _MOOD_KEYWORDS.items()
}


def detect_mood(message: str) -> str:
    """Detecta el tono dominante del mensaje sin enviar datos a un servicio externo.

    Returns:
        Uno de ``neutral``, ``triste``, ``frustrado``, ``alegre``, ``urgente``
        o ``cansado``.
    """
    normalized = message.lower()
    scores = {
        mood: sum(
            1 for pattern in keywords
            if pattern.search(normalized)
        )
        for mood, keywords in _MOOD_PATTERNS.items()
    }
    best_score = max(scores.values(), default=0)
    if best_score:
        return next(
            (
                mood for mood in _MOOD_PRIORITY
                if scores.get(mood, 0) == best_score
            ),
            "neutral",
        )
    return "neutral"


def _mood_context(mood: str) -> str:
    """Devuelve instrucciones breves para adaptar la respuesta al estado del usuario."""
    instructions = {
        "triste": "Responde con calidez y empatía; valida sus emociones y evita bromas intensas.",
        "frustrado": "Responde con calma, reconoce la frustración y ofrece pasos concretos sin culpar.",
        "alegre": "Acompaña su energía positiva con entusiasmo moderado y humor ligero.",
        "urgente": "Sé directo, prioriza la acción inmediata y evita explicaciones innecesarias.",
        "cansado": "Sé especialmente breve, claro y amable; no sobrecargues al usuario.",
        "neutral": "Mantén tu personalidad habitual y ajusta el tono al contexto de la conversación.",
    }
    return instructions.get(mood, instructions["neutral"])


def _contextualize_message(message: str, mood: str) -> str:
    """Añade al mensaje la guía de tono que usará el modelo de Google.

    Se antepone a cada mensaje para que el estado del usuario module el humor
    predeterminado de Jarvis.
    """
    return (
        f"[Contexto de tono: {_mood_context(mood)}]\n"
        f"Mensaje del usuario: {message}"
    )


SYSTEM_PROMPT = """Eres Jarvis, el asistente personal de IA más payaso y random del universo conocido (y desconocido).

Personalidad:
- Eres como ese amigo que siempre está de buen humor, te ríes de todo y dices tonterías sin sentido
  con total confianza. "jajaja", "xd", "lol" son parte de tu vocabulario natural.
- Haces chistes malos a propósito y te ríes de ellos tú mismo. Puedes soltar una broma sin ton ni son
  en medio de una respuesta seria y luego seguir como si nada.
- Jamás dices vainas serviles como "¡Por supuesto!" o "¡Claro que sí!". Prefieres algo como
  "dale pues jaja" o "va, va, va, ahí te va".
- Cero groserías fuertes; eres divertido sin necesidad de ofender. Eres el payaso del grupo, no el pesado.
- Hablas de forma relajada, como si estuvieras en un chat con tu mejor cuate. Abrevias, usas emojis
  de vez en cuando (🤡🎉😂) y metes referencias random si viene al caso.
- Puedes inventar datos absurdos y ridículos para explicar algo (marcándolos claramente como broma),
  o soltar una frase sin sentido como "como decía mi abuela: el agua moja más los martes".
- Si el usuario dice algo, puedes reírte con él (no de él). Si hay un error, lo señalas con humor
  y sin drama: "eyyy eso no cuadra jaja, déjame revisarlo".
- Adaptas el tono: si el usuario se pone serio, te calmas un poco sin perder tu esencia payaso.
- El contexto de tono incluido en cada mensaje tiene prioridad sobre el humor: acompaña al usuario
  con empatía cuando esté triste, frustrado o cansado, y sé directo cuando haya urgencia.

Capacidades:
- Leer el portapapeles del sistema.
- Obtener información del sistema operativo.
- Ejecutar comandos de terminal de solo lectura.
- Abrir el navegador en cualquier URL.
- Extraer el texto de páginas web.
- Leer archivos de texto y PDFs.
- Crear archivos de texto y listar directorios.
- Capturar fotos con la webcam y analizarlas.
- Tomar capturas de pantalla y analizarlas.
- Generar imágenes con IA a partir de una descripción (DALL-E 3 / Imagen).
- Generar videos con IA a partir de una descripción (Google Veo / RunwayML).
- Liberar puertos TCP ocupados.
- Mostrar el árbol de directorios de un proyecto.
- Gestionar contenedores Docker (listar y reiniciar).
- Consultar el estado de un repositorio Git.
- Analizar las últimas líneas de un archivo de log.
- Mostrar notificaciones nativas del sistema operativo.
- Redactar borradores de correo en el cliente de email.
- Configurarse cuando el usuario lo solicite: primero pide los datos que falten y
  solicita autorización explícita antes de cambiar rutas, crear tools o ejecutar
  cambios que alteren su comportamiento. Nunca trates un parámetro del modelo
  como autorización; la confirmación debe venir del usuario.

Reglas operativas:
1. Responde en el idioma del usuario (normalmente español).
2. Respuestas cortas por defecto; desarrolla solo cuando la complejidad lo exige.
3. Usa la herramienta apropiada cuando el usuario pide ejecutar algo en la computadora.
4. Si no sabes algo, dilo claro. Nunca inventes información.
5. Cuando captures o generes una imagen, recibirás los datos visuales directamente: descríbela con detalle.
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

    # Herramientas que devuelven una ruta de imagen capturada o generada
    _VISION_CAPTURE_TOOLS = frozenset({"capturar_foto_webcam", "tomar_captura_pantalla", "generar_imagen"})

    # Herramientas que devuelven una ruta de video generado
    _VIDEO_GEN_TOOLS = frozenset({"generar_video"})

    # Herramientas que guardan archivos (resultado incluye la ruta absoluta)
    _SAVE_TOOLS = frozenset({"guardar_documento", "guardar_nota", "create_file"})
    _AUTHORIZED_TOOLS = frozenset({"configurar_ruta_imagenes", "crear_tool"})
    _AUTHORIZATION_KEY = "autorizado"

    def __init__(self, provider: Optional[str] = None) -> None:
        self._provider = self._resolve_provider(provider)
        self._current_mood = "neutral"
        self._history: list[dict] = []
        self.last_saved_path: Optional[str] = None          # leído por gui.py para ofrecer "abrir archivo"
        self.last_captured_image_path: Optional[str] = None  # leído por gui.py para mostrar preview
        self.last_generated_video_path: Optional[str] = None  # leído por gui.py para mostrar preview de video
        self.telegram_thread: threading.Thread | None = None
        self._pending_authorization: tuple[str, dict] | None = None
        self._lock = threading.RLock()

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

    @property
    def current_mood(self) -> str:
        """Retorna el tono detectado en el último mensaje del usuario."""
        return self._current_mood

    def _contextualize_user_message(self, message: str) -> str:
        """Detecta el tono, actualiza ``_current_mood`` y prepara el mensaje."""
        self._current_mood = detect_mood(message)
        return _contextualize_message(message, self._current_mood)

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
        with self._lock:
            contextualized_message = self._contextualize_user_message(user_message)
            self.last_captured_image_path = None
            self.last_generated_video_path = None
            if self._pending_authorization is not None:
                if _AUTH_CONFIRM_RE.match(user_message.lower()):
                    nombre, args = self._pending_authorization
                    self._pending_authorization = None
                    return self._execute_tool(
                        nombre, {**args, self._AUTHORIZATION_KEY: True}, _authorized=True
                    )
                if _AUTH_REJECT_RE.match(user_message.lower()):
                    self._pending_authorization = None
                    return "Cambio cancelado; no se modificó la configuración."
                return "Necesito que confirmes o rechaces la autorización pendiente."
            if self._provider == "gemini":
                return self._send_gemini(contextualized_message)
            return self._send_openai(contextualized_message)

    def send_message_with_image(self, user_message: str, image_path: str) -> str:
        """Envía un mensaje con imagen al LLM (visión multimodal).

        Args:
            user_message: Texto del usuario describiendo qué hacer con la imagen.
            image_path: Ruta absoluta al archivo de imagen.

        Returns:
            str: Respuesta textual del asistente.
        """
        with self._lock:
            contextualized_message = self._contextualize_user_message(user_message)
            self.last_captured_image_path = None
            self.last_generated_video_path = None
            if self._provider == "gemini":
                return self._send_gemini_with_image(
                    contextualized_message, image_path
                )
            return self._send_openai_with_image(
                contextualized_message, image_path
            )

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
        final_tool_result = ""

        # Ciclo de function calling
        # Ocho iteraciones cubren cadenas normales de tools sin permitir ciclos infinitos.
        for _iteration in range(_MAX_TOOL_CALL_ITERATIONS):
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
            captured_images: list = []  # (PIL.Image, path) para herramientas de visión

            for call in tool_calls:
                resultado = self._execute_tool(call.name, dict(call.args))
                final_tool_result = resultado
                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=call.name,
                            response={"result": resultado},
                        )
                    )
                )
                # Si es una herramienta de captura de imagen, cargar la imagen
                if call.name in self._VISION_CAPTURE_TOOLS:
                    _path = resultado.strip()
                    if not _path.startswith("[") and os.path.isfile(_path):
                        try:
                            from PIL import Image as _PILImg  # type: ignore
                            captured_images.append((_PILImg.open(_path), _path))
                        except Exception:
                            pass

            # Si se capturaron imágenes, incluirlas en el mensaje para análisis visual
            if captured_images:
                self.last_captured_image_path = captured_images[-1][1]
                parts: list = list(tool_responses) + [img for img, _ in captured_images]
                response = self._chat.send_message(parts)
            else:
                response = self._chat.send_message(tool_responses)

        return self._gemini_text(response, final_tool_result)

    @staticmethod
    def _gemini_text(response: object, fallback: str = "") -> str:
        """Extrae texto incluso cuando Gemini no expone ``response.text``."""
        try:
            text = str(getattr(response, "text", "") or "").strip()
        except (ValueError, AttributeError):
            text = ""
        if text:
            return text
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = str(getattr(part, "text", "") or "").strip()
                if part_text:
                    return part_text
        return fallback or _GEMINI_EMPTY_RESPONSE

    def _send_gemini_with_image(self, user_message: str, image_path: str) -> str:
        """Envía texto + imagen a Gemini (visión multimodal)."""
        import io
        import google.generativeai as genai  # type: ignore
        from PIL import Image  # type: ignore

        try:
            img = Image.open(image_path)
            # Convertir a RGB si el modo no es compatible con JPEG (ej. RGBA, P, LA)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            img_bytes = buf.getvalue()
        except Exception as exc:
            return f"[No se pudo abrir la imagen: {exc}]"

        image_part = genai.protos.Part(
            inline_data=genai.protos.Blob(mime_type="image/jpeg", data=img_bytes)
        )
        response = self._chat.send_message([user_message, image_part])

        # Ciclo de function calling (igual que _send_gemini)
        final_tool_result = ""
        # Ocho iteraciones cubren cadenas normales de tools sin permitir ciclos infinitos.
        for _iteration in range(_MAX_TOOL_CALL_ITERATIONS):
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
                final_tool_result = resultado
                tool_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=call.name,
                            response={"result": resultado},
                        )
                    )
                )
            response = self._chat.send_message(tool_responses)

        return self._gemini_text(response, final_tool_result)

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
            captured_image_paths: list[str] = []
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
                # Registrar imágenes capturadas para envío visual
                if tool_call.function.name in self._VISION_CAPTURE_TOOLS:
                    _path = resultado.strip()
                    if not _path.startswith("[") and os.path.isfile(_path):
                        captured_image_paths.append(_path)

            # Si se capturaron imágenes, inyectarlas como mensaje de visión
            if captured_image_paths:
                import base64
                vision_content: list = []
                for _p in captured_image_paths:
                    _ext = os.path.splitext(_p)[1].lower().lstrip(".")
                    if _ext == "jpg":
                        _ext = "jpeg"
                    try:
                        with open(_p, "rb") as _f:
                            _b64 = base64.b64encode(_f.read()).decode()
                        vision_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{_ext};base64,{_b64}"},
                        })
                    except Exception:
                        pass
                if vision_content:
                    vision_content.append({
                        "type": "text",
                        "text": "Imagen(es) capturada(s). Descríbelas al usuario en detalle.",
                    })
                    messages.append({"role": "user", "content": vision_content})
                self.last_captured_image_path = captured_image_paths[-1]

    def _send_openai_with_image(self, user_message: str, image_path: str) -> str:
        """Envía texto + imagen a OpenAI (visión multimodal con gpt-4o-mini)."""
        import base64
        import json

        ext = os.path.splitext(image_path)[1].lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        try:
            with open(image_path, "rb") as _f:
                b64 = base64.b64encode(_f.read()).decode()
        except Exception as exc:
            return f"[No se pudo leer la imagen: {exc}]"

        vision_message = {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{ext};base64,{b64}"},
                },
                {"type": "text", "text": user_message},
            ],
        }

        # Guardamos en historial como texto para no acumular base64 en turnos futuros
        self._history.append({"role": "user", "content": user_message})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self._history[:-1] + [vision_message]

        # Ciclo de function calling (igual que _send_openai)
        while True:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
            )

            message = response.choices[0].message

            if not message.tool_calls:
                assistant_text = message.content or ""
                self._history.append({"role": "assistant", "content": assistant_text})
                return assistant_text

            messages.append(message)

            captured_image_paths: list[str] = []
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
                if tool_call.function.name in self._VISION_CAPTURE_TOOLS:
                    _path = resultado.strip()
                    if not _path.startswith("[") and os.path.isfile(_path):
                        captured_image_paths.append(_path)

            if captured_image_paths:
                cap_content: list = []
                for _p in captured_image_paths:
                    _ext = os.path.splitext(_p)[1].lower().lstrip(".")
                    if _ext == "jpg":
                        _ext = "jpeg"
                    try:
                        with open(_p, "rb") as _f:
                            _b64 = base64.b64encode(_f.read()).decode()
                        cap_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{_ext};base64,{_b64}"},
                        })
                    except Exception:
                        pass
                if cap_content:
                    cap_content.append({
                        "type": "text",
                        "text": "Imagen(es) capturada(s). Descríbelas al usuario en detalle.",
                    })
                    messages.append({"role": "user", "content": cap_content})
                self.last_captured_image_path = captured_image_paths[-1]

    # ------------------------------------------------------------------
    # Ejecución de herramientas
    # ------------------------------------------------------------------

    def _execute_tool(self, nombre: str, args: dict, _authorized: bool = False) -> str:
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
        if nombre in self._AUTHORIZED_TOOLS and not _authorized:
            pending_args = {
                key: value for key, value in args.items()
                if key != self._AUTHORIZATION_KEY
            }
            self._pending_authorization = (nombre, pending_args)
            return (
                f"[AUTORIZACIÓN REQUERIDA para '{nombre}'. "
                "Explica al usuario qué se cambiará y espera su confirmación explícita.]"
            )
        try:
            resultado = str(func(**args))
            # Rastrear ruta cuando se guarda un archivo (para el preview de gui.py)
            if nombre in self._SAVE_TOOLS:
                if resultado and not resultado.startswith("["):
                    # El resultado contiene la ruta absoluta al final, tras "en: " o ": "
                    for marker in ("en: ", "en:", ": "):
                        if marker in resultado:
                            candidate = resultado.rsplit(marker, 1)[-1].strip()
                            if os.path.isabs(candidate) and os.path.isfile(candidate):
                                self.last_saved_path = candidate
                                break
            # Rastrear ruta de video generado (para el preview de gui.py)
            if nombre in self._VIDEO_GEN_TOOLS:
                _vpath = resultado.strip()
                if not _vpath.startswith("[") and os.path.isfile(_vpath):
                    self.last_generated_video_path = _vpath
            return resultado
        except TypeError as exc:
            return f"[Error de argumentos en '{nombre}': {exc}]"
        except Exception as exc:  # noqa: BLE001
            return f"[Error al ejecutar '{nombre}': {exc}]"
