
# RAG Technology Discovery Chatbot

## Project Overview
AWS 기반 논문·특허 기술 탐색 챗봇 프로젝트

## Development Environment
- Visual Studio Code
- ChatGPT
- Python 3.13
- HTML / JavaScript
- Git / GitHub

## AWS Architecture
- Amazon S3: 웹 및 문서 저장소
- Amazon CloudFront: 웹사이트 배포
- Amazon API Gateway: HTTP API
- AWS Lambda: Python 백엔드

## Implemented APIs
GET /health
POST /search

## Current Status
2주차 AWS 배포 환경 구성 완료

현재는 테스트 응답을 제공하며,
실제 RAG 검색 및 LLM 생성 기능은 미구현 상태입니다.

## Future Work
- OpenAlex / KIPRIS API 연동
- Amazon Bedrock Knowledge Bases
- Amazon S3 Vectors
- 근거 기반 기술 검색 및 답변 생성
