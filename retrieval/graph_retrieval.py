"""Expand ranked papers through publication-time affiliations."""

from retrieval.bm25_search import BM25Search, query_keywords

INSTITUTION_LIMIT = 3


def expand_evidence(hits, graph):
    researchers = {}
    institutions = {}
    topics = {}
    citations = {}
    for hit in hits:
        paper = hit["paper"]
        paper_id = paper["id"]
        for _, target, edge in graph.out_edges(paper_id, data=True):
            node = graph.nodes[target]
            relation = edge["relation"]
            if relation == "ABOUT":
                topics[target] = {"id": target, "name": node["name"]}
            if relation == "CITES":
                citations[target] = {"id": target, "title": node.get("name"), "collected": node["collected"]}
            if relation != "AUTHORED_BY":
                continue
            author = {"id": target, "name": node["name"]}
            researchers[target] = author
            for _, institution_id, affiliation in graph.out_edges(target, data=True):
                if (affiliation["relation"] != "AFFILIATED_WITH"
                        or affiliation["evidence_paper"] != paper_id):
                    continue
                org = institutions.setdefault(institution_id, {
                    "id": institution_id, "name": graph.nodes[institution_id]["name"],
                    "papers": {}, "researchers": {}, "paths": [],
                })
                org["papers"][paper_id] = hit["score"]
                org["researchers"][target] = author
                org["paths"].append({
                    "paper_id": paper_id, "paper_title": paper["title"],
                    "researcher_id": target, "researcher_name": node["name"],
                    "institution_id": institution_id, "institution_name": org["name"],
                })
    ranked = []
    for org in institutions.values():
        paper_scores = org.pop("papers")
        org.update(score=sum(paper_scores.values()), paper_ids=list(paper_scores),
                   paper_count=len(paper_scores), researchers=list(org["researchers"].values()))
        ranked.append(org)
    ranked.sort(key=lambda org: (-org["score"], org["id"]))
    return {
        "researchers": list(researchers.values()), "institutions": ranked[:INSTITUTION_LIMIT],
        "topics": list(topics.values()), "cited_papers": list(citations.values()),
    }


def retrieve(question, papers, graph, top_k=5):
    hits = BM25Search(papers).search(question, top_k)
    return {
        "question": question, "keywords": query_keywords(question), "papers": hits,
        **expand_evidence(hits, graph),
    }


if __name__ == "__main__":
    import argparse
    import json

    import networkx as nx

    from collector.build_graph import ROOT, build_graph

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= len(args.question.strip()) <= 500 or not 1 <= args.top_k <= 100:
        parser.error("질문은 1~500자, --top-k는 1~100이어야 합니다.")
    try:
        # A fresh clone can search the same public metadata used by the browser.
        local_papers = ROOT / "data/papers.json"
        if local_papers.exists():
            papers = json.loads(local_papers.read_text(encoding="utf-8"))["papers"]
            graph = build_graph(papers)
        else:
            papers = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))["papers"]
            graph = nx.node_link_graph(
                json.loads((ROOT / "data/graph.json").read_text(encoding="utf-8")), edges="edges"
            )
        result = retrieve(args.question, papers, graph, args.top_k)
        for hit in result["papers"]:
            hit["paper"].pop("abstract", None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"검색 데이터를 읽을 수 없습니다 ({type(error).__name__}). 먼저 그래프를 구축하세요.\n")
