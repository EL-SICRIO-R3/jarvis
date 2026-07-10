# Guía de instalación y arranque — Jarvis Personal

Esta guía explica paso a paso cómo instalar todas las dependencias (incluyendo la librería **ai-tools-hub** desde GitHub) y cómo iniciar Jarvis.

---

## Requisitos previos

| Requisito | Versión mínima | Notas |
|---|---|---|
| Python | 3.10 | Se recomienda 3.11+ |
| Git | cualquiera | Necesario para descargar `ai-tools-hub` |
| Micrófono | — | Para el modo de voz |
| Conexión a internet | — | Para el LLM y el TTS neural |

**macOS solamente:** instala `portaudio` antes de continuar:

```bash
brew install portaudio
```

---

## 1. Clonar el repositorio de Jarvis

```bash
git clone https://github.com/EL-SICRIO-R3/jarvis.git
cd jarvis
```

---

## 2. Crear y activar un entorno virtual (recomendado)

```bash
# Crear el entorno
python -m venv .venv

# Activar en macOS / Linux
source .venv/bin/activate

# Activar en Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Activar en Windows (cmd.exe)
.venv\Scripts\activate.bat
```

---

## 3. Instalar dependencias (incluyendo ai-tools-hub)

Todas las dependencias están declaradas en `requirements.txt`. La línea clave es:

```
ai-tools-hub @ git+https://github.com/EL-SICRIO-R3/ia-tools.git
```

Esto le indica a `pip` que descargue e instale **ai-tools-hub** directamente desde su repositorio de GitHub, sin necesidad de subirlo a PyPI.

Ejecuta:

```bash
pip install -r requirements.txt
```

### ¿Qué hace pip en ese paso?

1. Clona el repositorio `EL-SICRIO-R3/ia-tools` en una carpeta temporal.
2. Ejecuta `pip install` sobre el paquete descargado.
3. Instala también las dependencias de `ai-tools-hub` (`pyperclip`, `requests`, `beautifulsoup4`, `pypdf`, `psutil`, `opencv-python`).

### Instalar ai-tools-hub de forma independiente (opcional)

Si quieres instalar o actualizar solo esa librería sin reinstalar todo:

```bash
# Instalación directa desde GitHub
pip install git+https://github.com/EL-SICRIO-R3/ia-tools.git

# Forzar reinstalación (para obtener la última versión)
pip install --force-reinstall git+https://github.com/EL-SICRIO-R3/ia-tools.git
```

---

## 4. Configurar las claves de API

Crea un archivo `.env` en la raíz del proyecto:

```bash
# macOS / Linux
cp .env.example .env   # si existe el ejemplo, o créalo manualmente:
touch .env
```

Abre `.env` y agrega al menos una clave:

```env
# Proveedor principal — Google Gemini (recomendado)
GEMINI_API_KEY=tu_clave_aqui

# Proveedor alternativo — OpenAI (fallback)
# OPENAI_API_KEY=tu_clave_aqui

# Telegram (opcional; activa el control remoto al iniciar Jarvis)
# TELEGRAM_BOT_TOKEN=pega_aqui_el_token_de_BotFather
# TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321

# Voz ultra-natural — ElevenLabs TTS (opcional, recomendado)
# ELEVENLABS_API_KEY=tu_clave_aqui
```

> **¿Dónde obtengo la clave?**
> - Gemini: [Google AI Studio → API Keys](https://aistudio.google.com/app/apikey)
> - OpenAI: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
> - ElevenLabs: [elevenlabs.io/app/settings/api-keys](https://elevenlabs.io/app/settings/api-keys)

---

## 5. Iniciar Jarvis

```bash
python main.py
```

### Control remoto desde Telegram (opcional)

1. Crea un bot con [@BotFather](https://t.me/BotFather) y copia su token.
2. Añade `TELEGRAM_BOT_TOKEN=...` al mismo `.env` y vuelve a iniciar Jarvis.
3. Envía `/start` al bot y luego tus instrucciones en texto.

`TELEGRAM_ALLOWED_CHAT_IDS` es opcional, pero se recomienda configurarlo con los
IDs numéricos autorizados para evitar que otra persona con acceso al bot pueda
controlar el equipo. Usa `/reset` para borrar el historial de conversación.

Al arrancar verás en la terminal:

```
[Jarvis] Iniciando…
[Jarvis] Agente iniciado con proveedor: gemini
[Jarvis] Listo.
```

La ventana gráfica aparece con la esfera animada en **azul** (iniciando). Una vez que el motor de voz esté listo, cambia a **verde**: Jarvis está escuchando.

Di **"Jarvis"** seguido de tu instrucción y el asistente responderá.

---

## Solución de problemas frecuentes

| Problema | Solución |
|---|---|
| `ModuleNotFoundError: ai_tools_hub` | Asegúrate de tener el entorno virtual activado y ejecuta `pip install -r requirements.txt` de nuevo. |
| `pip` no puede clonar el repo de GitHub | Verifica que Git esté instalado (`git --version`) y que tengas acceso a internet. |
| Error de `pyaudio` en macOS | Ejecuta `brew install portaudio` y luego `pip install pyaudio`. |
| `EnvironmentError: No se encontró ninguna clave de API` | Revisa que el archivo `.env` esté en la raíz del proyecto y que la clave sea válida. |
| La esfera se queda en azul y no pasa a verde | El micrófono no fue reconocido. Verifica los permisos de micrófono del sistema operativo. |

---

## Estructura de archivos relevante

```
jarvis/
├── main.py            # Punto de entrada → ejecuta este archivo
├── ai_agent.py        # Motor de IA (Gemini / OpenAI + ai-tools-hub)
├── gui.py             # Interfaz gráfica
├── tools.py           # Herramientas del sistema (usa ai-tools-hub)
├── requirements.txt   # Dependencias (incluye ai-tools-hub desde GitHub)
├── .env               # Claves de API (NO subir a git)
├── SETUP.md           # Esta guía
└── README.md          # Documentación completa del proyecto
```
