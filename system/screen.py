#!/usr/bin/env python3
"""Deterministic, rule-based screening hit resolver implementing the bank's identity SOP.

Usage: screen.py <data folder> <output file>
"""
import calendar
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from functools import lru_cache

# ----------------------------------------------------------------------------- utils

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
for _k, _v in list(MONTHS.items()):
    MONTHS[_k[:3]] = _v
MONTHS["sept"] = 9
MON_RE = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def checked_date(year, month=None, day=None):
    if not 1 <= year <= 9999:
        return None
    if month is not None and not 1 <= month <= 12:
        return None
    if day is not None:
        if month is None or not 1 <= day <= calendar.monthrange(year, month)[1]:
            return None
    return (year, month, day)


def parse_date(s):
    """Return (y, m, d) with None for unknown parts, or None."""
    if not s:
        return None
    s = str(s).strip()
    t = s.lower().replace(",", " ").replace(".", " ")
    t = re.sub(r"\s+", " ", t).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        return checked_date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", t)
    if m:
        return checked_date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", t)
    if m:
        return checked_date(int(m[1]), int(m[2]), None)
    m = re.fullmatch(r"(\d{4})", t)
    if m:
        return checked_date(int(m[1]), None, None)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return checked_date(int(m[3]), int(m[2]), int(m[1]))
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)? (" + MON_RE + r") (\d{4})", t)
    if m:
        return checked_date(int(m[3]), MONTHS[m[2][:3] if m[2][:4] != "sept" else "sept"], int(m[1]))
    m = re.fullmatch(r"(" + MON_RE + r") (\d{1,2})(?:st|nd|rd|th)? (\d{4})", t)
    if m:
        return checked_date(int(m[3]), MONTHS[m[1][:3]], int(m[2]))
    m = re.fullmatch(r"(" + MON_RE + r") (\d{4})", t)
    if m:
        return checked_date(int(m[2]), MONTHS[m[1][:3]], None)
    return None


DATE_IN_TEXT = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|\d{4}/\d{1,2}/\d{1,2}"
    r"|\d{1,2}(?:st|nd|rd|th)? " + MON_RE + r",? \d{4}"
    r"|" + MON_RE + r" \d{1,2}(?:st|nd|rd|th)?,? \d{4}"
    r"|" + MON_RE + r",? \d{4}"
    r"|\b(?:1[89]|20)\d{2}\b", re.I)


def dates_in(text):
    out = []
    for m in DATE_IN_TEXT.finditer(text or ""):
        d = parse_date(m.group(0))
        if d:
            out.append((m.start(), m.group(0), d))
    return out


def fmt_date(d):
    if not d:
        return "unknown"
    y, m, dd = d
    if m and dd:
        return "%04d-%02d-%02d" % (y, m, dd)
    if m:
        return "%04d-%02d" % (y, m)
    return "%04d" % y


def date_key(d):
    return (d[0], d[1] or 0, d[2] or 0)


def date_bounds(d):
    """Earliest/latest possible calendar dates represented by a partial date."""
    if not d:
        return None, None
    y, m, day = d
    lo = (y, m or 1, day or 1)
    hi_month = m or 12
    hi_day = day or calendar.monthrange(y, hi_month)[1]
    return lo, (y, hi_month, hi_day)


def definitely_after(a, b):
    """True only when every date represented by a is after every date in b."""
    alo, _ = date_bounds(a)
    _, bhi = date_bounds(b)
    return bool(alo and bhi and alo > bhi)


def definitely_before(a, b):
    """True only when every date represented by a is before every date in b."""
    _, ahi = date_bounds(a)
    blo, _ = date_bounds(b)
    return bool(ahi and blo and ahi < blo)


# ----------------------------------------------------------------------------- countries

