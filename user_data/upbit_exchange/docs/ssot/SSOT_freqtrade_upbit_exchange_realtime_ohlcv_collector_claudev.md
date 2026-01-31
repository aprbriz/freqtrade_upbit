업비트 실시간 OHLCV 수집기 - SSOT (Single Source of Truth)
프로젝트: Freqtrade_upbit Real-time OHLCV Collector
버전: v2.3 (간소화)
생성일: 2026-01-26
최종 업데이트: 2026-01-28

📸 SNAPSHOT (현재 상태)

✅ Phase 0/1 완료
- 24시간+ 무중단 운영 (9시간 주기 재연결, 무제한 재연결)
- CRITICAL-001 해결 완료 (상세: update_history.txt)

✅ DEC-014 리팩토링 완료 (2026-01-28)
```
upbit_exchange/
├── common/        # Cloud/PC 공통 (aggregator, dedup, reconnect)
├── cloud/         # Cloud Collector (collector, writer, multi_aggregator)
├── pc_app/        # PC 차트 앱 (Phase 2.5+ 예정)
└── collector.py   # 래퍼
```

현재 기능
- BTC/ETH/XRP WebSocket 실시간 수집
- 0.5초, 1초, 3틱봉 생성/저장
- SQLite WAL 모드, 배치 처리
- 자동 재연결, graceful shutdown

🔒 불변 규칙 (IMMUTABLE RULES)

IR-001: SSOT 원칙
- 모든 결정은 이 문서에만 기록
- 코드로 때우지 말고 질문 등록

IR-002: 파일 수정 범위
- Phase 2: cloud/collector.py, cloud/ohlcv_writer.py, cloud/multi_aggregator.py
- common: tick_aggregator.py, timeframe_aggregator.py
- 새 파일 추가 시 승인 필요

IR-003: 안정성 우선
- 장애 격리, 예외 처리, 로깅

IR-004: 장기 운영 대응
- 메모리 누수 방지, 재연결 로직 강화

IR-005: 데이터 무결성
- 중복 방지, 유효성 검증, timestamp 순서


📋 SCOPE

✅ In-Scope
- 업비트 KRW 3개 pair (BTC, ETH, XRP)
- 다중 타임프레임 OHLCV, SQLite 저장
- 24시간+ 무중단 운영, 재연결, 안전 종료

❌ Out-of-Scope
- 데이터 분석/시각화, 백테스팅, 트레이딩 로직
- REST API, Web UI, 타 거래소


🎯 ACCEPTANCE CRITERIA (완료 기준)

AC-001: 기능 동작
[x] 24시간+ 무중단 실행 ✅
[x] 자동 재연결 (무제한, 9시간 주기) ✅
[x] 안전 종료 (5초 이내) ✅

AC-002: 데이터 품질
[ ] 중복 0건, 손실률 < 0.1%, timestamp 순서 보장

AC-003: 성능
[ ] CPU < 10%, 메모리 < 1GB (24시간)
- H/W: 오라클 ARM Core 3, RAM 23GB, HDD 200GB

AC-004: 운영 안정성
[x] 로그 추적, 장애 격리, 재시도 없음 ✅

AC-005: 코드 품질
[ ] docstring, 한글 주석, try-except, logging, 타입 힌트


✅ CHECKLIST (완료 체크리스트)

Phase 0/1: ✅ 완료 (update_history.txt 참조)

Phase 2 구현 대기 🚧
[ ] CollectorManager + Short/Mid/Long Collector
[ ] DB 파일 분리 (short/10s_1m/10m)
[ ] DerivedAggregator (메모리 전용)
[ ] config/CLI/HTTP/통계
[ ] 중복 제거, 전역 레이트리밋, DB 재시도
[ ] 큐 오버로드 보호


