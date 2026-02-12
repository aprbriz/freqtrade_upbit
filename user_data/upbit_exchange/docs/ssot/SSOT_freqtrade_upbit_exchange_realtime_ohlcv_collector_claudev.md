# 업비트 실시간 OHLCV 수집기 + PC 차트 앱 - SSOT (Single Source of Truth)

**프로젝트**: Freqtrade_upbit Real-time OHLCV Collector + PC Chart App  
**버전**: v3.3 (diff-최소(=변경리스크 최소) 가드레일 + PC 앱 Light/Dark 테마 규칙 추가)  
**생성일**: 2026-01-26  
**최종 업데이트**: 2026-02-12  

---

## 📸 SNAPSHOT (현재 상태)

### ✅ Phase 0/1 완료 (Cloud Collector)
- 24시간+ 무중단 운영 (9시간 주기 재연결, 무제한 재연결)
- CRITICAL-001 해결 완료 (상세: update_history.txt)
- BTC/ETH/XRP WebSocket 실시간 수집
- 0.5초, 1초, 3틱봉 생성/저장
- SQLite WAL 모드, 배치 처리
- 자동 재연결, graceful shutdown

### ✅ DEC-014 리팩토링 완료 (2026-01-28)
upbit_exchange/
├── common/ # Cloud/PC 공통 (aggregator, dedup, reconnect)
├── cloud/ # Cloud Collector (collector, writer, multi_aggregator)
├── pc_app/ # PC 차트 앱 (Phase 2.5)
└── collector.py # 래퍼


### 🚧 Phase 2: Cloud Collector 고도화 (구현 대기)
- CollectorManager + Short/Mid/Long 분리
- DB 파일 분리 (short/10s_1m/10m)
- DerivedTimeframeAggregator (메모리 전용)
- config/CLI/HTTP/통계

### 🚧 Phase 2.5: PC 차트 앱 (설계 완료 ✅, 구현 대기)
- **듀얼 모니터 UI** 설계 확정 (DEC-015)
- **Raw Trade WebSocket 최적화** 설계 확정 (DEC-016)
- DB + LIVE 오버레이 병합 설계
- BURST 감지 및 자동 전환
- Upbit 유사 스타일 UI

---

## 🔒 불변 규칙 (IMMUTABLE RULES)

### IR-001: SSOT 원칙
- 모든 결정은 이 문서에만 기록
- 코드로 때우지 말고 질문 등록

### IR-002: 파일 수정 범위
**Phase 2 (Cloud):**
- cloud/collector.py, cloud/ohlcv_writer.py, cloud/multi_aggregator.py
- common: tick_aggregator.py, timeframe_aggregator.py, dedup_cache.py, reconnect_limiter.py, constants.py

**Phase 2.5 (PC 앱):**
- pc_app/ 하위 전체 (신규 생성)
- 기존 Cloud 코드 수정 금지
- common/ 코드는 vendor 복사 방식으로 재사용 (직접 참조 금지)

### IR-003: 안정성 우선
- 장애 격리, 예외 처리, 로깅
- UI 프리징 0 (PC 앱 핵심)
- 재연결 폭주 방지

### IR-004: 장기 운영 대응
- 메모리 누수 방지
- 재연결 로직 강화 (backoff/jitter/cooldown)
- 24/7 기준 설계

### IR-005: 데이터 무결성
- 중복 방지, 유효성 검증, timestamp 순서
- 섞임/유령 캔들 방지 (context_id, generation_id)
- cutover_ts 기준 병합

### IR-006: “diff 최소”는 작업량 최소가 아니라 **변경 리스크 최소**
- “diff 최소”는 **AC/SSOT 100% 충족을 전제로** 변경량을 최소화하여 회귀/드리프트 위험을 줄이는 규칙이다.
- **기능 축소/스펙 삭제/완화 금지**(AC/SSOT에 있는 요구사항은 유지).
- “diff 최소”보다 우선하는 것: **(1) AC 충족 (2) 운영 안정성(재연결/종료/누수/중복) (3) 데이터 무결성**.
- 리팩토링/정리/추상화는 금지(단, AC 충족에 “필수”인 최소 범위만 예외).
- 임시 땜빵(TODO/주석으로 남기기) 금지. **테스트 없이도 바로 실행 가능**해야 한다.

---

## 📋 SCOPE

### ✅ In-Scope

**Phase 0/1 완료:**
- 업비트 KRW 3개 pair (BTC, ETH, XRP)
- 다중 타임프레임 OHLCV, SQLite 저장
- 24시간+ 무중단 운영, 재연결, 안전 종료

**Phase 2 구현 대기:**
- CollectorManager + Short/Mid/Long Collector 분리
- DB 파일 분리 (ohlcv_short/10s_1m/10m.sqlite)
- DerivedTimeframeAggregator (메모리 전용, 1초봉 기반)
- config.yml, CLI, HTTP endpoints (/health, /stats)
- 중복 제거, 전역 레이트리밋, DB 재시도, 큐 오버로드 보호

**Phase 2.5 PC 차트 앱:**
- **Windows PC 전용 차트 앱** (PyQt5/PySide6)
- **듀얼 모니터 기본 전제** (모니터 1: XRP+BTC, 모니터 2: ETH+진단패널)
- **DB 기반 평시 조회 + BURST 시 LIVE 전환**
- **Raw Trade 단일 구독** (3개 심볼 고정, 타임프레임 재구독 불필요)
- **로컬 Aggregation** (common/MultiAggregator 재사용)
- **Upbit 유사 UI 스타일** (dual-chart-monitor.html 기준)
- **BURST 감지 상태머신** (2단계 게이트 + 히스테리시스)
- **WS 재연결 안정화** (backoff/jitter/cooldown, Upbit 레이트리밋 준수)
- **coalesce + 하단 티커** (UI 프리징 방지)
- **context_id/generation_id 기반 섞임 방지**
- **Light/Dark 테마 전제(라이트 기본 + 다크 옵션)** (DEC-026, DEC-027)

### ❌ Out-of-Scope

**Cloud:**
- 데이터 분석/시각화, 백테스팅, 트레이딩 로직
- REST API, 타 거래소
- Prometheus/Grafana 연동 (후순위)

**PC 앱:**
- Android 알람 앱 (중기 개발)
- 주문 실행/거래 기능
- 틱 원본 전량 저장/렌더
- 차트 데이터 보간 (없는 캔들 채우기 금지)
- Cloud collector 설계 변경/DB 스키마 변경
- FastAPI/REST health check 서버
- 부드러운 애니메이션/60fps 고정 최적화
- REST API로 갭 복구 (PC 앱은 정본 아님)

---

## 🎯 ACCEPTANCE CRITERIA (완료 기준)

### AC-001: Cloud Collector 기능 동작
- [x] 24시간+ 무중단 실행 ✅
- [x] 자동 재연결 (무제한, 9시간 주기) ✅
- [x] 안전 종료 (5초 이내) ✅
- [ ] Phase 2: short/mid/long DB 분리 기록
- [ ] Phase 2: Derived 메모리 전용 동작

### AC-002: Cloud 데이터 품질
- [ ] 중복 0건
- [ ] 손실률 < 0.1%
- [ ] timestamp 순서 보장

