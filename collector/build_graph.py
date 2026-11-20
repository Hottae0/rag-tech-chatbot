"""Build a directed evidence graph and export a metadata-only catalog."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PAPER_FIELDS = ("id", "title", "publication_year", "doi", "cited_by_count")


def build_graph(papers):
    graph = nx.MultiDiGraph()
    for paper in papers:
        graph.add_node(paper["id"], type="Paper", name=paper["title"],
                       publication_year=paper["publication_year"], collected=True)
    for paper in papers:
        paper_id = paper["id"]
        for authorship in paper["authorships"]:
            author = authorship["author"]
            graph.add_node(author["id"], type="Researcher", name=author["name"])
            graph.add_edge(paper_id, author["id"], key="AUTHORED_BY", relation="AUTHORED_BY")
            for institution in authorship["institutions"]:
                graph.add_node(institution["id"], type="Institution", name=institution["name"])
                graph.add_edge(author["id"], institution["id"], key=paper_id,
                               relation="AFFILIATED_WITH", evidence_paper=paper_id)
        if topic := paper["primary_topic"]:
            graph.add_node(topic["id"], type="Topic", name=topic["name"])
            graph.add_edge(paper_id, topic["id"], key="ABOUT", relation="ABOUT")
        for reference in paper["referenced_works"]:
            if reference not in graph:
                graph.add_node(reference, type="Paper", collected=False)
            graph.add_edge(paper_id, reference, key="CITES", relation="CITES")
    return graph


def public_catalog(papers, provenance):
    def public_entity(entity):
        return {"id": entity["id"], "name": entity["name"]}

    return {
        "schema_version": 1,
        "provenance": {
            "source": "OpenAlex",
            "collected_at": provenance.get("collected_at"),
            "access": provenance.get("access"),
        },
        "papers": [
            {
                **{field: paper[field] for field in PUBLIC_PAPER_FIELDS},
                "source": paper["id"],
                "authorships": [
                    {"author": public_entity(item["author"]),
                     "institutions": [public_entity(org) for org in item["institutions"]]}
                    for item in paper["authorships"]
                ],
                "primary_topic": public_entity(paper["primary_topic"]) if paper["primary_topic"] else None,
                "referenced_works": paper["referenced_works"],
            }
            for paper in papers
        ],
    }


def write_json(path, payload):
    # Replace atomically in the destination directory so readers never see partial JSON.
    with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as handle:
        try:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.close()
            os.replace(handle.name, path)
        finally:
            Path(handle.name).unlink(missing_ok=True)


def export_graph(dataset, root=ROOT):
    papers = dataset["papers"]
    graph = build_graph(papers)
    catalog = public_catalog(papers, dataset["provenance"])
    write_json(root / "data/graph.json", nx.node_link_data(graph, edges="edges"))
    for directory in ("data", "frontend", "docs"):
        write_json(root / directory / "catalog.json", catalog)
    return graph


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/papers.json")
    args = parser.parse_args()
    try:
        graph = export_graph(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"입력 데이터를 읽을 수 없습니다 ({type(error).__name__}).\n")
    print(f"그래프 노드 {graph.number_of_nodes()}개, 엣지 {graph.number_of_edges()}개")
