# TechBridge AI

**Metadata-based Graph Retrieval MVP**

제조 중소기업이 기술 문제를 입력하면 관련 논문과 연구자, 논문 발표 당시 소속기관을 찾습니다. 현재 카탈로그는 리튬이온 배터리 열화 및 급속 충전 분야 OpenAlex 논문 30건으로 구축했습니다. 기관 점수는 관련 논문의 주제 적합도를 합산한 값입니다. 실제 기술이전 조건, 현재 소속, 협력 의향은 기관에 직접 확인해야 합니다.

## 구조

```text
OpenAlex → collector/collect.py → data/papers.json (로컬)
    → collector/build_graph.py → data/graph.json + 공개 catalog.json
질문 → 기술 키워드 → BM25 논문 후보 → 그래프 탐색 → 기관 점수와 근거 경로
```

NetworkX 방향 다중 그래프는 논문, 연구자, 기관, 주제를 OpenAlex ID로 연결합니다. 소속 엣지는 저자·기관·근거 논문 단위로 보존합니다. 검색 시 시작 논문의 ID와 소속 근거 논문의 ID가 일치하는 경로만 사용합니다. 기관 점수는 해당 기관에 연결된 상위 논문의 BM25 점수를 논문별로 한 번씩 합산합니다. 논문 가중치는 1이며 점수가 같으면 OpenAlex ID 순으로 정렬합니다. 인용은 OpenAlex의 `referenced_works`에 있는 쌍만 연결합니다. 수집 범위 밖 피인용 논문에는 ID만 기록합니다.

