"""The agent loop: local model + tools + guardrails.

Guardrails (each one exists because of a failure seen in testing, see README):
  1. Scope check before the model runs (VA claims, legal, medical, crisis).
  2. Tool-call cap and repeat-call detection, then a forced answer or handoff.
  3. Citations by id only. The model writes [id], code swaps in the name and links
     from the data. Unknown ids and any raw URL the model writes are removed.
  4. If the final answer has no valid citation, a plain list built from the
     retrieved records replaces it.
"""
import json
import re
import time

from .llm import chat
from .tools import HANDOFF_EMAIL, TOOL_FUNCS, TOOL_SCHEMAS, card, _load, handoff_to_human

MAX_TOOL_CALLS = 4

SYSTEM = f"""You help veterans, service members and military spouses find training programs listed on Skills for Vets (skillsforvets.org).

Rules:
- Always call search_programs before recommending anything. Recommend only programs returned by the tools with "relevance": "strong".
- If no result is strong, or the user asks about a program that is not in the results, say plainly that it is not in the Skills for Vets directory. Do not guess a link for it.
- Refer to a program ONLY by its id in square brackets, like [fortinet-veterans-program]. Do not write program names or URLs yourself; they are added automatically.
- Use only facts present in the tool results. If eligibility, cost, dates or state limits are not in the results, say "check the official page".
- Do not answer questions about VA disability claims, ratings, appeals, GI Bill payment amounts, legal issues or medical care. Call handoff_to_human for those.
- If no result fits, say so plainly and suggest emailing {HANDOFF_EMAIL}.
- Keep answers short: up to 3 programs. Write one bullet per program in this form:
  - [program-id]: one sentence on why it fits, using the format, cost or eligibility from the results.
  End with one sentence telling the user to confirm details on the official page.
- Never mention relevance labels, scores, ids or tool names to the user."""

# --- 1. scope check -----------------------------------------------------------
CRISIS = re.compile(r"\b(suicid\w*|kill (myself|me)|end (my|it all)|hurt myself|self[- ]harm|don'?t want to live)\b", re.I)
OUT_OF_SCOPE = [
    (re.compile(r"\b(disability (claim|rating|compensation|percent)|va (claim|rating)|c&p exam|appeal|back ?pay|service[- ]connect\w*|nexus letter|\d{2,3} ?%)", re.I), "VA disability claims and ratings"),
    (re.compile(r"\b(lawyer|attorney|legal advice|sue|lawsuit|court|discharge upgrade|custody|divorce)\b", re.I), "legal questions"),
    (re.compile(r"\b(medication|diagnos\w*|symptom\w*|therapy|therapist|doctor|ptsd treatment|prescription|dosage)\b", re.I), "medical questions"),
    (re.compile(r"\b(how much\b.*\b(gi bill|bah|mha|housing allowance|housing stipend|va)\b|(gi bill|bah|mha|housing allowance)\b.*\b(rate|amount|pay me))", re.I), "GI Bill or housing payment amounts"),
]
TRAINING_INTENT = re.compile(r"\b(programs?|train\w*|bootcamps?|courses?|class(es)?|apprentice\w*|certif\w*|skillbridge|learn\w*|school|jobs?)\b", re.I)


def scope_check(q):
    if CRISIS.search(q):
        return {"kind": "crisis", "text": (
            "If you are thinking about hurting yourself, please contact the Veterans Crisis Line now: "
            "dial 988 and press 1, or text 838255. It is free and confidential, 24/7.\n\n"
            f"For training questions later, the Skills for Vets team is at {HANDOFF_EMAIL}.")}
    for rx, topic in OUT_OF_SCOPE:
        if rx.search(q):
            if topic != "GI Bill or housing payment amounts" and TRAINING_INTENT.search(q):
                # Seen in eval: "I have a 70% rating, any coding bootcamps?" was refused.
                # A training question that mentions a rating still gets an answer, plus a note.
                return {"kind": "note", "text": f"I can't help with {topic}; for that, email {HANDOFF_EMAIL}."}
            h = handoff_to_human(topic)
            return {"kind": "handoff", "text": (
                f"I can only help find training programs in the Skills for Vets directory, so I can't answer {topic}. "
                f"{h['message']}")}
    return None


# --- 3/4. citation check ------------------------------------------------------
ID_RX = re.compile(r"\[([a-z0-9][a-z0-9\-]{2,})\]")
URL_RX = re.compile(r"https?://[^\s\)\]>\"']+")


