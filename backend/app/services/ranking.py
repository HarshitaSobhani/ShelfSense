"""Pure ranking logic: no database access, so behaviour can be verified on small controlled datasets."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

_STOP = set(
    "a an the and or of to in on for with without about like that this is are was were be as at by from it its "
    "i me my want something book books novel novels story stories read reading love".split()
)


def tokenize(q: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", q.lower()) if w not in _STOP and len(w) > 1]


def _stem(w: str) -> str:
    """Light plural stemmer: enough to match 'houses'/'house' and 'mysteries'/'mystery'."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tag_token_matches(tokens: list[str], tag: str) -> bool:
    tag_words = {_stem(w) for w in re.findall(r"[a-z0-9]+", tag.lower())}
    stems = {_stem(t) for t in tokens}
    return bool(tag_words) and tag_words <= stems


@dataclass
class Candidate:
    book_id: int
    author_ids: tuple[int, ...] = ()
    semantic: float | None = None  # cosine; None if no embedding
    lexical: float = 0.0  # 0..1
    exact: bool = False  # title or author contains the query
    genres: frozenset[str] = frozenset()
    moods: frozenset[str] = frozenset()
    tropes: frozenset[str] = frozenset()
    pacing: str | None = None


@dataclass
class Factor:
    factor: str
    weight: float
    value: float
    contribution: float
    evidence: str

    def as_dict(self) -> dict:
        return {
            "factor": self.factor,
            "weight": round(self.weight, 3),
            "value": round(self.value, 4),
            "contribution": round(self.contribution, 4),
            "evidence": self.evidence,
        }


@dataclass
class Ranked:
    book_id: int
    score: float
    factors: list[Factor] = field(default_factory=list)


@dataclass
class TasteProfile:
    """Tag affinities in 0..1 per kind. `explicit` marks tags the user asked for directly."""

    genres: dict[str, float] = field(default_factory=dict)
    moods: dict[str, float] = field(default_factory=dict)
    tropes: dict[str, float] = field(default_factory=dict)
    explicit_genres: frozenset[str] = frozenset()
    explicit_moods: frozenset[str] = frozenset()
    explicit_tropes: frozenset[str] = frozenset()
    pacing: str | None = None

    def is_empty(self) -> bool:
        return not (self.genres or self.moods or self.tropes or self.pacing)


def build_profile(
    weighted_books: list[tuple[float, frozenset[str], frozenset[str], frozenset[str]]],
    pref_genres: list[str] = (),  # type: ignore[assignment]
    pref_moods: list[str] = (),  # type: ignore[assignment]
    pref_tropes: list[str] = (),  # type: ignore[assignment]
    pacing: str | None = None,
) -> TasteProfile:
    """weighted_books: (weight, genres, moods, tropes). Positive weights add affinity; negative ones
    reduce it. Implicit affinities are scaled to at most 0.8; explicit preferences are pinned to 1.0."""
    acc: list[dict[str, float]] = [{}, {}, {}]
    for w, *tagsets in weighted_books:
        for i, tags in enumerate(tagsets):
            for t in tags:
                acc[i][t] = acc[i].get(t, 0.0) + w
    out = []
    for d in acc:
        pos = {t: v for t, v in d.items() if v > 0}
        mx = max(pos.values(), default=0.0)
        out.append({t: 0.8 * v / mx for t, v in pos.items()} if mx > 0 else {})
    eg, em, et = (frozenset(x) for x in (pref_genres, pref_moods, pref_tropes))
    for d, ex in zip(out, (eg, em, et), strict=True):
        for t in ex:
            d[t] = 1.0
    return TasteProfile(out[0], out[1], out[2], eg, em, et, pacing)


def taste_vector(items: list[tuple[float, np.ndarray]]) -> np.ndarray | None:
    """Weighted mean of embeddings; negative weights (low ratings) push the vector away."""
    if not items:
        return None
    v = sum(w * e for w, e in items)
    n = float(np.linalg.norm(v))
    if not isinstance(v, np.ndarray) or n < 1e-6:
        return None
    return v / n