⚠️ RISK REGISTER
✅ RISK-001~005, 007: 해결/완화됨 (update_history.txt)
⚠️ RISK-002: DB 크기 증가 - 수동 cleanup 필요
🟡 RISK-006: 다중 DB 쓰기 - Phase 2에서 해결 예정


📝 DECISION LOG (주요 결정)

DEC-001~010: ✅ 확정 (update_history.txt)
- SQLite WAL, 배치100, 틱봉 음수, 9시간 재연결, 무제한 재연결

DEC-011: Phase 2 DB 마이그레이션 (P2-001)
- ohlcv.sqlite → ohlcv_short.sqlite (일회성 rename)
- 안전장치: 기존 파일 보호, 실패 시 fail-fast

DEC-012: 중복 제거 우선순위 (P2-002)
- trade_uuid → sequential_id → fallback 5-tuple
- 런타임 필드 존재 확인

DEC-013: 큐 오버로드 격리/회복 (P2-003)
- HIGH_WATERMARK: DEGRADED + 백프레셔
- HARD_LIMIT: 의도적 연결 종료 → 쿨다운 → 재연결
- drop 우선이 아닌 격리/회복 중심

DEC-014: 디렉토리 구조 분리 ✅
- common/cloud/pc_app 구조로 코드 재사용성/유지보수성 향상


🚧 PHASE 2 구현 명세 v2.0 (간소화)

목표
- DB 파일 분리로 write 경합 축소
- Collector 단위 장애 격리
- 합성 봉(메모리 전용) vs 직접 수집 봉(DB 저장) 분리
- 재연결 폭주 방지, graceful shutdown, 리소스 누수 0

Phase 2 Scope
✅ In: Manager, 독립 WS/DB, DerivedAggregator, config/CLI/HTTP, 재시도, 오버로드 보호
❌ Non: watchdog, 새 파일(승인 없이), REST 보정, 외부 재시작

아키텍처
```
CollectorManager
  ├─ ShortCollector (ohlcv_short.sqlite)
  │    ├─ Timeframe(500ms, 1s) + Tick(3) → DB
  │    └─ Derived(5s,10s,33s,57s,1m) → 메모리 전용
  ├─ MidCollector (ohlcv_10s_1m.sqlite)
  │    └─ Timeframe(10s, 1m) → DB
  └─ LongCollector (ohlcv_10m.sqlite)
       └─ Timeframe(10m) → DB
```

핵심 정책 (POL-001~013, 간소화)

POL-001: CollectorManager
- collectors 생성/관리, start/stop, health/stats
- graceful shutdown 순서 보장
- 전역 재연결 레이트리밋 (1회/초, 30회/분)

POL-002: Collector
- 독립 WS/DB/Writer, 재연결(DEC-009/010), generation 모델

POL-003: generation(세션)
- 재연결 시 generation_id 증가
- Derived는 generation 변경 시 reset

POL-004: 재연결
- backoff(1초~60초, 2배, jitter 0~1초)
- 쿨다운: 10분 내 실패 10회 → 5분 대기

POL-005: DB
- SQLite WAL, writer 단일화
- locked/busy 재시도: 50ms~2초, 총 10초 상한
- 실패 시 DEGRADED 표시

POL-006: 중복 제거
- trade_uuid → sequential_id → fallback
- 런타임 필드 존재 확인, market별 N=20,000

POL-007: 큐/오버로드
- HIGH_WATERMARK: DEGRADED + 백프레셔
- HARD_LIMIT: 연결 종료 → 회복 → 재연결 (drop 우선 아님)

POL-008: DerivedAggregator
- Short만, 1초봉 기반, 메모리 전용(DB 저장 금지)

POL-009: graceful shutdown
- WS close → drain → flush → join, partial 캔들 폐기

POL-010: 로그
- 틱 로그 금지, 30초 통계만, 상태 전이, 경고/오류(rate-limit)

POL-011: HTTP
- --http-port 0 또는 미지정 시 OFF
- GET /health, GET /stats

