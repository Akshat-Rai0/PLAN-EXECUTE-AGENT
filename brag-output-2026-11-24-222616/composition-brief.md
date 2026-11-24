# Hyperframes Composition Brief: Plan-and-Execute Agent

## Objective
Create a short launch-style brag video for Plan-and-Execute Agent — a LangGraph agent that plans before it acts.

## Output
- Composition directory: `brag-output-2026-11-24-222616/composition/`
- Rendered video: `brag-output-2026-11-24-222616/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 21 seconds (explicit scene plan sums to 21.0s)

## Source Material
- Project root: `/Users/bipinkumarrai/Desktop/EVERYTHING/CODING PROJECTS/PORTFOLIO PROJ/plan-execute-agent-scaffold`
- Primary files read: `index.html` (landing page), `README.md`, `frontend/package.json`
- Product name: Plan-and-Execute Agent
- Tagline / strongest claim: "An agent that thinks first, then acts." / "ReAct guesses. This plans."
- Key UI or visual moment to recreate: the five-step loop (plan → executor → approval gate → check_new_info → synthesize) as numbered circles, plus a chat/debugger-style run trace (goal typed → plan steps appear → approval gate interrupts → replan → final answer)
- Copy that must appear verbatim:
  - "ReAct guesses." / "This plans."
  - "Plan-and-Execute Agent"
  - "Think first, then act."
  - Node names: `plan_node`, `tavily_search_node`, `reason_node`, `check_new_info_node`, `synthesize_node` (and one high-risk node like `shell_node` or `browser_use_node` for the gate)
  - Stats: `19+ LangGraph nodes` · `12 tools` · `28 golden goals` · `136 tests`
  - Footer: `OPEN SOURCE · LANGGRAPH · FASTAPI · REACT`
  - Goal example typed in chat: `who won the latest f1 race?`

## Creative Direction
- Tone preset: `deadpan`
- Creative direction: "editorial infra-project film — serif headlines, mono labels, long holds, one dry joke"
- Interpretation: 4 scenes, long settled holds, slow entrances, minimal motion after landing; text is the visual; music is a barely-there bed; almost no SFX.
- Angle: open on the quiet accusation against the ReAct baseline, let the product answer with total calm; the joke is restraint — an agent that pauses to ask permission and rewrites its own plan.
- Hook: paper-white frame, one serif line "ReAct guesses." fades in slowly with a mono caption `BASELINE · NO PLAN · NO MAP`.
- Outro / punchline: "Plan-and-Execute Agent" in Fraunces with italic "Think first, then act.", small mono footer, long hold.
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals (no particles, no gradients-as-decoration, no waveform visualizers)
  - Confetti / celebration energy / loud transitions
  - Anything that breaks the editorial paper-and-ink look of the source site

## Visual Identity
- Background: paper `#fbfaf6`; ink surfaces `#1a1917`, `#f8f6f0`; rules `#e2e0d8`
- Text: ink `#1a1917`, secondary `#4a4843`, muted `#8a8880`
- Accent: blue `#2b5f8a`, rust italic `#c84b2f` (site uses `#c6dced` on dark / accent blue in serif italics on light — use blue `#2b5f8a` for the italic accent on paper, matching `h2 em`), green `#2a6b45`, amber `#9a5c0a`, purple `#5c3b8a`
- Display font: Fraunces (serif, light weights + italic) — download woff2 into `assets/fonts/`
- Body font: DM Sans; mono labels: DM Mono — download woff2 into `assets/fonts/`
- Visual references from the project: hero serif headline treatment, mono uppercase section labels with a trailing rule (`SECTION-LABEL ——`), numbered circle loop steps in ink/blue/amber/green/purple, pill tags, the ink hero card with pills, the site's stats grid

## Storyboard
Use the storyboard in `brag-output-2026-11-24-222616/brag-plan.md` as the creative contract.

