# Provenance Guard

A backend system that classifies submitted creative writing as likely AI-generated,
likely human-written, or uncertain — and gives readers a transparent, plain-language
label along with a path to appeal.

## Architecture Overview

A submission travels through the following path:

**Submission flow:**
1. **Rate limiting** checks the request before any processing begins
2. **POST /submit** accepts the text and creator_id
3. **Signal 1 (LLM classification)** scores the text semantically via Groq
4. **Signal 2 (stylometric heuristics)** scores the text statistically
5. **Confidence scoring** combines both signals into one 0–1 score
6. **Transparency label** maps the score to plain-language text
7. **Audit log** records the full decision
8. The response returns content_id, attribution, confidence, and label

**Appeal flow:**
1. Creator submits content_id and their reasoning to POST /appeal
2. Content status is updated to "under_review"
3. The appeal is logged alongside the original decision
4. Confirmation is returned to the creator

```
[POST /submit]
      |
      | (text, creator_id)
      v
[Rate Limiting] --- limit exceeded ---> [429 Response]
      |
      v
[Signal 1: LLM Classification] --(llm_score)--+
      |                                         |
[Signal 2: Stylometric Heuristics] --(stylometric_score)--+
      |
      v
[Confidence Scoring] --(combined score)--> [Transparency Label]
      |
      v
[Audit Log] ---> [Response to Creator]
```

## Detection Signals

### Signal 1: LLM-Based Classification (Groq, llama-3.3-70b-versatile)
**What it measures:** Semantic meaning and stylistic coherence. The model is
prompted to assess holistically whether the text reads as human- or AI-written,
returning a score from 0 (human) to 1 (AI).

**Why we chose it:** AI writing tends to be semantically consistent and coherent
in a way that reads as uniform, while human writing has more natural variation
in tone, digression, and meaning. An LLM can recognize these patterns far more
reliably than surface statistics because it's trained on the deep structure of
language, not just word counts.

**What it misses:** Formal, structured human writers (academics, non-native
English speakers writing carefully) can be misclassified as AI. Lightly edited
AI text — where a human has revised tone and word choice — can be misclassified
as human, since the edits introduce natural variation the model reads as
authentic.

### Signal 2: Stylometric Heuristics (pure Python)
**What it measures:** Three statistical properties of the text, combined into
one score:
- **Sentence length variance** (40% weight) — AI text tends toward uniform
  sentence lengths; human text varies more.
- **Type-token ratio / TTR** (40% weight) — ratio of unique words to total
  words. Higher TTR (varied vocabulary) is treated as more human-like.
- **Punctuation density** (20% weight, lower weight because it's the
  weakest discriminator of the three) — denser, more consistent punctuation
  is treated as more AI-like.

**Why we chose it:** These are measurable, computable-in-pure-Python
properties that are structurally independent of the LLM's semantic judgment —
giving the pipeline a second, genuinely different lens on the same text.

**What it misses:** Sophisticated AI-generated writing that uses varied,
non-repetitive vocabulary can score a high (human-like) TTR despite being
machine-generated — see the signal disagreement example below. Consistent,
formal human writers can score as AI-like on sentence variance and punctuation
density for the same reason the LLM signal misses them.

## Confidence Scoring

Both signals return a float between 0 and 1. They are combined using a
weighted average:

```
confidence = (llm_score * 0.6) + (stylometric_score * 0.4)
```

The LLM is weighted higher (60%) because semantic understanding is harder to
fake than surface statistics — a writer can accidentally produce uniform
sentence lengths, but mimicking the deep coherence patterns an LLM picks up
on is much harder. Stylometrics is weighted lower (40%) because it can be
fooled by any consistent, careful writer, human or AI.

The combined score maps to three zones:

| Score Range | Classification |
|-------------|----------------|
| 0.00 – 0.39 | Likely Human   |
| 0.40 – 0.80 | Uncertain      |
| 0.81 – 1.00 | Likely AI      |

This is a deliberately wide uncertain band. False positives — labeling a
human's work as AI-generated — are worse than false negatives on a creative
platform, so the system is designed to express genuine uncertainty rather
than force a confident-sounding answer it can't back up.

### Validating the scores are meaningful

We tested 4 deliberately chosen inputs spanning the confidence range:

| Input | LLM Score | Stylometric Score | Combined | Label |
|-------|-----------|--------------------|----------|--------|
| Clearly AI-generated (AI/society paragraph) | 0.83 | 0.16 | **0.56 (Uncertain)** | see note below |
| Clearly human (casual ramen review) | 0.21 | 0.12 | **0.17 (Likely Human)** | correct |
| Borderline: formal human (monetary policy) | 0.42 | 0.10 | **0.29 (Likely Human)** | correct |
| Borderline: lightly edited AI (remote work) | 0.27 | 0.07 | **0.19 (Likely Human)** | system fooled |

