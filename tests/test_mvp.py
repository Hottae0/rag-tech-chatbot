import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from collector import openalex_client as client
from collector.build_graph import ROOT, build_graph, public_catalog
from retrieval.bm25_search import BM25Search, query_keywords
from retrieval.graph_retrieval import expand_evidence, retrieve

FIXTURE = Path(__file__).parent / "fixtures/openalex_works.json"
W101 = "https://openalex.org/W101"
W102 = "https://openalex.org/W102"
A101 = "https://openalex.org/A101"
I101 = "https://openalex.org/I101"
I102 = "https://openalex.org/I102"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def papers(payload):
    return [client.normalize_work(work) for work in payload["results"][:2]]


def test_key_required(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(client, "open_request", lambda *args, **kwargs: pytest.fail("unexpected request"))
    with pytest.raises(client.OpenAlexError, match="OPENALEX_API_KEY"):
        client.search_works("battery")


@pytest.mark.parametrize(("status", "reason", "attempts"), [
    (401, "인증", 1), (403, "권한", 1), (429, "예산", 1), (503, "서버", 3),
])
def test_http_errors(monkeypatch, status, reason, attempts):
    secret = "fixture-authentication-secret"
    monkeypatch.setenv("OPENALEX_API_KEY", secret)
    monkeypatch.setattr(client.time, "sleep", lambda seconds: None)
    requests = []

    def fail(request, timeout):
        requests.append(request)
        raise HTTPError(request.full_url, status, secret, {}, io.BytesIO(secret.encode()))

    monkeypatch.setattr(client, "open_request", fail)
    with pytest.raises(client.OpenAlexError, match=rf"{status}.*{reason}") as error:
        client.search_works("battery")
    assert len(requests) == attempts
    assert requests[0].get_header("Authorization") == "Bearer " + secret
    assert secret not in requests[0].full_url
    assert secret not in str(error.value)
    assert error.value.__suppress_context__


def test_timeout(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda seconds: None)
    attempts = []

    def fail(request, timeout):
        attempts.append(timeout)
        raise URLError(TimeoutError())

    monkeypatch.setattr(client, "open_request", fail)
    with pytest.raises(client.OpenAlexError, match="시간 초과"):
        client.search_works("battery", anonymous=True)
    assert attempts == [30, 30, 30]


def patch_response(monkeypatch, payload):
    def respond(request, timeout):
        assert request.get_header("Authorization") is None
        response = io.BytesIO(json.dumps(payload).encode())
        response.status = 200
        return response

    monkeypatch.setattr(client, "open_request", respond)


def test_parsing_and_deduplication(monkeypatch, payload):
    patch_response(monkeypatch, payload)
    status, papers = client.search_works("battery", anonymous=True)
    assert status == 200
    assert [paper["id"] for paper in papers] == [W101, W102]
    assert papers[0]["cited_by_count"] == 5
    assert papers[0]["landing_page_url"] == "https://example.org/papers/101"
    assert papers[1]["abstract"] == ""
    assert len(papers[1]["authorships"]) == 2
    assert papers[1]["authorships"][1]["institutions"] == []


def test_bad_response(monkeypatch):
    patch_response(monkeypatch, {"results": None})
    with pytest.raises(client.OpenAlexError, match="목록"):
        client.search_works("battery", anonymous=True)


def test_abstract():
    assert client.reconstruct_abstract({"world": [2], "hello": [0, 1, None, -1]}) == "hello hello world"
    assert client.reconstruct_abstract(None) == ""


def test_edges_follow_publication_evidence(papers):
    graph = build_graph(papers)
    assert graph[W101][A101]["AUTHORED_BY"]["relation"] == "AUTHORED_BY"
    assert graph[A101][I101][W101]["evidence_paper"] == W101
    assert graph[A101][I102][W102]["evidence_paper"] == W102
    assert W102 not in graph[A101][I101]
    assert W101 not in graph[A101][I102]


def test_citations_only_from_source(papers):
    graph = build_graph(papers)
    citations = {(source, target) for source, target, relation in graph.edges(keys=True) if relation == "CITES"}
    assert citations == {(W101, W102), (W101, "https://openalex.org/W999")}
    assert graph.nodes["https://openalex.org/W999"]["collected"] is False


def test_bm25_ranking_and_sources(papers):
    first, second = BM25Search(papers).search("degradation fast charging and thermal")
    assert first["paper"]["id"] == W101
    assert first["score"] > second["score"]
    assert "degradation" in first["matched_terms"]
    assert first["paper"]["doi"] == "https://doi.org/10.1234/test.battery"
    assert second["paper"]["doi"] is None
    assert second["paper"]["landing_page_url"] is None
    assert second["paper"]["source"] == W102


def test_affiliation_ranking_keeps_provenance_and_scores_once(papers):
    graph = build_graph(papers)
    hits = [{"paper": papers[0], "score": 2.0}, {"paper": papers[1], "score": 1.0}]
    first, second = expand_evidence(hits, graph)["institutions"]
    assert (first["id"], first["score"], first["paper_count"]) == (I101, 2.0, 1)
    assert len(first["paths"]) == 2
    assert first["paper_ids"] == [W101]
    assert (second["id"], second["score"], second["paper_count"]) == (I102, 1.0, 1)
    assert second["paths"][0]["paper_id"] == W102
    only_first = retrieve("충전 속도와 배터리 열화", papers, graph)
    assert [org["id"] for org in only_first["institutions"]] == [I101]
    assert only_first["topics"][0]["name"] == "Battery research"
    assert only_first["cited_papers"][0]["id"] == W102


def test_korean_query():
    assert {"battery", "fast", "charging", "degradation", "lifetime"} == set(
        query_keywords("배터리 충전 속도와 수명")
    )


def test_empty_inputs_and_results(monkeypatch, papers):
    patch_response(monkeypatch, {"results": []})
    assert client.search_works("battery", anonymous=True) == (200, [])
    assert retrieve("미등록검색어", papers, build_graph(papers))["papers"] == []
    assert retrieve("battery", [], build_graph([]))["institutions"] == []


def test_catalog_excludes_private_fields_and_secrets(monkeypatch, papers):
    secret = "fixture-secret-never-published"
    monkeypatch.setenv("OPENALEX_API_KEY", secret)
    papers[0]["api_key"] = secret
    papers[0]["abstract"] = secret
    papers[0]["landing_page_url"] = "https://example.org/?leaked=" + secret
    papers[0]["authorships"][0]["author"]["private_field"] = secret
    exported = json.dumps(public_catalog(papers, {"api_key": secret, "query": secret}))
    assert secret not in exported and "abstract" not in exported
    for path in [ROOT / "data/catalog.json", ROOT / "frontend/catalog.json", ROOT / "docs/catalog.json"]:
        serialized = path.read_text(encoding="utf-8")
        assert "abstract" not in serialized
        assert "api_key" not in serialized.lower()
        assert "Bearer " not in serialized


def test_static_deployment_files_match():
    for filename in ("index.html", "app.js", "style.css", "catalog.json"):
        assert (ROOT / "frontend" / filename).read_bytes() == (ROOT / "docs" / filename).read_bytes()
    assert (ROOT / "docs/catalog.json").read_bytes() == (ROOT / "data/catalog.json").read_bytes()
