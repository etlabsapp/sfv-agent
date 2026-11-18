"""Load the Skills for Vets program records and build the local vector index."""
import json
import os
from datetime import datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SNAPSHOT = os.path.join(ROOT, "data", "programs.snapshot.json")
INDEX = os.path.join(ROOT, "data", "index.npz")
SOURCE = os.environ.get("SFV_SOURCE")  # path to a programs.json file; only needed to refresh the snapshot
SITE = "https://skillsforvets.org"


def make_snapshot():
    raw = json.load(open(SOURCE))
    programs = [p for p in raw["programs"] if not p.get("archival")]
    keep = [
        "slug", "name", "organization", "category", "all_categories", "job_titles",
        "status", "format", "format_detail", "state_residency", "location", "cost",
        "cost_detail", "free_no_benefit", "requires_gi_bill", "active_duty_transitioning",
        "veteran_any_era", "spouse_family_caregiver", "skillbridge", "eligibility",
        "what_you_get", "duration", "deadline_detail", "topic_tags", "url",
        "program_path", "last_verified",
    ]
    rows = [{k: p.get(k) for k in keep} for p in programs]
    out = {
        "source_file": SOURCE,
        "snapshot_taken": datetime.now().isoformat(timespec="seconds"),
        "archived_records_skipped": len(raw["programs"]) - len(programs),
        "count": len(rows),
        "programs": rows,
    }
    json.dump(out, open(SNAPSHOT, "w"), indent=1)
    return out


def load_programs():
    return json.load(open(SNAPSHOT))["programs"]


def doc_text(p):
    parts = [
        p["name"], f"Organization: {p['organization']}", f"Category: {p['all_categories'] or p['category']}",
        f"Jobs: {p.get('job_titles') or ''}", f"Topics: {p.get('topic_tags') or ''}",
        f"Format: {p['format']}", f"Location: {p.get('location') or ''} States: {p.get('state_residency') or ''}",
        f"Cost: {p['cost']}", f"Who: {p['eligibility']}", f"What you get: {p['what_you_get']}",
    ]
    return "\n".join(parts)[:1800]


def build_index():
    from .llm import embed
    progs = load_programs()
    vecs = []
    for i in range(0, len(progs), 16):
        vecs += embed([doc_text(p) for p in progs[i:i + 16]], kind="doc")
    m = np.array(vecs, dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    np.savez(INDEX, vectors=m, slugs=np.array([p["slug"] for p in progs]))
    return m.shape


if __name__ == "__main__":
    if SOURCE:
        s = make_snapshot()
        print(f"snapshot: {s['count']} active programs (skipped {s['archived_records_skipped']} archived) from {s['source_file']}")
    elif os.path.exists(SNAPSHOT):
        s = json.load(open(SNAPSHOT))
        print(f"using existing snapshot: {s['count']} programs (taken {s.get('snapshot_taken')})")
    else:
        raise SystemExit("No snapshot found. Set SFV_SOURCE to a programs.json file and rerun.")
    print("index shape:", build_index())
