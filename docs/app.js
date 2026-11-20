const koreanKeywords = {
  "리튬이온": "lithium ion", "리튬 이온": "lithium ion",
  "배터리": "battery", "충전": "charging", "급속 충전": "fast charging",
  "급속충전": "fast charging", "고속 충전": "fast charging",
  "고속충전": "fast charging", "충전 속도": "fast charging",
  "수명": "lifetime degradation", "열화": "degradation", "전기차": "electric vehicle",
  "반도체": "semiconductor", "리튬 도금": "lithium plating",
  "전해질": "electrolyte", "음극": "anode", "양극": "cathode", "온도": "temperature",
};
const stopWords = new Set("a an and are as at be by can could for from how i in is it of on or that the this to was we what which with would".split(" "));
const singular = { batteries: "battery", vehicles: "vehicle", lifetimes: "lifetime" };
const example = "배터리 충전 속도를 유지하면서 수명을 늘리는 기술이 필요합니다.";

function tokenize(value) {
  return (value.toLowerCase().match(/[a-z]+[0-9]*|[0-9]+/g) ?? [])
    .filter(word => !stopWords.has(word))
    .map(word => Object.hasOwn(singular, word) ? singular[word] : word);
}

export function keywordsFor(question) {
  const translated = Object.entries(koreanKeywords)
    .filter(([word]) => question.includes(word))
    .map(([, english]) => english);
  return [...new Set(tokenize([question, ...translated].join(" ")))];
}

export function indexPapers(papers) {
  const frequencies = new Map();
  let totalLength = 0;
  const documents = papers.map(paper => {
    const words = tokenize([paper.title, paper.primary_topic?.name ?? ""].join(" "));
    const terms = new Map();
    for (const word of words) terms.set(word, (terms.get(word) ?? 0) + 1);
    for (const word of terms.keys()) frequencies.set(word, (frequencies.get(word) ?? 0) + 1);
    totalLength += words.length;
    return { paper, length: words.length, terms };
  });
  return { documents, frequencies, averageLength: totalLength / papers.length || 1 };
}

const compareId = (first, second) => first < second ? -1 : Number(first !== second);

export function search(index, keywords) {
  const { documents, frequencies, averageLength } = index;
  return documents.map(({ paper, length, terms }) => {
    const matched = keywords.filter(term => terms.has(term));
    const normalization = 1.5 * (0.25 + 0.75 * length / averageLength);
    const score = matched.reduce((total, term) => {
      const frequency = frequencies.get(term);
      const idf = Math.log1p((documents.length - frequency + 0.5) / (frequency + 0.5));
      const count = terms.get(term);
      return total + idf * count * 2.5 / (count + normalization);
    }, 0);
    return { paper, score, matched };
  }).filter(hit => hit.score > 0)
    .sort((a, b) => b.score - a.score || compareId(a.paper.id, b.paper.id))
    .slice(0, 5);
}

export function rankInstitutions(hits) {
  const institutions = new Map();
  for (const { paper, score } of hits) {
    for (const { author, institutions: affiliations } of paper.authorships) {
      for (const institution of affiliations) {
        if (!institutions.has(institution.id)) {
          institutions.set(institution.id, { ...institution, scores: new Map(), authors: new Map(), paths: [] });
        }
        const org = institutions.get(institution.id);
        org.scores.set(paper.id, score);
        org.authors.set(author.id, author);
        org.paths.push({ paper, author, institution });
      }
    }
  }
  return [...institutions.values()].map(org => ({
    ...org, score: [...org.scores.values()].reduce((sum, score) => sum + score, 0),
  })).sort((a, b) => b.score - a.score || compareId(a.id, b.id)).slice(0, 3);
}

export function sourceUrl(value) {
  if (typeof value !== "string") return null;
  if (/^https:\/\/openalex\.org\/[WAIT][1-9]\d*$/.test(value)) return value;
  if (/^https?:\/\/doi\.org\/10\.\d{4,}\/[^\s\\\x00-\x1f\x7f]+$/.test(value)) return value;
  return null;
}

const named = (record) => record.name || record.id.split("/").pop();
const authorList = (items) => items.map(named).join(", ");
const get = (id) => document.getElementById(id);

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function link(text, url) {
  const href = sourceUrl(url);
  if (!href) return element("span", text);
  const node = element("a", text);
  node.href = href;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}

function paperCard({ paper, score, matched }) {
  const card = element("article", undefined, "card");
  const authors = paper.authorships.map(({ author }) => author);
  const title = element("h3");
  title.append(link(paper.title, sourceUrl(paper.doi) || paper.id));
  card.append(
    element("p", `${paper.publication_year ?? "연도 미상"} · 관련성 ${score.toFixed(3)}`, "meta"),
    title,
    element("p", (authorList(authors.slice(0, 4)) || "저자 정보 없음") + (authors.length > 4 ? ` 외 ${authors.length - 4}명` : "")),
    element("p", `일치 키워드 · ${matched.join(", ")}`, "meta"),
    link(sourceUrl(paper.doi) ? "DOI 원문 페이지" : "OpenAlex 논문 정보", sourceUrl(paper.doi) || paper.id),
  );
  return card;
}