`data/catalog.json`, `frontend/catalog.json`, `docs/catalog.json`은 같은 공개용 스냅샷입니다. 제목, 발행연도, DOI, OpenAlex ID, 저자·기관·주제·인용 ID 등 메타데이터만 내보냅니다. 초록과 원문 본문은 공개 파일에서 제외합니다. 로컬 초록은 Git에서 제외된 `data/papers.json`에 저장합니다. [OpenAlex 데이터 설명](https://help.openalex.org/data/how-its-built/), [원문 라이선스](https://help.openalex.org/access/fulltext/)

## 설치

Python 3.11 이상을 사용합니다. 웹사이트는 Python 표준 HTTP 서버와 브라우저에서 실행할 수 있습니다.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## OpenAlex 인증 및 수집

Mac 터미널에서 첫 명령 실행 후 재발급한 키를 입력하고 Enter를 누릅니다. 같은 터미널에서 다음 명령을 실행합니다.

```sh
read -s OPENALEX_API_KEY
export OPENALEX_API_KEY
python3 -m collector.collect --check
```

`--check`는 Bearer로 요청하고 HTTP 상태, 논문 제목과 발행연도, OpenAlex ID 3건을 출력합니다. 키는 서버측 요청 헤더에만 전달합니다. `.env.example`은 빈 값으로 제공하며 `.env`를 따로 사용한다면 셸에서 환경변수로 내보내야 합니다. [OpenAlex 공식 인증 문서](https://help.openalex.org/api/authentication/)

```sh
python3 -m collector.collect --limit 30
python3 -m collector.build_graph
```

수집 범위는 20~100건입니다. `--query`로 수집 질의를 바꿀 수 있습니다. `--anonymous`를 명시하면 공식 익명 접근을 사용합니다. 현재 체크인한 스냅샷은 익명 접근으로 수집했습니다. 요청은 최대 3페이지, 익명 요청은 1페이지이며 서버 오류와 타임아웃만 요청당 최대 두 번 재시도합니다. HTTP 401은 인증, 403은 활성화 또는 권한, 429는 예산 또는 호출 속도, 5xx는 서버 오류로 구분합니다. 429에서는 종료합니다. 검색 결과가 0건이면 이전 수집본을 보존합니다.

## 검색

수집 단계 없이 체크인한 공개 카탈로그로 검색할 수 있습니다.

```sh
python3 -m retrieval.graph_retrieval '배터리 충전 속도를 유지하면서 수명을 늘리는 기술이 필요합니다.'
```

CLI는 기술 키워드, 관련 논문과 점수, 저자, 주제, 피인용 논문, 상위 기관과 근거 경로를 JSON으로 출력합니다.

Python과 JavaScript 모두 양수 IDF를 사용하는 Okapi BM25를 구현합니다. 로컬 Python은 수집본이 있으면 제목·주제·초록을 사용하고, 공개 카탈로그만 있는 경우 제목과 주제를 사용합니다. 브라우저는 제목과 주제만 사용하므로 로컬 수집본으로 검색한 점수와 순위가 달라질 수 있습니다. 두 구현은 영어 토큰과 배터리 분야 한국어 사전을 사용합니다. 사전에 없는 한글 표현은 변환하지 않으며 초기 카탈로그 범위 밖 기술은 검색 결과가 적거나 없을 수 있습니다.

## 로컬 웹

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory docs
```

브라우저에서 `http://127.0.0.1:8765/`를 열고 예시 질문을 입력하거나 직접 질문을 작성합니다. 추천 근거를 펼치면 논문·저자·기관 경로를 볼 수 있습니다. 그래프에서 기관을 바꾸거나 노드를 클릭하면 관련 OpenAlex 링크가 열리는 상세 항목이 표시됩니다. 웹은 카탈로그를 같은 디렉터리에서 읽고 검색을 브라우저 안에서 실행합니다. 기존 AWS 데모의 소스는 주소 오타를 수정해 `frontend/aws-demo.html`에 보관합니다.

## GitHub Pages

프런트엔드 코드는 `frontend/`에서 편집한 뒤 배포용 소스와 동기화합니다. 그래프 빌드가 공개 카탈로그 세 파일을 갱신합니다.

```sh
cp frontend/index.html frontend/app.js frontend/style.css docs/
```

PR을 검토하고 병합한 뒤 저장소 관리자 또는 유지관리자가 Settings → Pages → Deploy from a branch → `main` → `/docs`를 선택합니다. 배포 후 프로젝트 주소에서 화면과 카탈로그 로딩을 확인합니다. [GitHub Pages 배포 설정](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), [프로젝트 사이트](https://hottae0.github.io/rag-tech-chatbot/)

## 테스트

```sh
python3 -m pytest -q
node --test tests/browser_search.test.mjs
```

Python 테스트는 API 요청을 대체한 fixture로 인증 오류, 시간 초과, 데이터 정규화, 그래프 근거, 순위, 공개 데이터 경계를 확인합니다. Node 테스트는 공개 스냅샷으로 검색과 추천 경로, 링크 허용 목록을 검사합니다. 실제 OpenAlex 호출은 `--check`와 수집 명령으로 별도 실행합니다.

## 비용

공식 한도는 무료 개인 키 일일 $1 상당의 API 예산과 초당 30건이며, 익명 접근은 키 없는 별도 예산과 초당 10건입니다. 익명 예산 한도는 무료 키의 10분의 1입니다. 개발 중 무료 익명 메타데이터 검색만 실행했습니다. 크레딧 구매, 유료 LLM, 별도 서버 또는 데이터베이스가 필요하지 않습니다. 공개 저장소의 GitHub Pages는 GitHub Free 범위에서 사용할 수 있습니다. 기존 AWS 과금은 이 MVP 비용과 별개이며 AWS 계정 사용량은 이 프로젝트에서 집계하지 않습니다. [OpenAlex 인증 및 한도](https://help.openalex.org/api/authentication/), [GitHub Pages 이용 범위](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

## GraphRAG 확장

현재 코드는 검색(`BM25Search`), 탐색과 근거 구성(`expand_evidence`), 결과 조합(`retrieve`)을 분리합니다. 향후 Dense Retrieval로 검색을 교체하거나, 인용 기반 확장 또는 Personalized PageRank를 추가할 수 있습니다. 근거 부분 그래프를 텍스트로 직렬화하고 선택적으로 로컬 Ollama에 전달하는 답변 생성 단계를 후속으로 붙일 수 있습니다. BM25-only, BM25 + Graph Expansion, Citation-aware Retrieval, Personalized PageRank, Local LLM GraphRAG는 평가 질문과 검토자 판정으로 비교할 계획입니다. [비즈니스 기획서](docs/business_plan.md)
