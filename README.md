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

*(placeholder — to be completed in Milestone 5)*

## Appeals Workflow

*(placeholder — to be completed in Milestone 5)*

## Rate Limiting

*(placeholder — to be completed in Milestone 5)*

## Audit Log

*(placeholder — to be completed in Milestone 5)*

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

*(to be completed)*

## AI Usage

*(to be completed)*