import httpx
import respx

from flathunter.notify.telegram import TelegramSender


@respx.mock
async def test_send_to_multiple_chats_and_edit_all() -> None:
    n = {"i": 0}

    def reply(request: httpx.Request) -> httpx.Response:
        n["i"] += 1
        return httpx.Response(200, json={"ok": True, "result": {"message_id": n["i"]}})

    route = respx.post(url__regex=r"https://api.telegram.org/bottok/\w+").mock(side_effect=reply)
    tg = TelegramSender("tok", "11, 22", "33")
    ids = await tg.send("x", [], loud=False, silent=False)
    assert ids == "11:1,22:2" and tg.all_chat_ids == {"11", "22", "33"}
    assert await tg.send("x", [], loud=True, silent=False) == "33:3"
    await tg.edit(ids, "y", [], loud=False)
    assert route.call_count == 5
