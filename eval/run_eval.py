"""Run the eval set against the local agent and write eval/results.json + eval/results.md."""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sfv_agent.agent import run  # noqa: E402
from sfv_agent.llm import CHAT_MODEL  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def grade(case, t):
    cited, ans = t.get("cited", []), t["answer"]
    if case["type"] == "programs":
        hit = [c for c in cited if c in case["expect_any"]]
        return bool(hit), f"cited {cited}"
    if case["type"] == "not_found":
        ok = not cited and "couldn't find" in ans
        return ok, f"cited {cited}"
    if case["type"] == "handoff":
        ok = not cited and "info@skillsforvets.org" in ans
        return ok, f"cited {cited}, handoff={t.get('handoff')}"


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "questions"
    cases = json.load(open(os.path.join(HERE, name + ".json")))
    rows = []
    for i, c in enumerate(cases, 1):
        t = run(c["q"])
        ok, why = grade(c, t)
        rows.append({"n": i, "type": c["type"], "q": c["q"], "pass": ok, "detail": why,
                     "seconds": t["seconds"], "tool_calls": t["tool_calls"],
                     "guardrail_events": t["guardrail_events"], "answer": t["answer"]})
        print(f"{i:2d} {'PASS' if ok else 'FAIL'} {t['seconds']:5.1f}s {c['type']:9s} {c['q'][:70]}  {why[:120]}", flush=True)
    passed = sum(r["pass"] for r in rows)
    times = [r["seconds"] for r in rows if r["tool_calls"]]
    summary = {"model": CHAT_MODEL, "passed": passed, "total": len(rows),
               "median_seconds_when_model_ran": statistics.median(times) if times else None}
    json.dump({"summary": summary, "rows": rows}, open(os.path.join(HERE, f"results-{name}.json"), "w"), indent=1)
    with open(os.path.join(HERE, f"results-{name}.md"), "w") as f:
        f.write(f"Model: {CHAT_MODEL}. Passed {passed} of {len(rows)}.\n\n| # | Type | Question | Result | Seconds | Notes |\n|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['n']} | {r['type']} | {r['q']} | {'pass' if r['pass'] else 'FAIL'} | {r['seconds']} | {r['detail'][:150]}; guardrails: {'; '.join(r['guardrail_events'])[:200]} |\n")
    print(summary)


if __name__ == "__main__":
    main()