COUNTRY_ALIASES = {
    "us": "United States", "usa": "United States", "u.s.": "United States", "united states of america": "United States",
    "american": "United States", "gb": "United Kingdom", "uk": "United Kingdom", "british": "United Kingdom",
    "great britain": "United Kingdom", "england": "England", "english": "England", "scotland": "Scotland",
    "scottish": "Scotland", "wales": "Wales", "welsh": "Wales",
    "ng": "Nigeria", "nigerian": "Nigeria", "de": "Germany", "german": "Germany", "es": "Spain", "spanish": "Spain",
    "fr": "France", "french": "France", "bd": "Bangladesh", "bangladeshi": "Bangladesh", "it": "Italy", "italian": "Italy",
    "ie": "Ireland", "irish": "Ireland", "ca": "Canada", "canadian": "Canada", "nl": "Netherlands", "dutch": "Netherlands",
    "the netherlands": "Netherlands", "au": "Australia", "australian": "Australia", "ke": "Kenya", "kenyan": "Kenya",
    "at": "Austria", "austrian": "Austria", "pk": "Pakistan", "pakistani": "Pakistan", "za": "South Africa",
    "south african": "South Africa", "sg": "Singapore", "singaporean": "Singapore", "se": "Sweden", "swedish": "Sweden",
    "ec": "Ecuador", "ecuadorian": "Ecuador", "pt": "Portugal", "portuguese": "Portugal", "rs": "Serbia", "serbian": "Serbia",
    "br": "Brazil", "brazilian": "Brazil", "dk": "Denmark", "danish": "Denmark", "th": "Thailand", "thai": "Thailand",
    "pl": "Poland", "polish": "Poland", "ch": "Switzerland", "swiss": "Switzerland", "no": "Norway", "norwegian": "Norway",
    "vn": "Vietnam", "vietnamese": "Vietnam", "viet nam": "Vietnam", "gh": "Ghana", "ghanaian": "Ghana", "pa": "Panama",
    "panamanian": "Panama", "sy": "Syria", "syrian": "Syria", "ht": "Haiti", "haitian": "Haiti", "ci": "Cote D'Ivoire",
    "ivorian": "Cote D'Ivoire", "cote d'ivoire": "Cote D'Ivoire", "côte d'ivoire": "Cote D'Ivoire", "ivory coast": "Cote D'Ivoire",
    "me": "Montenegro", "montenegrin": "Montenegro", "dz": "Algeria", "algerian": "Algeria", "in": "India", "indian": "India",
    "ru": "Russia", "russian": "Russia", "russian federation": "Russia", "kp": "North Korea", "north korean": "North Korea",
    "cn": "China", "chinese": "China", "mx": "Mexico", "mexican": "Mexico", "fi": "Finland", "finnish": "Finland",
    "id": "Indonesia", "indonesian": "Indonesia", "co": "Colombia", "colombian": "Colombia", "ar": "Argentina",
    "argentine": "Argentina", "argentinian": "Argentina", "ae": "United Arab Emirates", "uae": "United Arab Emirates",
    "emirati": "United Arab Emirates", "iq": "Iraq", "iraqi": "Iraq", "ir": "Iran", "iranian": "Iran", "jo": "Jordan",
    "jordanian": "Jordan", "lb": "Lebanon", "lebanese": "Lebanon", "jp": "Japan", "japanese": "Japan", "kr": "South Korea",
    "south korean": "South Korea", "korea, republic of": "South Korea", "eg": "Egypt", "egyptian": "Egypt", "tr": "Turkey",
    "turkish": "Turkey", "turkiye": "Turkey", "türkiye": "Turkey", "am": "Armenia", "armenian": "Armenia", "be": "Belgium",
    "belgian": "Belgium", "pe": "Peru", "peruvian": "Peru", "ma": "Morocco", "moroccan": "Morocco", "hu": "Hungary",
    "hungarian": "Hungary", "cz": "Czech Republic", "czech": "Czech Republic", "czechia": "Czech Republic",
    "nz": "New Zealand", "new zealander": "New Zealand", "md": "Moldova", "moldovan": "Moldova", "si": "Slovenia",
    "slovenian": "Slovenia", "ua": "Ukraine", "ukrainian": "Ukraine", "gr": "Greece", "greek": "Greece", "ro": "Romania",
    "romanian": "Romania", "ph": "Philippines", "filipino": "Philippines", "my": "Malaysia", "malaysian": "Malaysia",
    "sa": "Saudi Arabia", "saudi": "Saudi Arabia", "il": "Israel", "israeli": "Israel", "af": "Afghanistan",
    "afghan": "Afghanistan", "ve": "Venezuela", "venezuelan": "Venezuela", "cl": "Chile", "chilean": "Chile",
    "macao": "Macao Special Administrative Region of China", "macau": "Macao Special Administrative Region of China",
    "hong kong": "Hong Kong", "hk": "Hong Kong", "lu": "Luxembourg", "cy": "Cyprus", "mt": "Malta", "bg": "Bulgaria",
    "hr": "Croatia", "croatian": "Croatia", "ba": "Bosnia and Herzegovina", "by": "Belarus", "belarusian": "Belarus",
    "kz": "Kazakhstan", "uz": "Uzbekistan", "lk": "Sri Lanka", "np": "Nepal", "et": "Ethiopia", "tz": "Tanzania",
    "ug": "Uganda", "zw": "Zimbabwe", "cm": "Cameroon", "sn": "Senegal", "tn": "Tunisia", "ly": "Libya", "sd": "Sudan",
    "ye": "Yemen", "qa": "Qatar", "kw": "Kuwait", "bh": "Bahrain", "om": "Oman", "cu": "Cuba", "do": "Dominican Republic",
    "jm": "Jamaica", "gt": "Guatemala", "hn": "Honduras", "ni": "Nicaragua", "sv": "El Salvador", "cr": "Costa Rica",
    "bo": "Bolivia", "py": "Paraguay", "uy": "Uruguay", "mm": "Myanmar", "kh": "Cambodia", "la": "Laos", "mn": "Mongolia",
    "tw": "Taiwan", "is": "Iceland", "ee": "Estonia", "lv": "Latvia", "lt": "Lithuania", "sk": "Slovakia", "al": "Albania",
    "mk": "North Macedonia", "ge": "Georgia", "az": "Azerbaijan", "mp": "Northern Mariana Islands", "pr": "Puerto Rico",
    "gu": "Guam",
}
NOT_COUNTRIES = {"international", "europe", "global", "worldwide", "unknown", "none", ""}


def norm_country(s):
    if not s:
        return None
    s = re.sub(r"\[.*?\]", "", str(s)).strip().strip(".")
    low = s.lower()
    if low in NOT_COUNTRIES:
        return None
    if low in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[low]
    if low.startswith("the "):
        low2 = low[4:]
        if low2 in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[low2]
        s = s[4:]
    # canonical capitalisation
    return KNOWN_COUNTRIES.get(s.lower(), s)


KNOWN_COUNTRIES = {}  # lower -> canonical, filled from data
COUNTRY_TEXT_RE = None


def build_country_index(names):
    global COUNTRY_TEXT_RE
    for n in names:
        c = norm_country(n)
        if c and len(c) > 3:
            KNOWN_COUNTRIES.setdefault(c.lower(), c)
    terms = set(KNOWN_COUNTRIES) | {k for k in COUNTRY_ALIASES if len(k) > 3}
    terms = sorted(terms, key=lambda term: (-len(term), term))
    COUNTRY_TEXT_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)


def countries_in_text(text):
    out = []
    for m in COUNTRY_TEXT_RE.finditer(text or ""):
        c = norm_country(m.group(1))
        if c and c not in out:
            out.append(c)
    return out


# ----------------------------------------------------------------------------- names

PLACEHOLDERS = {"na", "n/a", "test", "unknown", "xxx", "none", "null", "nil", "tbc", "tbd", "noname", "x", "xx", "xxxx"}
VARIANT = {}
LEGAL_FORMS = set()


def load_variants(path):
    with open(path, encoding="utf-8") as handle:
        d = json.load(handle)
    for i, g in enumerate(d.get("groups", [])):
        for n in g:
            VARIANT.setdefault(strip_accents(n.lower()), set()).add(i)
    for f in d.get("company_legal_forms", []):
        LEGAL_FORMS.add(re.sub(r"[^a-z0-9]", "", strip_accents(f.lower())))
    name_parts.cache_clear()
    part_match.cache_clear()
    names_agree.cache_clear()


@lru_cache(maxsize=50000)
def name_parts(name, company=False):
    if not name:
        return []
    s = strip_accents(str(name)).lower()
    s = re.sub(r"\(.*?\)|\[.*?\]|\{.*?\}", " ", s)
    s = s.replace("n/a", " na ")
    s = re.sub(r"[^a-z0-9\s]", " ", s.replace("'", "").replace("’", ""))
    out = []
    for p in s.split():
        if len(p) < 2:
            continue  # initials
        if p in PLACEHOLDERS or re.search(r"\d", p):
            continue
        if company and p in LEGAL_FORMS:
            continue
        if p not in out:
            out.append(p)
    return out


