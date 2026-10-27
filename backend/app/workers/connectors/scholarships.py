"""Connecteurs de bourses de master.

* Erasmus Mundus : catalogue officiel publié par l'EACEA (Commission européenne).
  Page HTML publique ; robots.txt respecté ; structure attendue : composants ECL
  (« ecl-content-block »). Si la structure change, l'erreur est journalisée et la
  collecte des autres sources continue.
* RSS/Atom générique : flux publics officiels configurés par l'utilisateur.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin, urlsplit

import feedparser
from bs4 import BeautifulSoup

from app.core.text import html_to_text, normalize_url
from app.workers.connectors.base import Connector, extract_deadline, is_internship_title, parse_iso_datetime
from app.workers.connectors.http import ConnectorError

EMJM_ELIGIBILITY = (
    "Être titulaire d'un premier diplôme de l'enseignement supérieur (licence ou équivalent) ou justifier "
    "d'un niveau d'apprentissage équivalent reconnu. Conditions détaillées (langues, documents, calendrier) "
    "à vérifier sur le site officiel du programme."
)


class ErasmusMundusConnector(Connector):
    name = "erasmus_mundus"
    official = True
    complete_listing = False
    DEFAULT_URL = "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en"

    def fetch(self) -> Iterator[dict[str, Any]]:
        base = self.config.get("url", self.DEFAULT_URL)
        max_pages = int(self.config.get("max_pages", 15))
        seen: set[str] = set()
        produced = 0
        for page in range(max_pages):
            resp = self.http.get(base, params={"page": page} if page else None, check_robots=True)
            items = self.parse_listing(resp.text, str(resp.url))
            if not items:
                if page == 0:
                    raise ConnectorError(
                        "Format de la page catalogue non reconnu (aucun programme trouvé) : connecteur à mettre à jour."
                    )
                break
            new = [i for i in items if i["official_url"] not in seen]
            if not new:
                break
            for item in new:
                seen.add(item["official_url"])
                yield item
                produced += 1
                if produced >= self.max_items:
                    self.truncated = True
                    return

    def parse_listing(self, html: str, page_url: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.select(".ecl-content-block, article.ecl-content-item, .ecl-content-item")
        results: list[dict[str, Any]] = []
        own_host = urlsplit(page_url).netloc
        for block in blocks:
            link = block.select_one(".ecl-content-block__title a[href], h1 a[href], h2 a[href], h3 a[href]")
            if link is None:
                continue
            title = " ".join(link.get_text(" ").split())
            href = urljoin(page_url, link["href"])
            if len(title) < 6 or urlsplit(href).netloc == own_host:
                # On ne garde que les liens vers le site officiel du programme (ou la fiche projet Erasmus+).
                continue
            meta = [
                " ".join(el.get_text(" ").split())
                for el in block.select(
                    ".ecl-content-block__primary-meta-item, .ecl-content-block__secondary-meta-item, "
                    ".ecl-content-block__description"
                )
            ]
            description = "\n".join(m for m in meta if m) or None
            results.append(
                {
                    "external_id": normalize_url(href)[:200],
                    "type": "masters_scholarship",
                    "title": title,
                    "organization": "Consortium Erasmus Mundus (programme soutenu par l'UE)",
                    "official_url": href,
                    "source_url": page_url,
                    "description": description,
                    "eligibility_criteria": EMJM_ELIGIBILITY,
                    "funding_type": "full",
                    "benefits": (
                        "Le catalogue EACEA recense les masters proposant des bourses Erasmus Mundus financées par l'UE "
                        "(frais de participation, voyage, allocation mensuelle) pour une partie des étudiants sélectionnés. "
                        "Montants et nombre de bourses : voir l'appel en vigueur sur le site du programme."
                    ),
                    "countries": [],
                    "tags": ["Erasmus Mundus"],
                    "is_official": True,
                    "raw": {"meta": meta},
                }
            )
        return results


class RssConnector(Connector):
    name = "rss"
    complete_listing = False

    def fetch(self) -> Iterator[dict[str, Any]]:
        feeds = self.config.get("feeds") or []
        if not feeds:
            raise ConnectorError("Aucun flux configuré (config.feeds).")
        produced, failures = 0, 0
        for feed in feeds:
            url = feed.get("url") if isinstance(feed, dict) else None
            if not url:
                continue
            try:
                resp = self.http.get(url)
            except ConnectorError as exc:
                failures += 1
                self.issue(f"feed:{url}", str(exc))
                continue
            parsed = feedparser.parse(resp.content)
            if parsed.bozo and not parsed.entries:
                failures += 1
                self.issue(f"feed:{url}", "Flux RSS/Atom illisible.")
                continue
            for entry in parsed.entries:
                title = " ".join(str(entry.get("title", "")).split())
                link = entry.get("link")
                if not title or not link:
                    continue
                summary = html_to_text(entry.get("summary") or entry.get("description"))
                opp_type = feed.get("type", "auto")
                if opp_type == "auto":
                    text = f"{title} {summary}".lower()
                    if is_internship_title(title):
                        opp_type = "internship"
                    elif any(w in text for w in ("scholarship", "bourse", "stipendium", "fellowship", "master")):
                        opp_type = "masters_scholarship"
                    else:
                        continue
                keywords = [k.lower() for k in feed.get("keywords", [])]
                if keywords and not any(k in f"{title} {summary}".lower() for k in keywords):
                    continue
                deadline = extract_deadline(summary) or extract_deadline(title)
                published = None
                if entry.get("published"):
                    published = parse_iso_datetime(entry.get("published"))
                yield {
                    "external_id": str(entry.get("id") or link)[:200],
                    "type": opp_type,
                    "title": title,
                    "organization": feed.get("organization") or parsed.feed.get("title") or urlsplit(link).netloc,
                    "official_url": link,
                    "source_url": url,
                    "description": summary or None,
                    "countries": feed.get("countries", []),
                    "deadline_at": deadline,
                    "deadline_status": "unverified" if deadline else "unknown",
                    "opens_at": published,
                    "tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")][:10],
                    "is_official": bool(feed.get("official", False)),
                    "raw": {"entry_id": entry.get("id"), "published": entry.get("published")},
                }
                produced += 1
                if produced >= self.max_items:
                    self.truncated = True
                    return
        if failures and failures == len(feeds):
            raise ConnectorError("Tous les flux configurés ont échoué.")
