"""Lecture d'une offre à partir d'un lien collé par un utilisateur.

Une seule page publique est lue, à la demande de l'utilisateur, avec les règles de la collecte :
robots.txt respecté, User-Agent identifiable, aucun contournement (connexion, CAPTCHA, anti-bot).

Protection SSRF : seules les adresses publiques sont contactées (http/https, ports 80/443, aucune
adresse privée, locale ou réservée), y compris à chaque redirection, et la taille lue est plafonnée.

Rien n'est inventé : un champ introuvable reste vide, une date trouvée reste « à vérifier », et
l'utilisateur relit le brouillon avant tout enregistrement.
"""

from __future__ import annotations

import io
import ipaddress
import json
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import get_settings
from app.core.text import html_to_text
from app.workers.connectors.base import extract_deadline, is_internship_title, parse_iso_datetime
from app.workers.connectors.geo import detect_countries, detect_remote

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
MAX_TEXT = 20_000
ALLOWED_PORTS = (80, 443)
ALLOWED_TYPES = ("text/html", "application/xhtml+xml", "application/json", "application/ld+json", "application/pdf")
SCHOLARSHIP_RE = re.compile(
    r"(?<![\w])(scholarships?|bourses?|fellowships?|stipendi(?:um|en)|becas?|borsa|borse)(?![\w])", re.I
)
GREENHOUSE_RE = re.compile(r"^https://(?:boards|job-boards)\.greenhouse\.io/(?P<board>[\w-]+)/jobs/(?P<id>\d+)", re.I)
LEVER_RE = re.compile(
    r"^https://jobs\.(?P<eu>eu\.)?lever\.co/(?P<site>[\w.-]+)/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)
LOGIN_PATH_RE = re.compile(r"/(login|signin|sign-in|authwall|connexion|auth)(/|$|\?)", re.I)

Resolver = Callable[[str, int], list[str]]


class LinkImportError(Exception):
    """Lecture impossible ; le message est destiné à l'utilisateur."""


class InvalidLink(LinkImportError):
    """Lien refusé avant toute connexion (format, identifiants, port, adresse non publique)."""


class AccessBlocked(LinkImportError):
    """Le site refuse la lecture automatique (robots.txt, connexion, CAPTCHA) : aucun contournement."""


def resolve_host(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise LinkImportError("Nom de domaine introuvable : vérifiez le lien.") from exc
    return sorted({str(info[4][0]) for info in infos})


def _is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url_shape(url: str) -> tuple[str, int]:
    """Contrôles sans réseau : http(s), sans identifiants, port standard, pas d'adresse IP non publique.
    Retourne (hôte, port)."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise InvalidLink("Lien invalide : seules les adresses http(s) sont acceptées.")
    if parts.username or parts.password:
        raise InvalidLink("Lien invalide : identifiants dans l'adresse refusés.")
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise InvalidLink("Lien invalide : port incorrect.") from exc
    if port not in ALLOWED_PORTS:
        raise InvalidLink("Lien refusé : port non standard.")
    try:
        literal = ipaddress.ip_address(parts.hostname)
    except ValueError:
        literal = None
    if literal is not None and not _is_public(str(literal)):
        raise InvalidLink("Lien refusé : cette adresse ne correspond pas à un site public.")
    return parts.hostname, port


def check_public_url(url: str, resolver: Resolver) -> str:
    """Refuse tout ce qui n'est pas une page web publique (y compris après résolution DNS)."""
    url = url.strip()
    host, port = check_url_shape(url)
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = resolver(host, port)
    if not addresses or not all(_is_public(a) for a in addresses):
        raise InvalidLink("Lien refusé : cette adresse ne correspond pas à un site public.")
    return url


@dataclass
class Fetched:
    url: str
    content_type: str
    body: bytes
    truncated: bool = False


class SafeFetcher:
    def __init__(self, *, transport: httpx.BaseTransport | None = None, resolver: Resolver = resolve_host):
        settings = get_settings()
        self.user_agent = settings.collector_user_agent
        self.resolver = resolver
        self.client = httpx.Client(
            timeout=min(settings.collector_timeout_seconds, 15.0),
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "fr,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/json,application/pdf;q=0.9,*/*;q=0.5",
            },
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> SafeFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, url: str, *, max_bytes: int = MAX_BYTES, types: tuple[str, ...] | None = ALLOWED_TYPES) -> Fetched:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            check_public_url(current, self.resolver)
            try:
                with self.client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise LinkImportError("Redirection invalide.")
                        current = urljoin(current, location)
                        continue
                    host = urlsplit(current).hostname
                    if resp.status_code in (401, 403, 407, 999):
                        raise AccessBlocked(
                            f"{host} refuse la lecture automatique (HTTP {resp.status_code}) : aucun contournement tenté."
                        )
                    if resp.status_code in (404, 410):
                        raise LinkImportError("Page introuvable (HTTP 404) : l'offre a peut-être été retirée.")
                    if resp.status_code >= 400:
                        raise LinkImportError(f"Le site a répondu HTTP {resp.status_code}.")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if types is not None and ctype and ctype not in types:
                        raise LinkImportError(f"Type de contenu non pris en charge ({ctype}).")
                    chunks: list[bytes] = []
                    size, truncated = 0, False
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            truncated = True
                            break
                        chunks.append(chunk)
                    return Fetched(current, ctype, b"".join(chunks), truncated)
            except httpx.TimeoutException as exc:
                raise LinkImportError("Le site n'a pas répondu à temps.") from exc
            except httpx.HTTPError as exc:
                raise LinkImportError(f"Erreur réseau ({exc.__class__.__name__}).") from exc
        raise LinkImportError("Trop de redirections.")

    def get_json(self, url: str) -> Any:
        fetched = self.get(url)
        try:
            return json.loads(fetched.body)
        except ValueError as exc:
            raise LinkImportError("Réponse JSON invalide.") from exc

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        try:
            fetched = self.get(f"{parts.scheme}://{parts.netloc}/robots.txt", max_bytes=500_000, types=None)
        except AccessBlocked:
            return False  # robots.txt lui-même interdit : on s'abstient
        except LinkImportError:
            return True  # pas de robots.txt lisible : aucune restriction déclarée
        parser = RobotFileParser()
        parser.parse(fetched.body.decode("utf-8", errors="replace").splitlines())
        return parser.can_fetch(self.user_agent, url)


@dataclass
class Extraction:
    method: str  # greenhouse-api | lever-api | json-ld | html | pdf | none
    fields: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    fetched: bool = False


def guess_type(title: str | None, *, intern: bool = False) -> str | None:
    if intern or (title and is_internship_title(title)):
        return "internship"
    if title and SCHOLARSHIP_RE.search(title):
        return "masters_scholarship"
    return None


def _deadline_fields(dt: datetime | None) -> dict[str, Any]:
    return {"deadline_date": dt.date() if dt else None}


def _clip(text: str | None, limit: int = MAX_TEXT) -> str | None:
    text = (text or "").strip()
    return text[:limit] if text else None


def _from_greenhouse(fetcher: SafeFetcher, board: str, job_id: str) -> Extraction:
    api = f"https://boards-api.greenhouse.io/v1/boards/{quote(board, safe='')}/jobs/{job_id}"
    job = fetcher.get_json(api)
    if not isinstance(job, dict) or not job.get("title"):
        raise LinkImportError("Format inattendu de l'API Greenhouse.")
    location = (job.get("location") or {}).get("name")
    fields = {
        "title": job.get("title"),
        "organization": job.get("company_name"),
        "official_url": job.get("absolute_url"),
        "description": _clip(html_to_text(job.get("content"))),
        "location": location,
        "countries": detect_countries(location),
        "remote": detect_remote(location),
        "fields": [d.get("name") for d in job.get("departments") or [] if isinstance(d, dict) and d.get("name")],
        "type": guess_type(job.get("title")),
    }
    notes = ["Offre lue via l'API publique Greenhouse (publiée par l'entreprise)."]
    return Extraction("greenhouse-api", fields, notes, True)


def _from_lever(fetcher: SafeFetcher, site: str, posting_id: str, eu: bool) -> Extraction:
    host = "api.eu.lever.co" if eu else "api.lever.co"
    post = fetcher.get_json(f"https://{host}/v0/postings/{quote(site, safe='')}/{posting_id}")
    if not isinstance(post, dict) or not post.get("text"):
        raise LinkImportError("Format inattendu de l'API Lever.")
    cats = post.get("categories") or {}
    location = cats.get("location")
    workplace = str(post.get("workplaceType") or "").lower()
    lists = "\n\n".join(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}" for lst in post.get("lists") or [])
    description = "\n\n".join(
        filter(None, [post.get("descriptionPlain") or html_to_text(post.get("description")), lists])
    )
    country = post.get("country")
    fields = {
        "title": post.get("text"),
        "organization": None,
        "official_url": post.get("hostedUrl"),
        "description": _clip(description),
        "location": location,
        "countries": [country] if isinstance(country, str) and len(country) == 2 else detect_countries(location),
        "remote": True if workplace == "remote" else (False if workplace == "onsite" else detect_remote(location)),
        "fields": [v for v in (cats.get("team"), cats.get("department")) if v],
        "type": guess_type(post.get("text"), intern=is_internship_title(str(cats.get("commitment") or ""))),
    }
    notes = ["Offre lue via l'API publique Lever (publiée par l'entreprise). L'API ne donne pas le nom de l'organisme."]
    return Extraction("lever-api", fields, notes, True)


def _jsonld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except ValueError:
            continue
        stack: list[Any] = [data]
        while stack:
            current = stack.pop()
            if isinstance(current, list):
                stack.extend(current)
            elif isinstance(current, dict):
                objects.append(current)
                if "@graph" in current:
                    stack.append(current["@graph"])
    return objects


def _types(obj: dict[str, Any]) -> set[str]:
    value = obj.get("@type")
    values = value if isinstance(value, list) else [value]
    return {str(v).lower() for v in values if v}


def _name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("name")
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str)), None)
    if not value:
        return None
    return " ".join(str(value).split()) or None


