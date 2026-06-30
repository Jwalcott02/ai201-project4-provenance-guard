import re
import statistics


def classify_with_stylometrics(text):
    """
    Computes stylometric heuristics and returns a float between 0-1.
    0 = likely human, 1 = likely AI.

    Combines three metrics:
    - Sentence length variance (low variance = more AI-like)
    - Type-token ratio (low TTR = more AI-like)
    - Punctuation density (high density = more AI-like)
    """
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    words = re.findall(r"\b[\w']+\b", text.lower())

    if len(sentences) < 2 or len(words) < 5:
        return 0.5

    # Metric 1: Sentence length variance
    sentence_lengths = [len(s.split()) for s in sentences]
    length_variance = statistics.variance(sentence_lengths)
    variance_score = max(0.0, min(1.0, 1 - (length_variance / 15)))

    # Metric 2: Type-token ratio (TTR)
    unique_words = set(words)
    ttr = len(unique_words) / len(words)
    ttr_score = max(0.0, min(1.0, 1 - ttr))

    # Metric 3: Punctuation density
    punctuation_count = len(re.findall(r'[,.;:!?\-]', text))
    punctuation_density = punctuation_count / len(words)
    punctuation_score = max(0.0, min(1.0, punctuation_density * 5))

    stylometric_score = (
        (variance_score * 0.4) +
        (ttr_score * 0.4) +
        (punctuation_score * 0.2)
    )

    return round(stylometric_score, 2)


def combine_scores(llm_score, stylometric_score):
    """
    Combines Signal 1 (LLM) and Signal 2 (stylometrics) into a single
    confidence score using a weighted average.
    """
    confidence = (llm_score * 0.6) + (stylometric_score * 0.4)
    return round(confidence, 2)


def get_attribution(confidence):
    """
    Maps a confidence score to an attribution category.
    """
    if confidence <= 0.39:
        return "likely_human"
    elif confidence <= 0.80:
        return "uncertain"
    else:
        return "likely_ai"