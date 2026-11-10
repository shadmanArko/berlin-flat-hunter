"""Minimal Telegram Bot API client (httpx) + a console sender for dry runs."""

from __future__ import annotations

import os
from typing import Any, Protocol

import httpx


class Sender(Protocol):
    async def send(self, text: str, buttons: list[list[dict[str, str]]], *, loud: bool, silent: bool) -> str: ...
    async def edit(self, message_id: str, text: str, buttons: list[list[dict[str, str]]], *, loud: bool) -> None: ...


class TelegramError(Exception):
    pass


class TelegramSender:
    def __init__(
        self, token: str, chat_id: str, p0_chat_id: str | None = None, client: httpx.AsyncClient | None = None
    ):
        self.token, self.chat_id, self.p0_chat_id = token, chat_id, p0_chat_id or None
        self.client = client or httpx.AsyncClient(timeout=30)

    @classmethod
    def from_env(cls) -> TelegramSender | None:
        t, c = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not t or not c:
            return None
        return cls(t, c, os.environ.get("TELEGRAM_P0_CHAT_ID"))

    async def call(self, method: str, **params: Any) -> Any:
        r = await self.client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=params)
        data = r.json()
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description')}")
        return data["result"]

    def _chat(self, loud: bool) -> str:
        return (self.p0_chat_id or self.chat_id) if loud else self.chat_id

    async def send(self, text: str, buttons: list[list[dict[str, str]]], *, loud: bool, silent: bool) -> str:
        chat = self._chat(loud)
        res = await self.call(
            "sendMessage",
            chat_id=chat,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            disable_notification=silent,
            reply_markup={"inline_keyboard": buttons},
        )
        return f"{chat}:{res['message_id']}"

    async def edit(self, message_id: str, text: str, buttons: list[list[dict[str, str]]], *, loud: bool) -> None:
        chat, mid = message_id.split(":")
        await self.call(
            "editMessageText",
            chat_id=chat,
            message_id=int(mid),
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup={"inline_keyboard": buttons},
        )

    async def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        res: list[dict[str, Any]] = await self.call(
            "getUpdates", offset=offset, timeout=timeout, allowed_updates=["callback_query"]
        )
        return res

    async def answer_callback(self, cb_id: str, text: str) -> None:
        await self.call("answerCallbackQuery", callback_query_id=cb_id, text=text)

    async def reply(self, chat_id: str, text: str) -> None:
        await self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)


class ConsoleSender:
    """Dry-run sender used until Telegram credentials exist."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str, buttons: list[list[dict[str, str]]], *, loud: bool, silent: bool) -> str:
        self.sent.append(text)
        print(
            ("🔊 " if loud else "")
            + text
            + "\n  buttons: "
            + " ".join(b["text"] for row in buttons for b in row)
            + "\n"
        )
        return f"console:{len(self.sent)}"

    async def edit(self, message_id: str, text: str, buttons: list[list[dict[str, str]]], *, loud: bool) -> None:
        print(f"(edit {message_id})\n{text}\n")
