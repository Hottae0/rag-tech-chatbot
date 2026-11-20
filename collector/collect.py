"""Verify OpenAlex access or collect a bounded batch of work metadata."""

import argparse
from datetime import datetime, timezone

from collector.build_graph import ROOT, write_json
from collector.openalex_client import DEFAULT_QUERY, OpenAlexError, search_works


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--check", action="store_true", help="배터리 논문 3건을 조회하고 저장하지 않습니다.")
    parser.add_argument("--anonymous", action="store_true", help="명시적으로 OpenAlex 키 없는 접근을 사용합니다.")
    args = parser.parse_args()
    if not args.check and not 20 <= args.limit <= 100:
        parser.error("--limit 범위는 20~100입니다.")
    query = "lithium ion battery" if args.check else args.query
    try:
        status, papers = search_works(query, 3 if args.check else args.limit, anonymous=args.anonymous)
        print(f"HTTP {status} | {'익명' if args.anonymous else 'Bearer'} | 논문 {len(papers)}건")
        if args.check:
            for paper in papers:
                print(f"{paper['publication_year'] or '연도 미상'} | {paper['title']} | {paper['id']}")
            return 0 if len(papers) == 3 else 1
        if not papers:
            parser.exit(1, "수집할 논문이 없습니다. 기존 로컬 파일을 보존했습니다.\n")
        if len(papers) < args.limit:
            parser.exit(1, f"요청 {args.limit}건 중 {len(papers)}건을 찾았습니다. 기존 로컬 파일을 보존했습니다.\n")
        write_json(ROOT / "data/papers.json", {
            "provenance": {
                "source": "OpenAlex", "query": query,
                "access": "anonymous" if args.anonymous else "bearer",
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
            "papers": papers,
        })
    except (OpenAlexError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
