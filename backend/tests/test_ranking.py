import numpy as np
import pytest

from app.services.ranking import (
    Candidate,
    build_profile,
    jaccard,
    minmax,
    rank,
    score_candidate,
    tag_token_matches,
    taste_vector,
    tokenize,
)

FS = frozenset


def test_tokenize_drops_stopwords():
    assert tokenize("I want a cozy book about found family") == ["cozy", "found", "family"]


@pytest.mark.parametrize(
    "tokens,tag,expected",
    [
        (["cozy"], "cozy", True),
        (["haunted", "houses"], "haunted house", True),
        (["houses"], "haunted house", False),
        (["mysteries"], "mystery", True),
        (["space"], "science fiction", False),
    ],
)
def test_tag_token_matches(tokens, tag, expected):
    assert tag_token_matches(tokens, tag) is expected


def test_profile_scaling_and_explicit_pinning():
    p = build_profile(
        [
            (2.0, FS({"fantasy"}), FS({"cozy"}), FS()),
            (1.0, FS({"fantasy", "horror"}), FS(), FS()),
            (-2.0, FS({"horror"}), FS(), FS()),
        ],
        pref_moods=["dark"],
    )
    assert p.genres["fantasy"] == pytest.approx(0.8) and "horror" not in p.genres  # disliked net-negative
    assert p.moods["dark"] == 1.0 and p.moods["cozy"] == pytest.approx(0.8)
    assert not p.is_empty() and build_profile([]).is_empty()


def test_taste_vector_pulls_toward_liked_and_away_from_disliked():
    a, b = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    v = taste_vector([(2.0, a), (-1.0, b)])
    assert v[0] > 0 and v[1] < 0 and np.linalg.norm(v) == pytest.approx(1.0)
    assert taste_vector([]) is None
    assert taste_vector([(1.0, a), (-1.0, a)]) is None  # cancels out: no signal


def test_scores_use_only_available_factors_and_sum_to_one_weight():
    c = Candidate(1, semantic=None, genres=FS({"fantasy"}))
    prof = build_profile([], pref_genres=["fantasy"])
    r = score_candidate(c, prof, semantic_available=True)
    assert {f.factor for f in r.factors} == {"genre", "mood", "trope", "pacing"}
    assert sum(f.weight for f in r.factors) == pytest.approx(1.0)
    assert next(f for f in r.factors if f.factor == "genre").value == 0.5  # 1.0 affinity / 2 normaliser


def test_ranking_on_controlled_dataset_semantic_dominates_but_metadata_breaks_ties():
    prof = build_profile([], pref_genres=["fantasy"], pref_moods=["cozy"])
    cands = [
        Candidate(1, (1,), semantic=0.80, genres=FS({"fantasy"}), moods=FS({"cozy"})),  # best on both
        Candidate(2, (2,), semantic=0.80, genres=FS({"horror"})),  # same semantic, no metadata
        Candidate(3, (3,), semantic=0.30, genres=FS({"fantasy"}), moods=FS({"cozy"})),  # metadata but far
        Candidate(4, (4,), semantic=0.85, genres=FS({"horror"})),
    ]
    order = [r.book_id for r in rank(cands, prof, semantic_available=True)]
    assert order == [1, 4, 2, 3]


def test_missing_embedding_not_treated_as_dissimilar():
    prof = build_profile([], pref_genres=["fantasy"], pref_moods=["cozy"], pref_tropes=["quest"])
    full = Candidate(1, semantic=0.2, genres=FS({"horror"}))
    meta_only = Candidate(2, semantic=None, genres=FS({"fantasy"}), moods=FS({"cozy"}), tropes=FS({"quest"}))
    order = [r.book_id for r in rank([full, meta_only], prof, semantic_available=True)]
    assert order[0] == 2


def test_author_diversity_penalty_is_applied_and_explained():
    cands = [Candidate(i, (7,), semantic=0.9 - i * 0.01) for i in range(3)] + [Candidate(9, (8,), semantic=0.85)]
    out = rank(cands, None, semantic_available=True, author_repeat_penalty=0.1)
    assert [r.book_id for r in out][:2] == [0, 9]
    assert any(f.factor == "diversity" and "author" in f.evidence for f in out[-1].factors) or any(
        f.factor == "diversity" for r in out for f in r.factors
    )


def test_negative_semantic_is_clamped():
    r = score_candidate(Candidate(1, semantic=-0.5), None, semantic_available=True)
    assert r.score == 0.0


def test_ranking_is_deterministic_on_ties():
    cands = [Candidate(i, semantic=0.5) for i in (5, 3, 9)]
    assert [r.book_id for r in rank(cands, None, semantic_available=True)] == [3, 5, 9]


def test_helpers():
    assert minmax({1: 2.0, 2: 1.0}) == {1: 1.0, 2: 0.5} and minmax({}) == {} and minmax({1: 0.0}) == {1: 0.0}
    assert jaccard(FS({"a", "b"}), FS({"b", "c"})) == pytest.approx(1 / 3) and jaccard(FS(), FS()) == 0.0
