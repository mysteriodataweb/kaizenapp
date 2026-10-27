"""Détection prudente du pays à partir d'un libellé de localisation.

Retourne une liste vide si rien n'est reconnu : on ne devine jamais au hasard."""

from __future__ import annotations

import re

from app.core.text import normalize_text

COUNTRIES: dict[str, list[str]] = {
    "FR": ["france", "frankreich"],
    "DE": ["germany", "allemagne", "deutschland"],
    "BE": ["belgium", "belgique", "belgien"],
    "NL": ["netherlands", "pays bas", "niederlande", "holland"],
    "LU": ["luxembourg"],
    "CH": ["switzerland", "suisse", "schweiz"],
    "AT": ["austria", "autriche", "osterreich"],
    "ES": ["spain", "espagne", "espana", "spanien"],
    "PT": ["portugal"],
    "IT": ["italy", "italie", "italia", "italien"],
    "IE": ["ireland", "irlande"],
    "GB": ["united kingdom", "uk", "royaume uni", "england", "scotland", "great britain"],
    "SE": ["sweden", "suede", "schweden"],
    "NO": ["norway", "norvege"],
    "DK": ["denmark", "danemark"],
    "FI": ["finland", "finlande"],
    "PL": ["poland", "pologne", "polen"],
    "CZ": ["czech republic", "czechia", "republique tcheque"],
    "HU": ["hungary", "hongrie"],
    "RO": ["romania", "roumanie"],
    "GR": ["greece", "grece"],
    "EE": ["estonia", "estonie"],
    "LT": ["lithuania", "lituanie"],
    "LV": ["latvia", "lettonie"],
    "US": ["united states", "usa", "etats unis", "u.s."],
    "CA": ["canada"],
    "MX": ["mexico", "mexique"],
    "BR": ["brazil", "bresil"],
    "AR": ["argentina", "argentine"],
    "IN": ["india", "inde"],
    "CN": ["china", "chine"],
    "JP": ["japan", "japon"],
    "KR": ["south korea", "coree du sud", "korea"],
    "SG": ["singapore", "singapour"],
    "AU": ["australia", "australie"],
    "NZ": ["new zealand", "nouvelle zelande"],
    "AE": ["united arab emirates", "emirats arabes unis", "uae"],
    "IL": ["israel"],
    "TR": ["turkey", "turquie", "turkiye"],
    "SN": ["senegal"],
    "CI": ["cote d ivoire", "ivory coast"],
    "MA": ["morocco", "maroc"],
    "TN": ["tunisia", "tunisie"],
    "DZ": ["algeria", "algerie"],
    "EG": ["egypt", "egypte"],
    "NG": ["nigeria"],
    "GH": ["ghana"],
    "KE": ["kenya"],
    "ZA": ["south africa", "afrique du sud"],
    "RW": ["rwanda"],
    "CM": ["cameroon", "cameroun"],
}

CITIES: dict[str, str] = {
    "paris": "FR",
    "lyon": "FR",
    "marseille": "FR",
    "toulouse": "FR",
    "lille": "FR",
    "bordeaux": "FR",
    "nantes": "FR",
    "grenoble": "FR",
    "sophia antipolis": "FR",
    "montpellier": "FR",
    "strasbourg": "FR",
    "berlin": "DE",
    "munich": "DE",
    "munchen": "DE",
    "hamburg": "DE",
    "frankfurt": "DE",
    "cologne": "DE",
    "koln": "DE",
    "stuttgart": "DE",
    "dusseldorf": "DE",
    "leipzig": "DE",
    "dresden": "DE",
    "heidelberg": "DE",
    "bonn": "DE",
    "karlsruhe": "DE",
    "aachen": "DE",
    "hannover": "DE",
    "nuremberg": "DE",
    "nurnberg": "DE",
    "brussels": "BE",
    "bruxelles": "BE",
    "antwerp": "BE",
    "ghent": "BE",
    "leuven": "BE",
    "liege": "BE",
    "amsterdam": "NL",
    "rotterdam": "NL",
    "utrecht": "NL",
    "eindhoven": "NL",
    "the hague": "NL",
    "delft": "NL",
    "zurich": "CH",
    "geneva": "CH",
    "geneve": "CH",
    "lausanne": "CH",
    "basel": "CH",
    "bern": "CH",
    "vienna": "AT",
    "wien": "AT",
    "madrid": "ES",
    "barcelona": "ES",
    "valencia": "ES",
    "lisbon": "PT",
    "lisboa": "PT",
    "porto": "PT",
    "milan": "IT",
    "milano": "IT",
    "rome": "IT",
    "roma": "IT",
    "turin": "IT",
    "dublin": "IE",
    "london": "GB",
    "manchester": "GB",
    "edinburgh": "GB",
    "cambridge": "GB",
    "oxford": "GB",
    "stockholm": "SE",
    "gothenburg": "SE",
    "oslo": "NO",
    "copenhagen": "DK",
    "helsinki": "FI",
    "warsaw": "PL",
    "krakow": "PL",
    "prague": "CZ",
    "budapest": "HU",
    "bucharest": "RO",
    "athens": "GR",
    "tallinn": "EE",
    "new york": "US",
    "san francisco": "US",
    "seattle": "US",
    "boston": "US",
    "austin": "US",
    "chicago": "US",
    "los angeles": "US",
    "washington": "US",
    "toronto": "CA",
    "montreal": "CA",
    "vancouver": "CA",
    "bangalore": "IN",
    "bengaluru": "IN",
    "tokyo": "JP",
    "seoul": "KR",
    "sydney": "AU",
    "melbourne": "AU",
    "dubai": "AE",
    "tel aviv": "IL",
    "istanbul": "TR",
    "dakar": "SN",
    "abidjan": "CI",
    "casablanca": "MA",
    "rabat": "MA",
    "tunis": "TN",
    "algiers": "DZ",
    "cairo": "EG",
    "lagos": "NG",
    "accra": "GH",
    "nairobi": "KE",
    "cape town": "ZA",
    "johannesburg": "ZA",
    "kigali": "RW",
    "douala": "CM",
    "yaounde": "CM",
}

REMOTE_WORDS = ("remote", "teletravail", "home office", "anywhere", "worldwide", "distanciel")


def detect_countries(location: str | None) -> list[str]:
    if not location:
        return []
    norm = f" {normalize_text(location)} "
    found: list[str] = []
    for code, names in COUNTRIES.items():
        if any(re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", norm) for n in names):
            found.append(code)
    for city, code in CITIES.items():
        if re.search(rf"(?<![\w]){re.escape(city)}(?![\w])", norm) and code not in found:
            found.append(code)
    # Code ISO explicite en fin de libellé, du type « Paris, FR » (pas « Remote - CA » ambigu : CA = Californie ?)
    m = re.search(r",\s*([A-Z]{2})\s*$", location.strip())
    if m and m.group(1) in COUNTRIES and m.group(1) not in found and m.group(1) not in ("CA",):
        found.append(m.group(1))
    return found


def detect_remote(location: str | None) -> bool | None:
    if not location:
        return None
    norm = normalize_text(location)
    return True if any(w in norm for w in REMOTE_WORDS) else None
