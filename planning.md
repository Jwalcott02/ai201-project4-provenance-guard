# Provenance Guard — Planning Document

## Architecture Narrative

### Submission Flow
A piece of text travels through the following components:

1. **Rate Limiting** — checks if the creator has exceeded their submission 
limit before any processing begins. Returns 429 if limit exceeded.
2. **API Endpoint (POST /submit)** — accepts the text and creator_id 
from the creator.
3. **Detection Pipeline** — two distinct signals analyze the text 
independently:
   - Signal 1: LLM Classification
   - Signal 2: Stylometric Heuristics
4. **Confidence Scoring** — both signal scores are combined into a 
single 0–1 confidence score.
5. **Transparency Label** — the confidence score maps to a 
human-readable label shown to the creator.
6. **Audit Log** — every decision, score, and label is recorded 
as a structured entry.
7. **Response** — content_id, attribution, confidence score, 
and label text are returned to the creator.

### Appeal Flow
If a creator disputes their classification:

1. Creator submits content_id and their reasoning to POST /appeal
2. System looks up the original decision
3. Content status is updated to "under_review"
4. Appeal is logged alongside the original decision
5. Confirmation is returned to the creator

## Architecture

### Submission Flow

[POST /submit]
      |
      | (text, creator_id)
      ↓
[Rate Limiting] ──── limit exceeded ────→ [429 Response]
      |
      | (text passes through)
      ↓
[Signal 1: LLM Classification]
      |
      | (llm_score 0-1)
      ↓
[Signal 2: Stylometric Heuristics]
      |
      | (stylometric_score 0-1)
      ↓
[Confidence Scoring]
      |
      | (combined score 0-1)
      ↓
[Transparency Label Generator]
      |
      | (label text)
      ↓
[Audit Log] ←─── records everything
      |
      | (content_id, attribution, confidence, label)
      ↓
[Response to Creator]


### Appeal Flow


[POST /appeal]
      |
      | (content_id, creator_reasoning)
      ↓
[Look up original decision]
      |
      ↓
[Update status → "under_review"]
      |
      ↓
[Audit Log] ←─── appends appeal_reasoning
      |
      ↓
[Confirmation Response]




## Detection Signals

### Signal 1: LLM-Based Classification
- **What it measures:** Semantic meaning and stylistic coherence — 
asks the model to assess whether the text reads as human or 
AI-generated holistically.
- **Why it differs:** AI writing tends to be semantically consistent 
and coherent in a way that feels uniform, while human writing has 
more natural variation in tone and meaning.
- **Blind spots:**
  - Formal or structured human writers may be misclassified as AI
  - Lightly edited AI text may be misclassified as human since 
  human edits introduce natural tone

### Signal 2: Stylometric Heuristics
- **What it measures:** Statistical properties of the text:
  - **Sentence length variance** — AI writing tends to have 
  uniform sentence lengths; human writing varies more
  - **Type-token ratio (TTR)** — ratio of unique words to total 
  words; humans use more varied vocabulary giving higher TTR; 
  AI reuses common words giving lower TTR
  - **Punctuation density** — AI tends to use proper consistent 
  punctuation; humans are more inconsistent and casual
- **Why it differs:** AI generates text with uniform statistical 
patterns while human writing is naturally variable and irregular.
- **Blind spots:**
  - Academic writers, journalists, or non-native English speakers 
  who write carefully and consistently may score as AI
  - Casual AI-generated text with varied punctuation may score 
  as human

## Confidence Scoring

Signals are combined into a single confidence score between 0–1 
where 1 = high confidence AI and 0 = high confidence human.

Both signals produce a score between 0-1. They are combined 
using a weighted average that trusts the LLM signal more:

confidence = (llm_score * 0.6) + (stylometric_score * 0.4)

The LLM is weighted higher (60%) because semantic patterns 
are harder to fake than surface statistics. Stylometrics 
adds structural evidence but is weighted lower (40%) because 
consistent human writers can fool it.



