# babyai-laya-probe

한국어: [README.ko.md](README.ko.md) — the original working README with every stage and command.

> **Draft (2026-11-18).** Numbers are copied from the committed reports and were checked against them; LID's numbers in [Prior work](#prior-work) are not yet checked against the paper.

A small, controlled study of one question: **how far can you hand step-by-step decisions to a small "choice" model, and how much of the remaining gap is closed by a few lines of code around it?**

The test bed is [BabyAI](https://minigrid.farama.org/environments/babyai/) (MiniGrid 3.2.0), single-room levels. The model is [Laya](https://huggingface.co/convaiinnovations/laya) — an encoder-only model (ModernBERT-large with a multiple-choice head, about 421M parameters) that scores a fixed list of options instead of generating text — fine-tuned on expert-bot demonstrations.

**This is not a new method and not a sample-efficiency result.** Fine-tuning a pretrained language model to pick BabyAI actions from text observations was published in 2022 (LID; see [Prior work](#prior-work)), with higher model-alone numbers than ours at equal demonstration counts. What this repository adds is narrower: paired measurements of a small executor-side rule, what part of that rule does the work, and a set of pre-declared, run-once checks.

## What we found

1. **A fine-tuned choice model finishes most rooms alone, at about the expert's pace.** With about 1,000 demonstrations per task it solves 84–92 % of unseen layouts on four single-room tasks, including a two-stage task (pick up one object, put it next to another).
2. **One executor rule closes most of the rest, and we never saw it break a room that was already solved.** *"If the same observation comes back within an episode, take the best action not yet tried there; when all were tried, forget that observation's record."* It lifts success to 96–99 %. Across about 40 fine-tuned checkpoints, 30 small-CNN checkpoints, and six untrained-model settings, the number of rooms it turned from success into failure was 0. This is an observation, not a guarantee (see [Limits](#limits)).
3. **What works in that rule is episode-wide memory of observations.** Looking only at the previous step loses almost all of the benefit. The model's ranking of the untried actions adds a little speed, not success. Clearing the record matters for weak models.
4. **Success rate alone is misleading.** Most untrained models reach 277–282 of 300 with the rule, close to the fine-tuned model's 297 — but only 131–214 of those are within twice the expert's step count, against 288 for the fine-tuned model. We report "solved within 2× the expert's steps" next to every success count.
5. **The pretrained model's advantage is at low demonstration counts.** On the two-stage task, 500 demonstrations give 236 of 300 for Laya and 7 for a 67k-parameter CNN trained on the same data; the CNN needs about ten times the data to catch up, and at 10,000 demonstrations the two are 6–11 rooms apart.
6. **The model is rarely wrong about *what* to do; it fails at *moving* when blocked or when the target is out of view.** Failures are loops — walking into a blocked cell, turning left and right in place.

## Setup

| | |
|---|---|
| Environment | MiniGrid 3.2.0, BabyAI levels, unmodified. Egocentric 7×7 partial view, rendered as text (`probe/obs_text.py`). |
| Tasks | `GoToLocal` (3 actions) · `PickupDist` (4) · `GoToLocal` with 16 objects (3) · `PutNextLocal` (5, two-stage) |
| Model | `convaiinnovations/laya` english, pinned revision `55cf4c4`, PyPI `laya==0.4.31`. Scores 3–5 fixed options per step. No action history in the input (except stage 11a). |
| Training | Expert-bot demonstrations only (`minigrid.utils.baby_ai_bot.BabyAIBot`), about 1,000 episodes per task (5k–12k steps), 3 training seeds, 5–12 minutes each on one RTX 5080. Loss is Laya's default (`rlcd`: a policy-gradient term rewarded by a proper scoring rule on the labels, plus soft cross-entropy). No interaction with the environment during training. |
| Evaluation | Closed loop on 300 unseen layouts per task. Development seeds 10000–10299; separate held-out seeds for three tasks, each used once after the pass/fail criteria were committed. |
| Baselines | Expert bot, random, a fixed-preference policy with and without the rule, a 67k-parameter CNN, and untrained hosted / local models. |

## Main results

Successes out of 300 (three training seeds) and, after the slash, successes within twice the expert's step count.

| | GoToLocal (held-out) | PickupDist (held-out) | GoToLocal, 16 objects (**dev seeds**) | PutNextLocal (held-out) |
|---|---|---|---|---|
| Random | 138 / 25 | 53 / 9 | 132 / 24 | 0 / 0 |
| No model + rule | 227 / 66 | 9 / 0 | 191 / 54 | 0 / 0 |
| **Laya alone** | 264 · 262 · 262 / 258 · 261 · 256 | 270 · 275 · 274 / 268 · 273 · 273 | 265 · 264 · 274 / 261 · 262 · 268 | 253 · 258 · 256 / 253 · 258 · 256 |
| **Laya + rule** | 296 · 296 · 295 / 278 · 285 · 270 | 289 · 293 · 292 / 285 · 290 · 288 | 297 · 297 · 296 / 279 · 285 · 283 | 298 · 299 · 298 / 288 · 292 · 293 |
| Rooms the rule broke | 0 | 0 | 0 | 0 |

The tasks differ, so columns are not a ranking of tasks. Step-level agreement with the expert is about 95 % on every task; it does not predict closed-loop success well, because one wrong step can turn into a loop.

### What part of the rule matters (stage 14)

Fine-tuned model, 1,000 demonstrations, mean of three seeds, development seeds. Success on GoToLocal / PutNextLocal.

| Variant | Success | Rooms broken |
|---|---|---|
| No rule | 275.7 / 251.0 | — |
| The rule as stated | 296.7 / 297.3 | 0 |
| Pick a *random* untried action (drop the model's ranking) | 296.7 / 295.4 | 0 |
| React only when the observation equals the *previous* step's (drop episode memory) | 281.0 / 256.7 | 0 |
| Never clear the record | 296.3 / 298.0 | 0 |
| Remember only the last 8 steps | 292.0 / 287.0 | 0 |
| Key on the true agent state instead of the observation (privileged) | 296.7 / 296.3 | 0 |
| No detection, 10 % random actions | 289.2 / 276.2 | 4 / 19 over 9 runs |

With a weak model (100 demonstrations) "never clear" costs 33 and 90 rooms. The same variants on the small CNN point the same way (`reports/stage14_cnn.md`); there, the privileged true-state key broke one room, the observation key none. "Same observation, different true state" happened on 0 steps in GoToLocal and at most 5 in PutNextLocal for the fine-tuned model — in one room with a 7×7 view it is essentially absent. Multi-room levels may differ.

### Demonstration count (stage 11b)

Model alone, within 2× the expert's steps, out of 300, mean of three seeds, development seeds.

| Demonstrations | GoToLocal — Laya | GoToLocal — CNN | PutNextLocal — Laya | PutNextLocal — CNN |
|---|---|---|---|---|
| 100 | 156.3 | 49.0 | 11.0 | 1.7 |
| 500 | 260.3 | 120.3 | 236.0 | 7.3 |
| 1,000 | 271.3 | 163.7 | 251.0 | 15.3 |
| 5,000 | 290.3 | 280.3 | 273.0 | 240.3 |
| 10,000 | 291.7 | 285.3 | 276.3 | 265.7 |

Adding the last four actions to the input at 1,000 demonstrations raises GoToLocal from 271.3 to 280.7 (stage 11a) — less than going to 5,000 demonstrations without them.

### Untrained models with the same rule (stages 5, 12, 13)

GoToLocal, same task description, development seeds. Success alone → with the rule (within 2×).

| Model | Alone | With rule (within 2×) |
|---|---|---|
| Laya, fine-tuned (for reference) | 276 | 297 (288) |
| TypeSafe Jev 1.14 | 163 | 282 (214) |
| Gemma 12B, local | 111 | 280 (163) |
| Gemini Decision 1, text | 75 | 277 (155) |
| Gemini Decision 1, image | 67 | 280 (142) |
| Gemini Decision 1, text + image | 30 | 201 (58) |
| Cloudflare clef-flash, local | 47 | 282 (131) |
| Apple Foundation Models, on-device (100 rooms) | 12 | — (see `reports/stage13.md`; rules for a model that returns no scores are on branch `mac/stage15`) |

These are reference lines from one task description that was written for one of the models; they are not a fair ranking of the models. Image input did not help in this setting.

### Smaller findings

- **One move of help** (`reports/help_test.md`): on the 23 rooms the fine-tuned model fails, inserting the expert's next action once rescues 6; inserting the best of the three actions rescues 16. Help works when it moves the agent to a place the model can continue from, not when it is merely "the right direction".
- **Numerical precision** (`reports/precision_check.json`): bf16 and fp32 inference pick a different top action on 1–2 of 1,625 steps, all near-ties, and change one room out of 300. Read any result that passes or fails a threshold by one or two rooms accordingly.

## Prior work

- **LID** — Li et al., *Pre-Trained Language Models for Interactive Decision-Making*, NeurIPS 2022 — fine-tunes GPT-2 by behaviour cloning on text renderings of the same 7×7 view and predicts the next action. Its reported success at 1,000 demonstrations is 99.0 % (GoToLocal), 99.0 % (PickupLoc) and 93.2 % (PutNextLocal); at 100 demonstrations 64.6 %, 28.7 % and 11.1 %. It includes past actions in the input. **Our model-alone numbers are lower at equal counts** (GoToLocal 87–93 %, PutNextLocal 82–86 % at 1,000 depending on seed and evaluation set; 52.6 % and 3.8 % at 100). The conditions are not matched (history input, evaluation set, environment version), and *we took LID's numbers from a secondary summary and have not checked them against the paper.*
- BabyAI (Chevalier-Boisvert et al., 2019) and BabyAI 1.1 (Hui et al., 2020) report demonstration requirements for small recurrent models; BabyAI-Text / GLAM (Carta et al., 2023), BALROG (2024) and Gato (2022) run language or generalist models on BabyAI under other training signals.
- The executor rule belongs to a known family (state–action tabu exploration, loop detection in agents). We did not find a published measurement of this exact rule with paired "previously solved rooms broken" counts; that is a statement about our search, not a claim of novelty.
- Step-by-step human correction of a BabyAI policy also has prior tools (e.g. RLHF-Blender).

## Limits

- Single-room levels with one instruction. No multi-room, door or key levels, which need memory the model does not have.
- "The rule broke 0 rooms" is an observation on the rooms tested. Under partial observation the same text can describe different states, so there is no general guarantee.
- The network has no memory, but **network + rule does** (the rule keeps a per-episode record). Do not read "memoryless" as applying to the combined agent.
- "Small" means small next to multi-billion-parameter generators; 421M is large next to the original BabyAI baselines.
- No ablation of pretraining (random initialisation, plain ModernBERT, head-only tuning).
- Held-out checks exist for three tasks at 1,000 demonstrations only. Stages 9 and 11–15 are development-seed results. Evaluation sets are 300 rooms; differences of a few rooms are noise.
- Expert labels come from a bot that remembers what it has seen; a memoryless student can receive conflicting labels for the same observation. We did not quantify this.
- Git commits are an audit trail of what was declared before each run, not an external preregistration.
- Results on BabyAI are not evidence about other domains. An attempt to carry the same recipe to a real-time game bot did not work with the data available there; timing tables read from game files did (outside this repository).

## Declared-before-run index

Each row was run once after its criteria were committed. Reports are in Korean; tables and raw per-room JSON are language-independent.

| Stage | What | Declared in | Result in | Outcome |
|---|---|---|---|---|
| 6 | GoToLocal, held-out seeds 20000–20299 | `reports/stage6_prereg.md` (`eea7aa4`) | `reports/stage6.md` (`37316c9`) | Model alone **missed** its band by 2 rooms on two seeds; rule effect reproduced |
| 8d | PickupDist, 30000–30299 | `stage8d_prereg.md` (`53923b2`) | `stage8d.md` (`e15e82b`) | Both criteria passed |
| 10e | PutNextLocal, 70000–70299 | `stage10e_prereg.md` (`97ba88c`) | `stage10e.md` (`ad462dd`) | Both criteria passed |
| 9 | 16 objects, transfer and retrain (dev) | `stage9_prereg.md` (`de405bd`) | `stage9.md` (`7dfe0ba`) | Transfer loses 20–28 rooms; retraining recovers |
| 11a | Last four actions in the input (dev) | `stage11_prereg.md` (`387b061`) | `stage11.md` (`9b0c6ae`) | "Explains part of the gap" |
| 11b | Demonstration-count curve (dev) | `stage11b_prereg.md` (`f01446a`); addenda `stage11b2_prereg.md` (`9616ad9`), `stage11b3_prereg.md` (`32e4c38`, `a9dd63e`) | `stage11b.md` (`91b6b4f`, `f3666c6`, `b486ae4`) | Demonstration count was the bottleneck up to about 5,000 |
| 12 | Hosted and local untrained models, text and image (dev) | `stage12_prereg.md` (`1e51527`) | `stage12.md` (`d02eb96`) | Reference lines; no thresholds |
| 13 | On-device Apple Foundation Models (dev, 100 rooms) | `stage13_prereg.md` (`0ac7302`); addenda `750c791`, `fd713ef`, `d604caa` | `stage13.md` (`817df4f`, `47db55d`, `fb9db09`, `a9161db`) | Reference line |
| 14 | Rule variants (dev) | `stage14_prereg.md` (`06091fc`) | `stage14.md` (`44efb15`) | See table above |
| — | One move of help (dev) | `help_test_prereg.md` (`1f36345`) | `help_test.md` (`1e3f909`) | Both pre-set criteria answered "no" |

Seed ranges and which are locked: `reports/seeds.md`. Checkpoints and caches kept outside the repository: `reports/checkpoints.md`.

## Repository layout

| Path | Contents |
|---|---|
| `probe/` | Environment-to-text, demonstration dumps, fine-tuning, closed-loop runners, one module per stage |
| `reports/` | One report and one declaration per stage (Korean), raw per-room results (`reports/stageN/*.json`) |
| `reports/summary_four_tasks.md` | The four tasks side by side, prior work, later stages (Korean; an English version is planned) |
| `tools/small_policy/` | The 67k-parameter CNN: training, the demonstration-count curve, the rule variants |
| `godot/` | A small Godot 4.7 game: replay of the model's choices, a semi-automatic "drive" mode and a puzzle mode built from rooms the weakest policy cannot finish alone (`godot/drive/PUZZLE.md`) |
| `README.ko.md` | The original Korean README with every stage and command. Where reports, code comments or error messages say "README", they mean that file |

## Reproducing

Experiments ran on WSL Ubuntu with one RTX 5080; the CNN and the game engine run on CPU.

```bash
uv venv ~/babyai-laya-venv --python 3.12
VIRTUAL_ENV=~/babyai-laya-venv uv pip install -r requirements.txt     # minigrid==3.2.0, laya==0.4.31
PY=~/babyai-laya-venv/bin/python
$PY -m probe.dump_demos --seeds 0-999 --out data/gotolocal_train.jsonl      # expert demonstrations
$PY -m probe.finetune data/gotolocal_train.jsonl --seed 0                   # about 5 minutes
$PY -m probe.closed_loop --policy model --model ~/babyai-laya-ft/gotolocal-s0 --name laya-s0
```

Per-stage commands are in [README.ko.md](README.ko.md) and at the top of each `probe/stageN.py`. Demonstration dumps and checkpoints are not in git; dumps are regenerated from seeds. For the published weights see [Licence](#licence).

## Game

A browser build is at <https://mokaflow.itch.io/babyai-laya-an-ai-in-the-room>. The model that drives in real time in the browser is the small CNN, not Laya; Laya appears as recorded replays. The baby and toy sprites are AI-generated images (sources in `godot/drive/baby/README.md` and `godot/drive/toys/README.md`).

## Licence

This repository is MIT-licensed; see [LICENSE](LICENSE).

Fine-tuned weights are released under Apache-2.0, the licence of the upstream checkpoint they are derived from. **Download links: _to be filled in when the upload finishes._** The published set is one checkpoint per task at 1,000 demonstrations (`gotolocal-s0`, `pickupdist-s0`, `putnext-s0`) plus `gotolocal-n5000-s0`; the other ~36 checkpoints are reproducible from the seeds and commands here and are not uploaded.

Third-party components:

- **MiniGrid 3.2.0** — Apache-2.0 according to the repository's `LICENSE` file; its package metadata says MIT. Not redistributed here; the demonstrations and room layouts in this repository were generated with it.
- **Laya** checkpoint and SDK — Apache-2.0 (model card). **ModernBERT** — Apache-2.0. The weights we publish are modified derivatives; the upstream notices travel with them.
- **Godot Engine** — MIT; the web build ships its `licenses.txt`.
- The baby and toy sprites in the puzzle mode are AI-generated images; see `godot/drive/baby/README.md` and `godot/drive/toys/README.md`.

## Language

Working notes, reports and declarations are in Korean. This page, the tables, the code, the commit messages and the raw result files are in English or language-independent.