**Signal disagreement example:** On the clearly AI-generated paragraph, the
LLM signal correctly scored 0.83 (likely AI) while stylometrics scored 0.16
(likely human) — driven by the text's sophisticated, varied vocabulary
producing a high type-token ratio, a property that normally signals human
writing. The combined score of 0.56 ("uncertain") reflects genuine signal
disagreement rather than a clean failure: TTR alone can't distinguish "varied
human vocabulary" from "polished AI vocabulary that avoids repetition." We
see this as the system behaving honestly — surfacing uncertainty when its two
independent signals disagree — rather than confidently picking the wrong
answer.

**High-confidence example vs. lower-confidence example:** the casual ramen
review (0.17) and the AI paragraph (0.56) show a clear, meaningful spread —
confidence is not a constant or a coin-flip binary.

## Transparency Label

The `/submit` response includes a `label` field with one of three exact text
variants, chosen based on the attribution category. All three were written to
be readable by a non-technical creator — no scores, no jargon, and a clear
next step where relevant.

**High-confidence AI (confidence > 0.80):**
> "Our system determined that this content is most likely AI generated. Your content is still visible to others. If you believe this is a mistake, please submit an appeal and we'll review it manually."

**Uncertain (confidence 0.40–0.80):**
> "Our system couldn't confidently determine whether this content was AI-generated or human-written. Your content is still visible to others. If you believe this is a mistake, you can submit an appeal and we'll review it manually."

**High-confidence Human (confidence < 0.40):**
> "Our system determined that this content is most likely human-written. Your work looks great — enjoy sharing it with your audience!"

