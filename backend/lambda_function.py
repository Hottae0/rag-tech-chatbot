
import json


def make_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8"
        },
        "body": json.dumps(body, ensure_ascii=False)
    }


def lambda_handler(event, context):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = event.get("rawPath", "/")

    # 1. 서버 상태 확인
    if method == "GET" and path == "/health":
        return make_response(200, {
            "status": "ok",
            "service": "rag-tech-chatbot",
            "message": "AWS Lambda is running"
        })

    # 2. 챗봇 질문 처리
    if method == "POST" and path == "/search":
        try:
            body = json.loads(event.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            return make_response(400, {
                "error": "Invalid JSON body"
            })

        if not isinstance(body, dict):
            return make_response(400, {
                "error": "JSON object is required"
            })

        question = body.get("question", "")

        if not isinstance(question, str) or not question.strip():
            return make_response(400, {
                "error": "Question is required"
            })

        if len(question) > 500:
            return make_response(400, {
                "error": "Question is too long"
            })

        return make_response(200, {
            "question": question,
            "answer": (
                f"'{question}'에 대한 테스트 응답입니다. "
                "현재 AWS 클라우드 환경에서 "
                "API가 정상적으로 실행되고 있습니다. "
                "실제 논문 및 특허 기반 RAG 검색 기능은 "
                "향후 추가할 예정입니다."
            ),
            "sources": [],
            "mode": "demo"
        })

    return make_response(404, {
        "error": "Route not found"
    })