def _overlap(profile: dict[str, float], tags: frozenset[str]) -> tuple[float, list[str]]:
    hits = sorted((t for t in tags if t in profile), key=lambda t: -profile[t])
    return min(1.0, sum(profile[t] for t in hits) / 2.0), hits


EXACT_BONUS = 0.5

DEFAULT_WEIGHTS = {
    "semantic": 0.55,
    "genre": 0.12,
    "mood": 0.12,
    "trope": 0.10,
    "pacing": 0.04,
    "lexical": 0.07,
}


def score_candidate(
    c: Candidate,
    profile: TasteProfile | None,
    *,
    semantic_available: bool,
    weights: dict[str, float] | None = None,
) -> Ranked:
    """Weights renormalise over the factors that are actually available for this candidate,
    so a book without an embedding is judged on metadata instead of being scored as dissimilar."""
    w = dict(weights or DEFAULT_WEIGHTS)
    factors: list[Factor] = []
    use_sem = semantic_available and c.semantic is not None
    if not use_sem:
        w.pop("semantic", None)
    if profile is None or profile.is_empty():
        for k in ("genre", "mood", "trope", "pacing"):
            w.pop(k, None)
    if c.lexical <= 0:
        w.pop("lexical", None)
    total_w = sum(w.values()) or 1.0

    def add(name: str, value: float, evidence: str) -> None:
        wt = w[name] / total_w
        factors.append(Factor(name, wt, value, wt * value, evidence))

    if "semantic" in w:
        sem = max(0.0, c.semantic or 0.0)
        add("semantic", sem, f"embedding cosine similarity {c.semantic:.2f}")
    if profile is not None and not profile.is_empty():
        for name, prof, tags in (
            ("genre", profile.genres, c.genres),
            ("mood", profile.moods, c.moods),
            ("trope", profile.tropes, c.tropes),
        ):
            if name in w:
                v, hits = _overlap(prof, tags)
                add(name, v, ("shares " + ", ".join(hits)) if hits else f"no {name} overlap")
        if "pacing" in w:
            match = 1.0 if profile.pacing and c.pacing == profile.pacing else 0.0
            add("pacing", match, f"pacing {c.pacing or 'unknown'} vs preferred {profile.pacing or 'any'}")
    if "lexical" in w:
        add("lexical", c.lexical, "keyword match in title, description or tags")
    score = sum(f.contribution for f in factors)
    if c.exact:  # additive: a book whose title or author matches the query should not be buried by embeddings
        factors.append(Factor("exact_match", EXACT_BONUS, 1.0, EXACT_BONUS, "title or author contains the query"))
        score += EXACT_BONUS
    return Ranked(c.book_id, score, factors)


def rank(
    cands: list[Candidate],
    profile: TasteProfile | None,
    *,
    semantic_available: bool,
    author_repeat_penalty: float = 0.04,
    weights: dict[str, float] | None = None,
) -> list[Ranked]:
    scored = [score_candidate(c, profile, semantic_available=semantic_available, weights=weights) for c in cands]
    by_id = {c.book_id: c for c in cands}
    scored.sort(key=lambda r: (-r.score, r.book_id))
    # greedy diversity pass: demote repeated authors
    seen: dict[int, int] = {}
    adjusted: list[Ranked] = []
    for r in scored:
        reps = max((seen.get(a, 0) for a in by_id[r.book_id].author_ids), default=0)
        if reps and author_repeat_penalty:
            pen = author_repeat_penalty * reps
            r.factors.append(Factor("diversity", 1.0, -pen, -pen, f"author already appears {reps}x above"))
            r.score -= pen
        for a in by_id[r.book_id].author_ids:
            seen[a] = seen.get(a, 0) + 1
        adjusted.append(r)
    adjusted.sort(key=lambda r: (-r.score, r.book_id))
    return adjusted


def minmax(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    mx = max(values.values())
    if mx <= 0 or math.isnan(mx):
        return {k: 0.0 for k in values}
    return {k: v / mx for k, v in values.items()}


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0