def edit_distance(a, b):
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@lru_cache(maxsize=100000)
def part_match(a, b):
    if a == b:
        return True
    va, vb = VARIANT.get(a), VARIANT.get(b)
    if va and vb and va & vb:
        return True
    short = min(len(a), len(b))
    if short < 4:
        return False
    lim = 1 if short <= 6 else 2
    return edit_distance(a, b) <= lim


def _max_name_matches(A, B):
    """Maximum one-to-one semantic matches, including a joined/split adjacent part."""
    @lru_cache(maxsize=None)
    def visit(amask, bmask):
        if not amask or not bmask:
            return 0
        abit = amask & -amask
        i = abit.bit_length() - 1
        rest_a = amask ^ abit
        best = visit(rest_a, bmask)  # leave this A part unmatched
        for j, b in enumerate(B):
            bj = 1 << j
            if not bmask & bj:
                continue
            if part_match(A[i], b):
                best = max(best, 1 + visit(rest_a, bmask ^ bj))
            # One written-together part can match two adjacent parts on the other side,
            # but it remains one semantic match and consumes both source parts.
            if j + 1 < len(B) and bmask & (1 << (j + 1)):
                if part_match(A[i], b + B[j + 1]):
                    best = max(best, 1 + visit(rest_a, bmask ^ bj ^ (1 << (j + 1))))
            # The reverse split: two adjacent parts in A match one part in B.
            for k in (i + 1,) if i + 1 < len(A) else ():
                ak = 1 << k
                if amask & ak and part_match(A[i] + A[k], b):
                    best = max(best, 1 + visit(rest_a ^ ak, bmask ^ bj))
        return best

    return visit((1 << len(A)) - 1, (1 << len(B)) - 1)


@lru_cache(maxsize=100000)
def names_agree(n1, n2, company=False):
    A, B = name_parts(n1, company), name_parts(n2, company)
    if not A or not B:
        return False
    matches = _max_name_matches(A, B)
    return matches >= 2 or matches == min(len(A), len(B))


def any_names_agree(names1, names2, company=False):
    for a in names1:
        for b in names2:
            if names_agree(a, b, company):
                return (a, b)
    return None


# ----------------------------------------------------------------------------- data

class Data:
    def __init__(self, folder):
        global COUNTRY_TEXT_RE, KNOWN_COUNTRIES, VARIANT, LEGAL_FORMS
        COUNTRY_TEXT_RE = None
        KNOWN_COUNTRIES = {}
        VARIANT = {}
        LEGAL_FORMS = set()
        j = lambda n: read_jsonl(os.path.join(folder, n + ".jsonl"))
        self.alerts = j("alerts")
        self.hits = {h["hit_id"]: h for h in j("hits")}
        self.customers = {c["record_id"]: c for c in j("customers")}
        accounts = j("accounts")
        onboarding = j("onboarding")
        kyc = j("kyc_checks")
        notes = j("notes")
        self.search = j("search_results")
        load_variants(os.path.join(folder, "name_variants.json"))

        self.acc_by_id = defaultdict(list)
        self.acc_by_login = defaultdict(list)
        self.acc_by_cust = defaultdict(list)
        for a in accounts:
            self.acc_by_id[a["account_id"]].append(a)
            if a.get("login_handle"):
                self.acc_by_login[a["login_handle"].lower()].append(a)
            self.acc_by_cust[a["customer_id"]].append(a)
        self.app_by_cust = defaultdict(set)
        self.app_by_acc = defaultdict(set)
        for o in onboarding:
            if o.get("kyc_applicant_id"):
                self.app_by_cust[o["customer_id"]].add(o["kyc_applicant_id"])
                self.app_by_acc[o["account_id"]].add(o["kyc_applicant_id"])
        self.kyc_by_app = defaultdict(list)
        for k in kyc:
            self.kyc_by_app[k["applicant_id"]].append(k)
        self.notes_by_email = defaultdict(list)
        for n in notes:
            if n.get("requester_email"):
                self.notes_by_email[n["requester_email"].lower()].append(n)
        self.cust_by_email = defaultdict(list)
        self.cust_by_phone = defaultdict(list)
        self.cust_by_token = defaultdict(set)
        self.customer_tokens = set()
        for c in self.customers.values():
            if c.get("email"):
                self.cust_by_email[c["email"].lower()].append(c["record_id"])
            if c.get("phone"):
                self.cust_by_phone[re.sub(r"\D", "", c["phone"])].append(c["record_id"])
            comp = c.get("entity_type") == "Company"
            for nm in (c.get("full_name"), c.get("preferred_name"), c.get("login_name")):
                for p in name_parts(nm, comp):
                    self.customer_tokens.add(p)
                    self.cust_by_token[self.tok_key(p)].add(c["record_id"])
        self.search_by_query = defaultdict(list)
        for s in self.search:
            self.search_by_query[" ".join(sorted(name_parts(s.get("query"))))].append(s)

        names = set()
        for c in self.customers.values():
            names.add(c.get("nationality"))
            names.add(c.get("residence_country"))
        for k in kyc:
            names.add(k.get("document_country"))
        for h in self.hits.values():
            for f in ("countries", "nationality", "citizenship"):
                names.update(h.get(f) or [])
            for a in h.get("addresses") or []:
                names.add(a.split(",")[-1])
        names.update(v for v in COUNTRY_ALIASES.values())
        build_country_index([n for n in names if n])

        # approved KYC checks per applicant -> kept separately; also index document numbers
        self.cust_by_doc = defaultdict(set)
        for c in self.customers.values():
            for k in self.checks_for_customer(c["record_id"]):
                if k.get("document_number"):
                    self.cust_by_doc[k["document_number"].upper()].add(c["record_id"])

    @staticmethod
    def tok_key(p):
        v = VARIANT.get(p)
        return "V%d" % min(v) if v else p

    def checks_for_customer(self, cid):
        apps = set(self.app_by_cust.get(cid, ()))
        out = []
        for ap in sorted(apps):
            for k in self.kyc_by_app.get(ap, ()):
                if k.get("result") == "approved":
                    out.append(k)
        return out


# ----------------------------------------------------------------------------- customer side

def full_dob(d):
    return d is not None and d[1] is not None and d[2] is not None


