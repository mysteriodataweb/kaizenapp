"""Modèles d'e-mails HTML (lisibles sur mobile, styles en ligne) et texte brut."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape

from app.core.config import get_settings
from app.core.timeutil import safe_zone

TYPE_LABELS = {"internship": "Stage", "masters_scholarship": "Bourse de master"}
ELIGIBILITY_LABELS = {
    "eligible": "Éligible (critères publiés satisfaits)",
    "ineligible": "Inéligible (critère publié incompatible)",
    "unknown": "Éligibilité à confirmer",
}


@dataclass
class EmailItem:
    opportunity_id: str
    title: str
    organization: str
    type: str
    official_url: str
    deadline_at: datetime | None
    deadline_status: str
    eligibility: str | None
    score: float | None
    confidence: float | None
    reasons: list[str] = field(default_factory=list)
    note: str | None = None


def format_deadline(dt: datetime | None, status: str, tz: str | None) -> str:
    if dt is None or status == "unknown":
        return "Date limite inconnue — à vérifier sur la source officielle"
    local = dt.astimezone(safe_zone(tz))
    label = local.strftime("%d/%m/%Y")
    if (local.hour or local.minute) and not (local.hour == 23 and local.minute == 59):
        label += local.strftime(" à %H:%M")
    if status == "unverified":
        return f"{label} (date NON vérifiée — confirmez-la sur le site officiel)"
    return label


def _score_text(item: EmailItem) -> str:
    if item.score is None:
        return "Score non calculé"
    conf = item.confidence or 0
    label = "élevée" if conf >= 0.8 else "moyenne" if conf >= 0.5 else "faible"
    return f"{item.score:.0f}/100 (fiabilité {label})"


def _app_link(item: EmailItem) -> str:
    return f"{get_settings().frontend_url.rstrip('/')}/opportunities/{item.opportunity_id}"


def item_html(item: EmailItem, tz: str | None) -> str:
    reasons = "".join(f"<li style='margin:0 0 4px'>{escape(r)}</li>" for r in item.reasons[:4])
    note = f"<p style='margin:8px 0 0;font-weight:700'>{escape(item.note)}</p>" if item.note else ""
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:2px solid #111;margin:0 0 16px;background:#fff">
<tr><td style="padding:14px 16px">
<p style="margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.06em">
<span style="background:#FFC400;border:1px solid #111;padding:2px 6px">{escape(TYPE_LABELS.get(item.type, item.type))}</span>
&nbsp;{escape(item.organization)}</p>
<h2 style="margin:0 0 8px;font-size:18px;line-height:1.25">{escape(item.title)}</h2>
<p style="margin:0 0 4px"><strong>Date limite :</strong> {escape(format_deadline(item.deadline_at, item.deadline_status, tz))}</p>
<p style="margin:0 0 4px"><strong>Éligibilité :</strong> {escape(ELIGIBILITY_LABELS.get(item.eligibility or "unknown", "À confirmer"))}</p>
<p style="margin:0 0 4px"><strong>Compatibilité :</strong> {escape(_score_text(item))}</p>
{f"<ul style='margin:6px 0 0 18px;padding:0;font-size:14px'>{reasons}</ul>" if reasons else ""}
{note}
<p style="margin:12px 0 0">
<a href="{escape(item.official_url)}" style="display:inline-block;background:#FFC400;color:#111;border:2px solid #111;padding:8px 12px;font-weight:700;text-decoration:none">Source officielle</a>
&nbsp;<a href="{escape(_app_link(item))}" style="color:#111;font-weight:700">Voir l'analyse</a></p>
</td></tr></table>"""


def item_text(item: EmailItem, tz: str | None) -> str:
    lines = [
        f"• {item.title} — {item.organization} [{TYPE_LABELS.get(item.type, item.type)}]",
        f"  Date limite : {format_deadline(item.deadline_at, item.deadline_status, tz)}",
        f"  Éligibilité : {ELIGIBILITY_LABELS.get(item.eligibility or 'unknown', 'À confirmer')}",
        f"  Compatibilité : {_score_text(item)}",
    ]
    lines += [f"  - {r}" for r in item.reasons[:4]]
    if item.note:
        lines.append(f"  {item.note}")
    lines += [f"  Source officielle : {item.official_url}", f"  Analyse : {_app_link(item)}", ""]
    return "\n".join(lines)


def layout(title: str, intro: str, body_html: str, footer: str | None = None) -> str:
    settings = get_settings()
    footer = footer or (
        "Le score de compatibilité n'est pas une probabilité d'acceptation. "
        "Aucune candidature n'est envoyée sans votre validation."
    )
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:#f4f4f0;font-family:Arial,Helvetica,sans-serif;color:#111">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:16px 8px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
<tr><td style="background:#111;color:#fff;padding:14px 16px;border:2px solid #111">
<strong style="font-size:13px;letter-spacing:.08em;text-transform:uppercase">Opportunity Intelligence</strong></td></tr>
<tr><td style="background:#fff;border:2px solid #111;border-top:0;padding:20px 16px">
<h1 style="margin:0 0 8px;font-size:22px;line-height:1.2">{escape(title)}</h1>
<p style="margin:0 0 16px;font-size:15px">{escape(intro)}</p>
{body_html}
<p style="margin:16px 0 0"><a href="{escape(settings.frontend_url)}/dashboard" style="color:#111;font-weight:700">Ouvrir le tableau de bord</a></p>
</td></tr>
<tr><td style="padding:12px 4px;font-size:12px;color:#444">{escape(footer)}<br>
Gérer vos alertes : {escape(settings.frontend_url)}/notifications</td></tr>
</table></td></tr></table></body></html>"""


def render_items(
    title: str, intro: str, items: list[EmailItem], tz: str | None, extra_text: str = ""
) -> tuple[str, str]:
    html = layout(title, intro, "".join(item_html(i, tz) for i in items) + extra_text)
    text = "\n".join([title, "", intro, "", *[item_text(i, tz) for i in items]])
    text += "\nLe score de compatibilité n'est pas une probabilité d'acceptation.\n"
    return html, text


def render_simple(title: str, paragraphs: list[str], link: tuple[str, str] | None = None) -> tuple[str, str]:
    body = "".join(f"<p style='margin:0 0 12px'>{escape(p)}</p>" for p in paragraphs)
    if link:
        body += (
            f"<p><a href='{escape(link[1])}' style='display:inline-block;background:#FFC400;color:#111;"
            f"border:2px solid #111;padding:10px 14px;font-weight:700;text-decoration:none'>{escape(link[0])}</a></p>"
        )
    html = layout(title, "", body)
    text = "\n\n".join([title, *paragraphs] + ([f"{link[0]} : {link[1]}"] if link else []))
    return html, text
