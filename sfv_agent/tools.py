"""Tools the agent can call. Every program fact comes from the snapshot."""
import re

import numpy as np

from .data import INDEX, SITE, load_programs
from .llm import embed

HANDOFF_EMAIL = "info@skillsforvets.org"

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "washington dc": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
CODES = set(STATES.values())
# AP-style abbreviations that show up in the location field (e.g. "Las Vegas, Nev.").
AP_ABBR = {"ala": "AL", "ariz": "AZ", "ark": "AR", "calif": "CA", "colo": "CO", "conn": "CT", "del": "DE",
           "fla": "FL", "ga": "GA", "ill": "IL", "ind": "IN", "kan": "KS", "ky": "KY", "la": "LA", "md": "MD",
           "mass": "MA", "mich": "MI", "minn": "MN", "miss": "MS", "mo": "MO", "mont": "MT", "neb": "NE",
           "nev": "NV", "okla": "OK", "ore": "OR", "pa": "PA", "tenn": "TN", "va": "VA", "vt": "VT",
           "wash": "WA", "wis": "WI", "wyo": "WY"}
BRANCHES = {
    "army": ["army"], "navy": ["navy", "usn"], "air force": ["air force", "usaf"],
    "marine corps": ["marine"], "coast guard": ["coast guard", "uscg"], "space force": ["space force"],
}
FORMATS = {"online": ["online"], "in-person": ["in-person", "in person"], "hybrid": ["hybrid"]}

_programs = None
_by_slug = None
_matrix = None


def _load():
    global _programs, _by_slug, _matrix
    if _programs is None:
        _programs = load_programs()
        _by_slug = {p["slug"]: p for p in _programs}
        z = np.load(INDEX)
        order = {s: i for i, s in enumerate(z["slugs"])}
        _matrix = z["vectors"][[order[p["slug"]] for p in _programs]]
    return _programs, _by_slug, _matrix


def norm_state(s):
    """Return a 2-letter code, or None if the value is not a US state."""
    if not s:
        return None
    t = s.strip().lower().replace(".", "")
    if t.upper() in CODES:
        return t.upper()
    return STATES.get(t)


def states_in_text(text):
    """US states named in free text, by full name or upper-case 2-letter code."""
    text = text or ""
    found = set()
    low = text.lower()
    for name, code in STATES.items():
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            found.add(code)
    for code in re.findall(r"\b([A-Z]{2})\b", text):
        if code in CODES:
            found.add(code)
    for ab in re.findall(r",\s*([A-Z][a-z]{1,4})\.", text):
        if ab.lower() in AP_ABBR:
            found.add(AP_ABBR[ab.lower()])
    if "west virginia" in low and not re.search(r"(?<!west )virginia", low):
        found.discard("VA")
    if "washington dc" in low or "washington, dc" in low or "washington, d.c" in low:
        found.discard("WA")
    return found


def program_states(p):
    """States a program is tied to: residency limits first, else an in-person/hybrid location on file."""
    raw = (p.get("state_residency") or "").strip()
    codes = set()
    for part in re.split(r"[;,/]", raw):
        c = norm_state(part)
        if c:
            codes.add(c)
    if not codes and (p.get("format") or "").lower() not in ("online",):
        codes = states_in_text(p.get("location"))
    return codes


STOP = set("""a an the and or for of to in on at with by from is are be i im i'm me my we our you your
any some there what which who how where when can could would should do does did get want need looking
program programs veteran veterans vet vets military service member members free training course courses
near about tell link apply anything something options option help find good best""".split())


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9+#]+", (text or "").lower()) if t not in STOP and len(t) > 1]


def lexical_coverage(query, p):
    """Share of the query's distinctive words that appear in the program's own text."""
    q = set(tokens(query))
    if not q:
        return 0.0
    hay = " ".join(str(p.get(k) or "") for k in
                   ("name", "organization", "all_categories", "job_titles", "topic_tags", "what_you_get")).lower()
    hits = sum(1 for t in q if re.search(r"\b" + re.escape(t), hay))
    return hits / len(q)


def card(p, short=True):
    st = program_states(p)
    out = {
        "id": p["slug"],
        "name": p["name"],
        "organization": p["organization"],
        "category": p["category"],
        "format": p["format"],
        "state_limits": ", ".join(sorted(st)) if st else "none recorded",
        "location": (p.get("location") or "")[:200],
        "status": p["status"],
        "cost": p["cost"],
        "free_without_benefits": p["free_no_benefit"],
        "eligibility": (p["eligibility"] or "")[:320 if short else 1200],
        "official_link": p["url"],
        "skills_for_vets_page": SITE + (p.get("program_path") or f"/programs/{p['slug']}/"),
    }
    if not short:
        out.update({
            "what_you_get": p["what_you_get"], "duration": p["duration"],
            "deadline_detail": p["deadline_detail"], "cost_detail": p["cost_detail"],
            "skillbridge": p["skillbridge"], "last_verified": p["last_verified"],
        })
    return out