Scene summary:
1. The accusation — 0–4.0s — paper field, serif "ReAct guesses." + mono caption `BASELINE · NO PLAN · NO MAP`; long hold
2. The answer — 4.0–9.5s — serif "This plans." (italic accent) + ink hero-style card with mono label `PLAN-AND-EXECUTE AGENT`, sub-line, and quiet pills (`HITL GATES` `SANDBOXED` `DYNAMIC TOOLS`); elements arrive ~0.6s apart then hold
3. The working agent — 9.5–16.5s — recreated chat/debugger panel: goal `who won the latest f1 race?` appears, five plan steps appear sequentially with status dots, a high-risk step pauses behind an amber `HUMAN APPROVAL REQUIRED` gate chip then resolves approved, `check_new_info_node` fires one amber `replan` tick, `synthesize_node` delivers a short final answer block
4. Receipts — 16.5–21.0s — four stat pairs arrive staggered (`19+ LangGraph nodes`, `12 tools`, `28 golden goals`, `136 tests`), then name card "Plan-and-Execute Agent" + italic "Think first, then act." + mono footer `OPEN SOURCE · LANGGRAPH · FASTAPI · REACT`; long hold

## Audio
- Audio role: sparse professional accents over a barely-there bed — deadpan restraint
- Audio arc: low steady bed throughout; two or three dry procedural cues; gentle fade-out at the end
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` — copy to `composition/assets/music/`
- Music treatment: `data-volume` ≈ 0.15, start ~0.5s in, fade out over final ~1.5s
- Music cue guidance: bundled preset exists — `.agents/skills/brag/assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json` (~110 BPM). Strong cues: 8.74s, 13.11s, 17.47s, 18.56s, 22.93s (relative to track start; the video is 21s so cues at 17.47/18.56 are usable, 22.93 is beyond). At most 1-2 cue locks; the plan-steps sequence in scene 3 may sit near a beat around 9-10s; optional final emphasis near 17.5-18.5s for the name card. Restraint wins over sync.
- Audio-reactive treatment: none — deadpan stays still
- Audio-coupled moments:
  - Scene 3 approval gate — one muted, serious click as the gate appears/resolves
  - Scene 3 plan-step arrivals — silent or near-silent (machine working, not foley)
  - Scene 4 name card — one soft bell (`impact/impactBell_heavy_000.ogg` at low volume) under the name landing
  - Scene 2 card entrance — optional single soft `interface/drop_001.ogg` tick
- SFX selection guidance: very sparse; prefer low/high-frequency-safe files; deadpan = restraint. Check `.agents/skills/brag/assets/sfx/sfx-analysis.md` before picking; copy chosen files into `composition/assets/sfx/...`
- Exact SFX choice: Hyperframes chooses filenames, timestamps, density, volume after the animation exists
- Audio files: copy music + any selected SFX into `composition/assets/`

## Hyperframes Instructions
Load the composition-building Hyperframes skills — `hyperframes` (composition contract + `data-*` timing, `references/format.md`; motion, eases and seek-safe keyframes in `references/motion.md`; look in `references/look.md`), `hyperframes-registry` (ready-made effects, transitions, titles), `media-use` (music, SFX, audio-reactive data), and `hyperframes-cli` (lint/check/render). /brag is its own workflow: skip the `hyperframes` storyline step: don't read `references/types/*` or `references/story.md`, don't propose storylines, and don't write a `SPEC.md`. The brag plan and composition brief replace them, including the LOOK line `references/look.md` asks for. Also skip its `usage`, `history`, `feedback` and REVIEW.md steps; `check` is brag's gate. Do not route into its generic launch-video workflow. Prefer native Hyperframes conventions over anything in `/brag`.

Requirements:
- Show at least one real UI, copy, or visual element from the source project (the loop nodes, hero card, stat numbers, serif/mono typography are all real project material).
- Keep all text readable in the final render — honor the reading-time floors: every line holds long enough to read.
- Keep the video within 15-25 seconds (target 21s).
- Include the planned music/SFX layer (deadpan restraint applies to density, not presence).
- Treat `/brag` audio notes as guidance, not a fixed cue sheet. Choose SFX after the visual animation exists.
- Treat music cue metadata as optional timing hints — 1-2 cue locks max; readability first.
- Use SFX to support motion and interaction; restraint when the edit is already quiet.
- When music is present, audio-reactive treatment is `none` for this video (deadpan) — do not wire RMS modulation.
- Use local assets for audio and fonts (`assets/fonts/*.woff2`, `assets/music/*.mp3`, `assets/sfx/...`); paths relative to `composition/`.
- Run `npx hyperframes check` before render — it is brag's single gate.
- Keep creation and rendering local.
