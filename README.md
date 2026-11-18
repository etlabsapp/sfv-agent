# Skills for Vets program finder (local AI demo)

A small question-and-answer agent for the Skills for Vets program directory. You ask something like "Is there free welding training in Texas?" and it searches the directory, answers with matching programs, and lists each program's official link and its Skills for Vets page.

Everything runs on this computer. The language model and the embedding model run through Ollama. There are no API keys and no calls to a hosted AI service; `sfv_agent/llm.py` refuses to start if `OLLAMA_URL` points anywhere other than localhost.

This is a portfolio demo. It is not on skillsforvets.org.

## What it does

- Searches 314 programs from a snapshot of the Skills for Vets directory taken Nov 17, 2026 (5 archived records skipped). The snapshot (`data/programs.snapshot.json`) and the embeddings index (`data/index.npz`, about 1.1 MB) ship with the repo. Search combines embeddings with keyword matching and can filter by state, branch, audience (for example SkillBridge) and free-only.
- Gives the model three tools: `search_programs`, `get_program` and `handoff_to_human`.
- Answers only from the retrieved records. The model refers to programs by id, and the code swaps in the name and links from the data, so links in an answer come from the directory, not from the model.
- Hands off to info@skillsforvets.org for things it should not answer: VA claims and ratings, legal questions, medical questions, and GI Bill payment amounts. If a message sounds like a crisis, it gives the Veterans Crisis Line (dial 988 and press 1, or text 838255) first.
- Says "I couldn't find ..." when someone asks about a program that is not in the directory, instead of describing something else.

## Model

- Chat: Qwen2.5 3B Instruct, Q4_K_M quantization (GGUF from Hugging Face), loaded in Ollama as `sfv-qwen2.5-3b` with temperature 0.1 and an 8K context.
- Embeddings: nomic-embed-text v1.5, Q8_0, loaded as `sfv-nomic-embed`.

A 3B model was picked so it runs on a laptop CPU. It makes mistakes a larger model would not, which is why most of the code is checks around the model (see "What broke and how I fixed it").

## How to run

One-time setup (downloads about 2.3 GB of model files, creates the Ollama models, installs Python packages, builds the index):

```
./setup.sh
```

Web page at http://127.0.0.1:8765 (starts Ollama if it is not running):

```
./start.sh
```

Terminal:

```
.venv/bin/python cli.py "Any lineman apprenticeships in North Carolina?"
.venv/bin/python cli.py --debug          # interactive, shows tool calls and guardrail events
```

Tests and eval:

```
.venv/bin/python -m tests.test_guardrails     # no model needed, a few seconds
.venv/bin/python eval/run_eval.py questions   # 25 questions, about 8 minutes on CPU
.venv/bin/python eval/run_eval.py heldout     # 10 held-out questions
```

To refresh the data after the site's program list changes, set `SFV_SOURCE` to a `programs.json` file and run `.venv/bin/python -m sfv_agent.data`. To rebuild only the embeddings index from the existing snapshot, run the same command without `SFV_SOURCE` (Ollama and the embedding model must be running).

## Limits

- Speed. On this box (8 CPU cores, no GPU, 15 GB RAM) a typical answer takes 11 to 25 seconds, median about 16 seconds in the final eval; the slowest was 34 seconds. Handoff and crisis replies are instant because they are decided before the model runs. A slower laptop will be slower.
- Not on the live site. The site is static hosting; running the model needs a machine with Ollama on it. Putting this online would mean a server or a hosted model, which is outside this demo.
- Answers are only as current as the snapshot. Program status, deadlines and eligibility change; every answer tells the user to confirm on the official page.
- Relevance is uneven at the edges. When the directory has only one or two good matches, the model sometimes fills out the list with weaker ones (for "Salesforce administrator" it also listed a SkillBridge cybersecurity program and an intro Linux course).
- The checks catch specific known failure patterns (wrong state, spouse or veteran eligibility the record does not support, invented ids and URLs). They do not verify every sentence the model writes.
- The eval is small (35 questions) and written by the same person who built the agent, so passing it is a sanity check, not proof.

## Eval results

Pass rules (`eval/run_eval.py`): a program question passes if the answer cites at least one of the expected programs; a "not in directory" question passes if it cites nothing and says "couldn't find"; a handoff question passes if it cites nothing and gives info@skillsforvets.org.

