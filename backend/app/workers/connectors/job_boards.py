"""Connecteurs d'API publiques de job boards (stages).

* Greenhouse Job Board API — publique et documentée : https://developers.greenhouse.io/job-board.html
* Lever Postings API — publique et documentée : https://github.com/lever/postings-api
* Arbeitnow Job Board API — publique et gratuite : https://www.arbeitnow.com/api

Greenhouse et Lever publient les offres des entreprises elles-mêmes (source officielle).
Arbeitnow est un agrégateur : ses annonces restent « non vérifiées ».
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

from app.core.text import html_to_text
from app.workers.connectors.base import Connector, is_internship_title, parse_iso_datetime
from app.workers.connectors.geo import detect_countries, detect_remote
from app.workers.connectors.http import ConnectorError


def _entries(config: dict[str, Any], key: str, id_field: str) -> list[dict[str, str]]:
    out = []
    for item in config.get(key, []) or []:
        if isinstance(item, str) and item.strip():
            out.append({id_field: item.strip(), "organization": item.strip().replace("-", " ").title()})
        elif isinstance(item, dict) and item.get(id_field):
            out.append({**item, "organization": item.get("organization") or str(item[id_field]).title()})
    return out


class GreenhouseConnector(Connector):
    name = "greenhouse"
    official = True
    complete_listing = True
    API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

    def fetch(self) -> Iterator[dict[str, Any]]:
        boards = _entries(self.config, "boards", "token")
        if not boards:
            raise ConnectorError("Aucun board Greenhouse configuré (config.boards).")
        keywords = self.config.get("extra_keywords", [])
        failures, produced = 0, 0
        for board in boards:
            token = board["token"]
            try:
                data = self.http.get_json(self.API.format(token=quote(token, safe="")), params={"content": "true"})
            except ConnectorError as exc:
                failures += 1
                self.issue(f"board:{token}", str(exc))
                continue
            jobs = data.get("jobs") if isinstance(data, dict) else None
            if not isinstance(jobs, list):
                failures += 1
                self.issue(f"board:{token}", "Format inattendu : clé 'jobs' absente.")
                continue
            for job in jobs:
                title = str(job.get("title") or "")
                if not is_internship_title(title, keywords):
                    continue
                url = job.get("absolute_url")
                if not url:
                    self.issue(f"{token}:{job.get('id')}", "Annonce sans URL officielle : ignorée.")
                    continue
                location = (job.get("location") or {}).get("name")
                offices = [o.get("location") or o.get("name") for o in job.get("offices") or [] if isinstance(o, dict)]
                countries = detect_countries(" ; ".join(filter(None, [location, *offices])))
                yield {
                    "external_id": f"{token}:{job.get('id')}",
                    "type": "internship",
                    "title": title,
                    "organization": job.get("company_name") or board["organization"],
                    "official_url": url,
                    "source_url": url,
                    "description": html_to_text(job.get("content")),
                    "countries": countries,
                    "location": location,
                    "remote": detect_remote(location),
                    "fields": [
                        d.get("name") for d in job.get("departments") or [] if isinstance(d, dict) and d.get("name")
                    ],
                    "opens_at": (
                        parse_iso_datetime(job.get("first_published")) or parse_iso_datetime(job.get("updated_at"))
                    ),
                    "is_official": True,
                    "raw": {
                        k: job.get(k) for k in ("id", "requisition_id", "updated_at", "first_published", "location")
                    },
                }
                produced += 1
                if produced >= self.max_items:
                    self.truncated = True
                    return
        if failures == len(boards):
            raise ConnectorError("Tous les boards Greenhouse configurés ont échoué.")


class LeverConnector(Connector):
    name = "lever"
    official = True
    complete_listing = True
    API = {"global": "https://api.lever.co/v0/postings/{site}", "eu": "https://api.eu.lever.co/v0/postings/{site}"}

    def fetch(self) -> Iterator[dict[str, Any]]:
        sites = _entries(self.config, "sites", "site")
        if not sites:
            raise ConnectorError("Aucun site Lever configuré (config.sites).")
        keywords = self.config.get("extra_keywords", [])
        failures, produced = 0, 0
        for site in sites:
            slug = site["site"]
            base = self.API.get(site.get("region", "global"), self.API["global"])
            try:
                postings = self.http.get_json(base.format(site=quote(slug, safe="")), params={"mode": "json"})
            except ConnectorError as exc:
                failures += 1
                self.issue(f"site:{slug}", str(exc))
                continue
            if not isinstance(postings, list):
                failures += 1
                self.issue(f"site:{slug}", "Format inattendu : liste attendue.")
                continue
            for post in postings:
                title = str(post.get("text") or "")
                cats = post.get("categories") or {}
                commitment = str(cats.get("commitment") or "")
                if not (is_internship_title(title, keywords) or is_internship_title(commitment)):
                    continue
                url = post.get("hostedUrl") or post.get("applyUrl")
                if not url:
                    self.issue(f"{slug}:{post.get('id')}", "Annonce sans URL officielle : ignorée.")
                    continue
                location = cats.get("location")
                all_locations = cats.get("allLocations") or []
                countries = (
                    [post["country"]] if isinstance(post.get("country"), str) and len(post["country"]) == 2 else []
                )
                countries = countries or detect_countries(" ; ".join(filter(None, [location, *all_locations])))
                lists = "\n\n".join(
                    f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}" for lst in post.get("lists") or []
                )
                description = "\n\n".join(
                    filter(
                        None,
                        [
                            post.get("descriptionPlain") or html_to_text(post.get("description")),
                            lists,
                            post.get("additionalPlain"),
                        ],
                    )
                )
                salary = post.get("salaryRange") or {}
                stipend = None
                if salary.get("min") or salary.get("max"):
                    stipend = f"{salary.get('min', '?')}–{salary.get('max', '?')} {salary.get('currency', '')} {salary.get('interval', '')}".strip()
                workplace = str(post.get("workplaceType") or "").lower()
                yield {
                    "external_id": f"{slug}:{post.get('id')}",
                    "type": "internship",
                    "title": title,
                    "organization": site["organization"],
                    "official_url": url,
                    "source_url": url,
                    "description": description or None,
                    "countries": countries,
                    "location": location,
                    "remote": True
                    if workplace == "remote"
                    else (False if workplace == "onsite" else detect_remote(location)),
                    "fields": [v for v in (cats.get("team"), cats.get("department")) if v],
                    "funding_type": "full" if stipend else "unknown",
                    "stipend": stipend,
                    "opens_at": parse_iso_datetime(post.get("createdAt")),
                    "tags": [commitment] if commitment else [],
                    "is_official": True,
                    "raw": {k: post.get(k) for k in ("id", "createdAt", "country", "workplaceType", "categories")},
                }
                produced += 1
                if produced >= self.max_items:
                    self.truncated = True
                    return
        if failures == len(sites):
            raise ConnectorError("Tous les sites Lever configurés ont échoué.")


class ArbeitnowConnector(Connector):
    name = "arbeitnow"
    official = False  # agrégateur
    complete_listing = False
    API = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self) -> Iterator[dict[str, Any]]:
        max_pages = int(self.config.get("max_pages", 5))
        keywords = self.config.get("extra_keywords", [])
        produced = 0
        url: str | None = self.API
        for page in range(1, max_pages + 1):
            if not url:
                break
            payload = self.http.get_json(url)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                if page == 1:
                    raise ConnectorError("Format inattendu : clé 'data' absente.")
                self.issue(f"page:{page}", "Format inattendu.")
                break
            for job in payload["data"]:
                title = str(job.get("title") or "")
                job_types = " ".join(job.get("job_types") or [])
                if not (is_internship_title(title, keywords) or is_internship_title(job_types)):
                    continue
                if not job.get("url"):
                    continue
                location = job.get("location")
                yield {
                    "external_id": str(job.get("slug") or job["url"]),
                    "type": "internship",
                    "title": title,
                    "organization": job.get("company_name") or "Entreprise non précisée",
                    "official_url": job["url"],
                    "source_url": job["url"],
                    "description": html_to_text(job.get("description")),
                    "countries": detect_countries(location),
                    "location": location,
                    "remote": bool(job.get("remote")) if job.get("remote") is not None else None,
                    "tags": [*(job.get("tags") or []), *(job.get("job_types") or [])],
                    "opens_at": parse_iso_datetime(job.get("created_at")),
                    "is_official": False,
                    "raw": {k: job.get(k) for k in ("slug", "created_at", "job_types", "location", "remote")},
                }
                produced += 1
                if produced >= self.max_items:
                    self.truncated = True
                    return
            links = payload.get("links") or {}
            url = links.get("next") if isinstance(links, dict) else None