def render(answer, seen, weak=()):
    """Replace [id] with name + links. Drop ids and URLs that did not come from tool results."""
    _, by_slug, _ = _load()
    events = []
    # Links go in the Sources block, built from data. Drop markdown links the model writes inline.
    answer = re.sub(r",?\s*\[[^\]\n]*\]\(\s*https?://[^)\s]*\s*\)", "", answer)
    allowed_urls = set()
    for slug in seen:
        c = card(by_slug[slug])
        allowed_urls |= {c["official_link"].rstrip("/"), c["skills_for_vets_page"].rstrip("/")}

    def url_sub(m):
        u = m.group(0).rstrip(".,;")
        if u.rstrip("/") in allowed_urls:
            return m.group(0)
        events.append(f"removed unverified URL {u}")
        return "[link removed]"
    answer = URL_RX.sub(url_sub, answer)

    cited = []
    kept_lines = []
    for line in answer.split("\n"):
        bad = [x for x in ID_RX.findall(line) if x not in seen]
        if bad:
            for slug in bad:
                if slug in weak:
                    events.append(f"weak match {slug} cited; line removed")
                elif slug in by_slug:
                    events.append(f"id {slug} exists but was not retrieved this turn; line removed")
                else:
                    events.append(f"unknown id {slug}; line removed")
            continue
        kept_lines.append(line)
    answer = "\n".join(kept_lines)

    # Location claims: a line that ties a program to a state the data does not support.
    from .tools import program_states, states_in_text
    checked = []
    for line in answer.split("\n"):
        ids = [x for x in ID_RX.findall(line) if x in seen]
        if len(ids) == 1:
            p = by_slug[ids[0]]
            st = program_states(p)
            claimed = states_in_text(re.sub(r"\[[^\]]*\]", "", line))
            # Seen in testing: a SkillBridge (active duty only) program described as open to spouses.
            if re.search(r"\bspouses?\b", line, re.I) and p.get("spouse_family_caregiver") != "Yes":
                events.append(f"spouse claim not supported for {ids[0]}; claim removed")
                line = re.sub(r"\s*(,|and|or)?\s*(military )?spouses?\b", "", line, flags=re.I)
            # Seen in a web smoke test: "SkillBridge training for veterans in North Carolina"
            # for a SkillBridge program (active duty only) with no state on file.
            if p.get("veteran_any_era") == "No" and re.search(r"\bfor (all )?veterans\b", line, re.I):
                events.append(f"veteran claim not supported for {ids[0]}; changed to active duty")
                line = re.sub(r"\bfor (all )?veterans\b", "for transitioning active duty members", line, flags=re.I)
            fmt = (p.get("format") or "").lower()
            if claimed and not st and fmt != "online":
                events.append(f"location claim {sorted(claimed)} with no state on file for {ids[0]}; claim removed")
                line = f"- [{ids[0]}]: no state is listed for this program. Check the official page for locations."
                claimed = set()
            wrong = sorted(c for c in claimed if st and c not in st)
            if wrong:
                events.append(f"location claim {wrong} not supported for {ids[0]} (on file: {sorted(st)}); claim removed")
                where = ", ".join(sorted(st))
                line = f"- [{ids[0]}]: location on file is {where}. Check the official page for details."
        checked.append(line)
    answer = "\n".join(checked)

    def id_sub(m):
        slug = m.group(1)
        if slug in seen:
            if slug not in cited:
                cited.append(slug)
            return f"**{by_slug[slug]['name']}**"
        if slug in by_slug:
            events.append(f"id {slug} exists but was not retrieved this turn; removed")
        else:
            events.append(f"unknown id {slug} removed")
        return "[unverified program removed]"
    answer = ID_RX.sub(id_sub, answer)
    answer = re.sub(r",?\s*\[(skills_for_vets_page|official_link|link|url)\]", "", answer)
    answer = re.sub(r"\[([A-Za-z][^\]\n]{3,80})\]", r"(\1)", answer)
    answer = re.sub(r"[^\n.]*\b(relevance|match score|match_score)\b[^\n.]*\.?", "", answer)
    answer = re.sub(r",\s*(?=\.|\n|$)", "", answer)
    # Strip leftover phrases that point at a link we removed.
    answer = re.sub(r"[^\n.]*\[link removed\][^\n.]*\.?", "", answer).strip()

    # Fallback: model named a retrieved program in plain text instead of [id].
    if not cited:
        low = answer.lower()
        for slug in seen:
            if by_slug[slug]["name"].lower() in low:
                cited.append(slug)
        if cited:
            events.append("model used names, not ids; matched by exact name")
    return answer, cited, events


def sources_block(cited):
    _, by_slug, _ = _load()
    lines = []
    for s in cited:
        c = card(by_slug[s])
        where = c["format"] if c["format"] not in (None, "", "Check") else "format: see official page"
        loc = (by_slug[s].get("location") or "").strip()
        if loc and not loc.startswith("See the eligibility"):
            where += "; " + loc[:110]
        lines.append(f"- {c['name']} ({where}): {c['official_link']} (details: {c['skills_for_vets_page']})")
    return "Sources:\n" + "\n".join(lines)