### AC-003: Cloud 성능
- [ ] CPU < 10%, 메모리 < 1GB (24시간)
- H/W: 오라클 ARM Core 3, RAM 23GB, HDD 200GB

### AC-004: Cloud 운영 안정성
- [x] 로그 추적, 장애 격리 ✅
- [x] 재시도 없음 (즉시 폭주 방지) ✅

### AC-005: Cloud 코드 품질
- [ ] docstring, 한글 주석, try-except, logging, 타입 힌트

### AC-PC-001: PC 앱 기능 동작
- [ ] 드롭다운으로 심볼/타임프레임 선택 가능
- [ ] 듀얼 모니터 UI (모니터 1: XRP+BTC, 모니터 2: ETH+진단패널)
- [ ] 단일 모니터 폴백 (탭/스택 모드)
- [ ] 상태 칩 3개 (MODE, WS, BURST) 정상 표시
- [ ] 통합 진단 패널 (3개 심볼 전체 상태) 갱신
- [ ] 버튼 3개 (LIVE 시작, DB 전환, ACK) 정상 동작
- [ ] DB_ONLY에서 DB 차트 정상 출력 (KST 축)
- [ ] LIVE_ACTIVE에서 마지막 봉 틱 단위 갱신 체감 제공
- [ ] 갭 표시 규칙 준수 (보간 없음, 장애 갭 마커)
- [ ] 3틱봉 인덱스축 + KST 툴팁
- [ ] Raw Trade 단일 구독 (3개 심볼 고정)
- [ ] 타임프레임 변경 시 즉시 전환 (0.1초)
- [ ] **테마 기본값 Light(흰 배경) 적용** (DEC-027)
- [ ] **테마 토글 Dark(검정/다크) 적용** (DEC-027)
- [ ] **테마 전환 시 텍스트/아이콘/그리드/구분선 자동 조정(가독성 유지)** (DEC-027)

### AC-PC-002: PC 앱 성능/안정성
- [ ] BURST 폭주 시 UI 프리징 없음 (coalesce 허용)
- [ ] 메모리 무한 증가 없음 (bounded)
- [ ] 드랍 우선순위 (1~5) 작동
- [ ] 하단 티커 coalesce/드랍 안내
- [ ] WS 재연결 폭주 없음 (backoff/jitter/window/cooldown)
- [ ] 종료 시 스레드/소켓 누수 없음
- [ ] config.json 생성/로드/저장 정상
- [ ] 로그 로테이션 적용 (24/7 대응)
- [ ] SQLite 로컬 복사본 mode=ro 오픈
- [ ] 듀얼 모니터 핫플러그 대응 (자동 폴백)
- [ ] **테마 전환이 성능/프리징에 영향 없음(토큰 기반, 즉시 반영)** (DEC-027)

### AC-PC-003: PC 앱 섞임 방지
- [ ] Raw Trade 방식 섞임 방지 (context_id, generation_id)
- [ ] 타임프레임 변경 시 섞임 없음
- [ ] context_id mismatch 즉시 폐기

### AC-PC-004: PC 앱 LIVE 오버레이
- [ ] cutover_ts 기준 병합 규칙 준수
- [ ] bounded 정책 (시간 + 개수 2중 제한)
- [ ] DB catch-up barrier 복귀 동작

### AC-PC-005: PC 앱 WS 장애 대응
- [ ] partial/global silent 구분
- [ ] 단계적 대응 (재구독→재연결)
- [ ] 파싱 실패만으로 재연결하지 않음
- [ ] Upbit 레이트리밋 준수 (연결 5회/초, 구독 5회/초 + 100회/분)

---

## ✅ CHECKLIST (완료 체크리스트)

### Phase 0/1: ✅ 완료 (update_history.txt 참조)

### Phase 2 구현 대기 🚧
- [ ] CollectorManager + Short/Mid/Long Collector
- [ ] DB 파일 분리 (short/10s_1m/10m)
- [ ] DerivedTimeframeAggregator (메모리 전용)
- [ ] config/CLI/HTTP/통계
- [ ] 중복 제거, 전역 레이트리밋, DB 재시도
- [ ] 큐 오버로드 보호

### Phase 2.5 PC 앱 구현 대기 🚧
- [ ] MainEngine (WS + Aggregation + BURST 감지)
- [ ] 듀얼 모니터 UI (Window1: XRP+BTC, Window2: ETH+진단패널)
- [ ] DB_ONLY / LIVE_WARMUP / LIVE_ACTIVE / LIVE_COOLDOWN 상태머신
- [ ] Raw Trade 단일 구독 (3개 심볼)
- [ ] 로컬 Aggregation (common/MultiAggregator 재사용)
- [ ] cutover_ts 기반 병합
- [ ] context_id/generation_id 격리
- [ ] BURST 감지 (2단계 게이트 + 히스테리시스)
- [ ] WS 재연결 (backoff/jitter/cooldown)
- [ ] coalesce + 하단 티커
- [ ] 통합 진단 패널 (3개 심볼 상태)
- [ ] Upbit 유사 UI 스타일 (dual-chart-monitor.html 기준)
- [ ] config.json, 로그 로테이션
- [ ] 듀얼 모니터 핫플러그 대응
- [ ] **Light/Dark 테마 토글 + 토큰 시스템 적용** (DEC-027)
- [ ] **상승=빨강 / 하락=파랑 유지 + 경고/장애 의미 분리** (DEC-027)

---

## ⚠️ RISK REGISTER

### ✅ RISK-001~005, 007: 해결/완화됨 (update_history.txt)

### ⚠️ RISK-002: DB 크기 증가
- 수동 cleanup 필요
- Phase 2.5에서 DB는 Cloud에서 관리 (PC 앱은 읽기 전용)

### 🟡 RISK-006: 다중 DB 쓰기
- Phase 2에서 해결 예정 (독립 DB 파일)

### 🟡 RISK-PC-001: PC 앱 UI 프리징
- **대응**: coalesce, 스레드 분리, bounded 버퍼
- **허용**: 중간 프레임 생략 (최신만 렌더)

### 🟡 RISK-PC-002: WS 재연결 폭주
- **대응**: backoff/jitter/window/cooldown, Upbit 레이트리밋
- **모니터링**: 재연결 횟수, last_message_age

### 🟡 RISK-PC-003: 데이터 섞임/유령 캔들
- **대응**: context_id, generation_id, cutover_ts
- **검증**: mismatch 즉시 폐기, UI 렌더링 전 필터

### 🟡 RISK-PC-004: BURST 오탐/미탐
- **대응**: 2단계 게이트, 히스테리시스, 쿨다운
- **튜닝**: 실전 운영 후 파라미터 조정

### 🟡 RISK-PC-005: 메모리 누수 (24/7)
- **대응**: bounded 버퍼 (시간 + 개수 2중 제한)
- **모니터링**: overlay 범위, 스냅샷 크기

### 🟡 RISK-PC-006: 라이트 테마에서 가독성/계층 붕괴
- **증상**: 그리드 과진/희미, 카드 경계 소실, 경고가 차트 색(빨강/파랑)과 혼동, 상단 바 과도한 자극, KPI 강조 실패
- **대응**: 토큰 기반 테마 + 계층 규칙 강제 (DEC-027)
- **검증**: Light/Dark 모두에서 동일한 정보 계층 체감 유지

---

## 📝 DECISION LOG (주요 결정)