def person_closure(data, cid):
    """Records belonging to the same person (shared phone + same full DOB, or same approved document number)."""
    seen = {cid}
    stack = [cid]
    while stack:
        c = data.customers[stack.pop()]
        dob = parse_date(c.get("dob"))
        nxt = set()
        if c.get("phone") and full_dob(dob):
            for o in data.cust_by_phone.get(re.sub(r"\D", "", c["phone"]), ()):
                if parse_date(data.customers[o].get("dob")) == dob:
                    nxt.add(o)
        for k in data.checks_for_customer(c["record_id"]):
            if k.get("document_number"):
                nxt |= data.cust_by_doc.get(k["document_number"].upper(), set())
        for o in nxt:
            if o not in seen:
                seen.add(o)
                stack.append(o)
    return sorted(seen)


def kyc_note_parse(note, data):
    """Parse an identity-verification note into (name, dob, country)."""
    text = note.get("text") or ""
    name = None
    name_patterns = (
        r"\blegal name\s*:\s*([^,.;\n]+)",
        r"\bname on document\s*:\s*([^,.;\n]+)",
        r"\b(?:verified|validated|accepted|checked|processed)\s+(?:the\s+)?(?:passport|national ID|driving licence|identity document|ID)\s+(?:for|of)\s+([^,.;\n]+)",
        r"\b(?:identity verification|identity check|checks?|verification)\s+for\s+([^,.;\n]+)",
        r"\bfor\s+(?:the\s+)?(?:passport|national ID|driving licence|identity document|ID)\s+(?:of\s+)?([^,.;\n]+)",
        r"\bsuccessful\s+(?:identity\s+)?check\s+on\s+([\wÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[\wÀ-ÖØ-öø-ÿ'’.-]+){1,4})\s*(?:,|\(|\b(?:born|DOB|date of birth)\b)",
        r"\bfor\s+([\wÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[\wÀ-ÖØ-öø-ÿ'’.-]+){1,4})\s*(?:,|\(|\b(?:born|DOB|date of birth)\b)",
        r"^\s*([\wÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[\wÀ-ÖØ-öø-ÿ'’.-]+){1,4})['’]s\s+(?:identity|ID)",
        r"^\s*([\wÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[\wÀ-ÖØ-öø-ÿ'’.-]+){1,4})\s*(?:\(|,\s*(?:born|DOB)|,\s*DOB)",
    )
    for pattern in name_patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m:
            candidate = re.sub(r"\s+", " ", m.group(1)).strip(" .,:;'’")
            # KYC notes often place a check date immediately after the name
            # without punctuation ("for JANE DOE on 2025-02-01"). Do not
            # mistake the date preposition or month for a legal-name token.
            candidate = re.split(
                r"\s+\bon\s+(?=(?:\d{4}\b|\d{1,2}(?:st|nd|rd|th)?\s+" + MON_RE + r"\b|" + MON_RE + r"\s+\d{1,2}\b))",
                candidate, maxsplit=1, flags=re.I)[0].strip(" .,:;'’")
            if len(name_parts(candidate)) >= 1 and not re.search(
                    r"\b(?:persona|sumsub|veriff|onfido|passport|national ID|driving licence|DOB|date of birth)\b",
                    candidate, re.I):
                name = candidate
                break
    created = parse_date(note.get("created_at"))
    dob = None
    for pos, raw, d in dates_in(text):
        if d == created:
            continue
        prefix = text[max(0, pos - 55):pos]
        if re.search(r"\b(?:born|DOB|date of birth|birth date|subject date of birth|recorded DOB|DOB recorded|DOB confirmed|date of birth on document)\b[^.!?]{0,45}$", prefix, re.I):
            dob = d
            break
    cleaned = text.replace(name, " ") if name else text
    cs = countries_in_text(cleaned)
    return name, dob, (cs[0] if cs else None)


def is_kyc_note(n):
    if n.get("channel") != "kyc":
        return False
    text = n.get("text") or ""
    if re.search(r"\b(?:rejected|declined|failed|expired|not\s+(?:approved|verified|accepted)|unable to verify|could not verify|unsuccessful)\b", text, re.I):
        return False
    return bool(re.search(r"\b(?:verified|confirmed|cleared|validated|passed|accepted|approved|completed identity verification|identity check complete|successful check|successfully processed)\b", text, re.I))


def lived_countries_in_note(text):
    """Return country mentions explicitly tied to where the customer lived or resided."""
    phrases = re.finditer(
        r"\b(?:lived|living|resided|residing|was resident|residency|residence|resident|employment and residency|home)\b[^.!?\n]{0,60}\b(?:in|at)\b[^.!?\n]*",
        text or "", re.I)
    out = []
    for phrase in phrases:
        for country in countries_in_text(phrase.group(0)):
            if country not in out:
                out.append(country)
    return out


def build_person(data, records):
    """Collect one person's facts from all their records."""
    P = {"records": records, "names": [], "dob": None, "dob_src": None, "countries": {}, "verified_name": None,
         "verified_src": None, "entity_type": data.customers[records[0]].get("entity_type"),
         "name_sources": defaultdict(set), "country_sources": defaultdict(set)}
    checks = []  # (date, id, name, dob, country)
    for cid in records:
        c = data.customers[cid]
        for nm in (c.get("full_name"), c.get("preferred_name"), c.get("login_name")):
            if nm and nm not in P["names"]:
                P["names"].append(nm)
                P["name_sources"][nm].add(cid)
        for f in ("residence_country", "nationality"):
            cc = norm_country(c.get(f))
            if cc:
                P["countries"].setdefault(cc, cid)
                P["country_sources"][cc].add(cid)
        for k in data.checks_for_customer(cid):
            checks.append((date_key(parse_date(k.get("checked_at")) or (0, 0, 0)), k["check_id"], k.get("verified_name"),
                           parse_date(k.get("verified_dob")), norm_country(k.get("document_country"))))
            country = norm_country(k.get("document_country"))
            if country:
                P["countries"].setdefault(country, k["check_id"])
                P["country_sources"][country].add(k["check_id"])
        if c.get("email"):
            for n in data.notes_by_email.get(c["email"].lower(), ()):
                if is_kyc_note(n):
                    nm, dob, cc = kyc_note_parse(n, data)
                    checks.append((date_key(parse_date(n.get("created_at")) or (0, 0, 0)), n["note_id"], nm, dob, cc))
                    if cc:
                        P["countries"].setdefault(cc, n["note_id"])
                        P["country_sources"][cc].add(n["note_id"])
                    if nm:
                        P["name_sources"][nm].add(n["note_id"])
                else:
                    for cc in lived_countries_in_note(n.get("text")):
                        P["countries"].setdefault(cc, n["note_id"])
                        P["country_sources"][cc].add(n["note_id"])
    checks.sort(key=lambda x: (x[0], x[1]))
    if checks:
        latest = checks[-1]
        P["verified_name"], P["verified_src"] = latest[2], latest[1]
        if latest[3]:
            P["dob"], P["dob_src"] = latest[3], latest[1]
        if latest[2]:
            P["name_sources"][latest[2]].add(latest[1])
        if latest[2] and latest[2] not in P["names"]:
            P["names"].insert(0, latest[2])
    if not P["dob"]:
        for cid in records:
            d = parse_date(data.customers[cid].get("dob"))
            if d:
                P["dob"], P["dob_src"] = d, cid
                break
    return P


