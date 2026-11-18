"""Ask the Skills for Vets agent from the terminal.  python cli.py "question"  (or no args for a prompt)"""
import sys

from sfv_agent.agent import run


def show(q, debug):
    t = run(q)
    print("\n" + t["answer"])
    if debug:
        print(f"\n[tools: {t['tool_calls']}]\n[guardrails: {t['guardrail_events']}]")
    print(f"\n({t['seconds']}s)")


if __name__ == "__main__":
    debug = "--debug" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--debug"]
    if args:
        show(" ".join(args), debug)
    else:
        print("Skills for Vets program finder (local model). Ctrl-C to quit.")
        while True:
            try:
                q = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q:
                show(q, debug)