### DEC-001~010: ✅ 확정 (update_history.txt)
- SQLite WAL, 배치100, 틱봉 음수, 9시간 재연결, 무제한 재연결

### DEC-011: Phase 2 DB 마이그레이션 (P2-001)
- ohlcv.sqlite → ohlcv_short.sqlite (일회성 rename)
- 안전장치: 기존 파일 보호, 실패 시 fail-fast

### DEC-012: 중복 제거 우선순위 (P2-002)
- trade_uuid → sequential_id → fallback 5-tuple
- 런타임 필드 존재 확인

### DEC-013: 큐 오버로드 격리/회복 (P2-003)
- HIGH_WATERMARK: DEGRADED + 백프레셔
- HARD_LIMIT: 의도적 연결 종료 → 쿨다운 → 재연결
- drop 우선이 아닌 격리/회복 중심

### DEC-014: 디렉토리 구조 분리 ✅
- common/cloud/pc_app 구조로 코드 재사용성/유지보수성 향상
- 상태: ✅ 확정 (2026-01-28)

### DEC-015: PC 앱 듀얼 모니터 UI (Phase 2.5) ✅
- **듀얼 모니터 기본 전제**
- 모니터 1: BTC + ETH 듀얼 차트 (50:50)
- 모니터 2: XRP 차트 (80%) + 통합 진단 패널 (20%)
- 단일 프로세스, 2개 독립 창, PyQt5/PySide6
- 단일 모니터 환경 시 자동 폴백 (탭/스택 모드)
- **이유**: 트레이딩 효율성, 동시 모니터링, 진단 정보 통합
- **상태**: ✅ 설계 확정 (2026-01-28)
- **참조**: `pc_app/DESIGN_DUAL_MONITOR.md`

### DEC-016: PC 앱 WebSocket 최적화 (Phase 2.5) ✅
- **Raw trade 단일 구독 방식** (구독 수 항상 3개 고정)
- **로컬 Aggregation** (common/MultiAggregator 재사용)
- **타임프레임 변경 시 WS 재구독 불필요** (0.1초 전환)
- **"Active + Previous" 정책 폐기** (TTL 불필요)
- **메모리**: 3 심볼 × 5 타임프레임 × 1000 캔들 = 약 1.5 MB (+1 MB)
- **이유**: 구독 수 감소, 전환 로직 단순화, Upbit 레이트리밋 안정성
- **상태**: ✅ 설계 확정 (2026-01-28)
- **참조**: `pc_app/WEBSOCKET_OPTIMIZATION.md`

### DEC-017: PC 앱 common/ 재사용 방식 (Phase 2.5) ✅
- **vendor 복사 방식** 권장 (pc_app/vendor/)
- **직접 참조 금지** (sys.path 조작 금지)
- **이유**: 환경 격리, 배포 단순화, 수정 영향 최소화
- **대상**: tick_aggregator.py, timeframe_aggregator.py, 순수 계산 로직만
- **금지**: asyncio, OS 종속 로직, Cloud collector 수정
- **상태**: ✅ 원칙 확정 (2026-01-28)

### DEC-018: PC 앱 설정 파일/로그 로테이션 (Phase 2.5) ✅
- **설정 파일**: config.json (실행 경로 우선, %APPDATA% 대안)
- **로그 로테이션**: maxBytes=50MB, backupCount=5
- **로그 위치**: %LOCALAPPDATA%/UpbitRealTimeChart/logs/app.log
- **이유**: 하드코딩 방지, 24/7 무한 증가 방지
- **상태**: ✅ 원칙 확정 (2026-01-28)

### DEC-019: PC 앱 SQLite 접근 가정 (Phase 2.5) ✅
- **로컬 복사본만** (네트워크 공유 SQLite 금지)
- **mode=ro + immutable=1** (읽기 전용 강제)
- **동기화**: 사용자 책임 (rsync, scp 등)
- **이유**: 락/파일깨짐 위험, WAL 충돌 방지
- **상태**: ✅ 원칙 확정 (2026-01-28)

### DEC-020: PC 앱 BURST 계산 기준 (Phase 2.5) ✅
- **trade_ts_ms 기반** (Upbit 제공 timestamp)
- **로컬 수신 시각 금지** (네트워크 지연 오탐 방지)
- **진단용**: recv_rate 별도 계산 (UI 표기)
- **상태 전이**: trade_ts_ms 우선
- **이유**: 시간 기반 윈도우 정확성, 틱 몰림 오탐 방지
- **상태**: ✅ 원칙 확정 (2026-01-28)

### DEC-021: PC 앱 Hybrid 레벨 정의 (Phase 2.5) ✅
- **레벨 1**: Python-only + decimation
- **레벨 2**: Hybrid-lite (핫루프만 C++, UI는 Python/PyQt)
- **레벨 3**: Full-native (UI까지 Qt C++)
- **목표**: 레벨 2 (Hybrid-lite)
- **시작**: 레벨 1 → 프로파일링 → 병목 확인 → 레벨 2
- **C++ 범위**: (1) 집계 핫루프, (2) ring buffer/큐, (3) 스냅샷 생성
- **UI**: Python/PyQt 유지
- **이유**: 실측 기반 최적화, YAGNI 원칙
- **상태**: ✅ 원칙 확정 (2026-01-28)

### DEC-022: PC 앱 봉 확정 규칙 (Phase 2.5) ✅
- **시간봉**: "다음 구간 첫 틱 도착 시" 직전 봉 FINAL 확정
- **타이머 기반 금지** (벽시계 자동 닫힘 금지)
- **3틱봉**: 3번째 틱에서 FINAL + 다음 봉 시작
- **이유**: 데이터 정합성 (경합 조건 없음), 거래소 timestamp 우선
- **단점 인지**: 거래 없으면 확정 안 됨 (BTC/ETH/XRP는 유동성 충분)
- **상태**: ✅ 확정 (2026-01-28)

### DEC-023: PC 앱 Upbit WS 레이트리밋 (Phase 2.5) ✅
- **연결**: 초당 최대 5회
- **구독**: 초당 최대 5회 + 분당 100회
- **구현**: rate limiter로 송신 폭주 방지
- **위반 시**: 계정 제재 가능
- **상태**: ✅ 필수 확정 (2026-01-28)

### DEC-024: PC 앱 비상모드 정책 (Phase 2.5) ✅
- **A (틱 드랍 유지) 금지**
- **C + B 동시 직행**:
  - C) 메시지창 (확인 버튼 + 5초 후 자동 닫힘)
  - B) 즉시 DB_ONLY 강제 전환
- **이후**: 자동 LIVE 재진입 금지 (사용자 버튼만)
- **이유**: 정확성 우선, 캔들 희생 방지
- **상태**: ✅ 확정 (2026-01-28)

### DEC-025: Phase 2 테이블 분리(타임프레임별) ✅
- **규칙**: ohlcv_{QUOTE}_{BASE}_tf{timeframe_ms}
- **PK**: ts 단일 PK 유지 (테이블 분리로 충돌 제거)
- **음수 타임프레임**: tf-3 등 그대로 포함 (식별자 안전 처리)
- **마이그레이션**: 기존 테이블 유지, 신규 규칙으로 새 테이블 생성
- **이유**: 동일 ts 덮어쓰기(PK 충돌) 제거
- **상태**: ✅ 확정 (2026-01-28)

