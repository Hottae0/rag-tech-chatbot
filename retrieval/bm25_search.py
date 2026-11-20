"""Okapi BM25 with positive IDF and a battery-domain Korean dictionary."""

import math
import re
from collections import Counter

KOREAN_KEYWORDS = {
    "리튬이온": "lithium ion", "리튬 이온": "lithium ion",
    "배터리": "battery", "충전": "charging", "급속 충전": "fast charging",
    "급속충전": "fast charging", "고속 충전": "fast charging",
    "고속충전": "fast charging", "충전 속도": "fast charging",
    "수명": "lifetime degradation", "열화": "degradation", "전기차": "electric vehicle",
    "반도체": "semiconductor", "리튬 도금": "lithium plating",
    "전해질": "electrolyte", "음극": "anode", "양극": "cathode", "온도": "temperature",
}
STOP_WORDS = set("a an and are as at be by can could for from how i in is it of on or that the this to was we what which with would".split())
WORD_PATTERN = re.compile(r"[a-z]+[0-9]*|[0-9]+")


def tokenize(value):
    return [
        {"batteries": "battery", "vehicles": "vehicle", "lifetimes": "lifetime"}.get(word, word)
        for word in WORD_PATTERN.findall(value.lower()) if word not in STOP_WORDS
    ]


def query_keywords(question):
    translated = " ".join(
        english for korean, english in KOREAN_KEYWORDS.items() if korean in question
    )
    return list(dict.fromkeys(tokenize(question + " " + translated)))


class BM25Search:
    def __init__(self, papers):
        self.papers = papers
        self.documents = [Counter(tokenize(
            " ".join((paper["title"], paper.get("abstract", ""),
                      (paper.get("primary_topic") or {}).get("name", "")))
        )) for paper in papers]
        self.lengths = [sum(document.values()) for document in self.documents]
        self.average_length = sum(self.lengths) / max(len(self.documents), 1) or 1
        self.frequency = Counter(word for document in self.documents for word in document)

    def search(self, question, top_k=5):
        terms = query_keywords(question)
        hits = []
        for paper, document, length in zip(self.papers, self.documents, self.lengths):
            normalization = 1.5 * (0.25 + 0.75 * length / self.average_length)
            score = 0.0
            matches = []
            for term in terms:
                if term in document:
                    frequency = self.frequency[term]
                    idf = math.log1p((len(self.documents) - frequency + 0.5) / (frequency + 0.5))
                    count = document[term]
                    score += idf * count * 2.5 / (count + normalization)
                    matches.append(term)
            if score > 0:
                hits.append({"paper": paper, "score": score, "matched_terms": matches})
        hits.sort(key=lambda hit: (-hit["score"], hit["paper"]["id"]))
        return hits[:max(0, top_k)]