def dob_compatible(a, b):
    if not a or not b:
        return True
    for x, y in zip(a, b):
        if x is not None and y is not None and x != y:
            return False
    return True


def record_fits(data, cid, scr):
    c = data.customers[cid]
    comp = c.get("entity_type") == "Company"
    if scr.get("name"):
        names = [c.get("full_name"), c.get("preferred_name"), c.get("login_name")]
        if not any(names_agree(scr["name"], n, comp) for n in names if n):
            return False
    if scr.get("dob") and not dob_compatible(parse_date(scr["dob"]), parse_date(c.get("dob"))):
        # also allow verified dob
        ok = any(dob_compatible(parse_date(scr["dob"]), parse_date(k.get("verified_dob")))
                 for k in data.checks_for_customer(cid))
        if not ok:
            return False
    if scr.get("country"):
        sc = norm_country(scr["country"])
        cs = {norm_country(c.get("residence_country")), norm_country(c.get("nationality"))}
        if sc not in cs:
            return False
    if scr.get("city"):
        city = strip_accents(scr["city"]).lower()
        if city not in strip_accents((c.get("city") or "") + " " + (c.get("address") or "")).lower():
            return False
    return True


def resolve_customer(data, alert):
    scr = alert["customer"]
    cands = None
    if alert.get("account_ref"):
        cands = sorted({a["customer_id"] for a in data.acc_by_id.get(alert["account_ref"], ())})
    elif alert.get("login_handle"):
        cands = sorted({a["customer_id"] for a in data.acc_by_login.get(alert["login_handle"].lower(), ())})
    elif alert.get("email"):
        cands = sorted(set(data.cust_by_email.get(alert["email"].lower(), ())))
    if cands is not None:
        # A supplied link is authoritative. Do not jump to unrelated global name
        # candidates when that link is empty or its screened attributes do not fit.
        if len(cands) > 1:
            fit = [c for c in cands if record_fits(data, c, scr)]
            cands = fit
    else:
        comp = scr.get("entity_type") == "Company"
        parts = name_parts(scr.get("name"), comp)
        pool = set()
        for p in parts:
            # Candidate retrieval must be at least as permissive as the SOP's
            # bounded typo/variant rules; exact-token retrieval silently misses
            # valid candidates before record_fits() can evaluate them.
            for token in data.customer_tokens:
                if part_match(p, token):
                    pool |= data.cust_by_token.get(data.tok_key(token), set())
        cands = sorted(c for c in pool if record_fits(data, c, scr))
    # group into persons
    persons, seen = [], set()
    for c in cands:
        if c in seen:
            continue
        rec = person_closure(data, c)
        rec = [c] + [r for r in rec if r != c]
        seen |= set(rec)
        persons.append(rec)
    return persons


# ----------------------------------------------------------------------------- hit side

LISTING_PHRASE = {
    "sanctions": "a sanctioned individual", "pep": "a politically exposed person",
    "enforcement": "the subject of enforcement action", "adverse media": "named in adverse media",
    "soe": "a state-owned enterprise official",
}
AGE_PATTERNS = [
    r"\baged? (?:of )?(\d{1,3})\b", r"\bage:? (\d{1,3})\b", r"\b(\d{1,3}) years? (?:of age|old)\b",
    r"\b(\d{1,3})-year-old\b", r"\bwas (\d{1,3})\b", r", (\d{1,3}),", r"\bage of (\d{1,3})\b", r"\breached (\d{1,3})\b",
]


def find_age(text):
    for p in AGE_PATTERNS:
        m = re.search(p, text, re.I)
        if m:
            a = int(m.group(1))
            if 0 < a < 120:
                return a, m.start()
    return None, None


def age_birth_years(text):
    """From 'aged N ... in <date>' text, return ((y-n-1, y-n), date) or None."""
    age, age_pos = find_age(text)
    if age is None:
        return None
    ds = [d for _, raw, d in dates_in(text) if d[0] > 1800 and not (raw.isdigit() and int(raw) == age)]
    positioned = [(pos, d) for pos, raw, d in dates_in(text)
                  if d[0] > 1800 and not (raw.isdigit() and int(raw) == age)]
    # The event date usually follows the age. Prefer the closest such date and
    # preserve the two possible birth years caused by a year-boundary ambiguity.
    following = [item for item in positioned if item[0] >= age_pos]
    selected = min(following, key=lambda item: item[0]) if following else (positioned[0] if positioned else None)
    if not selected:
        return None
    event = selected[1]
    y = event[0]
    return (y - age - 1, y - age), event


def to_known_country(x):
    """Map a free-text place to a country. Returns (country|None, understood:bool)."""
    if isinstance(x, dict):
        x = x.get("country") or x.get("name") or ", ".join(str(v) for v in x.values() if v)
    if not x:
        return None, True
    raw = re.sub(r"\[.*?\]", "", str(x)).strip()
    if raw.lower() in NOT_COUNTRIES:
        return None, True
    last = raw.split(",")[-1].strip()
    c = norm_country(last)
    if c and c.lower() in KNOWN_COUNTRIES:
        return c, True
    found = countries_in_text(raw)
    if found:
        return found[-1], True
    return None, False


UNKNOWN_PLACE = []


def hit_countries(h):
    out = {}
    unknown = False
    for f in ("countries", "nationality", "citizenship", "addresses", "place_of_birth"):
        v = h.get(f)
        if not v:
            continue
        for x in (v if isinstance(v, list) else [v]):
            c, ok = to_known_country(x)
            if c:
                out.setdefault(c, f)
            elif not ok:
                unknown = True
    if unknown:
        out["?"] = "unparsed"
    return out