- `eval/questions.json` (25 questions, used while building): passed 25 of 25 in the final run (Nov 17, 2026). Median 15.8 seconds per answer when the model ran.
- `eval/heldout.json` (10 questions written after the fixes and not tuned against): passed 10 of 10 in the final run. Median 16.7 seconds.

History on the 25-question set: run 1 passed 20 of 25, run 2 passed 24, run 3 passed 25. The final run came after fix 9 below. The pre-fix final logs are kept as `eval/prefix-final-*.log`. Full answers for each question are in `eval/results-questions.json` and `eval/results-heldout.json`.

Guardrail unit tests (`tests/test_guardrails.py`, stubbed model): all 16 checks pass; output in `tests/last_run.txt`.

## What broke and how I fixed it

Each item below came from an eval log (`eval/run1.log` to `run3.log`) or a manual test.

1. Ignored the SkillBridge filter. "I'm active duty getting out in 6 months. Any SkillBridge programs in IT or cyber?" returned Cybrary and a certification program, neither of them SkillBridge. The model called search without the audience filter and added "free only" on its own. Fix: `repair_args` sets `audience=skillbridge` when the question says SkillBridge and drops `free_only` unless the user asked for free.
2. Lost the user's intent in the search query. "I'm in the Navy. Will they pay for my certification exams?" became a search for "certification" and returned Six Sigma and Google Ads certs. "Lineman apprenticeships in North Carolina" only found one of the expected programs. Fix: the search now embeds the user's full question alongside the model's query. Both passed in run 2.
3. Refused a fair question. "I'm a veteran with a 70% disability rating. Are there free coding bootcamps I can join?" was handed off because it mentioned a rating. Fix one: the scope check lets training questions through and adds a short note pointing rating questions to info@skillsforvets.org. That was not enough; in run 2 the model itself called `handoff_to_human` before searching. Fix two: a handoff before any search on a training question is blocked and the model is told to search first. Passed in run 3 and in the final run.
4. Swapped in other programs for one it did not have. "Tell me about the Lockheed Martin VetCyber Fellowship. What's the link to apply?" (not in the directory) got an answer about Cybrary and a Google cybersecurity certificate. Fix: if the question names a program that is not in the data, the agent says it couldn't find it, gives the directory link and the contact email, and stops.
5. Answered from memory. On several questions the model wrote an answer without calling search. Fix: if the first reply has no tool call, the agent asks it once to search first. This still fires regularly in the logs (for example on "I'm Air Force. Can I get my certs paid for?").
6. Invented programs and links. In testing the model wrote program names and URLs that are not in the data. Fix: citations are ids only; unknown ids, ids not retrieved this turn, and any URL not from a retrieved record are removed. If nothing valid is left, the answer is replaced with a plain list of the retrieved programs.
7. Claimed the wrong location. A test answer put VIPER's A&P program in Coastal Georgia; the record says Nellis AFB, Nevada. Fix: a line that ties a program to a state the record does not support is rewritten to the state on file.
8. Claimed eligibility the record does not support. An active-duty-only SkillBridge program was described as open to spouses. Fix: spouse claims are removed unless the record marks spouses as eligible.
9. Same pattern, found in the last web smoke test. "Any free HVAC training in North Carolina?" described the UA Veterans in Piping SkillBridge program as "Free SkillBridge training for veterans in North Carolina." The record lists no state and says veterans are not eligible (active duty only). The location check skipped it because it only compared against states on file. Fix: for a non-online program with no state on file, a state claim is removed; "for veterans" is changed to "for transitioning active duty members" when the record says veterans are not eligible. Two unit tests cover it. On a rerun after the fix the model described the program correctly on its own, so the check did not need to fire (`eval/smoke-nc-hvac.txt`).
10. Tool loops. A stubbed model that repeats the same call, or makes a new call every turn, is stopped by repeat detection and a cap of 4 tool calls, after which the agent still returns an answer built from what it found. These are covered by unit tests rather than seen in the eval.
11. A 5-minute stall in one eval run. In an earlier full run, the SkillBridge question took 311.9 seconds. The Ollama log shows no requests at all for about 307 seconds in that window (16:07 to 16:12 ET), so the time was not spent in the model; the eval process itself was paused. It did not recur in the final run.

## License

MIT. See `LICENSE`.