def fallback_answer(seen_order):
    _, by_slug, _ = _load()
    top = seen_order[:3]
    if not top:
        return (f"I couldn't find a matching program in the directory. Email {HANDOFF_EMAIL} and the team can help.", [])
    lines = ["Here are the closest matches in the Skills for Vets directory. Check each official page for eligibility and dates:"]
    for s in top:
        p = by_slug[s]
        lines.append(f"- **{p['name']}** ({p['organization']}; {p['format']}; cost: {p['cost']})")
    return "\n".join(lines), top


# --- named-program check -----------------------------------------------------
NAME_RX = re.compile(r"\b((?:[A-Z][\w&'-]*|of|for|the|and)(?:\s+(?:[A-Z][\w&'-]*|of|for|the|and)){1,6})")
SKIP_FIRST = {"I", "I'm", "Im", "Tell", "Are", "Is", "Can", "Do", "Does", "What", "Where", "Which", "How",
              "Any", "Give", "Show", "Find", "My", "We", "Hi", "Hello", "Please", "The"}
COMMON = {"Air Force", "Coast Guard", "Space Force", "Marine Corps", "Navy", "Army", "GI Bill",
          "Post-9/11 GI Bill", "VA", "VET TEC", "National Guard", "Skills for Vets", "United States"}


def named_programs_missing(question):
    """Return capitalized names in the question that match no program in the directory."""
    from .tools import STATES, tokens
    programs, _, _ = _load()
    missing = []
    for m in NAME_RX.finditer(question):
        words = m.group(1).split()
        while words and (words[0] in SKIP_FIRST or words[0].lower() in ("of", "for", "the", "and")):
            words = words[1:]
        while words and words[-1].lower() in ("of", "for", "the", "and"):
            words = words[:-1]
        if len(words) < 2:
            continue
        phrase = " ".join(words)
        if phrase in COMMON or phrase.lower() in STATES:
            continue
        toks = set(tokens(phrase))
        if not toks:
            continue
        best = 0.0
        for p in programs:
            hay = (p["name"] + " " + p["organization"]).lower()
            best = max(best, sum(1 for t in toks if re.search(r"\b" + re.escape(t), hay)) / len(toks))
        if best < 0.75:
            missing.append(phrase)
    return missing


# --- argument repair ---------------------------------------------------------
FREE_RX = re.compile(r"\b(free|no[- ]cost|without (the )?gi bill|no gi bill|don'?t want to use (my )?gi bill)\b", re.I)


def repair_args(fn, args, question):
    """Seen in testing: the 3B model drops or invents filters. Fix the obvious cases from the user's words."""
    from .tools import BRANCHES, STATES, CODES
    if fn != "search_programs":
        return args, []
    args, fixes = dict(args), []
    ql = question.lower()
    if args.get("free_only") and not FREE_RX.search(question):
        args.pop("free_only")
        fixes.append("dropped free_only (user did not ask for free)")
    if "skillbridge" in ql and args.get("audience") != "skillbridge":
        args["audience"] = "skillbridge"
        fixes.append("set audience=skillbridge from question")
    if not args.get("branch"):
        for b, words in BRANCHES.items():
            if any(re.search(r"\b" + w + r"\b", ql) for w in words):
                args["branch"] = b
                fixes.append(f"set branch={b} from question")
                break
    if not args.get("state"):
        found = [c for n, c in STATES.items() if re.search(r"\b" + n + r"\b", ql)]
        found += [c for c in re.findall(r"\b([A-Z]{2})\b", question) if c in CODES and c not in ("IT", "OR", "IN", "ME", "OK")]
        if found:
            args["state"] = found[0]
            fixes.append(f"set state={found[0]} from question")
    return args, fixes