def hit_names(h):
    ns = []
    for n in [h.get("name"), h.get("best_matching_name"),
              " ".join(x for x in (h.get("first_name"), h.get("middle_name"), h.get("last_name")) if x)]:
        if n and n not in ns:
            ns.append(n)
    for a in h.get("aliases") or []:
        n = a.get("name") if isinstance(a, dict) else a
        if n and n not in ns:
            ns.append(n)
    return ns


def hit_name_evidence(h, name=None):
    """Field-level references for the hit name(s) considered by a decision."""
    fields = []
    direct = ("name", "best_matching_name")
    for field in direct:
        value = h.get(field)
        if value and (name is None or value == name):
            fields.append(h["hit_id"] + "#" + field)
    split_name = " ".join(x for x in (h.get("first_name"), h.get("middle_name"), h.get("last_name")) if x)
    if split_name and (name is None or split_name == name):
        fields.extend(h["hit_id"] + "#" + f for f in ("first_name", "middle_name", "last_name") if h.get(f))
    for alias in h.get("aliases") or []:
        value = alias.get("name") if isinstance(alias, dict) else alias
        if value and (name is None or value == name):
            fields.append(h["hit_id"] + "#aliases")
    return dedup(fields)


def hit_country_evidence(h, country_fields=None):
    fields = []
    for country, field in (country_fields or hit_countries(h)).items():
        if country != "?":
            fields.append(h["hit_id"] + "#" + field)
    return dedup(fields)


def death_date_info(h):
    """Return a dated death and its source, without inferring from undated status."""
    direct = parse_date(h.get("deceased_date"))
    if direct:
        return direct, h["hit_id"] + "#deceased_date"
    text = h.get("profile_notes") or ""
    for m in re.finditer(r"\b(?:date of death|died|death occurred|deceased on|passed away on)\b[^\n.!?]{0,45}", text, re.I):
        found = dates_in(m.group(0))
        if found:
            return found[0][2], h["hit_id"] + "#profile_notes"
    return None, None


def listing_phrase(h):
    cat = h.get("primary_category") or ((h.get("categories") or [None])[0])
    return LISTING_PHRASE.get((cat or "").lower(), "named on a watchlist")


def hit_dobs(data, h):
    """List of (kind, possible_years:set, date_or_None, source_label, evidence_ids)."""
    out = []
    if h.get("dobs"):
        for s in h["dobs"]:
            d = parse_date(s)
            if d:
                label = "incorporation date" if h.get("entity_type") == "Company" else "date of birth"
                out.append(("listed", {d[0]}, d, "listed " + label,
                            [h["hit_id"] + "#dobs"]))
        if out:
            return out
    # The SOP explicitly permits only the structured dobs field as an
    # incorporation date for a company. Biography/search dates are not a
    # substitute for a company's incorporation record.
    if h.get("entity_type") == "Company":
        return []
    pn = h.get("profile_notes") or ""
    if pn:
        fp = re.split(r"\n\s*\n", pn.strip())[0]
        for sent in re.split(r"(?<=[.!?])\s+|\n", fp):
            m = re.search(r"\bborn\b", sent, re.I)
            if m:
                ds = dates_in(sent[m.start():])
                if ds:
                    d = ds[0][2]
                    out.append(("notes", {d[0]}, d, "profile notes", [h["hit_id"] + "#profile_notes"]))
                    continue
        if not out:
            yrs = age_birth_years(fp)
            if yrs:
                years, _event = yrs
                out.append(("notes", set(years), None, "profile notes", [h["hit_id"] + "#profile_notes"]))
        if out:
            return out
    # web search results
    phrase = listing_phrase(h)
    hc = set(hit_countries(h)) - {"?"}
    key_names = {" ".join(sorted(name_parts(n))) for n in hit_names(h)}
    seen = set()
    for kn in sorted(key_names):
        for s in data.search_by_query.get(kn, ()):
            if s["result_id"] in seen:
                continue
            seen.add(s["result_id"])
            txt = s.get("snippet") or ""
            if phrase.lower() not in txt.lower():
                continue
            if not hc or not (set(countries_in_text(txt)) & hc):
                continue
            yrs = age_birth_years(txt)
            if yrs:
                years, _event = yrs
                out.append(("search", set(years), None, "search results", [s["result_id"]]))
    return out


def earliest_report(h):
    best = None
    for line in (h.get("profile_notes") or "").split("\n"):
        m = re.match(r"\s*According to [^;\n]*; ([^:]+):", line)
        if m:
            d = parse_date(m.group(1))
            if d and (best is None or date_key(d) < date_key(best)):
                best = d
    return best


# ----------------------------------------------------------------------------- comparison

def dob_relation(cdob, hd):
    """'agree' | 'contradict' | 'neutral' for customer dob vs one hit dob entry."""
    _, years, d, _, _ = hd
    cy = cdob[0]
    if min(abs(cy - y) for y in years) > 1:
        return "contradict"
    if d is not None:
        if d[0] == cy:
            if d[1] and cdob[1] and d[1] != cdob[1]:
                return "contradict"
            if d[1] and cdob[1] and d[2] and cdob[2] and d[2] != cdob[2]:
                return "contradict"
            return "agree"
        return "neutral"
    return "agree" if cy in years else "neutral"


def max_age_at(dob, when):
    """Largest age the person can have on date `when` given partial dates."""
    dob_earliest, _ = date_bounds(dob)
    _, report_latest = date_bounds(when)
    age = report_latest[0] - dob_earliest[0]
    if report_latest[1:] < dob_earliest[1:]:
        age -= 1
    return age


