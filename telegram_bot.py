"""Puente opcional de Telegram para controlar Jarvis en una instalación local."""

from __future__ import annotations

import logging
import os
import asyncio
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from dotenv import load_dotenv

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

load_dotenv()
_LOGGER = logging.getLogger(__name__)
_MAX_MESSAGE_LENGTH = 4096


def _allowed_chat_ids() -> set[int]:
    values = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    result: set[int] = set()
    for value in values.split(","):
        try:
            if value.strip():
                result.add(int(value.strip()))
        except ValueError:
            _LOGGER.warning(
                "Se ignoró un TELEGRAM_ALLOWED_CHAT_IDS inválido: %s", value.strip()
            )
    return result


class TelegramBridge:
    """Recibe mensajes de Telegram y los procesa con un ``JarvisAgent``."""

    def __init__(self, agent: object, token: str | None = None) -> None:
        self.agent = agent
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.allowed_chat_ids = _allowed_chat_ids()
        self._stop_event: asyncio.Event | None = None

    async def handle_message(
        self, update: "Update", context: "ContextTypes.DEFAULT_TYPE"
    ) -> None:
        message = getattr(update, "effective_message", None)
        chat = getattr(update, "effective_chat", None)
        text = (getattr(message, "text", None) or "").strip()
        if message is None or chat is None or not text:
            return
        if self.allowed_chat_ids and getattr(chat, "id", None) not in self.allowed_chat_ids:
            await message.reply_text("Este chat no está autorizado para controlar Jarvis.")
            return
        if text == "/start":
            await message.reply_text("Jarvis conectado. Envíame una instrucción.")
            return
        if text == "/reset":
            self.agent.reset_history()
            await message.reply_text("Historial reiniciado.")
            return
        try:
            reply = await asyncio.to_thread(self.agent.send_message, text)
        except (OSError, RuntimeError, ValueError) as exc:
            _LOGGER.exception("Error procesando mensaje de Telegram")
            reply = f"[Error procesando la instrucción: {exc}]"
        await self._reply_chunks(message, reply)
        await self._send_generated_file(message)

    async def _reply_chunks(self, message: object, text: str) -> None:
        text = text or "(Jarvis no devolvió texto.)"
        for start in range(0, len(text), _MAX_MESSAGE_LENGTH):
            await message.reply_text(text[start:start + _MAX_MESSAGE_LENGTH])

    async def _send_generated_file(self, message: object) -> None:
        path = (
            getattr(self.agent, "last_saved_path", None)
            or getattr(self.agent, "last_captured_image_path", None)
            or getattr(self.agent, "last_generated_video_path", None)
        )
        if not path or not Path(path).is_file():
            return
        try:
            contents = Path(path).read_bytes()
            await message.reply_document(
                document=BytesIO(contents), filename=Path(path).name
            )
        except (OSError, ValueError):
            _LOGGER.exception("No se pudo enviar el archivo generado por Jarvis")

    async def run(self) -> None:
        """Ejecuta el polling hasta que el proceso sea detenido."""
        if not self.token:
            raise ValueError("Define TELEGRAM_BOT_TOKEN para activar Telegram.")
        from telegram.ext import Application, CommandHandler, MessageHandler, filters

        application = Application.builder().token(self.token).build()
        application.add_handler(CommandHandler("start", self.handle_message))
        application.add_handler(CommandHandler("reset", self.handle_message))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        self._stop_event = asyncio.Event()
        try:
            await self._stop_event.wait()
        finally:
            await application.updater.stop()
            await application.stop()
            await application.shutdown()


def start_telegram_bot(agent: object) -> bool:
    """Inicia Telegram en segundo plano si ``TELEGRAM_BOT_TOKEN`` está definido."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False
    import threading

    def _run() -> None:
        asyncio.run(TelegramBridge(agent, token).run())

    thread = threading.Thread(target=_run, name="jarvis-telegram", daemon=True)
    thread.start()
    agent._telegram_thread = thread  # type: ignore[attr-defined]
    return True
