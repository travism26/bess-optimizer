# Turning PR Review Into Deliberate Learning

Research date: 2026-08-01. Written for Travis, who runs bess-optimizer through an agentic pipeline (spec to agent-written PR to review to merge) and wants his review time to double as learning time instead of a rubber stamp.

## TLDR

- The interactive-HTML-diff-with-quiz pattern traces to Geoffrey Litt (Design Engineer, Notion), from his AI Engineer conference talk "Understanding is the New Bottleneck" and blog post published 2026-07-02 (geoffreylitt.com). His `/explain-diff` skill produces the exact four sections your installed skill uses: background, intuition, literate-diff code walkthrough, five-question quiz. Attribution confidence: high, this is a near-exact match, not a coincidental convergence.
- Litt's quiz idea explicitly borrows from Andy Matuschak's spaced-repetition "mnemonic medium" research (Quantum Country, orbit), and Simon Willison amplified and endorsed the talk on his own blog the same day, framing the risk as "cognitive debt." Willison separately runs a related but distinct pattern, "interactive explanations" / "linear walkthroughs," in his own Agentic Engineering Patterns guide, which predates Litt's talk (published starting Feb 2026) and looks like an independent, parallel thread rather than the same lineage.
- The strongest evidence-backed techniques for learning from AI-written code, beyond the quiz, are: predict-before-reading (rooted in the peer-reviewed PRIMM pedagogy, Sentance & Waite, King's College London), teach-back/Feynman explanation (meta-analysis effect size g=0.55 for self-explanation), and small-batch review discipline (defect detection rate must exceed production rate, or you miss things systematically, not occasionally).
- Reviewer checklists specific to AI-generated code converge on the same four failure modes across multiple independent sources: scope creep (quiet refactors bleeding outside the stated change), overfitting to tests (tests pass but don't verify the actual requirement), plausible-but-wrong idioms (looks right, structurally smooth, semantically off), and missing edge cases (happy path is well-represented in training data, error handling is not).
- For a 30-60 minute solo budget, the highest-leverage combo is: generate the explain-diff HTML first (5-10 min, already automated), predict the quiz answers before reading the code walkthrough (5 min), read the literate diff against a four-item AI-specific checklist (15-20 min), then write a 3-5 sentence teach-back summary from memory (5 min). Anki/spaced-repetition card generation is the first thing to cut under time pressure, it's the highest-effort, most delayed-payoff technique of the set.

## Attribution Findings

### The likely origin: Geoffrey Litt, "Understanding is the New Bottleneck"

Geoffrey Litt is a design engineer at Notion (previously known for work on malleable software and local-first tools). In mid-2026 he gave a talk at the AI Engineer conference and published a written/slide version on his own blog.

- Blog post: [Understanding is the new bottleneck](https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck.html), published 2026-07-02.
- Talk video: [Understanding is the new bottleneck, Geoffrey Litt, Notion, AI Engineer](https://www.youtube.com/watch?v=WkBPX-oDMnA), roughly 19 minutes, presented at the AI Engineer conference, July 2026.
- X/Twitter thread (same content, thread form): starts at [x.com/geoffreylitt/status/2072522251300409556](https://x.com/geoffreylitt/status/2072522251300409556). The literate-diff explanation is at [status/2072522296947011960](https://x.com/geoffreylitt/status/2072522296947011960), and the skill release tweet is at [status/2072522312856039461](https://x.com/geoffreylitt/status/2072522312856039461) ("Here's the skill if you want it: two variants that output either HTML or Notion page").
- The skill itself, as a gist: [gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524](https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524) (this URL returned a 403 to automated fetch during this research; content below is reconstructed from search-indexed excerpts and comments, treat exact wording with a little more caution than the blog post).
- Also indexed as a skill listing at [skills.rest/skill/explain-diff-html](https://skills.rest/skill/explain-diff-html).

**Why this is almost certainly the source of the installed skill.** The `/explain-diff` skill Litt describes has the identical four-section structure as `/Users/rickjms/code/bess/.claude/skills/explain-diff-html/SKILL.md`: background (with an explicit beginner-vs-already-familiar split), intuition (concrete/toy examples, diagrams), a literate/ordered code walkthrough (Litt's term: "literate diff," described as "structured as prose, walking through the changes in a sensible order, with surrounding explanation and embedded code snippets, faster to review than a raw diff"), and a five-question, medium-difficulty, interactive multiple-choice quiz at the end. Litt's personal rule, quoted across multiple sources: "I won't send code to others until I can pass the quiz." That is the same quiz-as-gate logic embedded in the installed skill's design intent. The scale problem he opens with, a real PR of 372 files changed, 55,219 lines added, 3,027 removed, is the framing for why raw diff review stopped working and literate/interactive explanation became necessary.

Litt says explicitly that the quiz idea draws on **Andy Matuschak**'s research into spaced repetition and "why books don't work" (mnemonic medium, Quantum Country, the Orbit project). Matuschak's own writing on this: [andymatuschak.org/prompts](https://andymatuschak.org/prompts/) ("How to write good prompts: using spaced repetition to create understanding") and [andymatuschak.org/primer](https://andymatuschak.org/primer/). This is a real, citable intellectual lineage, not a stretch: Litt is explicitly building a lightweight, one-shot version of Matuschak's "test yourself as you read" idea, applied to a PR instead of an essay.

**Simon Willison** covered Litt's talk the same day it went up: [simonwillison.net/2026/Jul/2/understand-to-participate](https://simonwillison.net/2026/Jul/2/understand-to-participate/). Willison's framing: the talk "particularly resonated" with him, and he ties it to his own recurring theme of **cognitive debt**, understanding drifting away from how the code actually works even though it runs and passes tests. He quotes Litt directly: "You can learn what the agent is doing to make sure you can be an active participant in the creative process... You need a rich set of concepts in your mind to think creatively and fluently about how to move something forward."

Important nuance: Willison runs a **separate, earlier** pattern in his own "Agentic Engineering Patterns" guide (a chaptered, evergreen guide, not a dated blog post), which started publishing 2026-02-23, roughly four and a half months before Litt's talk: [simonwillison.net/guides/agentic-engineering-patterns/interactive-explanations](https://simonwillison.net/guides/agentic-engineering-patterns/interactive-explanations/). Willison's "interactive explanations" chapter is about asking an agent to build an animated, playable visualization of a specific algorithm (his example: watching a Rust word-cloud placement algorithm spiral outward step by step, with pause/speed/frame controls), which is closer to Litt's separate "throwaway micro-worlds" idea (timeline scrubbers, migration visualizers) than to the quiz-and-literate-diff pattern specifically. Willison's guide also has a "linear walkthroughs" chapter, structured, step-by-step, line-by-line explanations using real code snippets, which is close in spirit to Litt's "literate diff" but predates it in publication.

**Verdict on attribution**: Litt is the clear originator of the specific pattern installed in this repo (background, intuition, literate-diff walkthrough, five-question interactive quiz, single self-contained HTML file). Willison is a documented, independent-but-related influence and amplifier, not the originator of this exact four-section shape, and Matuschak is the deeper intellectual root for the quiz-as-retrieval-practice mechanism specifically. I found no evidence connecting Steve Krouse or Val Town to this pattern; Val Town's PR-related work in the search results was about a GitHub-Copilot-style PR/fork feature on the Val Town platform itself, unrelated to reviewer-learning workflows. Treat any Val Town connection as unconfirmed / likely not applicable.

## Technique Catalog

Each entry: what it is, source/evidence, effort, what it teaches, when to skip it.

### 1. Interactive HTML diff explanation with quiz (Litt's pattern, already installed)

**What it is.** An agent generates a single self-contained HTML file with four sections (background, intuition, code walkthrough, five-question multiple-choice quiz with immediate feedback) for a given diff or PR. You read it instead of, or alongside, the raw diff.

**Source.** Geoffrey Litt, geoffreylitt.com, 2026-07-02; installed at `/Users/rickjms/code/bess/.claude/skills/explain-diff-html/SKILL.md`.

**Effort.** Near zero to generate (agent does it, 1-3 minutes of agent time). Reading it: 10-20 minutes depending on PR size.

**What it teaches.** Structured context you'd otherwise have to reconstruct yourself (why this code exists, what it replaces), plus a forced comprehension check via the quiz. The quiz is the load-bearing part, without it this degrades into "nicely formatted documentation you skim and forget," which does not create the retrieval effort that produces retention.

**When to skip.** Trivial PRs (one-line config change, dependency bump, pure rename). Also skip generating a fresh one for a PR that's a small delta on a PR you already fully explained-and-quizzed recently, in that case just diff against your last understanding.

### 2. Predict-before-reading ("guess the diff from the spec")

**What it is.** Before opening the PR at all, read your own spec/prompt and write down (even just mentally, better on paper) what you expect the diff to touch: which files, what the core data-flow change is, what the trickiest edge case will be. Then open the PR and compare.

**Source.** This is not, as far as I can confirm, a named practitioner ritual specific to AI PR review (I could not find one, e.g. no Krouse/Litt/Willison post that names this exact move). It is, however, strongly grounded in real pedagogy: **PRIMM** (Predict, Run, Investigate, Modify, Make), a peer-reviewed instructional model from Sue Sentance and Jane Waite at King's College London, whose first step is exactly "look at code and predict what it does before running it," documented at [computingeducationresearch.org/projects/primm](https://computingeducationresearch.org/projects/primm/) and validated in classroom studies showing PRIMM-taught students outperform students who write code without first predicting/reading it. Applying "predict" to "predict what the agent did from the spec, before reading" is a direct, well-supported analogy, just not one I found already packaged as an AI-PR-review technique by name.

**Effort.** 3-5 minutes, no tooling needed.

**What it teaches.** This is the highest-value-per-minute technique on this list because the gap between your prediction and reality is exactly the thing you didn't already know, either about the codebase, about the agent's approach, or about your own spec being underspecified. A large gap on "what files changed" often means your mental model of the codebase's module boundaries is stale. A large gap on "how it handles the edge case" often means the spec didn't actually pin that down, which is a spec-writing lesson, not a code-reading lesson.

**When to skip.** When the spec was so mechanical there's only one reasonable implementation (e.g., "rename this field everywhere"). Also low-value on PRs above roughly 500 changed lines, prediction accuracy craters and the exercise stops being diagnostic.

### 3. Teach-back / Feynman technique, with the agent as grader

**What it is.** After reviewing, write (don't just think) a plain-language explanation of the change as if to a new teammate, then ask an AI agent, ideally a fresh context that has read the actual diff, to grade the explanation for gaps or inaccuracies.

**Source.** The Feynman technique itself is well-documented pedagogy (choose a concept, explain in plain language, find where the explanation breaks, refine); a relevant meta-analysis found prompting learners to self-explain improves learning outcomes with a mean effect size of g=0.55 (a solidly medium-to-large effect in education research), summarized at [growthengineering.co.uk/feynman-technique](https://www.growthengineering.co.uk/feynman-technique/) and applied to code specifically at [freecodecamp.org](https://www.freecodecamp.org/news/how-to-understand-complex-coding-concepts-better-using-the-feynman-technique/). The "agent grades it" specific step wasn't found packaged as a named ritual by a specific practitioner in this research; it is a natural, low-risk extension of a well-evidenced technique, treat the grading-agent step as an editorial recommendation, not an attributed practice.

**Effort.** 5-10 minutes to write, near-zero to have an agent grade it.

**What it teaches.** Writing surfaces the difference between "I recognize this code as correct-looking" (recognition, weak) and "I can generate a correct account of why it's correct" (recall/construction, strong). This is the single best lever against the specific failure mode Travis flagged, merging too fast because a diff looks plausible.

**When to skip.** Skip the write-up for genuinely small, low-risk PRs; a one-sentence spoken summary to yourself is enough. Don't skip it for anything touching core optimization logic (LP formulation, rolling horizon, ancillary-services co-optimization) given what this repo does.

### 4. Small-batch / bounded review (defect-detection-rate discipline)

**What it is.** Cap the size of what you review in one sitting, and treat "PR too big to review in the time box" as a signal to ask the agent to split it, rather than a reason to skim faster.

**Source.** Bryan Finster, [AI Broke Your Code Review, Here's How to Fix It](https://bryanfinster.substack.com/p/ai-broke-your-code-review-heres-how): applies a Nyquist-Shannon sampling-theorem framing, "your defect detection rate must exceed your production rate, or you will miss problems not occasionally but systematically." Also echoed by Youngju Kim, [How to Review AI-Generated Code](https://www.youngju.dev/blog/culture/2026-05-14-reviewing-ai-generated-code-verification-loop-ai-slop-deep-dive-guide-2026.en): "reviewability inversely correlates with diff size, demand smaller PRs," and by [codeongrass.com](https://codeongrass.com/blog/how-to-review-ai-generated-code-faster-than-you-can-read/), which flags anything over roughly 200 lines for a "small fix" as worth a second look.

**Effort.** Zero extra review time; this is a policy on how you commission work from the agent, not a review-time activity. The cost shows up upstream, in how you scope specs.

**What it teaches.** Indirectly, this is what makes every other technique on this list actually work within a real time box. It's a precondition, not a standalone learning technique.

**When to skip.** Never skip the principle, but the threshold is judgment-dependent. For a solo project you already understand deeply, your effective bandwidth per PR is higher than for a team review of unfamiliar code.

### 5. AI-generated-code-specific reviewer checklist

**What it is.** A short, fixed checklist applied on every PR, targeting failure modes that are disproportionately common in agent-written code rather than human-written code.

**Source, converging across multiple independent write-ups:**
- Scope creep: "a model change that quietly refactors how that model is used in three other places," [verygood.ventures](https://verygood.ventures/blog/code-review-ai-generated-code/) and [Bryan Finster](https://bryanfinster.substack.com/p/ai-broke-your-code-review-heres-how).
- Overfitting to tests / fake tests: "tests that pass but verify nothing," caught by deliberately breaking the implementation and confirming the test fails, [youngju.dev](https://www.youngju.dev/blog/culture/2026-05-14-reviewing-ai-generated-code-verification-loop-ai-slop-deep-dive-guide-2026.en).
- Plausible-but-wrong idioms: "the surface is smooth, appropriate naming and structure, yet the logic contains subtle errors," same source; also framed as code that "looks idiomatic while being detached from the ticket, the architecture, or the operational constraints of the system" in the ShiftAsia guide.
- Missing edge cases: "AI models commonly implement happy-path steps correctly but fail on error cases, the happy-path logic is well-represented in training data, edge-case handling is not," [ShiftAsia](https://shiftasia.com/column/how-to-review-ai-generated-code-the-complete-developers-guide/).
- Delete-line test for bloat: "if removing a line breaks nothing, it's unnecessary," a fast heuristic for AI-generated verbosity/dead abstraction, [youngju.dev](https://www.youngju.dev/blog/culture/2026-05-14-reviewing-ai-generated-code-verification-loop-ai-slop-deep-dive-guide-2026.en).

**Effort.** 5-10 minutes if it's a real fixed checklist you run through (four to five yes/no items), not an open-ended "review carefully."

**What it teaches.** This is a bug-catching technique first and a learning technique second, but the "why did the agent do it this way" question, when you catch a checklist item, is exactly the moment worth pausing on. Every source above independently converges on the same four failure categories, which is a strong signal these are the real, recurring blind spots for agent-written code specifically (as opposed to generic code review advice).

**When to skip.** Never fully skip; this is the cheapest, highest-confidence item on the list. Compress it to a mental pass rather than written notes on trivial PRs.

### 6. Spaced repetition / Anki-style cards from merged PRs

**What it is.** After a PR teaches you something non-obvious (a gotcha in the LP formulation, a subtlety in how rolling-horizon state carries over), turn it into one or two spaced-repetition cards you review later (Anki, or a lightweight equivalent).

**Source.** Grounded in Matuschak's spaced-repetition research (see above) and general Anki-for-developers practice, e.g. [dasroot.net, Spaced Repetition for Technical Learning](https://dasroot.net/posts/2025/12/spaced-repetition-for-technical/), which documents AnkiConnect for programmatic card creation from code but, notably, has no specific pattern for generating cards from PRs or diffs; that specific pairing (PR to flashcard) was not found already implemented by a named practitioner in this research. Treat this as a reasonable extrapolation, not an attributed workflow.

**Effort.** 5-10 minutes per PR to write good cards (the hard part, per Matuschak's own writing on why writing good prompts is hard), plus a standing but small daily review habit outside the PR-review time box entirely.

**What it teaches.** Long-term retention of the handful of facts about your own system that are genuinely easy to forget and expensive to relearn (a subtle invariant, a non-obvious reason a constraint is modeled the way it is). This is a compounding technique, weeks and months, not something that pays off inside a single review session.

**When to skip.** This is the first thing to cut under time pressure. It has real value but a delayed payoff and a real ongoing cost (maintaining a review habit outside of PR review). Only worth it for the small subset of PRs that taught you something you'd be annoyed to have to re-derive in three months.

### 7. Guided re-implementation kata (rewrite one function cold)

**What it is.** Pick one meaningfully complex function or module from the merged PR, close the diff, and re-implement it from your own understanding, then diff your version against the agent's.

**Source.** No practitioner blog was found describing this specifically for AI-generated PRs by name. It's grounded in classic refactoring-kata practice (Emily Bache's katas, e.g. [understandlegacycode.com](https://understandlegacycode.com/blog/efficiently-practice-refactoring-katas/)) and general deliberate-practice theory, applied here by direct analogy: the kata target is "code someone else wrote" rather than a canned exercise, which is a bigger ask than a typical kata since it isn't pre-scoped for practice. One tangential but relevant observation from the bioinformatics-tooling space, [rewrites.bio](https://rewrites.bio/): "AI-generated implementations are fluent and fast, but confidently wrong in ways that are easy to miss," which is exactly the class of error this kata is designed to surface, since you can't paper over a gap in understanding while actually writing the code yourself.

**Effort.** 20-40 minutes. By far the most expensive technique on this list.

**What it teaches.** The deepest possible understanding, because you can't fake writing working code. It also directly tests whether the agent's approach was actually necessary, sometimes you'll produce something simpler and realize the agent over-engineered it (a real, common AI-code failure mode independently), or you'll get stuck exactly where the agent's approach was genuinely clever, which is itself useful information.

**When to skip.** Almost always, under a 30-60 minute budget. Reserve for PRs touching the parts of the system you most need to own deeply (for this repo, likely the core LP optimizer and the co-optimization logic), at a cadence of maybe one per week or per milestone, not per PR.

### 8. Annotation-first review

**What it is.** Before reading top to bottom, skim the whole diff once and drop short annotations (questions, "why here," "expected this file too") at specific lines, then do a second full pass to actually answer your own annotations.

**Source.** Well-documented as a general code-review best practice (e.g. [SmartBear](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/), [GitLab review guidelines](https://docs.gitlab.com/development/code_review/)), and there are now AI-review-specific tools built around this loop (annotate, feed straight back into an agent session), e.g. the Hacker News-featured [Revdiff](https://news.ycombinator.com/item?id=47742437), a TUI diff reviewer with inline annotations built specifically for AI-agent-produced diffs. Not a single named originator; this is a converged-upon general practice, adapted for the AI-PR context by recent tooling.

**Effort.** Adds roughly 5 minutes on top of a normal read (the skim pass is fast).

**What it teaches.** Separates "I noticed something odd" from "I resolved it," which prevents the common failure of noticing a red flag mid-read and then forgetting to come back to it once the narrative flow of the diff carries you past it. Minor value as a standalone learning technique, real value as a rigor technique that keeps techniques 2, 3, and 5 honest.

**When to skip.** Skip as a separate pass for small PRs, the two-pass structure only pays off once a diff is big enough that you'd otherwise lose track of open questions.

## Recommended 45-Minute PR Review Ritual

Designed for one PR, assuming it's a normal-sized change (not the split-worthy 500+ line case, in which case go back to the agent and ask for a smaller PR first, per technique 4).

**0. Before opening anything (2 min): predict.** Reread your own spec/prompt for this PR. Write two or three lines: which files/modules you expect touched, what the core mechanism will be, what the trickiest edge case is. This costs almost nothing and is the highest information-per-minute step you can take.

**1. Generate the explain-diff HTML (2-5 min, mostly agent time).** Run the installed `explain-diff-html` skill against the PR/branch. While it generates, do nothing else, don't start reading the raw diff in parallel, that defeats the point of having a structured explanation to read first.

**2. Read background and intuition sections (8-10 min).** This is where you check your step-0 prediction against reality: did the change touch what you expected, for the reason you expected? Note the gap, that gap is the thing you actually didn't know.

**3. Read the code walkthrough with the AI-specific checklist active (12-15 min).** As you read, run the four-item checklist from technique 5: scope creep, overfitting to tests, plausible-but-wrong idioms, missing edge cases. Use the annotation-first move (technique 8) if the PR is dense enough that you're likely to lose track of a red flag: jot a one-line note next to anything that trips a checklist item, keep reading, come back at the end of this step to resolve each note.

**4. Take the quiz (5 min).** Don't peek at the code while answering. This is Litt's actual gate: if you can't pass it, you're not done, go back into step 3 for the specific section the missed question came from. Passing on the first try with no hesitation is itself a useful signal that this PR didn't teach you much and can be merged with a light touch going forward.

**5. Teach-back, written, from memory (5-8 min).** Close the explainer. Write three to five sentences: what changed, why, and the one non-obvious thing about it. This is the step that converts "I passed a multiple-choice quiz" (recognition) into "I can generate an account" (recall), and it's the direct evidence-backed answer to "I merge too fast."

**6. Decide: merge, or flag one thing to fix first (2-3 min).** Merge. If you caught something in step 3 worth a follow-up spec change, write it down now, in the next spec, not as a scramble to un-merge later.

That's roughly 35-43 minutes depending on PR size, leaving slack. Reserve technique 7 (guided re-implementation kata) for a separate, deliberately scheduled session, once a week or once a milestone, on whichever recent PR touched the part of bess-optimizer Travis most needs to own cold (the LP optimizer, rolling-horizon logic, or the ancillary-services co-optimizer look like the natural candidates given the repo's structure). Treat technique 6 (spaced-repetition cards) as opportunistic: if step 5's teach-back surfaces something you'd hate to re-derive in three months, spend two extra minutes turning it into one Anki card; otherwise skip it entirely for that PR.

## How the Installed explain-diff-html Skill Fits

The skill at `/Users/rickjms/code/bess/.claude/skills/explain-diff-html/SKILL.md` is not a generic nice-to-have, it's a faithful implementation of Litt's actual, attributed pattern (background/intuition/code/quiz, single self-contained HTML file, five medium-difficulty multiple-choice questions with per-answer feedback, explicit prompt-injection guard against instructions embedded in the diff itself). It does the heavy lifting for steps 1, 2, and 4 of the ritual above essentially for free, agent time, not Travis's time.

What the skill does not do, and what the rest of this ritual is deliberately built to add around it:

- It doesn't force prediction before reading (step 0), which is the cheapest, highest-signal step and is entirely on Travis to self-impose.
- It doesn't force written teach-back (step 5). The quiz alone tests recognition (can you pick the right answer out of four); writing a teach-back from memory tests recall/construction, a meaningfully stronger form of the same self-explanation effect the quiz is going for, at low added cost.
- It doesn't enforce the AI-specific checklist (scope creep, test overfitting, plausible-but-wrong idioms, missing edge cases). The quiz is about whether you understood the change as written; the checklist is about whether the change, as written, should be trusted. Both are needed, and they're different questions.
- It doesn't police PR size. If Travis notices he's about to generate an explainer for a genuinely oversized PR, that's the signal to go back to the spec and split the work, not push through with a bigger explainer.

Net effect: the skill converts roughly 20-25 minutes of unaided diff-reading into 10-15 minutes of structured reading plus a built-in comprehension gate, freeing the time budget for the two additions (predict-before and teach-back-after) that the evidence says matter most for actually retaining what was learned, rather than just verifying it was momentarily true.