### DEC-026: “diff 최소” 운용 규칙(개발/수정 공통) ✅
- **정의**: diff 최소는 “작업량 최소”가 아니라 **변경 리스크(회귀/드리프트) 최소**를 의미
- **금지**: 기능 축소/스펙 삭제/완화, TODO/임시 땜빵
- **우선순위**: AC/SSOT 충족 > 운영 안정성(재연결/종료/누수/중복) > diff 최소
- **예외**: AC 충족을 위해 구조 변경이 필수라면, diff 최소를 이유로 회피 금지(SSOT/Task에 근거 남기기)
- **상태**: ✅ 원칙 확정 (2026-02-12)

### DEC-027: PC 앱 Light/Dark 테마 규칙 ✅
- **전제**: 라이트(흰 배경) 기본 + 다크(검정/다크) 옵션(토글)
- **토큰 기반**: background/surface/border/text-primary/text-secondary/grid/accent/warning/danger 등을 역할 기반으로 정의
- **가독성**: 테마 전환 시 텍스트/아이콘/그리드/구분선 자동 조정, 동일한 정보 계층 체감 유지
- **차트 색 확정**: **상승=빨강, 하락=파랑**(가격 전용 의미)
- **경고/장애 색 분리**: 가격색(빨강/파랑)과 혼동되지 않게 별도 의미체계(배지/아이콘/스트립/테두리 강조 중심)
- **라이트 취약점 방지(필수)**:
  - 그리드/축 과진·희미 방지(3단 대비)
  - 카드 경계 소실 방지(surface/background 톤 분리)
  - 상단 스트립 과자극 방지(Info/Warning/Critical 톤 분리)
  - KPI 계층(숫자/단위/설명) 고정, 임계치 초과 시만 강강조
- **상태**: ✅ 원칙 확정 (2026-02-12)

---

## 🚧 PHASE 2: Cloud Collector 고도화 (간소화)

### 목표
- DB 파일 분리로 write 경합 축소
- Collector 단위 장애 격리
- 합성 봉(메모리 전용) vs 직접 수집 봉(DB 저장) 분리
- 재연결 폭주 방지, graceful shutdown, 리소스 누수 0

### Scope
- ✅ In: Manager, 독립 WS/DB, DerivedAggregator, config/CLI/HTTP, 재시도, 오버로드 보호
- ❌ Non: watchdog, 새 파일(승인 없이), REST 보정, 외부 재시작

### 아키텍처
CollectorManager
├─ ShortCollector (ohlcv_short.sqlite)
│ ├─ Timeframe(500ms, 1s) + Tick(3) → DB
│ └─ Derived(5s,10s,33s,57s,1m) → 메모리 전용
├─ MidCollector (ohlcv_10s_1m.sqlite)
│ └─ Timeframe(10s, 1m) → DB
└─ LongCollector (ohlcv_10m.sqlite)
└─ Timeframe(10m) → DB


### 핵심 정책 (POL-001~013)
- **POL-001**: CollectorManager (생성/관리, graceful shutdown, 전역 레이트리밋)
- **POL-002**: Collector (독립 WS/DB/Writer, 재연결, generation 모델)
- **POL-003**: generation (재연결 시 증가, Derived reset)
- **POL-004**: 재연결 (backoff/jitter/쿨다운)
- **POL-005**: DB (WAL, locked/busy 재시도, DEGRADED, 테이블은 timeframe별 분리: ohlcv_{PAIR}_tf{timeframe_ms})
- **POL-006**: 중복 제거 (trade_uuid → sequential_id → fallback)
- **POL-007**: 큐/오버로드 (HIGH_WATERMARK, HARD_LIMIT)
- **POL-008**: DerivedAggregator (Short만, 1초봉 기반, 메모리 전용)
- **POL-009**: graceful shutdown (WS close → drain → flush → join)
- **POL-010**: 로그 (틱 로그 금지, 30초 통계, rate-limit)
- **POL-011**: HTTP (--http-port 0 또는 미지정 시 OFF)
- **POL-012**: 데이터 정합성 (price/volume/timestamp 검증)
- **POL-013**: silent failure 방지 (last_message_age 제공)

### 구현 요구사항 (P2-REQ-001~012)
- P2-REQ-001: Manager + Config
- P2-REQ-002: DB 분리 + 마이그레이션
- P2-REQ-003: DerivedAggregator
- P2-REQ-004: config_upbit_exchange.yml
- P2-REQ-005: CLI (--pairs, --http-port)
- P2-REQ-006: 통계 로그 30초
- P2-REQ-007: HTTP /health, /stats
- P2-REQ-008: 데이터 정합성
- P2-REQ-009: 중복 제거
- P2-REQ-010: 전역 레이트리밋
- P2-REQ-011: DB 재시도
- P2-REQ-012: 큐 오버로드 보호

---

## 🚧 PHASE 2.5: PC 차트 앱 (상세 명세)

### 1. Objective (목표)

- **Windows PC용 트레이딩/매매 전용 차트 앱**
- **평시**: Oracle Cloud DB (SQLite) 읽기 전용 조회
- **폭주(BURST)**: Upbit WS 직접 구독 + 메모리 LIVE 오버레이
- **체감**: "업비트 앱처럼 마지막 봉이 틱 단위로 변동"
- **비목표**: 부드러운 애니메이션 (있는 그대로 표시)
- **운영 원칙**: 방어적 / 24/7 기준 / UI 프리징 0 / 리소스 누수 0 / reconnect 폭주 방지

### 2. 아키텍처 개요

#### 2.1 전체 구조
[PC 앱]
├─ MainEngine
│ ├─ WS Manager (3 symbols, raw trade)
│ ├─ Aggregation Engine (common/MultiAggregator)
│ ├─ BURST Detector (2단계 게이트 + 히스테리시스)
│ ├─ Overlay Manager (bounded, cutover_ts)
│ └─ Snapshot Provider (UI용 immutable)
├─ UI Layer (PyQt5/PySide6)
│ ├─ Window 1: XRP + BTC 듀얼 차트
│ ├─ Window 2: ETH 차트 + 통합 진단 패널
│ └─ 하단 티커 (coalesce/드랍 안내)
└─ DB Layer (SQLite read-only)


#### 2.2 데이터 흐름
[Upbit WS] → [raw trade] → [Aggregator] → [Overlay] → [Snapshot] → [UI]
↓
[BURST Detector]
↓
[Mode Switch]
↓
[DB (Cloud)] ←───────── [cutover_ts 병합] ───────→ [Overlay]


### 3. 핵심 기능 명세

#### 3.1 듀얼 모니터 UI (DEC-015)

**모니터 1 (메인 트레이딩 창) - XRP & BTC**
- 좌우 50:50 분할
- 각 차트:
  - 심볼 헤더 (가격, 등락률, Upbit 로고)
  - 컨트롤 바 (타임프레임 드롭다운, 틱 레이어 토글, 상태 칩 3개)
  - 차트 영역 (캔들스틱 + 가격 레이블, X/Y축 + 숫자 표시)
  - 거래량 차트 (Y축 + 거래금액 숫자 표시)
  - 하단 티커 (coalesce/드랍 안내)
  - 초기 진입 시 DB에서 충분한 봉 로드 → 캔들 폭 ~3px 유지

