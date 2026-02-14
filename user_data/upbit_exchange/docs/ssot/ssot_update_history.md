# SSOT Update History

프로젝트 SSOT 변경 이력 (최신순)

---

## v3.4 - 2026-02-14 (SSOT 간소화)
- UPDATE HISTORY를 별도 파일(`ssot_update_history.md`)로 분리
- 완료된 DEC 항목(DEC-015~024) 1줄 요약
- Phase 2.5 상태를 "기본 구현 완료"로 갱신
- BACKLOG 간소화
- Phase 2/2.5 섹션 간략화 (참조 문서로 유도)

## v3.3 - 2026-02-12 (diff-최소 가드레일 + 테마 규칙 추가)
- IR-006 추가: diff 최소 = 변경리스크 최소(기능 축소/스펙 삭제 금지, AC 우선)
- DEC-026 추가: diff-최소 운용 규칙 확정
- DEC-027 추가: PC 앱 Light/Dark 테마 토큰 규칙 + 가격색(빨강/파랑) 확정 의미 분리
- AC-PC-001/002 및 DoD/Backlog에 테마 항목 추가
- RISK-PC-006 추가: 라이트 테마 가독성/계층 붕괴 리스크 및 완화

## v3.2 - 2026-02-01 (PC 앱 UI 보강)
- ETH 창 UI를 trading-monitor.jsx 기준으로 보강
- 차트/거래량 축과 좌표 숫자 표시 추가
- 초기 DB 로드로 캔들 폭 ~3px 유지
- 진단 패널 버튼(LIVE/DB) 동작 연결
- 상단 네비게이션 바 제거 (ETH 창)

## v3.1 - 2026-01-28 (Phase 2 P0 안정화 반영)
- DEC-025: 타임프레임별 테이블 분리 확정 (PK 충돌 제거)
- flush_timer 종료 레이스 제거 정책 반영 (cancel + idle wait + 재스케줄 차단)
- unfinished_tasks 비공개 API 제거 정책 반영
- Cloud 로그 경로를 프로젝트 루트 logs/로 고정

## v3.0 - 2026-01-28 (Phase 2.5 PC 앱 전체 명세 추가)
- PC 앱 Objective, 아키텍처, 핵심 기능 전체 상세 명세
- 듀얼 모니터 UI, Raw Trade WebSocket, BURST 감지, LIVE 오버레이, WS 재연결, UI 렌더링, 차트 표현, UI 스타일, DB 조회, 로깅, 설정, SQLite 접근, common/ 재사용, Hybrid, 스레드 분리, Android 알람 설계
- DEC-015~024 추가 (PC 앱 관련 결정 10개)
- AC-PC-001~005 추가 (PC 앱 Acceptance Criteria)
- BL-PC-001~010 추가 (PC 앱 구현 백로그)
- 목적: 작업지시서(1213줄) 기반 SSOT 상세화, PC 앱 설계 완전 문서화
- SSOT 라인 수: 345 → 약 800+ 줄

## v2.4 - 2026-01-28 (Phase 2.5 PC 앱 설계 추가)
- DEC-015: 듀얼 모니터 UI 설계 확정
- DEC-016: Raw Trade WebSocket 최적화 설계 확정
- BL-PC-001~004: PC 앱 구현 백로그 추가
- 목적: PC 차트 앱 설계 문서화, Phase 2.5 준비

## v2.3 - 2026-01-28 (SSOT 간소화)
- Phase 2 정책/요구사항 핵심만 간소화
- 완료된 사항 요약 처리
- 목적: Phase 2 구현 집중, 파일 크기 축소

## v2.2 - 2026-01-28 (디렉토리 리팩토링)
- DEC-014: common/cloud/pc_app 구조 분리
- 목적: 유지보수성, PC 앱 준비

## v2.1 - 2026-01-28 (SSOT 간소화)
- Phase 0/1 완료 내용 → update_history.txt

## v2.0 - 2026-01-27 (Phase 2 명세 확정)
- POL-001~013, P2-REQ-001~012

---

**이전 상세 변경 이력**: `update_history.txt` (Phase 0/1)