def _job_location(posting: dict[str, Any]) -> tuple[str | None, list[str]]:
    places = posting.get("jobLocation")
    places = places if isinstance(places, list) else [places] if places else []
    labels: list[str] = []
    codes: list[str] = []
    for place in places:
        address = place.get("address") if isinstance(place, dict) else None
        if isinstance(address, str):
            labels.append(address)
            continue
        if not isinstance(address, dict):
            continue
        country = address.get("addressCountry")
        country = _name(country) if isinstance(country, dict) else country
        parts = [address.get("addressLocality"), address.get("addressRegion")]
        if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country.strip()):
            codes.append(country.strip().upper())
        elif country:
            parts.append(str(country))
        labels.append(", ".join(str(p) for p in parts if p))
    label = " ; ".join(dict.fromkeys(lbl for lbl in labels if lbl)) or None
    countries = list(dict.fromkeys(codes + detect_countries(label)))
    return label, countries


def _salary(posting: dict[str, Any]) -> str | None:
    salary = posting.get("baseSalary")
    if not isinstance(salary, dict):
        return None
    value = salary.get("value")
    currency = salary.get("currency") or ""
    if isinstance(value, dict):
        low, high = value.get("minValue"), value.get("maxValue")
        amount = f"{low}–{high}" if low and high else (value.get("value") or low or high)
        unit = value.get("unitText") or ""
    else:
        amount, unit = value, ""
    return f"{amount} {currency} {unit}".strip() if amount else None


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "template", "svg", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = [" ".join(line.split()) for line in root.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return " ".join(str(tag["content"]).split()) or None
    return None


def _from_html(fetched: Fetched) -> Extraction:
    soup = BeautifulSoup(fetched.body, "html.parser")
    objects = _jsonld_objects(soup)
    head = fetched.body[:20_000].decode("utf-8", errors="ignore").lower()
    posting = next((o for o in objects if "jobposting" in _types(o)), None)
    org_obj = next(
        (o for o in objects if _types(o) & {"organization", "collegeoruniversity", "educationalorganization"}), None
    )
    site_name = _meta(soup, "og:site_name", "application-name")
    page_title = _meta(soup, "og:title", "twitter:title")
    h1 = soup.find("h1")
    h1_text = " ".join(h1.get_text(" ").split()) if h1 else None
    title_tag = " ".join(soup.title.get_text(" ").split()) if soup.title else None
    text = _visible_text(soup)
    challenge = ("captcha" in head or "cf-chl" in head or "challenge-platform" in head) and len(text) < 1500
    if challenge or (title_tag or "").lower().startswith("just a moment"):
        raise AccessBlocked("Le site présente une vérification anti-robot (CAPTCHA) : aucun contournement tenté.")

    notes: list[str] = []
    if posting:
        employment = posting.get("employmentType")
        employment = employment if isinstance(employment, list) else [employment]
        intern = any(str(e).upper() == "INTERN" for e in employment if e)
        location, countries = _job_location(posting)
        remote = True if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE" else detect_remote(location)
        deadline = parse_iso_datetime(posting.get("validThrough"))
        title = _name(posting.get("title")) or _name(posting.get("name"))
        fields = {
            "title": title,
            "organization": _name(posting.get("hiringOrganization")) or site_name,
            "description": _clip(html_to_text(posting.get("description"))) or _clip(text),
            "location": location,
            "countries": countries,
            "remote": remote,
            "stipend": _salary(posting),
            "type": guess_type(title, intern=intern),
            **_deadline_fields(deadline),
        }
        notes.append("Données structurées « JobPosting » trouvées sur la page.")
        if deadline:
            notes.append(
                "Date limite publiée dans les données structurées : vérifiez-la sur la page avant de la confirmer."
            )
        return Extraction("json-ld", fields, notes, True)

    title = page_title or h1_text or title_tag
    deadline = extract_deadline(text)
    fields = {
        "title": title,
        "organization": site_name or _name(org_obj),
        "description": _clip(text),
        "type": guess_type(title),
        **_deadline_fields(deadline),
    }
    notes.append("Pas de données structurées : titre et description repris du contenu de la page, à relire.")
    if deadline:
        notes.append("Une date limite a été repérée dans le texte : à vérifier.")
    return Extraction("html", fields, notes, True)


def _from_pdf(fetched: Fetched) -> Extraction:
    if fetched.truncated:
        raise LinkImportError("Document PDF trop volumineux (3 Mo maximum).")
    try:
        reader = PdfReader(io.BytesIO(fetched.body))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:15])
    except (PdfReadError, ValueError, KeyError) as exc:
        raise LinkImportError("Document PDF illisible.") from exc
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    title = next((line for line in lines if len(line) >= 10), None)
    deadline = extract_deadline(text)
    fields = {
        "title": title[:400] if title else None,
        "description": _clip("\n".join(lines)),
        "type": guess_type(title),
        **_deadline_fields(deadline),
    }
    notes = ["Document PDF : titre et description repris du texte, à relire."]
    if deadline:
        notes.append("Une date limite a été repérée dans le texte : à vérifier.")
    return Extraction("pdf", fields, notes, True)


def extract(url: str, fetcher: SafeFetcher) -> Extraction:
    """Lit le lien et produit un brouillon. Lève LinkImportError / AccessBlocked si la lecture est impossible."""
    url = check_public_url(url, fetcher.resolver)
    gh = GREENHOUSE_RE.match(url)
    if gh:
        return _from_greenhouse(fetcher, gh.group("board"), gh.group("id"))
    lever = LEVER_RE.match(url)
    if lever:
        return _from_lever(fetcher, lever.group("site"), lever.group("id"), bool(lever.group("eu")))
    if not fetcher.allowed_by_robots(url):
        raise AccessBlocked("Ce site n'autorise pas la lecture automatique de cette page (robots.txt).")
    fetched = fetcher.get(url)
    if LOGIN_PATH_RE.search(urlsplit(fetched.url).path + "?"):
        raise AccessBlocked("La page demande une connexion : aucun contournement tenté.")
    if fetched.content_type == "application/pdf" or fetched.body[:5] == b"%PDF-":
        result = _from_pdf(fetched)
    else:
        result = _from_html(fetched)
    if fetched.truncated and result.method != "pdf":
        result.notes.append("Page très longue : seul le début a été lu.")
    return result