def search_programs(query="", state=None, branch=None, format=None, audience=None,
                    free_only=False, limit=5, user_question=None):
    programs, _, matrix = _load()
    notes = []
    code = None
    if state:
        code = norm_state(str(state))
        if not code:
            notes.append(f"Ignored state={state!r}: not a US state.")
    br = None
    if branch:
        b = str(branch).lower()
        br = next((k for k, v in BRANCHES.items() if any(x in b for x in v) or b in k), None)
        if not br:
            notes.append(f"Ignored branch={branch!r}: not a recognized branch.")
    fmt = None
    if format:
        f = str(format).lower()
        fmt = next((k for k, v in FORMATS.items() if any(x in f for x in v) or "remote" in f and k == "online"), None)
        if not fmt:
            notes.append(f"Ignored format={format!r}: use online, in-person or hybrid.")
    aud = (audience or "").lower()

    q = (query or "").strip() or "veteran training program"
    qv = np.array(embed([q + (" | " + user_question if user_question else "")])[0], dtype=np.float32)
    qv /= np.linalg.norm(qv)
    scores = matrix @ qv

    ranked = []
    for i in np.argsort(-scores):
        p = programs[i]
        s = float(scores[i])
        st = program_states(p)
        if code:
            if st and code not in st:
                continue
            if code in st:
                s += 0.08  # prefer programs actually tied to the requested state
        if br:
            name = (p["name"] + " " + p["organization"]).lower()
            other = [k for k, v in BRANCHES.items() if k != br and any(x in name for x in v)]
            if other and not any(x in name for x in BRANCHES[br]):
                continue
            if any(x in name for x in BRANCHES[br]):
                s += 0.15
        if fmt and not any(x in (p["format"] or "").lower() for x in FORMATS[fmt]):
            continue
        if free_only and p["free_no_benefit"] != "Yes":
            continue
        if "spouse" in aud and p["spouse_family_caregiver"] != "Yes":
            continue
        if ("active" in aud or "transition" in aud) and p["active_duty_transitioning"] != "Yes":
            continue
        if "skillbridge" in aud and p["skillbridge"] != "Yes":
            continue
        lex = lexical_coverage(q, p)
        ranked.append((s + 0.1 * lex, s, lex, p))
    ranked.sort(key=lambda x: -x[0])
    limit = max(1, min(int(limit or 5), 8))
    results = []
    for combo, sem, lex, p in ranked[:limit]:
        strong = sem >= 0.70 or (lex >= 0.5 and sem >= 0.60)
        results.append(dict(card(p), match_score=round(combo, 3),
                            relevance="strong" if strong else "weak"))
    return {"results": results, "notes": notes, "total_matches": len(ranked)}


def get_program(id):
    _, by_slug, _ = _load()
    p = by_slug.get(str(id).strip().strip("/").split("/")[-1])
    if not p:
        return {"error": f"No program with id {id!r}. Use an id returned by search_programs."}
    return card(p, short=False)


def handoff_to_human(reason=""):
    return {
        "handoff": True,
        "contact": HANDOFF_EMAIL,
        "message": ("This is outside what the Skills for Vets program finder can answer reliably. "
                    f"Email {HANDOFF_EMAIL} and a person will follow up."),
        "reason": reason,
    }


TOOL_FUNCS = {"search_programs": search_programs, "get_program": get_program,
              "handoff_to_human": handoff_to_human}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_programs",
        "description": "Search the Skills for Vets directory of free or funded veteran training programs.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Career field or skill, e.g. 'cybersecurity', 'welding', 'CDL'."},
            "state": {"type": "string", "description": "US state name or 2-letter code. Only if the user named a state."},
            "branch": {"type": "string", "description": "Military branch, only if the user named one."},
            "format": {"type": "string", "enum": ["online", "in-person", "hybrid"]},
            "audience": {"type": "string", "enum": ["veteran", "spouse", "active duty", "skillbridge"]},
            "free_only": {"type": "boolean", "description": "True only if the user needs it free without using GI Bill or other benefits."},
        }, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_program",
        "description": "Get full details (eligibility, cost, deadlines) for one program by its id.",
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "handoff_to_human",
        "description": "Route the user to the Skills for Vets team when the question is not about finding a training program, or when the data does not answer it.",
        "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}},
]
