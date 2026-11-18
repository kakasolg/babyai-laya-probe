# babyai-laya-probe

한국어: [README.ko.md](README.ko.md) — the original working README with every stage and command.

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
| Apple Foundation Models, on-device (100 rooms) | 12 | 85 (30) |

These are reference lines from one task description that was written for one of the models; they are not a fair ranking of the models. Image input did not help in this setting.

Apple Foundation Models returns an answer but no scores, so "the best action not yet tried" is not available. For that line the same rule is applied by asking again with the already-tried actions removed from the options, together with removing "forward" when the cell ahead is blocked (`reports/stage15.md`, setting A3, first 100 development seeds; 0 rooms broken). A separate step-level check (stage 15c) asked the model to write a short reason before the action: forward into a blocked cell fell from 87.2 % to 30.9 % of blocked steps, but agreement with the expert fell from 62.5 % to 57.2 %, and some written reasons were made up.

### Smaller findings

- **One move of help** (`reports/help_test.md`): on the 23 rooms the fine-tuned model fails, inserting the expert's next action once rescues 6; inserting the best of the three actions rescues 16. Help works when it moves the agent to a place the model can continue from, not when it is merely "the right direction".
- **Numerical precision** (`reports/precision_check.json`): bf16 and fp32 inference pick a different top action on 1–2 of 1,625 steps, all near-ties, and change one room out of 300. Read any result that passes or fails a threshold by one or two rooms accordingly.

## Prior work

### LID (Li et al., NeurIPS 2022)