**모니터 2 (ETH + 진단 패널)**
- 좌측 80%: ETH 차트 (모니터 1과 동일 구성)
- 우측 20%: 통합 진단 패널
  - 현재 컨텍스트 (3개 심볼 전체)
  - Now(KST), last_tick_trade_ts(심볼별, KST), last_message_age(심볼별)
  - cutover_ts(KST), overlay 범위
  - DB catch-up 상태
  - invalid_trades / ooo_corrected / ooo_dropped (심볼별)
  - 연결 요약 (connected_since, 최근 에러, reconnect_attempts)
  - BURST 지표 (tick_rate, notional_rate, abs_return_rate)
  - 최근 갭 이벤트 3개
  - 행동 버튼 3개:
    - (1) LIVE 시작/유지 (심볼 선택)
    - (2) DB로 전환(안정) (심볼 선택)
    - (3) BURST 알림 ACK (전체)

**단일 모니터 폴백**
- OS가 2번 모니터 미인식 시 자동 병합
- 탭/스택 모드로 전환
- 상단 배지로 안내
- 마지막 창 배치는 config.json에 저장

**상세**: `pc_app/DESIGN_DUAL_MONITOR.md`

#### 3.2 WebSocket 구독 전략 (DEC-016)

**Raw Trade 단일 구독**
- 3개 심볼의 raw trade만 (XRP, BTC, ETH)
- 타임프레임별 구독 폐기
- 구독 수 항상 3개 고정 (심볼당 1개)

**로컬 Aggregation**
- PC 앱에서 common/MultiAggregator 사용
- raw trade → 1m/5m/15m/1h/일봉 등 모든 타임프레임 동시 생성
- Cloud collector와 동일한 검증된 로직 재사용

**타임프레임 변경**
1. active_timeframes[symbol] = new_timeframe (즉시 변경)
2. DB에서 historical 데이터 로드
3. UI 렌더링 (0.1초 완료)
4. 이후 LIVE는 Aggregator에서 자동 업데이트

**"Active + Previous" 정책 불필요**
- raw trade는 항상 동일하게 수신
- Aggregator는 모든 타임프레임 동시 유지
- 전환 시 표시 대상만 변경 (데이터 전환 없음)
- TTL, Previous 폐기 등 불필요

**메모리 관리**
- 3 심볼 × 5 타임프레임 × 1000 캔들 = 약 1.5 MB (+1 MB)
- 무시 가능한 수준

**섞임 방지**
- context_id: (symbol, generation_id)
- generation_id: WS 재연결 시 증가
- UI는 현재 generation_id와 일치하는 데이터만 렌더
- mismatch 즉시 폐기

**상세**: `pc_app/WEBSOCKET_OPTIMIZATION.md`

#### 3.3 상태 모델

**DataSourceMode**
- `DB_ONLY`: 평시, DB 조회
- `LIVE_WARMUP`: LIVE 전환 준비 (DB seed 로드)
- `LIVE_ACTIVE`: 폭주 중, WS 직접 구독
- `LIVE_COOLDOWN`: LIVE 종료 준비 (DB catch-up 확인)

**전환 흐름**
DB_ONLY → LIVE_WARMUP → LIVE_ACTIVE → LIVE_COOLDOWN → DB_ONLY
↑ ↓
└──────────────────────────────────────────────────────┘
(BURST 종료 or 사용자 전환)


**WSState (LIVE 계열 전용)**
- `WS_CONNECTED`: 정상
- `WS_SUSPECT_SILENT`: 무음 의심
- `WS_RECONNECTING`: 재연결 중
- `WS_COOLDOWN`: 재연결 대기
- `WS_DEGRADED`: 장기 실패

**BURSTState**
- `NORMAL`: 정상
- `CANDIDATE`: 1차 게이트 통과 (오탐 허용)
- `ACTIVE`: 2차 게이트 통과 (확정)
- `COOLDOWN`: 해제 대기

#### 3.4 BURST 감지 (2단계 게이트 + 히스테리시스)

**입력 (필수)**
- trade_ts_ms, price, volume
- 파생: tick_rate, notional_rate, abs_return_rate

**2단계 게이트**
- 1차: tick_rate로 빠른 후보 감지 (CANDIDATE)
- 2차: notional_rate OR abs_return_rate로 확정 (ACTIVE)

**히스테리시스**
- enter 임계치 > exit 임계치
- 출렁임 방지

**쿨다운**
- ACTIVE 종료 후 COOLDOWN 유지
- 쿨다운 기간 동안 재진입 방지

**초기값 (튜닝 가능)**
- tick_rate: W=10초 윈도우, 임계치 X tps
- notional_rate: 임계치 Y 원/초
- abs_return_rate: 임계치 Z %/초
- 쿨다운: 30초

**기준 시간**
- **trade_ts_ms 기반** (Upbit 제공 timestamp)
- recv_rate는 진단용만 (UI 표기)

#### 3.5 LIVE 오버레이 범위/정합성

**오버레이 범위**
- "현재 진행 봉 1개"가 아니라 **최근 N구간까지** 관리

**bounded 정책 (2중 제한)**
- overlay_horizon: 최근 15분 (기본 추천)
- overlay_max_candles_per_tf: 5000개/페어/타임프레임 (기본 추천)
- 실제 유지량 = clamp(시간기반 계산, max_candles)

**cutover_ts 기반 Merge Rule**
- cutover_ts_ms: LIVE_WARMUP 진입 시 고정
- start_ts < cutover_ts → DB Layer 우선
- start_ts >= cutover_ts → Live Overlay 우선 (덮어쓰기)
- cutover_guard_ms: 경계 안전마진 (튜닝)

**out-of-order 처리**
- ooo_allowance_ms (튜닝) 이내: 해당 bucket 보정
- 초과: 드랍 + 계수 + rate-limit 로그

**LIVE→DB 복귀 (DB catch-up barrier)**
- LIVE_COOLDOWN 동안 오버레이 유지
- DB가 오버레이의 최신 확정 구간을 따라왔는지 확인
- 확인 후 DB_ONLY 복귀
- 확인 방법: "최신 확정 봉 timestamp" 같은 경량 메타

#### 3.6 WS 재연결 (폭주 방지)

**Exponential backoff + jitter + 상한 + cooldown**
- initial_delay: 0.5s
- max_delay: 30s
- jitter: ±20%
- reconnect_window: 5분
- max_attempts_in_window: 20회
- exceed 시 cooldown: 60s (WS_COOLDOWN)
- 15분 이상 장기 실패 시 WS_DEGRADED

**partial vs global silent**
- partial: 특정 심볼만 무음 → 재구독 1회 → 계속 무음이면 재연결
- global: 모든 심볼 무음 → 즉시 재연결

**파싱 실패/이상값**
- 드랍 + 계수 + rate-limit 로그
- **파싱 실패만으로 재연결 금지**

**Upbit 레이트리밋 (DEC-023)**
- 연결: 초당 최대 5회
- 구독: 초당 최대 5회 + 분당 100회
- rate limiter로 송신 폭주 방지
- **위반 시 계정 제재 가능**

#### 3.7 UI 렌더링 규칙

**coalesce (허용)**
- 엔진: every tick으로 LIVE 갱신
- UI: 고정 주기 (20~60Hz)로 최신 스냅샷만 그림
- UI가 못 따라오면 중간 스냅샷 버림 (coalesce)

