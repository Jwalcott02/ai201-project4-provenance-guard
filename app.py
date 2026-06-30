import os
import uuid
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from groq import Groq
from signals import classify_with_stylometrics, combine_scores, get_attribution

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# In-memory audit log (list of dicts)
audit_log = []


# ── Signal 1: LLM Classification ──────────────────────────────────────────────
def classify_with_llm(text):
    """
    Sends text to Groq and returns a float between 0-1.
    0 = likely human, 1 = likely AI.
    """
    prompt = f"""You are an AI content detector. Analyze the following text and return a single decimal number between 0 and 1 representing the likelihood that it was AI-generated.

Use this scale:
- 0.00 to 0.39: Likely human-written
- 0.40 to 0.80: Uncertain
- 0.81 to 1.00: Likely AI-generated

Return ONLY the number. No explanation, no extra text, just the decimal number.

Text to analyze:
{text}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  # Low temperature = more consistent scoring
    )

    # Extract the number from the response
    raw = response.choices[0].message.content.strip()
    return float(raw)


# ── Audit Log Helper ───────────────────────────────────────────────────────────
def write_log(entry):
    """Appends a structured entry to the in-memory audit log."""
    audit_log.append(entry)


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()

    # Validate required fields
    if not data or "text" not in data or "creator_id" not in data:
        return jsonify({"error": "Missing required fields: text, creator_id"}), 400

    text = data["text"]
    creator_id = data["creator_id"]

    # Generate unique ID for this submission
    content_id = str(uuid.uuid4())

   # Run both signals
    llm_score = classify_with_llm(text)
    stylometric_score = classify_with_stylometrics(text)

    # Combine into final confidence score
    confidence = combine_scores(llm_score, stylometric_score)
    attribution = get_attribution(confidence)
    label = "Analysis complete. Full label text coming in next milestone."

    # Write to audit log
    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "status": "classified",
        "stylometric_score": stylometric_score,
    }
    write_log(entry)

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": label
    })


@app.route("/log", methods=["GET"])
def get_log():
    """Returns the most recent audit log entries."""
    return jsonify({"entries": audit_log})


if __name__ == "__main__":
    app.run(debug=True)