# --- 2. the loop --------------------------------------------------------------
def run(question, verbose=False):
    t0 = time.time()
    trace = {"question": question, "tool_calls": [], "guardrail_events": []}

    sc = scope_check(question)
    scope_note = None
    if sc and sc["kind"] == "note":
        scope_note = sc["text"]
        trace["guardrail_events"].append("scope check: mixed question, answering the training part")
        sc = None
    if sc:
        trace["guardrail_events"].append(f"scope check: {sc['kind']}")
        trace.update(answer=sc["text"], cited=[], handoff=True, seconds=round(time.time() - t0, 1))
        return trace

    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    seen, weak, handoff, calls_made, prev_calls = [], set(), False, 0, set()
    final = None
    nudged = False

    for _round in range(MAX_TOOL_CALLS + 2):
        allow_tools = calls_made < MAX_TOOL_CALLS
        if not allow_tools:
            messages.append({"role": "system", "content": "Tool limit reached. Answer now using only the results above, citing ids in [brackets]."})
        resp = chat(messages, TOOL_SCHEMAS if allow_tools else None)
        msg = resp["message"]
        tcs = msg.get("tool_calls") or []
        if not tcs:
            if not trace["tool_calls"] and not nudged:
                # Seen in testing: the model answered from memory without searching.
                nudged = True
                trace["guardrail_events"].append("model answered without searching; asked it to search first")
                messages.append({"role": "assistant", "content": msg.get("content", "")})
                messages.append({"role": "system", "content": "You must call search_programs before answering. Do not answer from memory."})
                continue
            final = msg.get("content", "")
            break
        messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": tcs})
        stop = False
        for tc in tcs:
            fn = tc["function"]["name"]
            args = tc["function"].get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            args, fixes = repair_args(fn, args, question)
            trace["guardrail_events"] += fixes
            key = fn + json.dumps(args, sort_keys=True)
            calls_made += 1
            if key in prev_calls:
                trace["guardrail_events"].append(f"repeated call {fn}{args}; stopping tool use")
                result = {"error": "You already made this exact call. Answer with what you have."}
                stop = True
            elif calls_made > MAX_TOOL_CALLS:
                trace["guardrail_events"].append("tool-call cap hit")
                result = {"error": "Tool limit reached."}
                stop = True
            elif (fn == "handoff_to_human" and TRAINING_INTENT.search(question)
                  and not any(c["tool"] == "search_programs" for c in trace["tool_calls"])):
                # Seen in eval: the model handed off a coding-bootcamp question because it
                # mentioned a disability rating, without ever searching.
                trace["guardrail_events"].append("handoff before any search on a training question; asked model to search first")
                result = {"error": "Search first. Call search_programs for the training part of the question; hand off only if nothing strong is found."}
                fn = "handoff_blocked"
            elif fn not in TOOL_FUNCS:
                result = {"error": f"Unknown tool {fn}"}
            else:
                try:
                    call_args = {k: v for k, v in args.items() if v not in (None, "")}
                    if fn == "search_programs":
                        # Seen in testing: the model shortens the query ("certification") and loses
                        # the user's intent ("Navy will pay for exams"). Embed both.
                        call_args["user_question"] = question
                    result = TOOL_FUNCS[fn](**call_args)
                except TypeError as e:
                    result = {"error": f"Bad arguments: {e}"}
            prev_calls.add(key)
            trace["tool_calls"].append({"tool": fn, "args": args})
            if fn == "search_programs" and "results" in result:
                for r in result["results"]:
                    if r["relevance"] == "weak":
                        weak.add(r["id"])
                    elif r["id"] not in seen:
                        seen.append(r["id"])
                if result.get("notes"):
                    trace["guardrail_events"] += result["notes"]
            if fn == "get_program" and "id" in result and result["id"] not in seen:
                seen.append(result["id"])
            if fn == "handoff_to_human":
                handoff = True
            messages.append({"role": "tool", "content": json.dumps(result)[:6000]})
        if stop:
            calls_made = MAX_TOOL_CALLS

    if final is None:
        final = ""

    if handoff and not seen:
        text = handoff_to_human()["message"]
        trace.update(answer=text, cited=[], handoff=True, seconds=round(time.time() - t0, 1))
        return trace

    missing = named_programs_missing(question)
    weak -= set(seen)
    answer, cited, events = render(final, set(seen), weak)
    trace["guardrail_events"] += events
    if not cited and not handoff:
        if seen:
            trace["guardrail_events"].append("no verified citation in model answer; replaced with retrieved list")
            answer, cited = fallback_answer(seen)
        else:
            trace["guardrail_events"].append("no strong match retrieved; answered 'not found'")
            answer = ("I couldn't find a program in the Skills for Vets directory that matches that. "
                      f"Email {HANDOFF_EMAIL} and the team can help, or browse https://skillsforvets.org/programs/.")
    if missing:
        trace["guardrail_events"].append(f"named program not in directory: {missing}")
        note = " and ".join(f'"{m}"' for m in missing)
        # Seen in eval: the model swapped in other programs instead of saying "not listed".
        # For a question about a named program that is not in the data, say so and stop.
        answer = (f"I couldn't find {note} in the Skills for Vets directory, so I can't give you a link, dates or "
                  f"eligibility for it. Email {HANDOFF_EMAIL} if you think it should be listed, or browse "
                  "https://skillsforvets.org/programs/ for similar programs.")
        cited = []
    if cited:
        answer = answer.strip() + "\n\n" + sources_block(cited)
    if scope_note:
        answer += "\n\n" + scope_note
    if HANDOFF_EMAIL not in answer and handoff:
        answer += f"\n\nFor anything else, email {HANDOFF_EMAIL}."
    trace.update(answer=answer, cited=cited, handoff=handoff, retrieved=seen,
                 raw_model_answer=final, seconds=round(time.time() - t0, 1))
    return trace
