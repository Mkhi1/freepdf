"""Extractive summaries with TextRank (PageRank over sentence similarity). No models, English and Arabic."""
import re
import unicodedata

import numpy as np

from ._lang_engine import split_sentences

SHARE = {"short": 0.10, "medium": 0.22, "long": 0.38}
MIN_WORDS = 4
LEAD_BONUS = 0.15
REDUNDANT_ABOVE = 0.6
WORD = re.compile(r"[^\W_]+", re.UNICODE)
ARABIC_MARKS = re.compile("[ً-ٰٟـ]")
ARABIC_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و")
ENGLISH_STOP = set("""a about above after again all also am an and any are as at be because been before being between
both but by can could did do does doing down during each few for from further had has have having he her here hers
him his how i if in into is it its just me more most my no nor not now of off on once only or other our out over own
same she should so some such than that the their them then there these they this those through to too under until up
very was we were what when where which while who whom why will with would you your""".split())
ARABIC_STOP = set("""في من على الى إلى عن مع هذا هذه ذلك تلك هو هي هم هن انا نحن انت انتم ان إن أن كان كانت يكون تكون
قد لا لم لن ما ماذا لماذا كيف اين متى الذي التي الذين اللذين او أو ثم حتى اذا إذا بعد قبل بين كل بعض غير
اي أي كما لكن لكنه عند عندما منذ خلال حول ضد نحو فقط ايضا أيضا هنا هناك جدا وقد وهو وهي وكان وفي ومن وعلى
ولا ولم ولكن بل او كذلك تم يتم""".split())


def normalise_word(word: str) -> str:
    word = unicodedata.normalize("NFKC", word).lower()
    if not re.search("[؀-ۿ]", word):
        return word
    word = ARABIC_MARKS.sub("", word)
    for src, dst in (("أإآٱ", "ا"), ("ى", "ي"), ("ة", "ه")):
        word = re.sub(f"[{src}]", dst, word)
    for prefix in ARABIC_PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            return word[len(prefix):]
    return word


def content_words(sentence: str) -> list[str]:
    stops = {normalise_word(w) for w in ENGLISH_STOP | ARABIC_STOP}
    words = [normalise_word(w) for w in WORD.findall(sentence)]
    return [w for w in words if len(w) > 1 and w not in stops and not w.isdigit()]


def clean_sentences(text: str) -> list[str]:
    text = re.sub(r"-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]*\n[ \t]*(?=[^\n])", " ", text)
    sentences = [re.sub(r"\s+", " ", s).strip() for s in split_sentences(text)]
    return [s for s in sentences if len(WORD.findall(s)) >= MIN_WORDS]


def tfidf_matrix(token_lists: list[list[str]]) -> np.ndarray:
    vocab = {w: i for i, w in enumerate(sorted({w for t in token_lists for w in t}))}
    counts = np.zeros((len(token_lists), max(len(vocab), 1)))
    for row, tokens in enumerate(token_lists):
        for word in tokens:
            counts[row, vocab[word]] += 1
    document_frequency = (counts > 0).sum(axis=0)
    idf = np.log((1 + len(token_lists)) / (1 + document_frequency)) + 1
    weighted = np.log1p(counts) * idf
    norms = np.linalg.norm(weighted, axis=1, keepdims=True)
    return weighted / np.where(norms == 0, 1, norms)


def pagerank(weights: np.ndarray, damping: float = 0.85, iterations: int = 200, tolerance: float = 1e-9) -> np.ndarray:
    """PageRank by power iteration on a weighted, symmetric sentence graph (scipy is not needed)."""
    size = len(weights)
    totals = weights.sum(axis=1, keepdims=True)
    transition = np.where(totals > 0, weights / np.where(totals == 0, 1, totals), 1.0 / size)
    scores = np.full(size, 1.0 / size)
    for _ in range(iterations):
        updated = (1 - damping) / size + damping * (transition.T @ scores)
        if np.abs(updated - scores).sum() < tolerance:
            return updated
        scores = updated
    return scores


def rank_sentences(sentences: list[str]) -> np.ndarray:
    tokens = [content_words(s) for s in sentences]
    vectors = tfidf_matrix(tokens)
    similarity = vectors @ vectors.T
    np.fill_diagonal(similarity, 0)
    similarity[similarity < 0.05] = 0
    base = pagerank(similarity)
    position = LEAD_BONUS * base.mean() * np.linspace(1, 0, len(sentences))
    return base + position


def target_counts(total: int) -> dict[str, int]:
    """Sentences to keep for each length, always growing from short to medium to long when the text allows."""
    counts: dict[str, int] = {}
    previous = 0
    for name in ("short", "medium", "long"):
        wanted = max(round(total * SHARE[name]), previous + 1, 2)
        counts[name] = min(wanted, total)
        previous = counts[name]
    return counts


def summarise(text: str, length: str = "medium") -> dict:
    sentences = clean_sentences(text)
    if not sentences:
        return {"text": "", "sentences": [], "total_sentences": 0}
    counts = target_counts(len(sentences))
    keep = counts.get(length, counts["medium"])
    if len(sentences) <= 2:
        return {"text": " ".join(sentences), "sentences": sentences, "total_sentences": len(sentences)}
    scores = rank_sentences(sentences)
    chosen = _pick(sentences, scores, keep)
    picked = [sentences[i] for i in sorted(chosen)]
    return {"text": " ".join(picked), "sentences": picked, "total_sentences": len(sentences),
            "indexes": sorted(chosen)}


def _pick(sentences: list[str], scores: np.ndarray, keep: int) -> list[int]:
    vectors = tfidf_matrix([content_words(s) for s in sentences])
    chosen: list[int] = []
    for index in np.argsort(-scores):
        if len(chosen) >= keep:
            break
        if any(float(vectors[index] @ vectors[j]) > REDUNDANT_ABOVE for j in chosen):
            continue
        chosen.append(int(index))
    for index in np.argsort(-scores):  # top up if redundancy filtering left us short
        if len(chosen) >= keep:
            break
        if int(index) not in chosen:
            chosen.append(int(index))
    return chosen