**하단 티커 (coalesce 안내)**
- coalesce 발생 시: 좌→우 스크롤 안내문구
- 예: "LIVE 업데이트가 폭주하여 중간 프레임을 생략하고 최신 상태로 점프 표시 중…"
- 1줄 유지, 우선순위로 덮어쓰기, 연속은 카운트로 흡수

**표시용 틱 레이어 (decimation)**
- 계산용 틱: 전량 반영 (최후까지 유지)
- 표시용 틱: 전용 버퍼 + decimation 허용
- 시간-셀 버킷으로 대표 샘플 유지 (기본: "마지막 틱")
- 폭주 시 자동 디그레이드 레벨 (0~3)
  - LEVEL 증가: 셀 크기 확대, 표시 버퍼 축소
  - LEVEL 3: 표시용 틱 레이어 자동 OFF (티커 안내)

**드랍 우선순위 (고정)**
1. 표시용 틱 레이어 데이터 드랍 (시각화 희생)
2. 중간 스냅샷 coalesce (프레임 생략)
3. 진단/통계 UI 업데이트 빈도 다운
4. 오버레이 범위 축소 (최근 구간만)
5. ~~Previous-WARM 구독 해제~~ → Raw trade 방식에서 해당 없음

**비상모드 (DEC-024)**
- **A (틱 드랍 유지) 금지**
- **C + B 동시 직행**:
  - C) 메시지창 (5초 후 자동 닫힘)
  - B) 즉시 DB_ONLY 강제 전환
- 이후 자동 LIVE 재진입 금지 (사용자 버튼만)

#### 3.8 차트 표현 규칙

**시간봉 (0.5s/1s/10s/1m/10m 등)**
- x축 라벨: KST 시간
- 거래 없는 구간: 보간 금지 → 빈 구간(갭) 그대로
- WS 장애/재연결 갭: 갭 마커(구간 밴드) 표시
- 마지막 봉: LIVE일 때 틱마다 논리 갱신 (렌더는 coalesce 가능)
- **봉 확정(FINAL)**: "다음 구간 첫 틱 도착 시" 직전 봉 확정 (타이머 기반 금지)

**3틱봉**
- x축: 인덱스 기반 (균등 간격)
- 각 봉 시간: 툴팁/라벨로 KST 표시
- 3번째 틱: FINAL 확정 + 다음 봉 시작
- 표시용 틱 레이어: 기본 OFF (옵션 ON 가능)

**버킷 기준 시간**
- **Upbit 제공 trade_ts_ms** (로컬 수신 시각 금지)
- bucket_start_ts = floor(trade_ts_ms / tf_ms) * tf_ms
- bucket_start_ts == cur_start_ts → LIVE 업데이트
- bucket_start_ts > cur_start_ts → 기존 LIVE FINAL + 새 LIVE 생성

#### 3.9 UI 스타일 (Upbit 유사)

**디자인 기준**: `dual-chart-monitor.html` 프로토타입

**핵심 디자인 요소**
1. **UPbit 브랜딩**
   - 로고: 파란 배경 #0051c7, 흰색 텍스트 'upbit' (Arial, bold)
   - 상단 헤더: 로고 + 심볼명 + 심볼코드

2. **컬러 팔레트**
   - 차트 배경: #0a1929 (다크 네이비)
   - 상승(빨강): #f23645
   - 하락(파랑): #2979ff
   - 텍스트: #6b7280 계열
   - 배경: 흰색(헤더), 회색(컨트롤), 노란색(티커)

3. **레이아웃**
   - 1920x1080 창 크기 고정
   - 심볼 헤더 → 컨트롤 바 → 차트 영역 → 거래량 차트 → 하단 티커
   - 상태 칩: pill shape, 아이콘 포함

4. **폰트**
   - 시스템: -apple-system, BlinkMacSystemFont, Segoe UI, Malgun Gothic
   - UPbit 로고: Arial

5. **성능 제약**
   - 애니메이션 최소화 (프리징 방지)
   - SVG 기반 차트 렌더링

**구현**: PyQt5/PySide6 스타일시트로 1:1 재현

#### 3.10 DB 조회 정책

**DB_ONLY**
- 초기 로딩: 최근 N개 또는 최근 T분
- 평시 갱신: 느린 폴링 (수초~수십초) + 온디맨드
- 폴링: 화면 필요 구간만 쿼리

**LIVE_WARMUP**
- DB seed 용 1회 최소 조회
- 마지막 확정 봉 + 현재 구간 시작 정보

**LIVE_ACTIVE**
- DB 폴링 기본 OFF
- 예외: 사용자 명시 요청 수준만 제한적 허용

**LIVE_COOLDOWN**
- DB catch-up barrier 확인용 경량 폴링만
- barrier 만족 시 DB_ONLY 복귀

#### 3.11 로깅/관측성

**필수 이벤트 로그 (간결 + rate-limit)**
- 모드 전환 (DB↔LIVE)
- WS 상태 변화
- BURST 상태 변화
- 갭 시작/종료
- decimation/드랍 레벨 변화
- 비상모드 강등

**진단 패널 카운터**
- coalesce_count
- tick_display_drop_count / tick_display_level
- invalid_trades / ooo_corrected / ooo_dropped
- reconnect_attempts_in_window
- emergency_fallback_events

**틱 전체 로그 금지**

#### 3.12 설정 파일/로그 로테이션 (DEC-018)

**설정 파일: config.json**
- 우선: 실행 파일과 동일 폴더
- 대안: %APPDATA%/UpbitRealTimeChart/config.json
- 없으면 기본값으로 생성
- UI 변경 값 저장

**설정 항목**
- DB 파일 경로, 기본 심볼/타임프레임
- BURST 감지 임계값 (튜닝 가능)
- WS 재연결 파라미터
- 창 배치 (모니터/좌표/크기)

**로그 로테이션**
- 위치: %LOCALAPPDATA%/UpbitRealTimeChart/logs/app.log
- 정책: maxBytes=50MB, backupCount=5
- 24/7 무한 증가 방지

#### 3.13 SQLite 접근 (DEC-019)

**로컬 복사본만**
- 네트워크 공유 SQLite 직접 오픈 금지
- 사용자가 주기적 동기화/복사 (rsync, scp 등)

**오픈 방식**
- file: URI + mode=ro
- 가능하면 immutable=1 (읽기 전용/불변 강제)

**실패 시**
- UI 경고 표시

#### 3.14 common/ 재사용 방식 (DEC-017)

**vendor 복사 권장**
- pc_app/vendor/로 필요 코드만 복사
- sys.path 조작 금지
- Cloud collector 원본 직접 참조 금지

**대상**
- tick_aggregator.py, timeframe_aggregator.py
- 순수 계산 로직만

**금지**
- asyncio, OS 종속 로직
- Cloud collector 수정

#### 3.15 Hybrid (Python + C++) 방향 (DEC-021)

**레벨 정의**
- 레벨 1: Python-only + decimation
- 레벨 2: Hybrid-lite (핫루프만 C++, UI는 Python)
- 레벨 3: Full-native (UI까지 C++)

**목표**: 레벨 2 (Hybrid-lite)

**시작**: 레벨 1 → 프로파일링 → 병목 확인 → 레벨 2

