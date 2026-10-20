R = "/api/v1/recommendations"
L = "/api/v1/library"


def rt(client, **params):
    r = client.get(R, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def names(body):
    return [i["book"]["title"] for i in body["items"]]


def rate(client, bid, v):
    assert client.put(f"/api/v1/books/{bid}/rating", json={"value": v}).status_code == 200


def test_cold_start_is_empty_and_says_so(client, auth, small_catalog):
    b = rt(client)
    assert b["items"] == [] and b["meta"]["cold_start"] is True and "preferences" in b["meta"]["notice"]


def test_requires_login(client, small_catalog):
    assert client.get(R).status_code == 401


def test_recommends_from_ratings_and_excludes_read(client, auth, small_catalog):
    ids = small_catalog
    rate(client, ids["Teacup Mornings"], 5)
    client.post(L, json={"book_id": ids["Teacup Mornings"], "status": "completed"})
    b = rt(client)
    ns = names(b)
    assert "Teacup Mornings" not in ns  # rated + completed: excluded
    assert ns[0] == "Kisses in the Mist" and b["meta"]["mode_used"] == "embedding+metadata"
    top = b["items"][0]
    assert "Teacup Mornings" in top["explanation"] and "cozy" in top["explanation"]
    assert any(f["factor"] == "semantic" for f in top["factors"])
    assert "Teacup Mornings" in names(rt(client, exclude_read=False))


def test_completed_book_without_rating_also_excluded(client, auth, small_catalog):
    ids = small_catalog
    rate(client, ids["Teacup Mornings"], 5)
    client.post(L, json={"book_id": ids["Kisses in the Mist"], "status": "completed"})
    assert "Kisses in the Mist" not in names(rt(client))
    assert "Kisses in the Mist" in names(rt(client, exclude_read=False))


def test_saved_books_influence_but_are_not_excluded(client, auth, small_catalog):
    client.post(L, json={"book_id": small_catalog["Starship Lullaby"], "status": "want_to_read"})
    ns = names(rt(client))
    assert "Starship Lullaby" in ns  # saved is not "read"


def test_low_rating_pushes_similar_books_down(client, auth, small_catalog):
    ids = small_catalog
    rate(client, ids["Teacup Mornings"], 5)
    rate(client, ids["Ashes of the Manor"], 1)
    ns = names(rt(client))
    assert ns.index("Kisses in the Mist") < ns.index("Iron Empire")
    assert "Ashes of the Manor" not in ns


def test_preferences_drive_recommendations_without_any_ratings(client, auth, small_catalog):
    client.put("/api/v1/me/preferences", json={"genres": ["fantasy"], "pacing": "medium"})
    b = rt(client)
    assert names(b)[0] == "The Dragon's Spell"
    assert b["meta"]["mode_used"] == "metadata_only"  # no rated/saved books: no taste vector, said explicitly
    assert b["meta"]["notice"]


def test_avoided_content_warnings_are_hard_filters(client, auth, small_catalog):
    client.put("/api/v1/me/preferences", json={"genres": ["horror", "fantasy"], "avoid_content_warnings": ["Violence"]})
    assert "Ashes of the Manor" not in names(rt(client))
    assert "Ashes of the Manor" not in names(rt(client, exclude_read=False))


def test_filters_apply_to_recommendations(client, auth, small_catalog):
    rate(client, small_catalog["Teacup Mornings"], 5)
    assert set(names(rt(client, pacing="fast"))) <= {"Starship Lullaby"}


def test_metadata_only_when_embedder_unavailable(client, auth, small_catalog_no_embeddings):
    ids = small_catalog_no_embeddings
    rate(client, ids["Teacup Mornings"], 5)
    b = rt(client)
    assert b["meta"]["mode_used"] == "metadata_only" and b["meta"]["semantic_available"] is False
    assert names(b)[0] == "Kisses in the Mist"  # shares mood 'cozy'
    assert all(f["factor"] != "semantic" for i in b["items"] for f in i["factors"])


def test_recommendations_are_per_user(client, auth, small_catalog):
    from tests.conftest import new_client

    rate(client, small_catalog["Teacup Mornings"], 5)
    other = new_client("o@example.com")
    assert other.get(R).json()["meta"]["cold_start"] is True


def test_pagination(client, auth, small_catalog):
    rate(client, small_catalog["Teacup Mornings"], 5)
    p1 = rt(client, page_size=2, page=1)
    p2 = rt(client, page_size=2, page=2)
    assert len(p1["items"]) == 2 and not set(names(p1)) & set(names(p2))
