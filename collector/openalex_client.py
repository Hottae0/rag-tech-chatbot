"""Bounded OpenAlex metadata searches with sanitized error messages."""

import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = "https://api.openalex.org/works"
FIELDS = ("id", "title", "abstract_inverted_index", "publication_year", "doi",
          "cited_by_count", "authorships", "primary_topic", "referenced_works",
          "primary_location")
DEFAULT_QUERY = "lithium-ion battery degradation AND fast charging"


class OpenAlexError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    """Keep the authorization header on the intended endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(request, timeout):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


def request_page(params, key):
    headers = {"User-Agent": "TechBridgeAI/0.1", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = Request(BASE_URL + "?" + urlencode(params), headers=headers)
    for attempt in range(3):
        try:
            with open_request(request, timeout=30) as response:
                payload = json.load(response)
                if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                    raise OpenAlexError("OpenAlex 응답에 논문 목록이 없습니다.")
                return response.status, payload
        except HTTPError as error:
            status = error.code
            error.close()
            if status == 401:
                message = "OpenAlex HTTP 401: 인증 오류"
            elif status == 403:
                message = "OpenAlex HTTP 403: 키 활성화 또는 접근 권한 확인 필요"
            elif status == 429:
                message = "OpenAlex HTTP 429: 일일 무료 예산 또는 호출 속도 제한"
            elif 500 <= status < 600:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                message = f"OpenAlex HTTP {status}: 서버 오류"
            else:
                message = f"OpenAlex HTTP {status}: 요청 실패"
        except (TimeoutError, URLError) as error:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            timed_out = isinstance(getattr(error, "reason", error), TimeoutError)
            message = "OpenAlex 연결 시간 초과" if timed_out else "OpenAlex 네트워크 연결 실패"
        except (UnicodeError, ValueError):
            message = "OpenAlex JSON 응답을 해석할 수 없습니다."
        raise OpenAlexError(message) from None


def as_object(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def clean_text(value):
    return value.strip() if isinstance(value, str) else ""


def openalex_id(value, kind):
    pattern = r"(?:https://openalex\.org/)?" + kind + r"[1-9][0-9]*"
    if isinstance(value, str) and re.fullmatch(pattern, value):
        return "https://openalex.org/" + value.rsplit("/", 1)[-1]
    return None


def safe_url(value):
    if not isinstance(value, str) or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme in {"https", "http"} and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return None


def reconstruct_abstract(index):
    positions = {}
    for word, indices in as_object(index).items():
        if isinstance(word, str):
            for position in as_list(indices):
                if type(position) is int and position >= 0:
                    positions[position] = word
    return " ".join(positions[position] for position in sorted(positions))


def entity(value, kind):
    source = as_object(value)
    entity_id = openalex_id(source.get("id"), kind)
    if entity_id:
        return {"id": entity_id, "name": clean_text(source.get("display_name"))}


def normalize_work(value):
    work = as_object(value)
    work_id = openalex_id(work.get("id"), "W")
    title = clean_text(work.get("title"))
    if not work_id or not title:
        return None

    authors = {}
    for record in map(as_object, as_list(work.get("authorships"))):
        author = entity(record.get("author"), "A")
        if not author:
            continue
        entry = authors.setdefault(author["id"], {"author": author, "institutions": {}})
        for institution in as_list(record.get("institutions")):
            institution = entity(institution, "I")
            if institution:
                entry["institutions"][institution["id"]] = institution

    doi = clean_text(work.get("doi"))
    if re.fullmatch(r"10\.\d{4,}/\S+", doi):
        doi = "https://doi.org/" + doi
    doi = safe_url(doi)
    if doi and not re.fullmatch(r"https?://doi\.org/10\.\d{4,}/\S+", doi):
        doi = None
    location = as_object(work.get("primary_location"))
    return {
        "id": work_id, "title": title,
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "publication_year": work.get("publication_year") if type(work.get("publication_year")) is int else None,
        "doi": doi,
        "cited_by_count": work.get("cited_by_count") if type(work.get("cited_by_count")) is int else 0,
        "authorships": [
            {"author": entry["author"], "institutions": list(entry["institutions"].values())}
            for entry in authors.values()
        ],
        "primary_topic": entity(work.get("primary_topic"), "T"),
        "referenced_works": sorted({
            reference for value in as_list(work.get("referenced_works"))
            if (reference := openalex_id(value, "W")) and reference != work_id
        }),
        "landing_page_url": safe_url(location.get("landing_page_url")),
        "source": work_id,
    }


def search_works(query, limit=30, *, anonymous=False):
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
        raise ValueError("검색어는 1~500자여야 합니다.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("논문 건수는 1~100이어야 합니다.")
    key = "" if anonymous else os.getenv("OPENALEX_API_KEY", "").strip()
    if not key and not anonymous:
        raise OpenAlexError("OPENALEX_API_KEY 환경변수가 필요합니다.")
    if any(character.isspace() for character in key):
        raise OpenAlexError("OpenAlex 키에 공백이 포함되어 있습니다.")
    params = {"search": query.strip(), "per_page": limit, "select": ",".join(FIELDS)}
    papers = {}
    for page in range(1, 4):
        status, payload = request_page({**params, "page": page}, key)
        for value in payload["results"]:
            if (work := normalize_work(value)):
                papers.setdefault(work["id"], work)
        if len(papers) >= limit or len(payload["results"]) < limit or anonymous:
            break
        if page < 3:
            time.sleep(1)
    return status, list(papers.values())[:limit]