function institutionCard(org, question) {
  const card = element("article", undefined, "card");
  const heading = element("h3");
  heading.append(link(named(org), org.id));
  const details = element("details");
  details.append(element("summary", "추천 근거 보기"), element("p", `검색 질문 · ${question}`));
  const evidence = element("ul", undefined, "evidence");
  for (const { paper, author, institution } of org.paths) {
    const item = element("li");
    item.append(link(paper.title, paper.id), " → ", link(named(author), author.id), " → ", link(named(institution), institution.id));
    evidence.append(item);
  }
  details.append(evidence);
  card.append(
    heading, element("p", `관련 논문 ${org.scores.size}건 · 추천 점수 ${org.score.toFixed(3)}`, "meta"),
    element("p", authorList([...org.authors.values()])),
    element("p", "관련 논문의 저자가 발표 당시 이 기관에 소속되어 있었습니다.", "meta"),
    details,
  );
  return card;
}

function svgElement(tag, attributes, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

function graphRow(svg, path, row) {
  const nodes = [
    { title: path.paper.title, id: path.paper.id, type: "논문" },
    { title: named(path.author), id: path.author.id, type: "연구자" },
    { title: named(path.institution), id: path.institution.id, type: "연구기관" },
  ];
  const xPositions = [12, 284, 452];
  const widths = [245, 142, 240];
  const y = 32 + row * 46;
  svg.append(svgElement("path", { d: `M257 ${y + 17} H284 M426 ${y + 17} H452`, class: "graph-edge" }));
  nodes.forEach(({ title, id, type }, index) => {
    const x = xPositions[index];
    const node = svgElement("g", {
      class: "graph-node", role: "button", tabindex: "0", "aria-label": `${type} ${title}`,
    });
    const maxLength = index === 1 ? 16 : 28;
    const label = title.length > maxLength ? title.slice(0, maxLength - 1) + "…" : title;
    node.append(
      svgElement("rect", { x, y, width: widths[index], height: 34, rx: 6 }),
      svgElement("text", { x: x + 8, y: y + 21 }, label),
      svgElement("title", {}, title),
    );
    const show = () => get("graph-detail").replaceChildren(element("strong", `${type} · `), link(title, id));
    node.addEventListener("click", show);
    node.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        show();
      }
    });
    svg.append(node);
  });
}

function renderGraph(org) {
  const paths = org.paths.slice(0, 6);
  const svg = svgElement("svg", { viewBox: `0 0 704 ${38 + paths.length * 46}`, "aria-label": "논문, 연구자 및 소속기관 연결" });
  ["논문", "연구자", "발표 당시 소속기관"].forEach((label, index) => {
    svg.append(svgElement("text", { x: [12, 284, 452][index], y: 20, class: "graph-label" }, label));
  });
  paths.forEach((path, row) => graphRow(svg, path, row));
  get("graph").replaceChildren(svg);
  get("graph-detail").replaceChildren();
}

function mount() {
  let catalogIndex;
  const form = get("search-form");
  const status = get("search-status");
  const questionInput = get("question");
  const graphPicker = get("graph-institution");
  const submit = get("submit");
  const retry = get("retry");

  async function loadCatalog() {
    retry.hidden = true;
    status.textContent = "";
    get("catalog-status").textContent = "카탈로그 불러오는 중…";
    try {
      const response = await fetch("./catalog.json", { signal: AbortSignal.timeout(10000) });
      if (!response.ok) throw new Error("Catalog unavailable");
      const catalog = await response.json();
      if (catalog.schema_version !== 1 || !Array.isArray(catalog.papers)) throw new Error("Invalid catalog");
      catalogIndex = indexPapers(catalog.papers);
      get("catalog-status").textContent = `OpenAlex · 논문 ${catalog.papers.length}건`;
      submit.disabled = catalog.papers.length === 0;
      if (submit.disabled) status.textContent = "카탈로그에 논문이 없습니다.";
    } catch {
      get("catalog-status").textContent = "카탈로그 연결 오류";
      status.textContent = "카탈로그를 불러올 수 없습니다. 연결과 catalog.json 파일을 확인하세요.";
      retry.hidden = false;
    }
  }

  retry.addEventListener("click", loadCatalog);
  get("example").addEventListener("click", () => {
    questionInput.value = example;
    questionInput.focus();
  });
  form.addEventListener("submit", event => {
    event.preventDefault();
    if (!catalogIndex || submit.disabled) return;
    const question = questionInput.value.trim();
    get("results").hidden = true;
    if (!question || question.length > 500) {
      status.textContent = "기술 문제를 1~500자로 입력하세요.";
      return;
    }
    const keywords = keywordsFor(question);
    const hits = search(catalogIndex, keywords);
    const institutions = rankInstitutions(hits);
    get("keywords").replaceChildren(...keywords.map(word => element("li", word)));
    get("paper-count").textContent = `${hits.length}건`;
    get("org-count").textContent = `${institutions.length}곳`;
    get("papers").replaceChildren(...hits.map(paperCard));
    get("institutions").replaceChildren(...institutions.map(org => institutionCard(org, question)));
    get("graph-panel").hidden = institutions.length === 0;
    if (!institutions.length && hits.length) {
      get("institutions").append(element("p", "검색된 논문에서 기관 소속 근거를 확인할 수 없습니다."));
    }
    graphPicker.replaceChildren(...institutions.map(org => element("option", named(org))));
    graphPicker.onchange = () => renderGraph(institutions[graphPicker.selectedIndex]);
    if (institutions.length) renderGraph(institutions[0]);
    status.textContent = hits.length
      ? `관련 논문 ${hits.length}건과 연구기관 후보 ${institutions.length}곳을 찾았습니다.`
      : "검색 결과가 없습니다. 배터리, 급속 충전, 열화 또는 영어 기술 키워드로 검색해 보세요.";
    get("results").hidden = !keywords.length && !hits.length;
  });
  loadCatalog();
}

if (typeof document !== "undefined") mount();
