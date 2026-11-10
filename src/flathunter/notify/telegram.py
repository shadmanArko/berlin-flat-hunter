"""Minimal Telegram Bot API client (httpx) + a console sender for dry runs."""

from __future__ import annotations

import asyncio
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
        self.send_gap_s = 3.0
        self.client = client or httpx.AsyncClient(timeout=30)

    @classmethod
    def from_env(cls) -> TelegramSender | None:
        t, c = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not t or not c:
            return None
        return cls(t, c, os.environ.get("TELEGRAM_P0_CHAT_ID"))

    async def call(self, method: str, **params: Any) -> Any:
        for attempt in range(4):
            r = await self.client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=params)
            data = r.json()
            if data.get("ok"):
                return data["result"]
            wait = (data.get("parameters") or {}).get("retry_after")
            if r.status_code == 429 and wait and attempt < 3:
                await asyncio.sleep(min(int(wait) + 1, 90))  # Telegram flood control: wait, then retry
                continue
            raise TelegramError(f"{method}: {data.get('description')}")
        raise TelegramError(f"{method}: gave up after retries")

    @staticmethod
    def _ids(value: str | None) -> list[str]:
        return [x.strip() for x in (value or "").split(",") if x.strip()]

    @property
    def all_chat_ids(self) -> set[str]:
        return set(self._ids(self.chat_id)) | set(self._ids(self.p0_chat_id))

    def _recipients(self, loud: bool) -> list[str]:
        return (self._ids(self.p0_chat_id) if loud else []) or self._ids(self.chat_id)

    async def send(self, text: str, buttons: list[list[dict[str, str]]], *, loud: bool, silent: bool) -> str:
        """Send to every recipient; returns 'chat:msg,chat:msg' so the alert can be edited everywhere."""
        refs: list[str] = []
        for chat in self._recipients(loud):
            await asyncio.sleep(self.send_gap_s)  # stay well under Telegram's per-group limit
            res = await self.call(
                "sendMessage",
                chat_id=chat,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                disable_notification=silent,
                reply_markup={"inline_keyboard": buttons},
            )
            refs.append(f"{chat}:{res['message_id']}")
        return ",".join(refs)

    async def edit(self, message_id: str, text: str, buttons: list[list[dict[str, str]]], *, loud: bool) -> None:
        for ref in message_id.split(","):
            chat, mid = ref.split(":")
            try:
                await self._edit_one(chat, mid, text, buttons)
            except TelegramError as e:
                if "not modified" not in str(e):  # identical content is fine
                    raise

    async def _edit_one(self, chat: str, mid: str, text: str, buttons: list[list[dict[str, str]]]) -> None:
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