### Thresholds
| Score Range | Classification |
|-------------|---------------|
| 0.00 – 0.39 | Likely Human  |
| 0.40 – 0.80 | Uncertain     |
| 0.81 – 1.00 | Likely AI     |

### Design Decision
A wide uncertain band (0.40–0.80) is intentional. False positives 
(labeling human work as AI) are worse than false negatives on a 
creative platform. The system should be honest about uncertainty 
rather than forcing a binary result.

## Transparency Labels

### High-Confidence AI (score > 0.80)
"Our system determined that this content is most likely AI generated. 
Your content is still visible to others. If you believe this is a 
mistake, please submit an appeal and we'll review it manually."

### Uncertain (score 0.40–0.80)
"Our system couldn't confidently determine whether this content was 
AI-generated or human-written. Your content is still visible to 
others. If you believe this is a mistake, you can submit an appeal 
and we'll review it manually."

### High-Confidence Human (score < 0.40)
"Our system determined that this content is most likely 
human-written. Your work looks great — enjoy sharing it 
with your audience!"

## Appeals Workflow

- **Who can appeal:** Any creator who receives a classification 
they disagree with
- **What they provide:** content_id and creator_reasoning 
(their explanation)
- **What the system does:**
  - Updates content status to "under_review"
  - Logs the appeal alongside the original decision
  - Returns confirmation to the creator
- **What a reviewer sees:** Original decision, confidence score, 
both signal scores, and the creator's reasoning

## Anticipated Edge Cases

1. **Formal human writers** — academics, journalists, or 
non-native English speakers who write carefully may trigger 
both signals, producing a high AI confidence score despite 
being human-written. The wide uncertain band and appeals 
workflow are the main safeguards here.

2. **Very short content** — a haiku or two-line poem gives 
both signals very little text to analyze. Stylometric metrics 
like sentence length variance become meaningless with only 
1–2 sentences, and the LLM has less context to work with. 
Confidence scores for short content should be treated 
with extra skepticism.

## API Surface

| Endpoint | Method | Accepts | Returns |
|----------|--------|---------|---------|
| /submit  | POST   | text, creator_id | content_id, attribution, confidence, label |
| /appeal  | POST   | content_id, creator_reasoning | confirmation, status |
| /log     | GET    | nothing | list of structured log entries |

## Audit Log Structure

Each log entry captures:
- content_id
- creator_id
- timestamp
- attribution (likely_ai, uncertain, likely_human)
- confidence (combined score)
- llm_score (signal 1 individual score)
- stylometric_score (signal 2 individual score)
- label (transparency label text)
- status (classified, under_review)
- appeal_reasoning (if appeal was filed)




## AI Tool Plan

### M3 — Submission Endpoint + Signal 1
- **Spec sections to provide:** Architecture diagram, 
Detection Signals, API Surface
- **What to ask for:** Flask app skeleton with POST /submit 
route stub and the Signal 1 LLM classification function
- **How to verify:** Test the LLM function independently 
with 2-3 sample texts before wiring into the endpoint. 
Check that POST /submit returns content_id, attribution, 
confidence, and label fields.

### M4 — Second Signal + Confidence Scoring
- **Spec sections to provide:** Detection Signals, 
Confidence Scoring, Architecture diagram
- **What to ask for:** Signal 2 stylometric heuristics 
function and scoring logic using the formula: 
confidence = (llm_score * 0.6) + (stylometric_score * 0.4)
- **How to verify:** Test with 4 inputs — clearly AI, 
clearly human, and two borderline cases. Scores should 
vary meaningfully across all four.

### M5 — Production Layer
- **Spec sections to provide:** Transparency Labels, 
Appeals Workflow, Architecture diagram
- **What to ask for:** Label generation function that 
maps confidence scores to label text, and POST /appeal 
endpoint
- **How to verify:** Test all three label variants are 
reachable by submitting inputs at different confidence 
levels. Verify appeal updates status to under_review 
in the audit log.