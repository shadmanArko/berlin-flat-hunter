"""Send instant alerts for listings that were never notified; edit alerts when a source is added;
process button callbacks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from flathunter.core.models import KeyValue, Listing, Notification, UserAction
from flathunter.core.profile import Profile
from flathunter.core.scoring import CLASS_ORDER
from flathunter.notify.render import render_alert
from flathunter.notify.telegram import Sender, TelegramSender


def alertable(cls: str | None, profile: Profile, li: Listing | None = None) -> bool:
    # Borderline rent on a flat that needs no WBS is a digest-level item unless free-market is "instant".
    if (
        cls == "needs_review"
        and li is not None
        and li.wbs_required is False
        and profile.include_free_market != "instant"
    ):
        return False
    if cls in ("P0_special_need", "P1_wbs", "needs_review"):
        return True
    return cls == "P2_free_market" and profile.include_free_market == "instant"


def _acted_on(s: Session, listing_id: int) -> bool:
    return s.scalar(select(UserAction.id).where(UserAction.listing_id == listing_id)) is not None


async def dispatch_new(s: Session, sender: Sender, profile: Profile) -> int:
    """Alert once per flat. A flat that gains a second source gets its existing alert edited."""
    sent = 0
    s.expire_all()  # sources may have been added since objects were loaded
    listings = sorted(
        s.scalars(select(Listing).where(Listing.status == "active")).all(),
        key=lambda x: (CLASS_ORDER.get(x.eligibility_class or "", 9), -(x.score or 0)),
    )
    for li in listings:
        if not alertable(li.eligibility_class, profile, li):
            continue
        prior = s.scalar(
            select(Notification)
            .where(Notification.listing_id == li.id, Notification.channel == "telegram")
            .order_by(Notification.id)
        )
        text, buttons = render_alert(li, profile)
        loud = li.eligibility_class == "P0_special_need"
        if prior is None:
            if _acted_on(s, li.id):
                continue
            mid = await sender.send(text, buttons, loud=loud, silent=li.eligibility_class == "needs_review")
            kind = "needs_review" if li.eligibility_class == "needs_review" else "instant"
            s.add(Notification(listing_id=li.id, channel="telegram", kind=kind, message_id=mid))
            sent += 1
        else:
            n_src = s.scalar(
                select(Notification).where(Notification.listing_id == li.id, Notification.kind == "source_added")
            )
            n_notified = len(li.sources)
            if prior.message_id and n_notified > 1 and n_src is None:
                await sender.edit(prior.message_id, text, buttons, loud=loud)
                s.add(
                    Notification(listing_id=li.id, channel="telegram", kind="source_added", message_id=prior.message_id)
                )
        s.commit()
    return sent


ACTION_REPLY = {
    "applied": "✅ als beworben gespeichert",
    "not_interested": "👎 ausgeblendet",
    "letter": "📝 Anschreiben-Generator kommt in M6",
}


async def handle_callbacks(s: Session, tg: TelegramSender) -> int:
    row = s.get(KeyValue, "tg_offset")
    offset = int(row.value) if row else 0
    updates: list[dict[str, Any]] = await tg.get_updates(offset)
    for u in updates:
        offset = u["update_id"] + 1
        cb = u.get("callback_query")
        if not cb or str(cb["message"]["chat"]["id"]) not in tg.all_chat_ids:
            continue  # ignore anything from other chats
        _, lid, action = cb["data"].split(":")
        if action in ("applied", "not_interested"):
            s.add(UserAction(listing_id=int(lid), action=action))
        await tg.answer_callback(cb["id"], ACTION_REPLY.get(action, "ok"))
    if row:
        row.value = str(offset)
    else:
        s.add(KeyValue(key="tg_offset", value=str(offset)))
    s.commit()
    return len(updates)
