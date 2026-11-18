"""Guardrail tests that do not depend on the model's mood.

The tool-loop tests swap the local model for a stub that never stops calling
tools, so the cap is exercised every run. Run: python -m tests.test_guardrails
"""
import itertools

from sfv_agent import agent

counter = itertools.count()


def stub_same_call(messages, tools=None):
    if tools:
        return {"message": {"content": "", "tool_calls": [
            {"function": {"name": "search_programs", "arguments": {"query": "welding"}}}]}}
    return {"message": {"content": "- [uhp-skilled-trades-institute-welding-program]: welding course."}}


def stub_new_call_every_time(messages, tools=None):
    if tools:
        n = next(counter)
        return {"message": {"content": "", "tool_calls": [
            {"function": {"name": "search_programs", "arguments": {"query": f"welding {n}"}}}]}}
    return {"message": {"content": "- [uhp-skilled-trades-institute-welding-program]: welding course."}}


def stub_invents(messages, tools=None):
    if tools and not any(m["role"] == "tool" for m in messages):
        return {"message": {"content": "", "tool_calls": [
            {"function": {"name": "search_programs", "arguments": {"query": "cybersecurity"}}}]}}
    return {"message": {"content": (
        "- [cybrary-for-veterans]: free cyber courses.\n"
        "- [lockheed-cyber-fellows]: paid fellowship, apply at https://lockheed.example.com/apply.\n"
        "Also see https://www.cybrary.it/ and https://fake-vets-grants.org/now.")}}


def stub_early_handoff(messages, tools=None):
    if tools and not any(m["role"] == "tool" for m in messages):
        return {"message": {"content": "", "tool_calls": [
            {"function": {"name": "handoff_to_human", "arguments": {"reason": "mentions a rating"}}}]}}
    if tools and sum(m["role"] == "tool" for m in messages) == 1:
        return {"message": {"content": "", "tool_calls": [
            {"function": {"name": "search_programs", "arguments": {"query": "coding bootcamp"}}}]}}
    import json as _j
    first = _j.loads([m for m in messages if m["role"] == "tool"][-1]["content"])["results"][0]["id"]
    return {"message": {"content": f"- [{first}]: free coding program."}}


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    return cond


def main():
    ok = True
    real_chat = agent.chat
    try:
        agent.chat = stub_same_call
        t = agent.run("welding classes?")
        ok &= check("repeat call is stopped", len(t["tool_calls"]) <= 2, f"{len(t['tool_calls'])} calls, events={t['guardrail_events']}")

        agent.chat = stub_new_call_every_time
        t = agent.run("welding classes?")
        ok &= check("tool-call cap holds", len(t["tool_calls"]) <= agent.MAX_TOOL_CALLS, f"{len(t['tool_calls'])} calls")
        ok &= check("still answers after cap", "Sources:" in t["answer"])

        agent.chat = stub_invents
        t = agent.run("cyber programs?")
        ok &= check("invented program line removed", "lockheed" not in t["answer"].lower())
        ok &= check("invented URL removed", "fake-vets-grants" not in t["answer"])
        ok &= check("real retrieved program kept", t["cited"] == ["cybrary-for-veterans"], str(t["cited"]))

        agent.chat = stub_early_handoff
        t = agent.run("I have a 70% rating. Any free coding bootcamps?")
        ok &= check("early handoff on training question is blocked", len(t["cited"]) == 1 and "VA disability" in t["answer"] and t["tool_calls"][1]["tool"] == "search_programs", str(t["guardrail_events"]))
    finally:
        agent.chat = real_chat

    out, cited, ev = agent.render(
        "- [viper-a-and-p-program-free-faa-a-and-p-with-a-job-offer]: A&P prep in Coastal Georgia.",
        {"viper-a-and-p-program-free-faa-a-and-p-with-a-job-offer"})
    ok &= check("wrong location claim replaced (VIPER is Nellis AFB, Nev.)", "Georgia" not in out and "NV" in out, out)
    out, cited, ev = agent.render(
        "- [ua-veterans-in-piping-vip-welding-hvacr-and-fire-sprinkler-skillbridge]: for active duty members and spouses.",
        {"ua-veterans-in-piping-vip-welding-hvacr-and-fire-sprinkler-skillbridge"})
    ok &= check("unsupported spouse claim removed", "spouse" not in out.lower(), out)
    out, cited, ev = agent.render(
        "- [ua-veterans-in-piping-vip-welding-hvacr-and-fire-sprinkler-skillbridge]: Free SkillBridge training for veterans in North Carolina.",
        {"ua-veterans-in-piping-vip-welding-hvacr-and-fire-sprinkler-skillbridge"})
    ok &= check("state claim with no state on file removed", "North Carolina" not in out, out)
    out, cited, ev = agent.render(
        "- [ua-veterans-in-piping-vip-welding-hvacr-and-fire-sprinkler-skillbridge]: Free SkillBridge training for veterans.",
        {"ua-veterans-in-piping-vip-welding-hvacr-and-fire-sprinkler-skillbridge"})
    ok &= check("veteran claim on active-duty-only program changed", "for veterans" not in out and "active duty" in out, out)

    for q, kind in [("How do I appeal my VA disability rating?", "handoff"),
                    ("I need a lawyer for my discharge upgrade", "handoff"),
                    ("What medication helps with PTSD nightmares?", "handoff"),
                    ("I don't want to live anymore", "crisis"),
                    ("Free welding training in Texas?", None)]:
        sc = agent.scope_check(q)
        ok &= check(f"scope: {q!r}", (sc or {}).get("kind") == kind, str((sc or {}).get("kind")))
    print("ALL PASS" if ok else "SOME FAILED")


if __name__ == "__main__":
    main()