**C++ 범위 (레벨 2)**
1. 틱 → 캔들/3틱봉 집계 핫루프
2. bounded ring buffer / lock-free 큐
3. 스냅샷 생성/복사 최소화

**UI**: Python/PyQt 유지

**원칙**: YAGNI, 실측 기반 최적화

#### 3.16 PC 부하/스레드 분리

**UI 메인 스레드**
- WS 처리/집계/DB I/O 금지
- 스냅샷(immutable)만 주기적 소비

**백그라운드 Worker**
- WS 수신 + tick→candle 집계
- QThread 또는 Thread 사용

**폭주 시**
- UI 프리징 금지
- 표시용 요소 우선 드랍 (우선순위 준수)
- 집계가 밀려도 운영 불가 수준이면:
  - **multiprocessing 허용** (GIL 회피)
  - 인터페이스: SnapshotProvider 형태로 고정 (교체 가능)
  - 과도 추상화 금지

#### 3.17 Android 2채널 알람 (중기 개발, 설계만)

**이번 범위**: Non-scope (구현하지 않음)

**중기 설계 원형**
- 채널 A: Cloud 감지 → Android 알림
- 채널 B: Android 로컬 WS 직접 구독 → 독립 알람
- 알람 앱 수준: ACK 전까지 반복, 화면 깨우기, Doze 대응

**PC 앱 연결**
- Android 알람 → 노트북 깨움 → PC 앱 실행 → LIVE 전환

**PC 앱 준비**
- BURST 알림 ACK 버튼 (알림 반복 억제 기준점)

### 4. Hard No (절대 금지)

#### 4.1 PC 앱 금지 사항
- UI 스레드에서 WS 수신/DB 쿼리/집계 루프
- 틱 원본 전량 저장/전량 렌더
- 거래 없는 구간 보간 (없는 캔들 채우기)
- context_id 없이 데이터 라우팅/집계/렌더
- Active/Previous 2개 초과 컨텍스트 유지 (Raw trade 방식에서는 1개만)
- 비상모드에서 "틱 드랍으로 LIVE 유지(A)" (반드시 C+B 직행)
- 비상모드 이후 자동 LIVE 재진입 (사용자 버튼만)
- healthcheck 서버/FastAPI/REST API 추가
- Cloud collector 코드 구조 훼손

#### 4.2 Cloud 금지 사항
- 기존 원칙 유지 (update_history.txt)

### 5. Definition of Done (측정 가능)

#### 5.1 PC 앱 기능
- [ ] 듀얼 모니터 UI 정상 표시
- [ ] 단일 모니터 폴백 동작
- [ ] 드롭다운 심볼/타임프레임 선택
- [ ] 상태 칩 3개 정상 갱신
- [ ] 통합 진단 패널 갱신
- [ ] 버튼 3개 정상 동작
- [ ] DB_ONLY 차트 출력 (KST 축)
- [ ] LIVE_ACTIVE 마지막 봉 틱 갱신
- [ ] 갭 표시 규칙 준수
- [ ] 3틱봉 인덱스축 + KST 툴팁
- [ ] Raw Trade 단일 구독 (3개)
- [ ] 타임프레임 즉시 전환 (0.1초)
- [ ] Light 기본 + Dark 옵션 토글 동작
- [ ] 테마 전환 시 글꼴/아이콘/그리드/구분선 가독성 유지
- [ ] 가격(빨강/파랑)과 경고/장애 표현 혼동 없음

#### 5.2 PC 앱 성능/안정성
- [ ] BURST 폭주 시 UI 프리징 없음
- [ ] 메모리 무한 증가 없음
- [ ] 드랍 우선순위 작동
- [ ] 하단 티커 안내
- [ ] WS 재연결 폭주 없음
- [ ] 종료 시 누수 없음
- [ ] config.json 정상
- [ ] 로그 로테이션 적용
- [ ] SQLite mode=ro 오픈
- [ ] 듀얼 모니터 핫플러그 대응

#### 5.3 PC 앱 섞임 방지
- [ ] Raw Trade 방식 섞임 방지
- [ ] 타임프레임 변경 시 섞임 없음
- [ ] context_id mismatch 즉시 폐기

#### 5.4 PC 앱 LIVE 오버레이
- [ ] cutover_ts 병합 규칙 준수
- [ ] bounded 정책 동작
- [ ] DB catch-up barrier 복귀

#### 5.5 PC 앱 WS 장애 대응
- [ ] partial/global silent 구분
- [ ] 단계적 대응
- [ ] 파싱 실패만으로 재연결하지 않음
- [ ] Upbit 레이트리밋 준수

---

## 📦 BACKLOG (향후 작업)

### Phase 2 구현 🚧
- BL-P2-CORE: Manager, Short/Mid/Long, DB 분리, Derived, generation
- BL-P2-OPS: config/CLI/HTTP, 통계, 정합성
- BL-P2-PROTECT: 중복 제거, 전역 레이트리밋, DB 재시도, 큐 보호
- BL-P2-VERIFY: 24시간 테스트, AC 검증

### Phase 2.5: PC 차트 앱 (설계 완료 ✅, 구현 대기 🚧)

**BL-PC-001: 듀얼 모니터 UI 구현**
- 모니터 1: XRP + BTC 듀얼 차트
- 모니터 2: ETH + 진단 패널
- PyQt5/PySide6, 단일 프로세스, 2개 독립 창
- 상세: `pc_app/DESIGN_DUAL_MONITOR.md`

**BL-PC-002: Raw Trade WebSocket + 로컬 Aggregation**
- 3개 심볼 raw trade 구독 고정
- common/MultiAggregator 재사용
- 타임프레임 변경 시 즉시 전환 (0.1초)
- 상세: `pc_app/WEBSOCKET_OPTIMIZATION.md`

**BL-PC-003: DB + LIVE 오버레이 병합**
- DB_ONLY / LIVE_WARMUP / LIVE_ACTIVE / LIVE_COOLDOWN
- BURST 감지, cutover_ts 병합, bounded 메모리
- 상태 칩 (LIVE/DB, WS:OK, NORMAL/BURST)

**BL-PC-004: UI 스타일 (Upbit 유사)**
- dual-chart-monitor.html 프로토타입 기준
- 컬러: #0a1929(차트배경), #f23645(상승), #2979ff(하락), #0051c7(로고)
- 1920x1080 고정, 상단 헤더/컨트롤/상태칩, 하단 티커

**BL-PC-005: BURST 감지 구현**
- 2단계 게이트 + 히스테리시스
- trade_ts_ms 기반
- 초기값 제공, 튜닝 가능

**BL-PC-006: WS 재연결 안정화**
- backoff/jitter/cooldown
- partial/global silent 구분
- Upbit 레이트리밋 (연결 5회/초, 구독 5회/초 + 100회/분)

**BL-PC-007: coalesce + decimation 구현**
- 중간 스냅샷 버리기
- 표시용 틱 레이어 드랍
- 하단 티커 안내

**BL-PC-008: config.json + 로그 로테이션**
- 설정 파일 생성/로드/저장
- 로그 로테이션 (50MB, backupCount=5)

**BL-PC-009: 통합 진단 패널**
- 3개 심볼 전체 상태
- BURST 지표, 연결 요약, 갭 이벤트