Design notes: the AI and uncertain labels are deliberately not accusatory —
they state the result as a system determination, confirm the content stays
visible, and point to the appeal path. The human label drops the appeal
mention entirely since offering an appeal on good news undermines the
reassurance. The uncertain label avoids implying the creator did anything
wrong (e.g. it doesn't suggest they "fix" their writing style).

## Appeals Workflow

Any creator who receives a classification they disagree with can submit an
appeal via `POST /appeal` with two fields: `content_id` (identifying their
original submission) and `creator_reasoning` (their explanation).

When an appeal is received, the system:
1. Looks up the matching entry in the audit log by `content_id`
2. Updates that entry's `status` from `"classified"` to `"under_review"`
3. Appends the creator's `appeal_reasoning` to the same log entry, preserving
   the original confidence score and both signal scores
4. Returns a confirmation with the new status

A human reviewer opening the appeal queue (the `/log` output, filtered to
`status: "under_review"`) sees the complete picture in one place: the
original confidence score, both individual signal scores, the label that was
shown, and the creator's reasoning — everything needed to make a manual call
without re-running the pipeline.

### Tested end-to-end

A formal academic-style submission scored 0.45 confidence (uncertain). The
creator appealed:

```json
{
  "content_id": "b6211ddf-929b-41e0-9b00-127d77c3eb3d",
  "creator_id": "test-appeal-user",
  "timestamp": "2026-06-30T18:59:14.069496+00:00",
  "attribution": "uncertain",
  "confidence": 0.45,
  "llm_score": 0.42,
  "stylometric_score": 0.5,
  "status": "under_review",
  "appeal_reasoning": "I wrote this myself for an economics paper. I write formally because it is an academic topic, not because I used AI."
}
```

The status flipped from `classified` to `under_review` and the reasoning was
preserved alongside the original decision, exactly as designed. Automated
re-classification is intentionally not implemented — appeals are meant to be
reviewed by a person.

## Rate Limiting

`POST /submit` is limited to **10 requests per minute and 100 per day per
client**, enforced with Flask-Limiter using in-memory storage.

**Reasoning:** A genuine creator submitting their own work for review would
rarely submit more than a handful of pieces in a single minute — 10/minute is
generous headroom for normal use (testing revisions, submitting a few short
pieces back to back) while still being low enough to stop a script from
flooding the endpoint with rapid automated requests. The 100/day ceiling
caps sustained abuse over a longer window without blocking someone who is
genuinely prolific.

### Tested

Firing 12 rapid requests in a loop produced 10 successful `200` responses
followed by two `429 Too Many Requests` responses:

```
200
200
200
200
200
200
200
200
200
200
429
429
```

The 429 response body confirms Flask-Limiter's own messaging:

```
429 Too Many Requests
Too Many Requests
10 per 1 minute
```

## Audit Log

Every call to `/submit` writes a structured entry (JSON, in-memory list) capturing:
`content_id`, `creator_id`, `timestamp`, `attribution`, `confidence`,
`llm_score`, `stylometric_score`, and `status`. Appeals append
`appeal_reasoning` and flip `status` to `under_review` on the same entry
rather than creating a separate record, so the full history of a submission
stays in one place.

`GET /log` returns all entries as JSON for documentation and grading
visibility (in a real deployment this endpoint would require auth).

### Sample entries (from testing)

```json
{
  "entries": [
    {
      "content_id": "44b74a8b-4266-49b7-8d29-58dafa9e8698",
      "creator_id": "test-ai",
      "timestamp": "2026-06-30T18:38:21.753984+00:00",
      "attribution": "uncertain",
      "confidence": 0.56,
      "llm_score": 0.83,
      "stylometric_score": 0.16,
      "status": "classified"
    },
    {
      "content_id": "49de3753-a7c4-432b-81f0-202589230d9c",
      "creator_id": "test-human",
      "timestamp": "2026-06-30T18:42:02.513410+00:00",
      "attribution": "likely_human",
      "confidence": 0.17,
      "llm_score": 0.21,
      "stylometric_score": 0.12,
      "status": "classified"
    },
    {
      "content_id": "b6211ddf-929b-41e0-9b00-127d77c3eb3d",
      "creator_id": "test-appeal-user",
      "timestamp": "2026-06-30T18:59:14.069496+00:00",
      "attribution": "uncertain",
      "confidence": 0.45,
      "llm_score": 0.42,
      "stylometric_score": 0.5,
      "status": "under_review",
      "appeal_reasoning": "I wrote this myself for an economics paper. I write formally because it is an academic topic, not because I used AI."
    }
  ]
}
```

**Known limitation of the log itself:** it is stored in memory and is wiped
on server restart. A production deployment would persist this to SQLite or a
real database, as noted in the project's recommended stack.

## Known Limitations

1. **Sophisticated AI vocabulary fools the TTR metric.** As shown in the
   signal disagreement example above, AI-generated text with varied,
   non-repetitive word choice scores a high (human-like) type-token ratio,
   pulling the combined confidence score down even when the LLM signal
   correctly flags the text as AI-generated.

2. **Very short content (e.g. a haiku or two-line poem) gives both signals
   too little data.** Stylometric metrics like sentence length variance are
   close to meaningless with only 1–2 sentences, and the LLM has minimal
   context to work with. Confidence scores for very short submissions should
   be treated with extra skepticism.

## Spec Reflection

**How the spec helped:** Defining the confidence thresholds (0.40 / 0.80) and
writing out the exact label text in planning.md *before* any code existed
made the Milestone 4 debugging session far faster than it would have been
otherwise. When the clearly-AI test paragraph came back as "uncertain"
(0.56) instead of "likely AI," having a pre-written, specific threshold table
meant we immediately knew that result was a real disagreement between
signals rather than vague code working "incorrectly" — there was a fixed
target to measure against instead of an implementation that could be
rationalized after the fact.

**Where implementation diverged from the plan:** The original plan treated
the two signals as roughly independent and combined them with a simple fixed
weighted average. In practice, testing in Milestone 4 surfaced a real
weakness in the stylometric signal: type-token ratio assumes high vocabulary
variety signals human writing, but sophisticated AI-generated text (the
"transformative paradigm shift" test case) also produces high TTR by
avoiding repetition. Rather than re-tuning the formula to force that one
test case into the "likely AI" bucket, we kept the original weighting and
documented the disagreement as a known, honest limitation — the system
surfacing "uncertain" when its two signals genuinely disagree is arguably
more correct behavior than confidently forcing the wrong label.

## AI Usage

**Instance 1 — Transparency label generation.** I asked Claude to generate a
`get_label_text()` function mapping attribution categories to label text. The
first version I wrote myself included the raw confidence score in the
returned string (e.g. "Confidence: 0.56 - ..."). Claude pointed out this
worked against the entire point of the label — it was designed in planning.md
to be readable by a non-technical creator, and showing a raw decimal
undercuts that. I removed the confidence number and the `confidence`
parameter entirely, leaving only the plain-language text.

**Instance 2 — Debugging the Milestone 4 score mismatch.** When the clearly
AI-generated test paragraph returned a combined confidence of 0.56 instead of
the expected high score, I asked Claude to help debug it. Rather than just
patching the formula until the test passed, Claude walked me through pulling
the individual `llm_score` (0.83, correct) and `stylometric_score` (0.16,
wrong) apart to find which signal was misbehaving, and helped me reason
through *why* — the text's varied, sophisticated vocabulary produced a high
TTR, which my formula treats as evidence of human writing. I chose to
document this as a known limitation in the README rather than alter the
formula's weighting to force that one test case to pass, since the original
60/40 LLM-weighted design was a deliberate decision, not an accident.