*Pre-Trained Language Models for Interactive Decision-Making* ([arXiv:2202.01771](https://arxiv.org/abs/2202.01771)) is the closest prior work: it fine-tunes GPT-2 by behaviour cloning on a text rendering of the same 7×7 BabyAI view and predicts the next action. Its Table 1, read from v4 of the paper:

| Task | Method | 100 | 500 | 1K | 5K | 10K |
|---|---|---|---|---|---|---|
| GoToLocal | BabyAI-Ori | 55.9 | 84.3 | 98.6 | 99.9 | 99.8 |
| GoToLocal | **LID-Text** | **64.6** | **97.9** | **99.0** | 99.5 | 99.5 |
| PickupLoc | BabyAI-Ori | 28.0 | 58.0 | 93.3 | 97.9 | 99.8 |
| PickupLoc | **LID-Text** | **28.7** | **73.4** | **99.0** | 99.6 | 99.8 |
| PutNextLocal | BabyAI-Ori | 14.3 | 16.8 | 43.4 | 81.2 | 97.7 |
| PutNextLocal | **LID-Text** | **11.1** | **93.0** | **93.2** | 98.9 | 99.9 |

Ours, model alone, at the same demonstration counts (development seeds; held-out range in brackets):

| Task | 100 | 500 | 1K |
|---|---|---|---|
| GoToLocal | 52.6 % | 87.1 % | 91.0–92.7 % [87.3–88.0 %] |
| PutNextLocal | 3.8 % | 78.7 % | 81.7–85.3 % [84.3–86.0 %] |

**We are below LID-Text at every count we can compare.** Against `BabyAI-Ori` — LID's re-run of the original BabyAI architecture, which has an LSTM memory — we are below on GoToLocal and well above on PutNextLocal (78.7 % vs 16.8 % at 500; about 84 % vs 43.4 % at 1,000).

What differs, from the paper:

- **History.** LID conditions on `(goal, history, observation)`, the history being previous actions written out as text. Our input has no history; stage 11a adds the last four actions and raises GoToLocal from 271.3 to 280.7 of 300 — not enough to close the gap.
- **Observation text.** LID turns all 7×7 cells into one long sentence ("purple ball", "grey wall", "open door"). Ours lists only the visible objects and the distance to the nearest wall in three directions — shorter and more abstracted.
- **Evaluation.** 500 episodes per task on BabyAI 1.1's standard test data; ours is 300 layouts per task from our own seed ranges. The BabyAI table gives no per-seed spread.
- **Tasks.** LID uses `PickupLoc`; we use `PickupDist`. Different levels.
- **Model.** "a standard pre-trained language model, GPT-2", AdamW at 1e-5 on one 32 GB GPU. The variant (124M / 355M / …) and the step limit per episode are not stated. Ours is a 421M encoder with a choice head.
- **Ablations.** LID's No-Pretrain / No-Seq / No-FT ablations are on VirtualHome, not BabyAI. Its BabyAI ablation (Appendix A) compares the text encoding against a convolutional encoding of the same grid.

One caution we cannot resolve: LID's `BabyAI-Ori` at 1,000 demonstrations (GoToLocal 98.6 %) is far above what the BabyAI 1.1 paper reports for small models at much larger demonstration counts. The two cannot both describe the same measurement, so neither is a leaderboard our numbers slot into.

### Other work

- BabyAI (Chevalier-Boisvert et al., 2019) and BabyAI 1.1 (Hui et al., 2020) report demonstration requirements for small recurrent models; BabyAI-Text / GLAM (Carta et al., 2023), BALROG (2024) and Gato (2022) run language or generalist models on BabyAI under other training signals.
- The executor rule belongs to a known family (state–action tabu exploration, loop detection in agents). We did not find a published measurement of this exact rule with paired "previously solved rooms broken" counts; that is a statement about our search, not a claim of novelty.
- Step-by-step human correction of a BabyAI policy also has prior tools (e.g. RLHF-Blender).

## Limits

- **We are below the closest prior work at equal demonstration counts** (see [Prior work](#prior-work)); nothing here is a sample-efficiency result.
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

Stage 13 and 15 reach the on-device model through a small signed macOS command-line app. That app lives in **Kortex, a separate personal project of the author's that is not part of this work and is not public**; running BabyAI through it was one test inside it, and nothing in this repository depends on it. Any signed macOS binary that answers a JSON request per step would do instead — `probe/stage13.py` takes the binary's path as an argument.

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

Per-stage commands are in [README.ko.md](README.ko.md) and at the top of each `probe/stageN.py`. Demonstration dumps and checkpoints are not in git; dumps are regenerated from seeds. Fine-tuned weights are available on request; see [Licence](#licence).

## Game

A browser build is at <https://mokaflow.itch.io/babyai-laya-an-ai-in-the-room>. The model that drives in real time in the browser is the small CNN, not Laya; Laya appears as recorded replays. The baby and toy sprites are AI-generated images (sources in `godot/drive/baby/README.md` and `godot/drive/toys/README.md`).

## Licence

This repository is MIT-licensed; see [LICENSE](LICENSE).

**Fine-tuned weights are not uploaded, but you may have them — just ask** (open an issue). They are a derivative of the upstream checkpoint and are shared under its licence, Apache-2.0. They are not hosted because every checkpoint here is reproducible from the seeds and commands in this repository: one fine-tuning run takes about 5 minutes on a single consumer GPU for a 1,000-demonstration task (see [Reproducing](#reproducing)).

Third-party components:

- **MiniGrid 3.2.0** — Apache-2.0 according to the repository's `LICENSE` file; its package metadata says MIT. Not redistributed here; the demonstrations and room layouts in this repository were generated with it.
- **Laya** checkpoint and SDK — Apache-2.0 (model card). **ModernBERT** — Apache-2.0. The weights we publish are modified derivatives; the upstream notices travel with them.
- **Godot Engine** — MIT; the web build ships its `licenses.txt`.
- The baby and toy sprites in the puzzle mode are AI-generated images; see `godot/drive/baby/README.md` and `godot/drive/toys/README.md`.

## Language

Working notes, reports and declarations are in Korean. This page, the tables, the code, the commit messages and the raw result files are in English or language-independent.