def decide_person(data, alert, h, P):
    ev = list(P["records"][:1])
    hname_list = hit_names(h)
    company_h = h.get("entity_type") == "Company"
    company_c = P["entity_type"] == "Company"
    cname = P["verified_name"] or (P["names"][0] if P["names"] else alert["customer"].get("name") or "the screened customer")
    hit_label = h.get("name") or (hname_list[0] if hname_list else "the listed entity")
    hit_type_evidence = [h["hit_id"] + "#entity_type"]

    if company_h != company_c:
        sentence = "%s is recorded as %s in customer record %s, while hit %s is typed as %s." % (
            cname, "a company" if company_c else "an individual", P["records"][0], hit_label,
            "a company" if company_h else "an individual")
        reason = sentence + " An individual and a company cannot be the same entity under the SOP, so this hit is DIFFERENT_ENTITY."
        return ("DIFFERENT_ENTITY", "ENTITY_TYPE_MISMATCH", reason, dedup(ev + hit_type_evidence + hit_name_evidence(h)))

    # A verified legal name outranks declared and screened names. Without one,
    # the customer's record names and the screened name remain usable evidence.
    compare_names = ([P["verified_name"]] if P["verified_name"] else
                     P["names"] + ([alert["customer"].get("name")] if alert["customer"].get("name") else []))
    agree_pair = any_names_agree(compare_names, hname_list, company_h)
    canonical_for_name = P["verified_name"] or next((n for n in P["names"] if n), alert["customer"].get("name"))
    real_parts = len(name_parts(canonical_for_name, company_c)) if canonical_for_name else 0
    if not company_c and real_parts < 2:
        agree_pair = None  # individuals with a single real name cannot be confirmed or cleared on name
    if P["verified_name"]:
        name_source_ids = [P["verified_src"]] if P.get("verified_src") else []
    elif agree_pair:
        name_source_ids = sorted(P["name_sources"].get(agree_pair[0], set())) or [alert["alert_id"]]
    else:
        name_source_ids = sorted({s for srcs in P["name_sources"].values() for s in srcs}) or [alert["alert_id"]]
    name_hit_ids = hit_name_evidence(h, agree_pair[1] if agree_pair else None)

    # DOB relation: every hit DOB must contradict before DOB alone can clear.
    hds = hit_dobs(data, h)
    cdob = P["dob"]
    dob_state = "unknown"
    dob_ev = []
    if cdob and hds:
        relations = [dob_relation(cdob, hd) for hd in hds]
        if all(r == "contradict" for r in relations):
            dob_state = "contradict"
        elif any(r == "agree" for r in relations):
            dob_state = "agree"
        else:
            dob_state = "neutral"
        for hd in hds:
            dob_ev.extend(hd[4])

    def hd_text():
        if not hds:
            return "the hit provides no usable birth or incorporation date"
        parts = []
        for _kind, years, d, _label, _evidence in hds:
            parts.append(fmt_date(d) if d else " or ".join(str(y) for y in sorted(years)))
        return "%s lists %s" % (hds[0][3], ", ".join(parts))

    src = lambda source: " (%s)" % source if source else ""
    contradictions = []

    # Explicit death date, either structured or in profile prose.
    dd, death_src = death_date_info(h)
    scr = parse_date(alert.get("screened_at"))
    if dd and scr and definitely_before(dd, scr):
        text = "The hit profile gives a death date of %s%s, while the customer was screened on %s." % (
            fmt_date(dd), src(death_src), fmt_date(scr))
        contradictions.append(("DECEASED", text + " The death predates screening, so this hit is DIFFERENT_ENTITY.", [death_src]))

    # Temporal impossibility at the earliest dated report.
    er = earliest_report(h)
    if er and cdob:
        if company_c and definitely_after(cdob, er):
            text = "%s was incorporated on %s%s, after the hit's earliest dated report on %s (%s#profile_notes)." % (
                cname, fmt_date(cdob), src(P["dob_src"]), fmt_date(er), h["hit_id"])
            contradictions.append(("TEMPORAL_IMPOSSIBILITY", text + " The company did not yet exist at that report date, so this hit is DIFFERENT_ENTITY.",
                                  [P["dob_src"], h["hit_id"] + "#profile_notes"]))
        elif not company_c:
            age = max_age_at(cdob, er)
            if age < 16:
                text = "%s's date of birth is %s%s, making the customer's maximum possible age %d at the hit's earliest dated report on %s (%s#profile_notes)." % (
                    cname, fmt_date(cdob), src(P["dob_src"]), max(age, 0), fmt_date(er), h["hit_id"])
                contradictions.append(("TEMPORAL_IMPOSSIBILITY", text + " The customer was under 16 at the report date, so this hit is DIFFERENT_ENTITY.",
                                      [P["dob_src"], h["hit_id"] + "#profile_notes"]))

    if dob_state == "contradict":
        text = "The customer's date of birth is %s%s, but %s." % (fmt_date(cdob), src(P["dob_src"]), hd_text())
        contradictions.append(("DOB_MISMATCH", text + " Every DOB supplied for the hit is contradicted, so it is DIFFERENT_ENTITY.",
                              [P["dob_src"]] + dob_ev))

    # A name contradiction is admissible only from a verified legal name.
    if P["verified_name"]:
        vparts = name_parts(P["verified_name"], company_c)
        confident_name = company_c or len(vparts) >= 2
        if confident_name and not any_names_agree([P["verified_name"]], hname_list, company_h):
            shown_hit_names = ", ".join(hname_list) if hname_list else "no usable name or alias"
            text = "The latest approved identity check gives the customer's legal name as %s (%s), while the hit gives %s." % (
                P["verified_name"], P["verified_src"], shown_hit_names)
            contradictions.append(("NAME_MISMATCH_VERIFIED", text + " None of the hit's names agrees with the verified legal name, so it is DIFFERENT_ENTITY.",
                                  [P["verified_src"]] + hit_name_evidence(h)))

    # Countries are collected across every linked record, every approved ID, and
    # notes that explicitly say where the customer lived.
    hit_country_map = hit_countries(h)
    unknown_place = "?" in hit_country_map
    hc = {k: v for k, v in hit_country_map.items() if k != "?"}
    cc = P["countries"]
    loc_state = "unknown"
    if hc and cc:
        loc_state = "agree" if set(hc) & set(cc) else ("unknown" if unknown_place else "contradict")
    shared = sorted(set(hc) & set(cc))
    customer_country_ids = sorted({source for sources in P["country_sources"].values() for source in sources})
    hit_country_ids = hit_country_evidence(h, hit_country_map)
    location_text = "The customer's records tie %s only to %s, while the hit's profile ties it only to %s." % (
        "the customer" if company_c else "the customer", ", ".join(sorted(cc)) or "no country", ", ".join(sorted(hc)) or "no country")

    # A location mismatch is not sufficient when name and DOB already agree.
    if loc_state == "contradict":
        location_evidence = customer_country_ids + hit_country_ids
        if agree_pair and dob_state == "agree" and not company_c:
            reason = "%s The name %s and DOB %s%s agree, but country differs; the SOP requires review in this situation." % (
                location_text, agree_pair[1], fmt_date(cdob), src(P["dob_src"]))
            return ("REVIEW", "INSUFFICIENT_DATA", reason,
                    dedup(ev + name_source_ids + name_hit_ids + [P["dob_src"]] + dob_ev + location_evidence))
        reason = location_text + " No customer and hit countries overlap, and the positive identity-match safeguard does not apply, so this hit is DIFFERENT_ENTITY."
        return ("DIFFERENT_ENTITY", "LOCATION_MISMATCH", reason, dedup(ev + location_evidence))

    # Existing hard contradictions take priority over a positive match.
    if contradictions:
        code, reason, evidence = contradictions[0]
        return ("DIFFERENT_ENTITY", code, reason, dedup(ev + evidence))

    name_ok = agree_pair is not None
    name_evidence = name_source_ids + name_hit_ids
    if company_c and name_ok and loc_state == "agree":
        reason = "The customer's name %s agrees with the hit name %s, and both are linked to %s." % (
            agree_pair[0], agree_pair[1], ", ".join(shared))
        reason += " No contradictory identity fact appears, so this is SAME_ENTITY."
        country_ids = [source for country in shared for source in P["country_sources"].get(country, set())]
        return ("SAME_ENTITY", "NAME_LOCATION_MATCH", reason,
                dedup(ev + name_evidence + country_ids + hit_country_ids))

    if not company_c and name_ok and dob_state == "agree":
        dob_evidence = [P["dob_src"]] + dob_ev
        if loc_state == "agree":
            reason = "The customer's DOB %s%s agrees with %s, and the customer's name %s agrees with hit name %s." % (
                fmt_date(cdob), src(P["dob_src"]), hd_text(), agree_pair[0], agree_pair[1])
            reason += " Both are also linked to %s, with no contradictory identity fact." % ", ".join(shared)
            country_ids = [source for country in shared for source in P["country_sources"].get(country, set())]
            return ("SAME_ENTITY", "NAME_DOB_LOCATION_MATCH", reason,
                    dedup(ev + name_evidence + dob_evidence + country_ids + hit_country_ids))
        reason = "The customer's DOB %s%s agrees with %s, and the customer's name %s agrees with hit name %s." % (
            fmt_date(cdob), src(P["dob_src"]), hd_text(), agree_pair[0], agree_pair[1])
        reason += " No permitted contradiction is present, so this is SAME_ENTITY."
        return ("SAME_ENTITY", "NAME_DOB_MATCH", reason, dedup(ev + name_evidence + dob_evidence))

    # Review remains explicit about which required fact is missing or unresolved.
    details = []
    if name_ok:
        details.append("The customer's name agrees with hit name %s." % agree_pair[1])
    else:
        details.append("The customer's name %s does not provide a reliable name agreement with hit %s." % (cname, hit_label))
    if company_c:
        details.append("Company confirmation also requires the same country, but the available country evidence does not establish that agreement.")
    elif not cdob:
        details.append("The customer's verified or declared date of birth is unavailable for comparison with the hit.")
    elif not hds:
        details.append("The hit provides no usable date of birth to confirm or contradict the customer.")
    elif dob_state == "neutral":
        details.append("The partial dates do not prove either agreement or contradiction.")
    else:
        details.append("The required name and date-of-birth agreement is not established by the available records.")
    return ("REVIEW", "INSUFFICIENT_DATA", " ".join(details),
            dedup(ev + name_evidence + [P["dob_src"]] + dob_ev + hit_country_ids))


