import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import test from "node:test";

import { indexPapers, keywordsFor, rankInstitutions, search, sourceUrl } from "../frontend/app.js";

const { papers } = JSON.parse(readFileSync(new URL("../frontend/catalog.json", import.meta.url)));

test("Korean search finds five real papers with source links", () => {
  const keywords = keywordsFor("배터리 충전 속도를 유지하면서 수명을 늘리는 기술이 필요합니다.");
  assert.deepEqual(keywords, ["battery", "charging", "fast", "lifetime", "degradation"]);
  const hits = search(indexPapers(papers), keywords);
  assert.equal(hits.length, 5);
  for (const hit of hits) assert.ok(sourceUrl(hit.paper.doi) || sourceUrl(hit.paper.id));
  const institutions = rankInstitutions(hits);
  assert.equal(institutions.length, 3);
  for (const org of institutions) {
    assert.equal(org.score, [...org.scores.values()].reduce((sum, value) => sum + value, 0));
    assert.ok(org.paths.every(({ paper, author, institution }) =>
      paper.authorships.some(item => item.author.id === author.id &&
        item.institutions.some(affiliation => affiliation.id === institution.id))));
  }
});

test("unmatched input and empty catalog yield no hits", () => {
  assert.deepEqual(search(indexPapers(papers), keywordsFor("미등록검색어")), []);
  assert.deepEqual(search(indexPapers([]), ["battery"]), []);
});

test("source URL allowlist blocks external and unsafe targets", () => {
  for (const input of ["javascript:alert(1)", "https://openalex.org.evil/W101",
    "https://openalex.org@evil.example/W101", "https://doi.org/10.1234/test\n"]) {
    assert.equal(sourceUrl(input), null);
  }
  assert.equal(sourceUrl("https://openalex.org/W101"), "https://openalex.org/W101");
  assert.equal(sourceUrl("https://doi.org/10.1234/test"), "https://doi.org/10.1234/test");
});
