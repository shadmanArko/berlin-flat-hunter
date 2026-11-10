"""Apply eligibility + scoring to a stored Listing."""

from __future__ import annotations

from flathunter.core.eligibility import Verdict, classify
from flathunter.core.models import Listing
from flathunter.core.profile import Profile
from flathunter.core.scoring import score


def listing_facts(li: Listing) -> dict[str, object]:
    return {
        "rooms": li.rooms,
        "size_m2": li.size_m2,
        "rent_cold": li.rent_cold,
        "operating_costs": li.operating_costs,
        "wbs_required": li.wbs_required,
        "special_need_required": li.special_need_required,
        "wbs_required_rooms": li.wbs_required_rooms,
        "district": li.district,
        "features": li.features,
        "title": li.title,
        "text": f"{li.title}\n{li.raw_text}",
    }


def evaluate(li: Listing, profile: Profile) -> Verdict:
    facts = listing_facts(li)
    v = classify(facts, profile)
    li.eligibility_class = v.eligibility_class
    note = f" [{'; '.join(v.notes)}]" if v.notes else ""
    li.eligibility_reason = v.reason + note
    li.rent_check = v.rent.status
    li.rent_limit_used = v.rent.limit
    li.rent_gross_cold = v.rent.gross_cold if v.rent.gross_cold is not None else li.rent_gross_cold
    li.score, _ = score(facts, v.rent.headroom, profile)
    return v