**BL-PC-010: Hybrid 레벨 1→2 전환 (선택)**
- 프로파일링 후 병목 확인
- C++ 핫루프 (집계, ring buffer, 스냅샷)

**BL-PC-011: Light/Dark 테마 토큰 + 토글(필수)**
- Light 기본(흰 배경) + Dark 옵션
- 토큰: background/surface/border/text/grid/accent/warning/danger
- 테마 전환 시 가독성/정보 계층 유지
- 가격(빨강/파랑) 전용 의미 + 경고/장애 의미 분리
- 라이트 취약점 5종(그리드/카드/경고/스트립/KPI) 방지

### 단기 (Phase 2 완료 후)
- P2-REQ로 흡수됨

### 중기 (1개월)
- BL-006: PC 차트 앱 구현 완료 (Phase 2.5)
- BL-007: freqtrade Web UI 연동
- BL-008: Android 2채널 알람 앱

### 장기 (3개월+)
- BL-009: REST API, 데이터 조회
- BL-010: CSV/Parquet 내보내기
- BL-011: 데이터 분석
- BL-012: 실시간 알림 (확장)

---

## 🔄 UPDATE HISTORY

### v3.3 - 2026-02-12 (diff-최소 가드레일 + 테마 규칙 추가)
- IR-006 추가: diff 최소 = 변경리스크 최소(기능 축소/스펙 삭제 금지, AC 우선)
- DEC-026 추가: diff-최소 운용 규칙 확정
- DEC-027 추가: PC 앱 Light/Dark 테마 토큰 규칙 + 가격색(빨강/파랑) 확정 의미 분리
- AC-PC-001/002 및 DoD/Backlog에 테마 항목 추가
- RISK-PC-006 추가: 라이트 테마 가독성/계층 붕괴 리스크 및 완화

### v3.2 - 2026-02-01 (PC 앱 UI 보강)
- ETH 창 UI를 trading-monitor.jsx 기준으로 보강
- 차트/거래량 축과 좌표 숫자 표시 추가
- 초기 DB 로드로 캔들 폭 ~3px 유지
- 진단 패널 버튼(LIVE/DB) 동작 연결
- 상단 네비게이션 바 제거 (ETH 창)

### v3.1 - 2026-01-28 (Phase 2 P0 안정화 반영)
- DEC-025: 타임프레임별 테이블 분리 확정 (PK 충돌 제거)
- flush_timer 종료 레이스 제거 정책 반영 (cancel + idle wait + 재스케줄 차단)
- unfinished_tasks 비공개 API 제거 정책 반영
- Cloud 로그 경로를 프로젝트 루트 logs/로 고정

### v3.0 - 2026-01-28 (Phase 2.5 PC 앱 전체 명세 추가)
- PC 앱 Objective, 아키텍처, 핵심 기능 전체 상세 명세
- 듀얼 모니터 UI, Raw Trade WebSocket, BURST 감지, LIVE 오버레이, WS 재연결, UI 렌더링, 차트 표현, UI 스타일, DB 조회, 로깅, 설정, SQLite 접근, common/ 재사용, Hybrid, 스레드 분리, Android 알람 설계
- DEC-015~024 추가 (PC 앱 관련 결정 10개)
- AC-PC-001~005 추가 (PC 앱 Acceptance Criteria)
- BL-PC-001~010 추가 (PC 앱 구현 백로그)
- 목적: 작업지시서(1213줄) 기반 SSOT 상세화, PC 앱 설계 완전 문서화
- SSOT 라인 수: 345 → 약 800+ 줄

### v2.4 - 2026-01-28 (Phase 2.5 PC 앱 설계 추가)
- DEC-015: 듀얼 모니터 UI 설계 확정
- DEC-016: Raw Trade WebSocket 최적화 설계 확정
- BL-PC-001~004: PC 앱 구현 백로그 추가
- 목적: PC 차트 앱 설계 문서화, Phase 2.5 준비

### v2.3 - 2026-01-28 (SSOT 간소화)
- Phase 2 정책/요구사항 핵심만 간소화
- 완료된 사항 요약 처리
- 목적: Phase 2 구현 집중, 파일 크기 축소

### v2.2 - 2026-01-28 (디렉토리 리팩토링)
- DEC-014: common/cloud/pc_app 구조 분리
- 목적: 유지보수성, PC 앱 준비

### v2.1 - 2026-01-28 (SSOT 간소화)
- Phase 0/1 완료 내용 → update_history.txt

### v2.0 - 2026-01-27 (Phase 2 명세 확정)
- POL-001~013, P2-REQ-001~012

---

## 📌 NOTES

### 개발 환경

**Cloud (Phase 0/1/2):**
- Python 3.8+, websocket-client>=1.0.0
- Oracle Cloud ARM Core 3, RAM 23GB, HDD 200GB
- Linux 환경

**PC 앱 (Phase 2.5):**
- Python 3.8+
- PyQt5 or PySide6
- Windows 10/11 (64-bit)
- 듀얼 모니터 권장 (단일 모니터 폴백 지원)

### DB 파일

**현재 (Phase 0/1):**
- ohlcv.sqlite

**Phase 2:**
- ohlcv_short.sqlite
- ohlcv_10s_1m.sqlite
- ohlcv_10m.sqlite
- 테이블 네이밍: ohlcv_{QUOTE}_{BASE}_tf{timeframe_ms}

**PC 앱:**
- Cloud DB의 로컬 복사본 (사용자 동기화)

### 실행

**Cloud (Phase 2 구현 후):**
```bash
python collector.py                         # 기본
python collector.py --pairs KRW-BTC,KRW-ETH # pair 지정
python collector.py --http-port 8000        # HTTP 활성화
PC 앱 (Phase 2.5 구현 후):

python pc_app_main.py  # 기본 실행
# config.json에서 설정 로드
종료
Cloud:

Ctrl+C (5초 이내 안전 종료)

PC 앱:

창 닫기 또는 종료 버튼

graceful shutdown (스레드/소켓 정리)

운영
Cloud:

24시간+ 무중단 가능 ✅

로그: tail -f logs/collector.log

9시간 자동 재연결

PC 앱:

노트북/PC 켜진 동안만 LIVE

DB는 Cloud에서 주기적 동기화

설정: config.json

로그: %LOCALAPPDATA%/UpbitRealTimeChart/logs/app.log

📚 참조 문서
Cloud (Phase 2)
update_history.txt (Phase 0/1 상세 이력)

PC 앱 (Phase 2.5)
pc_app/README.md
pc_app/DESIGN_DUAL_MONITOR.md (듀얼 모니터 상세 설계)
pc_app/WEBSOCKET_OPTIMIZATION.md (WebSocket 최적화 상세)
pc_app/WEBSOCKET_STRATEGY.md (v2.0)
pc_app/DUAL_MONITOR_SUMMARY.md (변경 요약)
user_data/upbit_exchange_memo/dual-chart-monitor.html (UI 프로토타입)
user_data/upbit_exchange_memo/phase2 작업시지서.md.md (전체 작업지시서)

마지막 업데이트: 2026-02-12 (v3.3)
다음 단계: Phase 2 v2.0 구현 → 24시간 검증 → Phase 2.5 PC 앱 구현
상태: Phase 2 구현 대기 🚧, Phase 2.5 설계 완료 ✅

::contentReference[oaicite:0]{index=0}