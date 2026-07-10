<div align="center">

```
  ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
  ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
  ██║███████║██████╔╝██║   ██║██║███████╗
  ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
  ██║██║  ██║██║  ██║ ╚████╔╝ ██║███████║
  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
        Personal AI Assistant
```

**Asistente personal de inteligencia artificial con voz, visión y control del sistema operativo**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![OpenAI](https://img.shields.io/badge/LLM-OpenAI%20GPT--4o-412991?logo=openai&logoColor=white)](https://openai.com/)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](#requisitos-del-sistema)
[![License](https://img.shields.io/badge/License-MIT-green)](#licencia)

</div>

---

## ¿Qué es Jarvis?

**Jarvis Personal** es un asistente de escritorio impulsado por IA que combina reconocimiento de voz, síntesis de habla, visión multimodal y control del sistema operativo en una sola aplicación. Inspirado en el asistente de Tony Stark, Jarvis escucha continuamente, entiende lenguaje natural y ejecuta acciones concretas en tu computadora: abre aplicaciones, navega en internet, guarda documentos y mucho más — sin que tengas que tocar el teclado.

La interfaz visual presenta una **esfera molecular animada en 3D** sobre fondo negro que cambia de color y comportamiento según el estado del asistente (escuchando, pensando, hablando, en pausa), ofreciendo una experiencia visual inmersiva y futurista.

---

## Tabla de contenido

- [Características principales](#características-principales)
- [Arquitectura del sistema](#arquitectura-del-sistema)
- [Flujo de funcionamiento](#flujo-de-funcionamiento)
- [Herramientas disponibles](#herramientas-disponibles)
- [Interfaz gráfica](#interfaz-gráfica)
- [Proveedores de IA](#proveedores-de-ia)
- [Requisitos del sistema](#requisitos-del-sistema)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Telegram](#telegram)
- [Uso](#uso)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Alcance y limitaciones](#alcance-y-limitaciones)

---

## Características principales

| Característica | Descripción |
|---|---|
| 🎤 **Voz continua** | Escucha en segundo plano con palabra de activación "Jarvis" |
| 🧠 **LLM dual** | Google Gemini 2.5 Flash Lite como motor principal; OpenAI GPT-4o-mini como fallback |
| 🖼️ **Visión multimodal** | Arrastra y suelta imágenes para que Jarvis las analice |
| 🛠️ **Function Calling** | El modelo invoca herramientas locales de forma autónoma |
| 📋 **Portapapeles** | Lee y escribe en el portapapeles del sistema |
| 🌐 **Navegador** | Abre URLs o realiza búsquedas en Google con un comando de voz |
| 💾 **Documentos** | Genera y guarda informes, resúmenes y notas en el escritorio |
| 🖥️ **Apps del sistema** | Abre aplicaciones instaladas (VSCode, Safari, Notepad, etc.) |
| 🔇 **Pausa / Reanuda** | Congela el ciclo de escucha sin cerrar la aplicación |
| ⌨️ **Atajo global** | `Ctrl+Espacio` / `Cmd+Espacio` muestra u oculta la ventana |
| 🌍 **Multiplataforma** | Compatible con macOS, Windows y Linux |

---

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        JARVIS PERSONAL                          │
│                                                                 │
│  ┌──────────────┐    ┌───────────────────┐    ┌─────────────┐  │
│  │   gui.py     │    │   ai_agent.py     │    │  tools.py   │  │
│  │              │    │                   │    │             │  │
│  │  JarvisWindow│◄──►│   JarvisAgent     │◄──►│  TOOLS_MAP  │  │
│  │              │    │                   │    │             │  │
│  │ ─ Tkinter UI │    │ ─ Gemini / OpenAI │    │ ─ clipboard │  │
│  │ ─ Esfera 3D  │    │ ─ Function Call   │    │ ─ browser   │  │
│  │ ─ STT / TTS  │    │ ─ Historial conv. │    │ ─ archivos  │  │
│  │ ─ Drag&Drop  │    │ ─ System Prompt   │    │ ─ apps      │  │
│  └──────────────┘    └───────────────────┘    └─────────────┘  │
│          │                    │                                 │
│          └────────────────────┘                                 │
│                    main.py                                      │
│              (orquestador principal)                            │
└─────────────────────────────────────────────────────────────────┘

Entrada de audio        Salida de audio         Sistema Operativo
┌──────────────┐        ┌──────────────────┐    ┌───────────────┐
│ Micrófono    │        │ edge-tts (neural) │    │ Portapapeles  │
│ PyAudio      │        │ pyttsx3 (fallback)│    │ Aplicaciones  │
│ SpeechRecog. │        │ afplay / mpv      │    │ Navegador     │
└──────────────┘        └──────────────────┘    │ Escritorio    │
                                                 └───────────────┘
```

### Módulos

| Archivo | Responsabilidad |
|---|---|
| `main.py` | Punto de entrada. Inicializa el agente, la ventana y el ciclo de vida de la app. |
| `ai_agent.py` | Gestiona la comunicación con el LLM (Gemini/OpenAI), el historial de conversación y el ciclo de Function Calling. |
| `gui.py` | Interfaz gráfica (Tkinter): esfera 3D animada, captura de voz (STT), síntesis de voz (TTS) y drag & drop de imágenes. |
| `tools.py` | Catálogo de funciones locales que el agente puede invocar: portapapeles, navegador, aplicaciones, archivos. |

---

## Flujo de funcionamiento

```
Usuario habla
     │
     ▼
[STT] SpeechRecognition transcribe audio
     │
     ▼
¿Contiene "jarvis"? ──No──► seguir escuchando
     │ Sí
     ▼
Limpia la frase (elimina la palabra de activación)
     │
     ▼
JarvisAgent.send_message(texto)
     │
     ▼
LLM procesa el mensaje con el System Prompt
     │
     ▼
¿Respuesta contiene Function Calls?
     │
   ──┴──────────────────────────────────────────────────┐
   │ Sí                                                  │ No
   ▼                                                     ▼
Ejecutar herramienta(s) en tools.py              Texto final
   │                                                     │
   ▼                                                     │
Devolver resultado al LLM ────────────────────────────► │
                                                         ▼
                                               [TTS] voz local sintetiza voz
                                                         │
                                                         ▼
                                               Jarvis responde en audio
                                               + texto en pantalla
```

---

## Herramientas disponibles

El agente detecta automáticamente cuándo debe usar una herramienta a partir del lenguaje natural del usuario:

### 📋 Portapapeles
| Herramienta | Descripción | Ejemplo de uso |
|---|---|---|
| `obtener_portapapeles` | Lee el texto actual del portapapeles | _"¿Qué tengo copiado?"_ |
| `copiar_al_portapapeles` | Escribe un texto en el portapapeles | _"Copia este resumen al portapapeles"_ |

### 💻 Aplicaciones y sistema
| Herramienta | Descripción | Ejemplo de uso |
|---|---|---|
| `abrir_vscode` | Abre VS Code, opcionalmente con una ruta | _"Abre VS Code en mi proyecto"_ |
| `abrir_aplicacion` | Lanza cualquier aplicación instalada | _"Abre Spotify"_ |
| `obtener_info_sistema` | Devuelve SO, versión y arquitectura | _"¿Qué sistema operativo tengo?"_ |

### 🌐 Navegador
| Herramienta | Descripción | Ejemplo de uso |
|---|---|---|
| `abrir_navegador` | Navega a una URL o dominio | _"Abre github.com"_ |
| `abrir_navegador` (buscar) | Busca en Google | _"Busca el precio del dólar"_ |

### 📄 Archivos y documentos
| Herramienta | Descripción | Ejemplo de uso |
|---|---|---|
| `guardar_nota` | Guarda texto en `jarvis_nota.txt` en el escritorio | _"Guarda una nota: llamar al médico"_ |
| `guardar_documento` | Genera y guarda un informe, reporte, carta, etc. | _"Crea un informe sobre Python y guárdalo"_ |

---

## Interfaz gráfica

La ventana de Jarvis mide **860 × 620 px** y está compuesta por:

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│           ◉  Esfera molecular 3D                    │
│          /|\ animada en tiempo real                 │
│         / | \  (72 partículas Fibonacci)            │
│                                                     │
│        Color cambia según estado:                   │
│        🔵 Azul     → Idle / iniciando               │
│        🟢 Verde    → Escuchando                     │
│        🟠 Naranja  → Procesando / pensando          │
│        💚 Verde cl.→ Hablando                       │
│        ⚫ Gris     → Pausado                        │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Texto de la última respuesta                       │
│  Estado actual del asistente                        │
│                [ ⏸ Pausar ]                         │
└─────────────────────────────────────────────────────┘
```

### Controles
| Acción | Gesto / tecla |
|---|---|
| Interrumpir TTS | Clic en la esfera o `Esc` |
| Pausar / reanudar | Botón "Pausar" en la parte inferior |
| Analizar imagen | Arrastra y suelta un archivo de imagen en la ventana |
| Mostrar / ocultar ventana | `Ctrl+Espacio` (Windows/Linux) · `Cmd+Espacio` (macOS) |

---

## Proveedores de IA

Jarvis detecta automáticamente qué proveedor usar según las variables de entorno disponibles:

```
GEMINI_API_KEY definida  →  Google Gemini 2.5 Flash Lite  (prioridad)
OPENAI_API_KEY definida  →  OpenAI GPT-4o-mini            (fallback)
Ninguna clave definida   →  Modo demo (UI funciona, sin respuestas LLM)
```

| Proveedor | Modelo | Function Calling | Visión |
|---|---|---|---|
| Google Gemini | `gemini-2.5-flash-lite` | ✅ Nativo | ✅ Multimodal |
| OpenAI | `gpt-4o-mini` | ✅ Nativo | ⚠️ Degradado a texto |

---

## Requisitos del sistema

- **Python** 3.10 o superior
- **Micrófono** funcional
- **Altavoces** o auriculares
- **Conexión a internet** (para LLM y TTS neural con edge-tts)
- **macOS**: `brew install portaudio`
- **Windows/Linux**: portaudio incluido vía `pyaudio`

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/EL-SICRIO-R3/jarvis.git
cd jarvis

# 2. Crear y activar entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# macOS: si falla pyaudio, instala primero portaudio
brew install portaudio && pip install pyaudio
```

---

## Configuración

Crea un archivo `.env` en la raíz del proyecto con al menos una clave de API:

```env
# Proveedor principal (recomendado)
GEMINI_API_KEY=tu_clave_de_gemini_aqui

# Proveedor alternativo (fallback)
# OPENAI_API_KEY=tu_clave_de_openai_aqui
```

> **Obtener claves:**
> - Gemini: [Google AI Studio](https://aistudio.google.com/app/apikey)
> - OpenAI: [platform.openai.com](https://platform.openai.com/api-keys)

---

## Uso

```bash
python main.py
```

## Telegram

Jarvis puede recibir instrucciones desde Telegram mientras la aplicación local
está ejecutándose. Instala las dependencias, crea un bot con BotFather y añade
su token al `.env`:

```env
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
# Recomendado: IDs numéricos separados por comas
TELEGRAM_ALLOWED_CHAT_IDS=123456789
```

Al arrancar `main.py`, el polling se inicia automáticamente si existe el token.
Envía `/start` al bot y después cualquier instrucción; `/reset` reinicia el
historial. Las respuestas largas se envían divididas y los archivos generados
se adjuntan automáticamente.

Una vez iniciado:

1. La ventana aparece con la esfera animada en estado **azul** (iniciando).
2. Al completar la inicialización de voz, cambia a **verde**: Jarvis está escuchando.
3. Di **"Jarvis"** seguido de tu instrucción:
   - _"Jarvis, abre Chrome"_
   - _"Jarvis, busca el clima de hoy"_
   - _"Jarvis, guarda una nota: comprar pan"_
   - _"Jarvis, crea un informe sobre las mejores prácticas en Python"_
4. La esfera cambia a **naranja** mientras procesa y a **verde claro** mientras habla.
5. Puedes interrumpir la respuesta en cualquier momento con `Esc` o haciendo clic.

---

## Estructura del proyecto

```
jarvis/
├── main.py            # Orquestador principal y punto de entrada
├── ai_agent.py        # Motor de IA: Gemini / OpenAI + Function Calling
├── gui.py             # Interfaz gráfica: esfera 3D, voz (STT/TTS), drag & drop
├── tools.py           # Herramientas locales del sistema operativo
├── requirements.txt   # Dependencias Python
├── .env               # Claves de API (NO incluir en git)
└── README.md          # Este archivo
```

---

## Alcance y limitaciones

### ✅ Dentro del alcance
- Conversación en lenguaje natural en **español** (y otros idiomas)
- Ejecución de acciones en el **sistema operativo local**
- Soporte **multiplataforma**: macOS, Windows y Linux
- Historial de conversación en memoria durante la sesión activa
- Análisis de imágenes arrastrando archivos a la ventana (solo Gemini)
- Generación y guardado de documentos de texto estructurado

### ⚠️ Limitaciones conocidas
- El historial de conversación **no persiste** entre sesiones (se reinicia al cerrar)
- La visión multimodal solo está disponible con el proveedor **Gemini**
- La herramienta `abrir_aplicacion` en Windows usa `start` por shell; algunos programas con espacios en el nombre pueden requerir ajustes
- La configuración de voz solo incluye voces locales/seleccionadas de Jarvis; `pyttsx3` permite el fallback offline
- No hay soporte para comandos que requieran autenticación en servicios externos (correo, calendario, etc.)
- La ventana es de tamaño **fijo** (860 × 620 px) y no es redimensionable

### 🗺️ Posibles extensiones futuras
- Persistencia del historial entre sesiones (SQLite / JSON)
- Plugins adicionales: control de música, calendario, correo
- Interfaz web opcional para acceso remoto
- Soporte de voz en más idiomas con modelos Whisper
- Redimensionado y modo compacto de la ventana

---

## Licencia

Este proyecto está bajo la licencia **MIT**. Consulta el archivo `LICENSE` para más detalles.

---

<div align="center">
  <sub>Hecho con ❤️ — <em>"Sometimes you gotta run before you can walk."</em> — Tony Stark</sub>
</div>