def decide_hit(data, alert, h, persons):
    if not persons:
        return {"decision": "REVIEW", "reason_code": "INSUFFICIENT_DATA", "customer_record_id": None,
                "reason": "No linked or sufficiently matching customer record was found for %s." % (
                    alert["customer"].get("name") or "the screened customer") +
                          " Without a resolved customer, the hit %s cannot be compared safely and remains REVIEW." % (h.get("name") or h["hit_id"]),
                "evidence": dedup([alert["alert_id"], h["hit_id"] + "#name"])}
    results = []
    for rec in persons:
        P = build_person(data, rec)
        results.append((rec, decide_person(data, alert, h, P)))
    if len(results) == 1:
        rec, (dec, code, reason, ev) = results[0]
        return {"decision": dec, "reason_code": code, "customer_record_id": rec[0], "reason": reason,
                "evidence": dedup(ev)}
    decs = {r[1][0] for r in results}
    allrec = [r[0][0] for r in results]
    if len(decs) == 1:
        dec = decs.pop()
        code = results[0][1][1]
        ev = []
        for r in results:
            ev += r[1][3]
        return {"decision": dec, "reason_code": code, "customer_record_id": "AMBIGUOUS",
                "reason": "%d different people in the system of record fit the screened customer (%s); each leads to the same decision. %s" % (
                    len(results), ", ".join(allrec), results[0][1][2]),
                "evidence": dedup(ev)}
    return {"decision": "REVIEW", "reason_code": "AMBIGUOUS_CUSTOMER_RECORD", "customer_record_id": "AMBIGUOUS",
            "reason": "%d separate customer identities fit the screened details for %s (%s), and they produce different decisions for hit %s." % (
                len(results), alert["customer"].get("name") or "the screened customer", ", ".join(allrec), h.get("name") or h["hit_id"]) +
                      " The record link is ambiguous, so the SOP requires REVIEW until the correct customer identity is resolved.",
            "evidence": dedup(allrec)}


def dedup(xs):
    return sorted({x for x in xs if x})


def main():
    folder, out = sys.argv[1], sys.argv[2]
    data = Data(folder)
    lines = evaluate(data)
    d = os.path.dirname(os.path.abspath(out))
    os.makedirs(d, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for row in lines:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def evaluate(data):
    """Return deterministic per-hit predictions for a loaded data folder."""
    lines = []
    for alert in sorted(data.alerts, key=lambda a: a["alert_id"]):
        persons = resolve_customer(data, alert)
        for hid in alert.get("hit_ids", []):
            h = data.hits.get(hid)
            if not h:
                continue
            try:
                r = decide_hit(data, alert, h, persons)
            except Exception as e:  # never crash: fall back to the safe decision
                print("screen: %s could not be evaluated (%s)" % (hid, type(e).__name__), file=sys.stderr)
                r = {"decision": "REVIEW", "reason_code": "INSUFFICIENT_DATA", "customer_record_id": None,
                     "reason": "The hit could not be evaluated automatically because the available records were incomplete or inconsistent. It is left for manual review.",
                     "evidence": [alert["alert_id"], hid]}
            row = {"hit_id": hid, "alert_id": alert["alert_id"]}
            row.update(r)
            lines.append(row)
    return lines


if __name__ == "__main__":
    main()