POL-012: 데이터 정합성
- price <= 0, volume < 0, timestamp 역전 검증

POL-013: silent failure 방지
- last_message_age 제공 (로그/HTTP)

구현 요구사항 (P2-REQ-001~012)

P2-REQ-001: Manager + Config
P2-REQ-002: DB 분리 + 마이그레이션
P2-REQ-003: DerivedAggregator
P2-REQ-004: config_upbit_exchange.yml
P2-REQ-005: CLI (--pairs, --http-port)
P2-REQ-006: 통계 로그 30초
P2-REQ-007: HTTP /health, /stats
P2-REQ-008: 데이터 정합성
P2-REQ-009: 중복 제거
P2-REQ-010: 전역 레이트리밋
P2-REQ-011: DB 재시도
P2-REQ-012: 큐 오버로드 보호

Phase 2 Acceptance Criteria

AC-P2-001: 기능
[ ] short/mid/long 동시 실행, 각 DB 정상 기록
[ ] DB 마이그레이션 정책 준수
[ ] Derived는 DB 저장 안 됨
[ ] HTTP ON/OFF 정상

AC-P2-002: 안정성
[ ] 24시간+ 무중단 (스레드/FD/메모리 누수 0)
[ ] last_message_age ≤ 5초
[ ] reconnect storm 방지 (쿨다운, 전역 레이트리밋)

AC-P2-003: 정합성
[ ] 큐 HIGH/HARD 동작 확인 (DEGRADED, 격리/회복)

AC-P2-005: 관측성
[ ] 통계 로그 + HTTP에서 last_message_age 확인


📦 BACKLOG (향후 작업)

Phase 2 구현 🚧
BL-P2-CORE: Manager, Short/Mid/Long, DB 분리, Derived, generation
BL-P2-OPS: config/CLI/HTTP, 통계, 정합성
BL-P2-PROTECT: 중복 제거, 전역 레이트리밋, DB 재시도, 큐 보호
BL-P2-VERIFY: 24시간 테스트, AC 검증

단기 (Phase 2 완료 후)
- P2-REQ로 흡수됨

중기 (1개월)
BL-006: 차트 제작 (web or PC-APP)
BL-007: freqtrade Web UI 연동

장기 (3개월+)
BL-008: REST API, 데이터 조회
BL-009: CSV/Parquet 내보내기
BL-011: 데이터 분석
BL-012: 실시간 알림


🔄 UPDATE HISTORY

v2.3 - 2026-01-28 (SSOT 간소화)
- Phase 2 정책/요구사항 핵심만 간소화
- 완료된 사항 요약 처리
- 목적: Phase 2 구현 집중, 파일 크기 축소

v2.2 - 2026-01-28 (디렉토리 리팩토링)
- DEC-014: common/cloud/pc_app 구조 분리
- 목적: 유지보수성, PC 앱 준비

v2.1 - 2026-01-28 (SSOT 간소화)
- Phase 0/1 완료 내용 → update_history.txt

v2.0 - 2026-01-27 (Phase 2 명세 확정)
- POL-001~013, P2-REQ-001~012


📌 NOTES

개발 환경
- Python 3.8+, websocket-client>=1.0.0

DB 파일
- 현재: ohlcv.sqlite
- Phase 2: ohlcv_short/10s_1m/10m.sqlite

실행 (Phase 2 구현 후)
```bash
python collector.py                         # 기본
python collector.py --pairs KRW-BTC,KRW-ETH # pair 지정
python collector.py --http-port 8000        # HTTP 활성화
```

종료
- Ctrl+C (5초 이내 안전 종료)

운영
- 24시간+ 무중단 가능 ✅
- 로그: tail -f logs/collector.log
- 9시간 자동 재연결


마지막 업데이트: 2026-01-28 (v2.3)
다음 단계: Phase 2 v2.0 구현 → 24시간 검증 테스트
상세 이력: update_history.txt
