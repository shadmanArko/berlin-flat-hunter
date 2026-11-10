"""Phase A application assist: a short, polite German cover letter + document checklist.
Built at runtime from the private profile; never stored or logged. No income figures."""

from __future__ import annotations

from datetime import date

from flathunter.core.models import Listing
from flathunter.core.profile import Profile

MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def _de_date(d: date) -> str:
    return f"{d.day}. {MONTHS[d.month - 1]} {d.year}"


def _move_in(li: Listing, profile: Profile) -> str:
    if profile.move_in_earliest and (not li.available_from or li.available_from < profile.move_in_earliest):
        return f"ab dem {_de_date(profile.move_in_earliest)}"
    if li.available_from and not li.available_now:
        return f"zum {_de_date(li.available_from)}"
    return "zeitnah, gern ab sofort"


def render_letter(li: Listing, profile: Profile) -> str:
    where = " ".join(x for x in (li.street, li.house_no) if x) or "Ihrer Wohnung"
    place = f"{where}" + (f" in {li.district or li.ortsteil}" if (li.district or li.ortsteil) else "")
    rooms = f"{li.rooms:g}-Zimmer-Wohnung" if li.rooms else "Wohnung"
    size = f" ({li.size_m2:g} m²)".replace(".", ",") if li.size_m2 else ""
    wbs_line = ""
    if li.wbs_required is not False:
        level = f"Wohnberechtigungsschein (WBS {profile.wbs_level})"
        extra = " mit besonderem Wohnbedarf" if profile.special_need else ""
        valid = f", gültig bis {_de_date(profile.valid_until)}" if profile.valid_until else ""
        rooms_txt = f"zu {profile.max_rooms:g} Räumen zuzüglich Küche und Nebenräumen"
        wbs_line = (
            f"Wir verfügen über einen {level}{extra} (Berechtigungsgruppe {profile.berechtigungsgruppe}){valid}. "
            f"Der WBS berechtigt uns {rooms_txt}; die angebotene Wohnung liegt innerhalb dieser Berechtigung.\n\n"
        )
    contact = [profile.contact_name]
    if profile.contact_phone:
        contact.append(f"Telefon: {profile.contact_phone}")
    if profile.contact_email:
        contact.append(f"E-Mail: {profile.contact_email}")
    ref = f" (Objekt: {li.title})" if li.title and len(li.title) < 70 else ""
    return (
        "Sehr geehrte Damen und Herren,\n\n"
        f"mit großem Interesse haben wir Ihr Angebot für die {rooms}{size} in der {place}{ref} gesehen "
        "und möchten uns hiermit dafür bewerben.\n\n"
        f"Wir sind ein Haushalt von {profile.household_size} Personen und suchen dringend eine dauerhafte, "
        "familiengerechte Wohnung in Berlin.\n\n"
        f"{wbs_line}"
        f"Ein Einzug wäre für uns {_move_in(li, profile)} möglich. "
        "Alle erforderlichen Unterlagen, darunter den WBS und die Überlassungsmitteilung, senden wir Ihnen "
        "gern umgehend zu. Über eine Einladung zu einer Besichtigung würden wir uns sehr freuen.\n\n"
        "Mit freundlichen Grüßen\n" + "\n".join(c for c in contact if c)
    )


def render_checklist(li: Listing, profile: Profile) -> str:
    items = [
        "1. WBS (Seite mit Wohnberechtigungsschein) – immer",
        "2. Überlassungsmitteilung (Vermieter füllt sie aus und schickt sie ans Wohnungsamt) – mit dem WBS übergeben",
        "3. Bescheinigung über die Prüfung der Wohnberechtigung / Einkommensnachweis – nur falls der Vermieter fragt",
        "4. Ausweise, Mietschuldenfreiheitsbescheinigung, Schufa, ggf. Formulare des Vermieters",
    ]
    notes = []
    if profile.documents_folder:
        notes.append(f"Ordner: {profile.documents_folder}")
    if not (profile.contact_phone and profile.contact_email):
        notes.append("⚠️ Telefon/E-Mail fehlen noch in config/profile.yaml – im Anschreiben ergänzen")
    if li.rent_check == "rent_borderline":
        notes.append("⚠️ Miete knapp über dem Limit: vor der Bewerbung beim Jobcenter nachfragen")
    if li.eligibility_class == "needs_review" and li.eligibility_reason:
        notes.append(f"⚠️ Prüfen: {li.eligibility_reason}")
    return "\n".join(items + notes)
