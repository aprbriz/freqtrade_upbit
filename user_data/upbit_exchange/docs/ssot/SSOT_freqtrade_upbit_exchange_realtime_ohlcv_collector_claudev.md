# 업비트 실시간 OHLCV 수집기 + PC 차트 앱 - SSOT (Single Source of Truth)

**프로젝트**: Freqtrade_upbit Real-time OHLCV Collector + PC Chart App  
**버전**: v3.5 (Phase 2.5 DETAILED WORK ORDER 통합)  
**생성일**: 2026-01-26  
**최종 업데이트**: 2026-02-15  

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
- CollectorManager + Short/Mid/Long 분리, DB 파일 분리, Derived 메모리 전용, config/CLI/HTTP

### ✅ Phase 2.5: PC 차트 앱 (구현 완료, 2026-02-12)
- Window1(BTC+ETH) + Window2(XRP+Dashboard) 듀얼 창, Light/Dark 테마, Raw Trade WS, 초기 DB 로드
- **참조**: `docs/DUAL_WINDOW_UI_REDESIGN_WORK_ORDER_UPDATED.md`

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
- [ ] **테마 기본값 Light(흰 배경) 적용** (DEC-027 v1)
- [ ] **테마 토글 Dark(검정/다크) 적용** (DEC-027 v1)
- [ ] **테마 전환 시 텍스트/아이콘/그리드/구분선 자동 조정(가독성 유지)** (DEC-027 v1)
- [ ] **SSH 로그인/연결 설정 다이얼로그 정상 표시** (DEC-033)
- [ ] **SSH 연결 테스트(비동기) 정상 동작** (DEC-033)
- [ ] **SSH Cancel/실패 시 폴백(로컬 스냅샷) 동작** (DEC-028, DEC-033)
- [ ] **DB 스냅샷 pull 성공 시 로컬 교체(atomic)** (DEC-028, DEC-PC-033)
- [ ] **주문 상태 칩 (LOCKED/READY/ERROR) 정상 표시** (DEC-031)
- [ ] **dry_run=true 시 ORDER LOCKED 표시** (DEC-031)
- [ ] **dry_run=false + 키 정상 시 ORDER READY 표시** (DEC-031)
- [ ] **LIVE_ACTIVE에서 볼륨 막대 틱 단위 누적** (DEC-032)
- [ ] **WS 연결 상태(L1/L2)와 "거래없음 n초"(L3) 분리 표기** (DEC-030)

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
- [ ] 듀얼 모니터 핫플러그 대응 (자동 폐)
- [ ] **테마 전환이 성능/프리징에 영향 없음(토큰 기반, 즉시 반영)** (DEC-027 v1)
- [ ] **SSH 연결 테스트/파일 전송이 UI 스레드 블로킹 없음(Worker)** (DEC-PC-034, DEC-033)
- [ ] **SSH 작업 타임아웃(3s/8s) 준수** (DEC-PC-036)
- [ ] **SSH 무한 재시도 없음(백오프만)** (DEC-PC-036)
- [ ] **passphrase 평문 저장/로그 출력 0건** (DEC-033, DEC-PC-034)
- [ ] **Upbit API 키 평문 저장/로그 출력 0건** (DEC-031)
- [ ] **실행 중 DB 교체 시 Close→Swap→Reopen 순서 준수** (DEC-PC-033)
- [ ] **PuTTY Portable 번들 사용(설치/PATH 요구 없음)** (DEC-PC-031)

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

### Phase 2.5 PC 앱 ✅ 기본 구현 완료 (2026-02-12)
- [x] MainEngine (WS + Aggregation), 듀얼 창(BTC+ETH / XRP+Dashboard)
- [x] 초기 DB 로드, Raw Trade 구독, 차트/거래량 축 표시
- [x] Light/Dark 테마 토큰 시스템, 상태 칩, KPI/커넥션/이벤트 대시보드
- [ ] **Pending**: BURST 감지, cutover_ts 병합, WS 재연결 backoff, coalesce/decimation
- **참조**: `docs/DUAL_WINDOW_UI_REDESIGN_WORK_ORDER_UPDATED.md`
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
- **대응**: 토큰 기반 테마 + 계층 규칙 강제 (DEC-027 v1)
- **검증**: Light/Dark 모두에서 동일한 정보 계층 체감 유지

### 🟡 RISK-PC-007: SQLite WAL 스냅샷 불일관 (DEC-028)
- **증상**: PC 앱이 Cloud DB를 네트워크 경로로 직접 열거나, WAL 모드의 메인 파일만 복사하면 불일치 발생
- **대응**: "원격에서 snapshot 생성 후 pull"로 완화 (SSH/SCP)
- **검증**: 스냅샷 pull 시 일관성 보장, 실패 시 폴백

### 🟡 RISK-PC-008: cutover 경계 모호성 (DEC-PC-032)
- **증상**: `cutover_ts` 경계가 `<`/`<=`로 혼재하면 중복/유령 캔들 발생
- **대응**: `<`/`>=` 경계 규칙을 문서로 고정하여 완화 (Strategy A+)
- **검증**: DB/LIVE 병합 시 중복/섞임 0건

### 🟡 RISK-PC-009: WS 경고 오탐 (알람 피로)
- **증상**: `last_message_age`를 연결 경고로 오인하여 "거래 없음" 시에도 경고 발생
- **대응**: L1/L2/L3 분리 + 3초 디바운싱으로 완화 (DEC-030)
- **검증**: 거래 공백 시 경고 없음, 실제 끊김 시만 경고

### 🟡 RISK-ORDER-KEY-001: Upbit 키 유출/로컬 저장 (DEC-031)
- **증상**: API 키가 로그/파일/레지스트리로 유출되거나, dry_run 무시하고 주문 전송
- **대응**: "메모리 전용 + 마스킹 + 로그 금지 + dry_run LOCK"으로 완화
- **검증**: dry_run=true 시 주문 LOCK, 키 평문 로그/파일 0건

### 🟡 RISK-ORDER-KEY-002: config.json 필드 변동/누락 (DEC-031)
- **증상**: `exchange.key`/`exchange.secret`/`dry_run` 필드 누락/타입 불일치 시 예외 처리 미흡
- **대응**: 필드 경로 고정 + 예외처리(누락/타입/빈값) + exchange.name 강제(upbit) + dry_run 게이트 + 누락 시 안전 LOCK + UI 원인 코드 표기
- **검증**: 필드 누락 시 LOCK, exchange.name != upbit 시 Fatal

### 🟡 RISK-SSH-LOGIN-001: SSH passphrase 취급 오류/평문 저장/로그 노출 (DEC-033, DEC-PC-034)
- **증상**: passphrase가 config.json/로그/에러 메시지로 유출
- **대응**: "저장 금지 + 마스킹 + 로그 금지 + UI/Worker 분리"로 완화
- **검증**: passphrase 평문 저장/로그 0건

### 🟡 RISK-SSH-DEP-001: SSH/PPK 처리에서 숨은 의존성/설치 문제 (DEC-PC-031)
- **증상**: paramiko 등 새 pip 의존성 추가 또는 PuTTY 설치/PATH 요구
- **대응**: "PuTTY Portable 번들 + 절대경로 호출(설치/PATH 금지)"로 완화
- **검증**: pip 의존성 추가 없음, PuTTY 설치 요구 없음

### 🟡 RISK-SSH-HANG-001: SSH Pull 무한 대기/프리징 (DEC-PC-036)
- **증상**: SSH/SCP 작업이 타임아웃 없이 무한 대기하거나, 무한 재시도로 폭주
- **대응**: "타임아웃(3s/8s) + 무한 재시도 금지 + 백오프"로 완화
- **검증**: SSH 작업 8초 초과 시 강제 중단, 무한 재시도 없음

### 🟡 RISK-PC-VOL-001: LIVE 볼륨 갱신이 끊겨 체감 저하 (DEC-032)
- **증상**: 가격/캔들은 틱 단위로 움직이는데 볼륨 막대는 멈춰 보임
- **대응**: "tick 누적 + coalesce 렌더"로 완화
- **검증**: LIVE_ACTIVE에서 볼륨 막대 틱 단위 증가 확인

---

## 📝 DECISION LOG (주요 결정)

### DEC-001~010: ✅ 확정 (update_history.txt)
- SQLite WAL, 배치100, 틱봉 음수, 9시간 재연결, 무제한 재연결

### DEC-011~014: Phase 2 Cloud 핵심 정책 ✅
- **DEC-011**: DB 마이그레이션 (ohlcv.sqlite → ohlcv_short.sqlite 일회성 rename)
- **DEC-012**: 중복 제거 (trade_uuid → sequential_id → fallback 5-tuple)
- **DEC-013**: 큐 오버로드 격리/회복 (HIGH_WATERMARK → DEGRADED, HARD_LIMIT → 연결 종료)
- **DEC-014**: 디렉토리 구조 분리 (common/cloud/pc_app)

### DEC-015~024: PC 앱 핵심 설계 ✅ (2026-01-28 확정)
- **DEC-015**: 듀얼 모니터 UI (W1: BTC+ETH 50:50, W2: XRP+Dashboard 65:35)
- **DEC-016**: Raw Trade 단일 구독 + 로컬 Aggregation (구독 수 3개 고정)
- **DEC-017~019**: vendor 복사, config.json, SQLite RO
- **DEC-020~022**: BURST trade_ts 기준, Hybrid 레벨 1→2, 봉 확정 규칙
- **DEC-023~024**: Upbit 레이트리밋, 비상모드 DB 강제 전환
- **상세**: `pc_app/DESIGN_DUAL_MONITOR.md`, `WEBSOCKET_OPTIMIZATION.md`

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

### DEC-027 (v1): PC 앱 Light/Dark 테마 규칙 ✅
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

### DEC-028: DB 소스는 (C) SSH로 원격 파일 Pull (Read-Only) ✅
- PC 앱은 Cloud SQLite를 네트워크로 직접 열지 않는다.
- 원격에서 **일관 스냅샷(snapshot sqlite 단일 파일)** 을 생성한 뒤, SSH/SCP로 로컬에 내려받아 **RO로 오픈**한다.
- 실패 시: 기존 로컬 스냅샷을 유지(폴백), UI에 "DB 업데이트 실패"만 표기.
- **상태**: ✅ 확정 (2026-02-15)

### DEC-029: 동기화/병합은 우선 "전략 A" ✅
- **A(확정)**: DB seed 먼저 로드 → WS LIVE 연결 → `cutover_ts` 기준으로 LIVE 오버레이가 덮어쓴다.
- **문서 명시(중기)**: 필요 시 **B(WS 버퍼 선행 → DB 로드 → 병합 → LIVE)** 로 전환 가능(이번 범위에서는 구현/의존 추가 금지).
- **상태**: ✅ 확정 (2026-02-15)

### DEC-030: UI 문구는 "시장정적" 금지, "거래없음" 사용 ✅
- `last_message_age`는 장애 경고가 아니라 **"거래없음 n초"**(데이터 신선도) 표기용.
- "연결 끊김/장애"는 **연결/heartbeat(L1/L2)** 로만 판단한다.
- **상태**: ✅ 확정 (2026-02-15)

### DEC-031: Upbit API 키는 Cloud의 freqtrade config.json에서 SSH로 읽어온다 (dry_run 게이트) ✅
- PC 앱은 Upbit API 키를 **로컬 파일/레지스트리/로그에 저장하지 않는다**(메모리 내에서만 보관).
- Oracle Cloud(SSH: `152.69.234.80:22`)에 있는 Freqtrade 설정 파일에서 읽는다:
  - 경로(실서버): `/home/opc/python/ft_userdata_upbit/user_data/config.json`
  - Docker(일반): `ft_userdata/user_data/config.json`
  - Docker(우리 프로젝트): `ft_userdata_upbit/user_data/config.json`
- `config.json`의 `dry_run` 값으로 주문 기능을 게이트한다:
  - `"dry_run": true` → **키를 읽지 않거나(선택), 읽더라도 주문 기능은 잠금(LOCK)**. UI에 `DRY_RUN: 주문 잠금` 명시.
  - `"dry_run": false` → `exchange.key`, `exchange.secret`를 읽어 **PC 앱 내부 "주문 모듈 경계"로 전달**한다. 주문 전송은 PC에서 직접 수행.
- SSH 인증은 **PuTTY 키(.ppk)를 그대로 사용**한다.
- 키 노출 방지(필수):
  - UI 표시는 마스킹(예: `****abcd`)만 허용.
  - 로그에는 절대 평문을 남기지 않는다(에러 메시지에도 포함 금지).
  - 메모리에서도 가능한 최소 범위로 유지(주문 모듈 초기화 이후 불필요하면 폐기).
- **상태**: ✅ 확정 (2026-02-15)

### DEC-032: LIVE 모드에서 거래량(볼륨)도 틱 단위로 누적/갱신한다 ✅
- 현재 PC 앱에서 **가격/캔들(분봉 포함)** 이 틱 단위로 움직이듯,
- LIVE_ACTIVE에서 **거래량(볼륨) 막대도 동일한 틱 스트림으로 누적**되어야 한다.
- 렌더링은 기존 정책을 따른다:
  - 계산/집계는 every tick 반영
  - UI는 coalesce(고정 주기)로 최신 스냅샷만 그림(중간 프레임 생략 가능)
- DB_ONLY에서 볼륨은 DB history만 표시(틸트/보정 금지).
- **상태**: ✅ 확정 (2026-02-15)

### DEC-033: SSH 로그인/연결 설정 다이얼로그(필수) ✅
- SSH/SCP가 필요한 기능(원격 DB 스냅샷 pull, 원격 config.json 조회)이 있으므로,
  **PC 앱 시작 시 "SSH 로그인/연결 설정" 창을 1회 표시**하는 것을 기본으로 한다.
- 인증은 **PuTTY(.ppk) 그대로 사용**한다.
  - (A) `.ppk + passphrase` (기본)
  - (B) `.ppk + Pageant` 사용 시 passphrase 입력 생략(가능하면)
  - (C) (옵션/후순위) password 로그인은 필요 시만(동일 UI 폼에서 선택)
- 입력 필드(기본값 포함):
  - host: `152.69.234.80`
  - port: `22`
  - username: `opc`
  - ppk_path: (사용자 선택; PuTTY의 .ppk)
  - passphrase: (옵션; **저장 금지**, 세션 메모리만)
  - remote_config_path: `/home/opc/python/ft_userdata_upbit/user_data/config.json`
- 동작/정책:
  - "연결 테스트(Test)" 버튼 제공(비동기). 성공해야 "적용(Apply)" 활성화.
  - "취소(Cancel)" 또는 테스트 실패 시: **SSH 기능 스킵 + 기존 로컬 스냅샷 유지(폴백)**, UI에 "SSH 미연결(로컬 DB 사용)" 표기.
  - SSH 연결 실패/타임아웃으로 앱이 죽거나 멈추면 실패(프리징 금지).
- 저장 정책(보안):
  - config.json에는 **host/port/username/ppk_path/remote_path 같은 '비밀 아닌 설정'만 저장**한다.
  - **passphrase/비밀번호는 절대 저장하지 않는다.**(평문 저장 금지, 로그 출력 금지)
- **상태**: ✅ 확정 (2026-02-15)

### DEC-PC-031: PuTTY Portable 번들(puttygen/pscp)로 .ppk 지원, pip 의존성 추가 없음(설치/PATH 강제 금지) ✅
- **pip 새 의존성(paramiko 등) 추가 금지 유지**
- **PuTTY Portable 번들 채택**:
  - `puttygen.exe` : `.ppk` 확인/검증(필요 시 변환)
  - `pscp.exe` : 스냅샷 파일 Pull 전용(RO)
- 번들은 `pc_app/third_party/putty/` 아래에 포함(PC 앱 범위 내 신규 파일은 허용).
- 사용자는 **.ppk 파일만 제공**하면 된다(기존 요구사항 유지).
- 보안/로그:
  - passphrase/키/명령어 출력 금지(로그에 남기지 않는다)
  - 스냅샷은 **읽기 전용 pull만** 수행(업로드/원격 실행 범위 확장 금지)
- **상태**: ✅ 확정 (2026-02-15)

### DEC-PC-032: Strategy A 유지 + A+(cutover_ts=next bucket) 고정, DB 다운로드 시간 갭 허용, 중기 B 가능 명시(이번 범위 구현 금지) ✅
- Strategy A 유지: **DB Seed 다운로드 → DB 로드 → LIVE 연결**
- DB 다운로드 시간(T) 동안 발생하는 데이터 갭은 **허용**한다.
  - 근거: SSOT에서 PC 앱은 "정본 아님", REST 갭 복구도 Non-scope.
- **A+ (필수 규칙)**:
  - **DB에서 "마지막 캔들 1개는 폐기"**(진행 중일 수 있으므로)
  - `cutover_ts`는 **폐기한 마지막 캔들의 다음 버킷 시작**으로 고정
    - 예: `cutover_ts = (last_db_bucket_start + tf_ms)`
  - 병합 규칙(경계 고정):
    - `bucket_start < cutover_ts` → DB만 표시(고정)
    - `bucket_start >= cutover_ts` → LIVE overlay만 표시(덮어씀)
  - UI에는 `cutover_ts` 기준으로 **"LIVE 시작" 마커/텍스트**를 남긴다.
- **"중기에는 B 가능" 문서 명시**:
  - 중기 개선안으로 **Strategy B(WS 버퍼 선행 → DB 로드 → 병합)** 가능성을 SSOT에 명시
  - **이번 작업 범위에서는 B 구현 금지**(범위 확장 방지)
- **상태**: ✅ 확정 (2026-02-15)

### DEC-PC-033: 실행 중 DB 교체는 Close→Swap(atomic)→Reopen 강제(Windows 파일 잠금 대응) ✅
- Windows에서 열려 있는 DB 파일은 rename/move가 실패할 수 있으므로, 실행 중 업데이트는 반드시:
  1. **DBReader Close(연결 완전 종료)**
  2. **파일 교체(atomic swap)**
     - 다운로드는 `*.tmp`로 받고
     - "검증(오픈 가능)" 후
     - 최종 파일로 rename(단, 1단계 Close가 선행되어야 함)
  3. **DBReader Reopen(RO로 재오픈)**
  4. UI에 "DB 갱신 성공/실패" 1줄 표기(스팸 금지, rate-limit)
- 실패 폴백: 교체 실패 시 기존 DB 유지(또는 기존 DB로 재오픈) + 사용자에게 안내
- **상태**: ✅ 확정 (2026-02-15)

### DEC-PC-034: Passphrase GUI 입력 + Worker 처리, 이번 실행 동안만 메모리 보관(디스크 저장 금지) ✅
- Passphrase 입력은 **GUI 다이얼로그**로 받는다.
- 검증/SSH Pull은 반드시 **Worker Thread**에서 수행(메인 UI 스레드 블로킹 금지).
- Passphrase 저장 정책:
  - 기본: **"이번 실행 동안만 메모리 보관"**(앱 종료 시 폐기)
  - 디스크 저장 금지(옵션으로도 금지; 요구 시 별도 DEC 필요)
- 인터랙션 흐름(명시):
  - 설정 화면에서:
    - host/user/port/ppk 경로 입력
    - "연결 테스트" 버튼
    - ppk가 암호화된 경우 passphrase 다이얼로그 표시
  - 테스트 성공 시에만 "저장" 활성화
- **상태**: ✅ 확정 (2026-02-15)

### DEC-PC-036: SSH timeout(연결 3s/전체 8s) 고정, 무한 대기/무한 재시도 금지(백오프만 허용) ✅
- SSH/SCP 작업은 아래 타임아웃을 강제:
  - 연결 시도 최대 3초
  - 전체 Pull 작업 최대 8초(초과 시 강제 중단)
- 재시도:
  - 자동 무한 재시도 금지
  - 사용자 버튼 또는 "주기 갱신"이 있다면 **백오프(예: 5s → 10s → 30s 상한)** 적용
- 실패 시 UI:
  - "DB 업데이트 실패(원인 요약)" 1줄 + 기존 DB 유지
- **상태**: ✅ 확정 (2026-02-15)

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

## 🚧 PHASE 2.5 DETAILED WORK ORDER (STEP 1~8)

> **출처**: "바로 실행 가능한 패키지(문서 1개 안에 STEP 1 → 1.5 → 2 → 3 → 5 → 8)" (2026-02-15 통합)  
> **목적**: P0(WS 경고 오탐 제거) + P0(SSH 스냅샷 DB seed) + P1(A전략 cutover 병합) + UX(거래없음 표기) + Upbit API 키 연동 + LIVE 볼륨 틱 갱신  
> **범위**: Phase 2.5 PC 앱 구현 작업지시서 (DEC-028~036 반영)

### A) DECISION LOG (이번에 확정된 DEC 1~3)

#### DEC-028 — DB 소스는 (C) SSH로 원격 파일 Pull (Read-Only)

* PC 앱은 Cloud SQLite를 네트워크로 직접 열지 않는다.
* 원격에서 **일관 스냅샷(snapshot sqlite 단일 파일)** 을 생성한 뒤, SSH/SCP로 로컬에 내려받아 **RO로 오픈**한다.
* 실패 시: 기존 로컬 스냅샷을 유지(폴백), UI에 "DB 업데이트 실패"만 표기.

#### DEC-029 — 동기화/병합은 우선 "전략 A"

* **A(확정)**: DB seed 먼저 로드 → WS LIVE 연결 → `cutover_ts` 기준으로 LIVE 오버레이가 덮어쓴다.
* **문서 명시(중기)**: 필요 시 **B(WS 버퍼 선행 → DB 로드 → 병합 → LIVE)** 로 전환 가능(이번 범위에서는 구현/의존 추가 금지).

#### DEC-030 — UI 문구는 "시장정적" 금지, "거래없음" 사용

* `last_message_age`는 장애 경고가 아니라 **"거래없음 n초"**(데이터 신선도) 표기용.
* "연결 끊김/장애"는 **연결/heartbeat(L1/L2)** 로만 판단한다.

#### DEC-031 — Upbit API 키는 Cloud의 freqtrade config.json에서 SSH로 읽어온다 (dry_run 게이트)

* PC 앱은 Upbit API 키를 **로컬 파일/레지스트리/로그에 저장하지 않는다**(메모리 내에서만 보관).
* Oracle Cloud(SSH: `152.69.234.80:22`)에 있는 Freqtrade 설정 파일에서 읽는다:
  - 경로(실서버): `/home/opc/python/ft_userdata_upbit/user_data/config.json`
  - Docker(일반): `ft_userdata/user_data/config.json`
  - Docker(우리 프로젝트): `ft_userdata_upbit/user_data/config.json`
* `config.json`의 `dry_run` 값으로 주문 기능을 게이트한다:
  - `"dry_run": true` → **키를 읽지 않거나(선택), 읽더라도 주문 기능은 잠금(LOCK)**. UI에 `DRY_RUN: 주문 잠금` 명시.
  - `"dry_run": false` → `exchange.key`, `exchange.secret`를 읽어 **PC 앱 내부 "주문 모듈 경계"로 전달**한다. 주문 전송은 PC에서 직접 수행.
* SSH 인증은 **PuTTY 키(.ppk)를 그대로 사용**한다.
* 키 노출 방지(필수):
  - UI 표시는 마스킹(예: `****abcd`)만 허용.
  - 로그에는 절대 평문을 남기지 않는다(에러 메시지에도 포함 금지).
  - 메모리에서도 가능한 최소 범위로 유지(주문 모듈 초기화 이후 불필요하면 폐기).

##### config.json 키 경로/구조 (고정 + 예외 처리 포함)

* 필드 경로(기본, 고정):
  - `dry_run` : boolean
  - `exchange.name` : `"upbit"` (권장/검증용)
  - `exchange.key` : string (Upbit Access Key)
  - `exchange.secret` : string (Upbit Secret Key)
* 예외 처리(실패 방식 고정):
  - 파일 없음/SSH 실패/JSON 파싱 실패 → 주문 기능 `LOCK`, UI에 "키 로드 실패(원인 코드만)" 표시, 앱은 계속 구동.
  - `dry_run` 누락/타입 불일치 → **안전 우선으로 `dry_run=true` 취급**(LOCK).
  - `exchange` 누락 → LOCK.
  - `exchange.key`/`exchange.secret` 누락 또는 빈 문자열 → LOCK.
  - `exchange.name != upbit` → **FATAL(차단)**: "이 앱은 Upbit 전용입니다. config.json의 exchange.name을 upbit로 설정하세요."

> 참고: 위 키 구조는 Freqtrade 문서의 일반적인 `config.json` 예시(`dry_run`, `exchange.key`, `exchange.secret`)를 따른다.

#### DEC-032 — LIVE 모드에서 거래량(볼륨)도 틱 단위로 누적/갱신한다

* 현재 PC 앱에서 **가격/캔들(분봉 포함)** 이 틱 단위로 움직이듯,
* LIVE_ACTIVE에서 **거래량(볼륨) 막대도 동일한 틱 스트림으로 누적**되어야 한다.
* 렌더링은 기존 정책을 따른다:
  - 계산/집계는 every tick 반영
  - UI는 coalesce(고정 주기)로 최신 스냅샷만 그림(중간 프레임 생략 가능)
* DB_ONLY에서 볼륨은 DB history만 표시(틸트/보정 금지).

#### DEC-033 — SSH 로그인/연결 설정 다이얼로그(필수)

* SSH/SCP가 필요한 기능(원격 DB 스냅샷 pull, 원격 config.json 조회)이 있으므로,
  **PC 앱 시작 시 "SSH 로그인/연결 설정" 창을 1회 표시**하는 것을 기본으로 한다.
* 인증은 **PuTTY(.ppk) 그대로 사용**한다.
  - (A) `.ppk + passphrase` (기본)
  - (B) `.ppk + Pageant` 사용 시 passphrase 입력 생략(가능하면)
  - (C) (옵션/후순위) password 로그인은 필요 시만(동일 UI 폼에서 선택)
* 입력 필드(기본값 포함):
  - host: `152.69.234.80`
  - port: `22`
  - username: `opc`
  - ppk_path: (사용자 선택; PuTTY의 .ppk)
  - passphrase: (옵션; **저장 금지**, 세션 메모리만)
  - remote_config_path: `/home/opc/python/ft_userdata_upbit/user_data/config.json`
* 동작/정책:
  - "연결 테스트(Test)" 버튼 제공(비동기). 성공해야 "적용(Apply)" 활성화.
  - "취소(Cancel)" 또는 테스트 실패 시: **SSH 기능 스킵 + 기존 로컬 스냅샷 유지(폴백)**, UI에 "SSH 미연결(로컬 DB 사용)" 표기.
  - SSH 연결 실패/타임아웃으로 앱이 죽거나 멈추면 실패(프리징 금지).
* 저장 정책(보안):
  - config.json에는 **host/port/username/ppk_path/remote_path 같은 '비밀 아닌 설정'만 저장**한다.
  - **passphrase/비밀번호는 절대 저장하지 않는다.**(평문 저장 금지, 로그 출력 금지)

---

### B) STEP 1 — Cursor 작업지시서 v1 (실행형)

#### 1) Objective

1. WS 경고 오탐 제거: "거래 없음"과 "연결 단절"을 분리한다.
2. DB seed 구현: SSH Pull(RO)로 원격 스냅샷을 내려받아 로컬 DB를 seed로 사용한다.
3. A전략 병합: `cutover_ts` 기준으로 DB history + LIVE overlay가 **중복/섞임 없이** 공존한다.
4. UI 문구/표기: "거래없음 n초"로 데이터 신선도를 표시한다.
5. SSH 로그인/연결 설정 UI: 앱 시작 시 SSH 설정을 받고, SSH 실패/취소 시 폴백으로 안전 동작한다.
6. Upbit API 키 연동(준비): Cloud의 Freqtrade `config.json`에서 SSH로 읽고 `dry_run` 게이트로 주문 기능을 잠근다(키 평문 저장/로그 금지).
7. LIVE 볼륨 틱 갱신: LIVE_ACTIVE에서 거래량 막대도 틱 단위 누적(렌더는 coalesce).

#### 2) Scope / Non-scope

**In-scope**

* `pc_app/engine.py`: 상태/진단/모드/seed/merge 핵심
* `pc_app/ui.py`: 상태칩/알림스트립/표기(거래없음/연결)
* `pc_app/ui.py`: SSH 로그인/연결 설정 다이얼로그(UI) + 테스트/저장/폴백 표기(비동기)
* `pc_app/pc_app_main.py`: DB 스냅샷 갱신 트리거/주기, UI 갱신(현 구조 유지 가능)
* Upbit API 키 로딩/게이트(DEC-031) 및 주문 모듈 경계까지 "전달"을 `pc_app/engine.py`/`pc_app_main.py` 내에서 수행(새 의존성 추가 금지, PuTTY(.ppk) 그대로 사용).
* LIVE 볼륨 틱 갱신(DEC-032) 반영은 `pc_app/engine.py`(스냅샷 생성) 및 `pc_app/ui.py`(볼륨 차트 렌더) 범위 내에서 수행.

**Non-scope (이번 작업에서 금지)**

* Cloud collector 코드/DB 스키마 변경
* Supabase/HTTP REST 연동(원격 API) 추가
* "전략 B" 구현(중기 계획으로만 문서 명시)
* 대규모 UI 아키텍처 리팩토링(signal-slot 완전 전환 등)
* 완전자동 주문/전략 자동화/시장가/스탑/예약/조건부 주문 구현(주문 기능은 "키 연동/게이트/경계"까지만)

#### 3) Hard No (절대 금지)

* `last_message_age`로 "연결 끊김" 판정
* 네트워크 공유 경로로 SQLite 직접 오픈
* TODO/임시 땜빵/Mock/stub 남기기
* UI 메인 스레드에서 SSH/DB I/O 블로킹 수행
* passphrase/비밀번호를 config.json에 저장하거나 로그로 출력
* Upbit API 키(Access/Secret)를 로그/에러/파일에 평문으로 남기기
* `dry_run=true` 인데 주문 기능을 "가능" 상태로 노출하기(반드시 LOCK)
* paramiko 등 새 pip 의존성 추가(금지) — PuTTY Portable 번들만 허용(DEC-PC-031)
* PuTTY 설치/PATH 요구(금지) — 번들 exe 절대경로로만 호출
* DB가 열린 상태에서 rename/move로 교체 시도(금지) — Close→Swap→Reopen 강제(DEC-PC-033)
* SSH 작업 무한 대기/무한 재시도(금지) — 타임아웃(3s/8s) + 백오프만 허용(DEC-PC-036)

#### 4) 설계/상태 모델 (필수)

##### 4.1 WS 상태(3계층 분리)

* **L1 Connection**: `ws_connected`(bool 또는 enum)
* **L2 Protocol health**: ping/pong 기반의 "alive"
* **L3 Data freshness**: `last_trade_age_sec` → UI에 "거래없음 n초"

##### 4.2 모드(최소 상태)

* `DB_ONLY`: DB history만 표시
* `LIVE_ACTIVE`: WS + overlay 표시(단, 병합 규칙은 `cutover_ts`가 핵심)

> LIVE 관련 세부 모드(WARMUP/COOLDOWN)는 이번 범위에서 "틀만 남기고" 확장하지 말고, A전략 병합이 정확히 동작하는 데 집중.

##### 4.3 주문 키/주문 가능 상태(최소 상태)

* `ORDER_LOCKED_DRYRUN`: `dry_run=true` → 주문 기능 잠금(키는 읽지 않거나, 읽더라도 사용 금지)
* `ORDER_KEYS_READY`: `dry_run=false` + 키 정상 로드 → 주문 모듈 경계까지 전달 완료(전송은 아직 Non-scope라도 "준비됨" 상태 표기 가능)
* `ORDER_KEYS_ERROR`: 로드 실패/필드 누락/SSH 실패/파싱 실패 → 잠금(LOCK)

UI 표기: `ORDER: LOCKED/READY/ERROR` 같은 중립 칩/문구(장애색 과다 사용 금지).

#### 5) A전략 병합 규칙(이번 핵심)

##### 5.1 CandleKey (캔들 병합 키)

* `(symbol, timeframe_ms, bucket_start_ts_ms)`
* `bucket_start_ts_ms = floor(trade_ts_ms / tf_ms) * tf_ms`
  (recv time 금지)

##### 5.2 cutover_ts 정의(전략 A)

* DB seed 로드 직후, 각 `(symbol, timeframe)`에 대해:

  * `last_db_bucket = DB에서 읽힌 마지막 캔들의 bucket_start_ts_ms`
  * **cutover_ts = last_db_bucket**
  * DB history에는 **`bucket_start < cutover_ts`** 만 유지(마지막 캔들은 "버림")
  * LIVE overlay는 **`bucket_start >= cutover_ts`** 구간만 책임(덮어쓰기)

> 이 규칙을 SSOT/작업지시서에 "경계 포함/미포함"까지 고정(반드시 그대로).

##### 5.2.1 Strategy A+ (최종 규칙) — cutover_ts를 "다음 버킷 시작"으로 고정

> 아래 A+ 규칙은 **DEC-PC-032(Strategy A+)**로 "확정"이며, 구현은 A+를 따른다.  
> 위 5.2의 정의는 역사적/초기 정의로 남겨두되, **최종 경계는 A+ 기준**으로 고정한다.

* DB seed 로드 직후, 각 `(symbol, timeframe)`에 대해:

  * `last_db_bucket_start = DB에서 읽힌 마지막 캔들의 bucket_start_ts_ms`
  * **DB의 마지막 캔들 1개는 폐기**(진행 중일 수 있으므로)
  * **cutover_ts = (last_db_bucket_start + tf_ms)**  ← "다음 버킷 시작"으로 고정
  * 병합 경계(문장으로 고정):
    - `bucket_start < cutover_ts`  → DB만 표시(고정)
    - `bucket_start >= cutover_ts` → LIVE overlay만 표시(덮어쓰기)
  * UI에는 `cutover_ts` 기준으로 **"LIVE 시작" 마커/텍스트**를 남긴다.

##### 5.3 섞임 방지

* `context_id = (symbol, generation_id)`
* `generation_id`는 WS 재연결마다 증가
* UI는 "현재 generation_id"만 렌더(불일치 즉시 폐기)

#### 6) SSH Pull 스냅샷 파이프라인(RO)

##### 6.1 원격 스냅샷 생성(일관성 보장)

* 원격에서 `ohlcv_short.sqlite`를 직접 scp하지 말고,
* **원격에서 snapshot sqlite 단일 파일을 생성**한 뒤 pull
  (WAL 모드 일관성 확보)

##### 6.2 로컬 교체(원자적)

* 임시 파일로 다운로드 → 간단 검증(예: 파일 존재/크기/오픈 가능) → atomic rename
* 실패 시 기존 로컬 스냅샷 유지

##### 6.3 오픈 방식

* 로컬은 read-only로 오픈(가능하면 immutable 옵션도 활용)
* DB 업데이트 중에도 앱이 "중간 파일"을 잡지 않도록 파일 교체는 원자적으로.

##### 6.4 Upbit API 키 로딩(SSH) — 스냅샷 파이프라인과 분리

* DB 스냅샷과 "키 로딩"은 동일한 SSH 채널을 공유할 수 있으나, 실패 격리는 분리한다:
  - DB pull 실패 ≠ 키 로딩 실패 (서로 독립 실패로 UI 표시)
  - 어느 쪽 실패든 앱은 계속 실행(LOCK/폴백)
* 키 로딩은 "원격 파일 읽기(cat)" 또는 "작은 파일 pull" 방식 중 택1로 고정하되,
  - PuTTY(.ppk) 그대로 사용이 가능한 방식이어야 한다(예: plink/pscp 기반).
* 키/설정 파일은 반드시 UTF-8/JSON 파싱으로 처리하고, 파싱 실패 시 LOCK.

##### 6.5 SSH 로그인/연결 설정 UX (필수)

* SSH 설정이 필요한 경우(초기 실행/설정 없음/직전 실패/사용자 갱신 트리거)는,
  **로그인/연결 설정 창을 먼저 띄워 SSH 세션을 확보**한 뒤에만 snapshot pull / config.json 조회를 시도한다.
* 로그인창 요구사항:
  - "Test(연결 테스트)"는 반드시 비동기(Worker)로 수행하고, 성공해야 Apply 가능
  - Cancel/실패 시: SSH 관련 동작은 스킵하고 로컬 스냅샷으로 실행(폴백), UI에 실패/미연결 표기
  - passphrase는 세션 메모리만 사용(저장/로그 금지)
  - Pageant 사용 시 passphrase 입력을 생략할 수 있으면 그 경로를 우선(사용자 경험 개선)
* UI 프리징 금지:
  - 연결 테스트/파일 전송/원격 실행은 UI 스레드에서 동기 호출 금지(실패 시 즉시 중단/타임아웃)

##### 6.6 PuTTY Portable 번들(필수) — 새 pip 의존성 추가 금지(DEC-PC-031)

* paramiko 등 **새 pip 의존성 추가는 금지**한다(SSOT/Work Order 기준).
* `.ppk`는 그대로 사용해야 하므로, **PuTTY Portable 바이너리 번들**을 채택한다:
  - `pc_app/third_party/putty/puttygen.exe` : `.ppk` 유효성/암호화 여부 확인(필요 시 변환)
  - `pc_app/third_party/putty/pscp.exe` : snapshot sqlite / config.json pull(RO)
  - (선택) `pc_app/third_party/putty/plink.exe` : 원격 명령 실행이 필요할 때(예: snapshot 생성 스크립트 트리거)
* "설치 + PATH 의존"은 금지한다. 항상 **번들된 exe의 절대경로**로 subprocess를 호출한다.
* 로그/보안:
  - passphrase/키/명령어 전문(호스트 포함) 출력 금지(로그에 남기지 않는다)
  - 키는 **메모리 상에서만** 유지(프로세스 종료 시 폐기)

##### 6.7 SSH 타임아웃/재시도 정책(필수 수치 고정: DEC-PC-036)

* SSH/SCP 작업 타임아웃을 하드 고정한다:
  - 연결 시도 최대 **3초**
  - 전체 Pull 작업 최대 **8초**(초과 시 강제 중단)
* 자동 무한 재시도 금지:
  - 사용자 버튼 또는 주기 갱신이 있다면 **백오프(예: 5s → 10s → 30s 상한)** 적용
* 실패 시 동작:
  - 기존 로컬 스냅샷 유지(폴백)
  - UI에 "DB 업데이트 실패(원인 요약)" 1줄(스팸 금지, rate-limit)

##### 6.8 실행 중 DB 스냅샷 교체 시퀀스(Windows lock 대응: DEC-PC-033)

Windows에서 열려 있는 DB 파일은 rename/move가 실패할 수 있으므로, 실행 중 업데이트는 반드시:

1) **DBReader Close(연결 완전 종료)**  
2) **파일 교체(atomic swap)**  
   - 다운로드는 `*.tmp`로 받고  
   - "검증(오픈 가능)" 후  
   - 최종 파일로 rename(단, 1단계 Close가 선행되어야 함)  
3) **DBReader Reopen(RO로 재오픈)**  
4) UI에 "DB 갱신 성공/실패" 1줄 표기(스팸 금지, rate-limit)

* 실패 폴백: 교체 실패 시 기존 DB 유지(또는 기존 DB로 재오픈) + 사용자 안내

#### 7) UI/표기 요구사항

* 연결 상태 표기(예: WS 칩):
  * DISCONNECTED: L1/L2 실패 시만
  * CONNECTED: L1/L2 OK
* 데이터 신선도 표기:
  * "거래없음 n초" (L3)
  * 이 표기는 **경고색/장애색과 분리**(중립 정보)
* 경고 스트립:
  * **디바운싱 3초**: 끊김 조건이 3초 지속될 때만 표시
  * OK↔WARN 출렁임 깜빡임 제거
* 주문 키/주문 가능 상태 표기(DEC-031):
  * `dry_run=true` → `ORDER: LOCKED (DRY_RUN)` 고정 표기
  * 키 로드 실패/필드 누락 → `ORDER: ERROR (KEY LOAD)` 표기(원인 코드만)
  * 키 정상 → `ORDER: READY` 표기(키는 마스킹)
* LIVE 볼륨 틱 갱신(DEC-032):
  * LIVE_ACTIVE에서 마지막 봉의 볼륨 막대가 틱마다 누적되는 것이 "체감"되어야 한다(렌더는 coalesce).
  * 가격/캔들 갱신과 볼륨 갱신이 분리되어 "가격은 움직이는데 볼륨은 멈춰 보이는" 현상 금지.

#### 8) Definition of Done (측정 가능)

* 앱 시작 직후 "거래가 없어도" WS 경고가 뜨지 않는다(대신 "거래없음 n초"만 표시)
* WS 실제 끊김 시: 3초 지속 후에만 경고 표시
* DB seed가 존재하면: 차트가 DB history로 채워진 뒤 LIVE 전환 가능
* A전략 병합으로:
  * `bucket_start < cutover_ts` 는 DB만
  * `bucket_start >= cutover_ts` 는 LIVE만
  * 중복/섞임(거래량 2배 등) 없음
* `dry_run=true`일 때 주문 기능은 항상 LOCK이고, 키 평문이 로그/파일에 남지 않는다.
* LIVE_ACTIVE에서 가격/캔들뿐 아니라 **볼륨 막대도 틱 단위로 누적**되는 것이 UI에서 확인된다(렌더는 coalesce여도 "증가"가 보임).
* SSH 설정이 없으면: 앱 시작 시 로그인/연결 설정 창이 뜨고, Cancel/실패해도 앱은 로컬 스냅샷으로 정상 구동한다(폴백).
* passphrase/비밀번호는 저장/로그 출력되지 않는다.

---

### C) STEP 1.5 — Gemini 품질 감사관 질문 리스트(질문만)

[BLOCKER]

1. DB 스냅샷 생성 방식이 "원격에서 snapshot 파일 생성 후 pull"로 고정되었는가? (WAL 모드 일관성 보장)
2. A전략 병합 규칙의 경계가 문서에 명확히 고정되었는가? (`< cutover_ts` vs `>= cutover_ts`)
3. `last_message_age`가 연결 경고 판정에 사용되지 않도록 "L1/L2 vs L3" 분리가 코드 레벨로 강제되었는가?
4. UI 경고 디바운싱(3초)이 실제로 적용되어 깜빡임/알람 피로가 제거되는가?
5. SSH/DB I/O가 UI 스레드를 블로킹하지 않는가?
6. `dry_run=true`일 때 주문 기능이 **반드시 LOCK**되고, 키 로딩/전달이 우회되지 않는가?
7. Upbit API 키가 로그/에러/파일로 유출될 여지가 없는가(마스킹/예외 메시지 포함)?
8. `config.json` 필드 경로(`dry_run`, `exchange.key`, `exchange.secret`) 누락/타입 불일치 시 "안전 우선 LOCK"으로 떨어지는가?
9. LIVE_ACTIVE에서 볼륨 막대가 틱 누적되며, cutover 병합 때문에 "볼륨 2배(중복)"가 재발하지 않는가?
10. SSH 로그인/연결 설정 창이 '초기/미설정/실패/사용자 갱신 트리거' 조건에서 반드시 뜨고, Cancel/실패 시 폴백(로컬 스냅샷)으로 안전하게 진행되는가?
11. passphrase/비밀번호가 config.json/로그에 저장되지 않도록 금지 규칙이 코드 레벨로 지켜지는가?

[MAJOR]

6. "거래없음 n초" 표기가 경고/장애와 동일한 색/표현 체계를 사용하지 않는가?
7. WS 재연결 시 generation_id 증가 및 context_id mismatch 폐기가 UI 렌더링에 반영되는가?
8. DB 스냅샷 pull 실패 시 폴백(기존 로컬 DB 유지) 정책이 명확한가?
9. 키 로딩 실패와 DB pull 실패가 UI/로그에서 구분되어 진단 가능하게 남는가?

[MINOR]

9. "중기 계획에서 B 전략 가능"이 문서에 명시되었는가(단, 이번 범위 구현 금지)?
10. 스냅샷 교체가 원자적(atomic)인지, 중간 파일 잡는 레이스가 없는지?
11. `exchange.name != upbit` 일 때 경고 표기는 과하지 않고(알람 피로), 사용자가 원인을 이해할 수 있는가?

핸드오프 6줄:

* 무엇을 했다(변경점):
* 왜 이렇게 했나(결정 근거):
* 유지해야 할 방향(Keep):
* 피해야 할 함정(Avoid):
* 다음 단계(Next):
* SSOT/Task 위치:

---

### C-2) STEP 1.5 QA 질문 응답 및 확정 결정서 (STEP 2 / v1.0)

아래는 **STEP 1.5 QA 질문 1~9에 대한 "결정/답변"을 제가 알아서 채운** **STEP 2 확정본(문서 1장짜리)**입니다.
이걸 그대로 SSOT Decision Log + Phase 2.5 Work Order에 붙여넣으면 됩니다. (전제: **Strategy A 유지**, 단 **중기 B 가능** 명시)

#### 0) 결론 요약

* **Q1(SSH/PPK 의존성 충돌)**: "새 pip 의존성 추가"는 하지 않는다. 대신 **PuTTY Portable 바이너리(puttygen/pscp)** 를 **pc_app 하위에 번들**하여 `.ppk`를 그대로 지원한다. (외부 설치/ PATH 요구 금지)
* **Q2(Strategy A 데이터 갭)**: **갭은 허용**한다(PC App은 정본 아님). 대신 **A를 '버킷 경계(start next bucket)'로 고정**해 "부분 캔들/볼륨 급락" 혼란을 최소화하고, UI에 "LIVE 시작 구간" 표시를 남긴다. 중기엔 B로 개선 가능함을 문서에 명시한다.
* **Q3(Windows 파일 잠금/DB 교체)**: 실행 중 DB 업데이트는 **Close → Swap(atomic) → Reopen** 시퀀스를 강제한다(락 잡은 상태 rename 금지).
* 나머지(4~9)도 아래처럼 **운영 가능한 수준으로 결정을 고정**한다.

#### 1) DEC-PC-031 — SSH/PPK 구현 방식 확정(의존성 충돌 해결)

**결론**

* **pip 새 의존성(paramiko 등) 추가 금지 유지**
* **PuTTY Portable 번들 채택**:
  * `puttygen.exe` : `.ppk` 확인/검증(필요 시 변환)
  * `pscp.exe` : 스냅샷 파일 Pull 전용(RO)
* 번들은 `pc_app/third_party/putty/` 아래에 포함(PC 앱 범위 내 신규 파일은 허용).
* 사용자는 **.ppk 파일만 제공**하면 된다(기존 요구사항 유지).

**이유(운영 관점)**

* `.ppk` 직접 처리를 표준 라이브러리로 해결 불가
* PuTTY를 "설치+PATH"로 강제하면 숨은 의존성/운영 사고가 발생
* 번들 방식이 가장 재현 가능하고 운영 안정적

**보안/로그**

* passphrase/키/명령어 출력 금지(로그에 남기지 않는다)
* 스냅샷은 **읽기 전용 pull만** 수행(업로드/원격 실행 범위 확장 금지)

#### 2) DEC-PC-032 — Strategy A의 "연결 순서/갭" 처리 방침 확정

**결론**

* Strategy A 유지: **DB Seed 다운로드 → DB 로드 → LIVE 연결**
* DB 다운로드 시간(T) 동안 발생하는 데이터 갭은 **허용**한다.
  * 근거: SSOT에서 PC 앱은 "정본 아님", REST 갭 복구도 Non-scope.
* 단, UX/정합성 혼란을 줄이기 위해 **A를 다음처럼 'A+'로 고정**한다:

**A+ (필수 규칙)**

* **DB에서 "마지막 캔들 1개는 폐기"**(진행 중일 수 있으므로)
* `cutover_ts`는 **폐기한 마지막 캔들의 다음 버킷 시작**으로 고정
  * 예: `cutover_ts = (last_db_bucket_start + tf_ms)`
* 병합 규칙(경계 고정):
  * `bucket_start < cutover_ts` → DB만 표시(고정)
  * `bucket_start >= cutover_ts` → LIVE overlay만 표시(덮어씀)
* UI에는 `cutover_ts` 기준으로 **"LIVE 시작" 마커/텍스트**를 남긴다.

**"중기에는 B 가능" 문서 명시**

* 중기 개선안으로 **Strategy B(WS 버퍼 선행 → DB 로드 → 병합)** 가능성을 SSOT에 명시
* **이번 작업 범위에서는 B 구현 금지**(범위 확장 방지)

#### 3) DEC-PC-033 — 실행 중 DB 스냅샷 교체(Windows 파일 잠금) 시퀀스 확정

**결론**

Windows에서 열려 있는 DB 파일은 rename/move가 실패할 수 있으므로, 실행 중 업데이트는 반드시:

1. **DBReader Close(연결 완전 종료)**
2. **파일 교체(atomic swap)**
   * 다운로드는 `*.tmp`로 받고
   * "검증(오픈 가능)" 후
   * 최종 파일로 rename(단, 1단계 Close가 선행되어야 함)
3. **DBReader Reopen(RO로 재오픈)**
4. UI에 "DB 갱신 성공/실패" 1줄 표기(스팸 금지, rate-limit)

**실패 폴백**

* 교체 실패 시: 기존 DB 유지(또는 기존 DB로 재오픈) + 사용자에게 안내

#### 4) DEC-PC-034 — Passphrase 입력/검증 UX (UI 프리징 0)

**결론**

* Passphrase 입력은 **GUI 다이얼로그**로 받는다.
* 검증/SSH Pull은 반드시 **Worker Thread**에서 수행(메인 UI 스레드 블로킹 금지).
* Passphrase 저장 정책:
  * 기본: **"이번 실행 동안만 메모리 보관"**(앱 종료 시 폐기)
  * 디스크 저장 금지(옵션으로도 금지; 요구 시 별도 DEC 필요)

**인터랙션 흐름(명시)**

* 설정 화면에서:
  * host/user/port/ppk 경로 입력
  * "연결 테스트" 버튼
  * ppk가 암호화된 경우 passphrase 다이얼로그 표시
* 테스트 성공 시에만 "저장" 활성화

#### 5) DEC-PC-035 — LIVE 전환 시 '볼륨 0부터' 문제 처리

**결론**

* 위의 **A+ (cutover_ts를 다음 버킷 시작으로 고정)**으로 해결한다.
  * LIVE가 DB의 "진행 중 캔들"을 덮어쓰지 않으므로,
  * DB 누적 볼륨을 LIVE에 seed 주입할 필요가 없다.
* 따라서 "볼륨 급락"은 구조적으로 최소화되며,
* 만약 표시상 공백이 생기면 그것은 **허용된 갭**이며 "LIVE 시작 마커"로 설명한다.

(참고: "같은 버킷에 덧칠" 방식은 Strategy B 계열이므로 이번 범위에서는 금지)

#### 6) DEC-PC-036 — SSH 네트워크 무한 대기 방지(Timeout/재시도)

**결론(필수 수치 고정)**

* SSH/SCP 작업은 아래 타임아웃을 강제:
  * 연결 시도 최대 3초
  * 전체 Pull 작업 최대 8초(초과 시 강제 중단)
* 재시도:
  * 자동 무한 재시도 금지
  * 사용자 버튼 또는 "주기 갱신"이 있다면 **백오프(예: 5s → 10s → 30s 상한)** 적용
* 실패 시 UI:
  * "DB 업데이트 실패(원인 요약)" 1줄 + 기존 DB 유지

#### 7) Q7 답변 — exchange.name이 upbit가 아닐 때(경고 vs 차단)

**결론**

* 현재 프로젝트는 **Upbit 전용**이므로:
  * `exchange.name != "upbit"`이면 **차단(Fatal)**
  * 이유/조치 안내:
    * "이 앱은 Upbit 전용입니다. config.json의 exchange.name을 upbit로 설정하세요."
* "경고만" 허용은 향후 다거래소 범위 확정 시 별도 DEC로 다룬다(현재 Non-scope).

#### 8) Q8 답변 — DB 스냅샷 없는 Cold Start에서 cutover_ts 정의

**결론**

* DB 스냅샷이 없으면 `DB_ONLY`는 불가 → **LIVE_ONLY로 시작**
* `cutover_ts`는 "DB 기반 병합"의 기준점이므로 **미정(None)** 으로 둔다.
* UI에 "DB 없음(Cold Start)" 상태를 명확히 표기하고,
* 사용자가 "DB Pull"을 실행해 스냅샷이 생기는 시점부터 A+ 규칙을 적용한다.

#### 9) Q9 답변 — SSH 정보 변경/ppk 경로 불일치 처리

**결론**

* config.json에 저장된 SSH 정보가 변경되면:
  * 자동으로 조용히 실패하지 말고,
  * "설정 불일치/검증 필요" 배지 표시
* ppk 경로가 깨졌거나 host/user가 바뀌었으면:
  * 설정 화면을 열어 재검증(연결 테스트) 후 저장
* 이전 정상 설정은 즉시 삭제하지 않고 유지(단, "현재 설정 불능" 표시)

#### 10) 추가 정보 요청에 대한 확정 답변

* 타겟 OS: **Windows 10/11 전용**(현재 범위에서 Mac/Linux 지원 없음)
* SSH 방식: **paramiko 추가 불허**, **PuTTY Portable 번들 + subprocess** 확정

#### 11) 문서 반영 지시(SSOT/Work Order에 무엇을 추가할지)

SSOT v3.4 Decision Log에 아래를 누적:

* DEC-PC-031: PuTTY Portable 번들(puttygen/pscp)로 .ppk 지원, pip 의존성 추가 없음
* DEC-PC-032: Strategy A 유지 + A+(cutover_ts=next bucket) 고정, 갭 허용, 중기 B 가능 명시
* DEC-PC-033: 실행 중 DB 교체는 Close→Swap→Reopen 강제(Windows lock 대응)
* DEC-PC-034: Passphrase GUI 입력 + Worker 처리, 메모리 보관만
* DEC-PC-036: SSH timeout(3s/8s) 고정, 무한대기 금지

Work Order(구현 지시서)에는:

* 병합 경계(`< cutover_ts` / `>= cutover_ts`)를 **문장으로 고정**
* DB 업데이트 시퀀스(Close→Swap→Reopen) **필수 절차로 명시**

#### 핸드오프 6줄

* 무엇을 했다(변경점): STEP 1.5에서 제기된 1~9번 질문에 대해 운영 가능하도록 결정을 고정(DEC-PC-031~036)하고, Work Order/SSOT에 반영할 문구를 마련했습니다.
* 왜 이렇게 했나(결정 근거): 숨은 의존성/Windows 파일 잠금/데이터 갭/Passphrase UI 프리징은 24/7 운영에서 P0 사고 포인트이므로 사전에 결정으로 봉인하기 위함입니다.
* 유지해야 할 방향(Keep): Strategy A(우선) + 중기 B 가능 명시, L1/L2/L3 분리, "거래없음" 표기, SSH Pull(RO).
* 피해야 할 함정(Avoid): PuTTY 설치/PATH 강제, last_message_age로 연결 경고, 열린 DB 파일 rename 시도, UI 스레드에서 SSH/DB I/O.
* 다음 단계(Next): 이 결정서를 기준으로 Cursor가 STEP4 구현(SSH pull/DB swap/WS 상태 분리/UI 표기)을 진행하고, Claude STEP5 혹독 리뷰로 Must Fix를 정리합니다.
* SSOT/Task 위치: SSOT v3.4 Decision Log(DEC-PC-031~036 추가) + `pc_app/engine.py`, `pc_app/ui.py`, `pc_app_main.py` 작업지시서.

---

### D) STEP 2 — Cursor 작업지시서 v2(확정본)

> STEP 1의 내용을 그대로 "확정본"으로 채택하되, 아래 3가지를 **문서에 명시적으로 추가**하고 고정한다.

#### v1 → v2 확정 변경 3개

1. DEC-029 문구 추가: "우선 A, 중기에는 B 가능(이번 범위 구현 금지)"
2. DEC-030 문구 추가: "시장정적 금지, 거래없음 사용"
3. SSH 스냅샷 파이프라인에서 "원격 snapshot 파일 생성 → pull"을 **강제**(WAL 리스크 차단)

#### v2에 "추가로 고정"된 운영 결정(DEC-PC-031~036)

아래는 STEP 1.5 QA에서 확정된 운영 결정을 v2(확정본)에 **누적**한다(범위 확장 아님, 구현 난이도만 봉인):

1. **DEC-PC-031**: `.ppk` 지원은 **PuTTY Portable 번들(puttygen/pscp) + subprocess**로 해결(새 pip 의존성 추가 금지).
2. **DEC-PC-032**: Strategy A 유지 + **A+(cutover_ts=next bucket)** 고정, DB 다운로드 시간 갭 허용, 중기 B 가능 명시(이번 구현 금지).
3. **DEC-PC-033**: 실행 중 DB 교체는 **Close→Swap(atomic)→Reopen** 강제(Windows lock 대응).
4. **DEC-PC-034**: Passphrase는 **GUI 입력** + Worker 처리, **이번 실행 동안만 메모리 보관**, 디스크 저장 금지.
5. **DEC-PC-036**: SSH 타임아웃(연결 3s / 전체 8s) 고정, 무한 대기/무한 재시도 금지(백오프만 허용).
6. **Q7**: `exchange.name != "upbit"`이면 Fatal(Upbit 전용).
7. **Q8**: DB 스냅샷 없는 Cold Start는 LIVE_ONLY로 시작, `cutover_ts=None`(DB Pull 후 A+ 적용).
8. **Q9**: SSH 정보/ppk 경로 불일치 시 "설정 불일치/검증 필요" 배지 + 연결 테스트 재검증 흐름 강제.

이 외 스펙/범위 변경 없음(범위 확장 금지).

핸드오프 6줄:

* 무엇을 했다(변경점): v1을 v2로 확정하면서 DEC-028/029/030을 문서에 고정 반영함.
* 왜 이렇게 했나(결정 근거): 오탐/무결성/스냅샷 일관성이 P0이기 때문.
* 유지해야 할 방향(Keep): L1/L2/L3 분리, A cutover 경계 고정, SSH pull RO 원칙.
* 피해야 할 함정(Avoid): last_message_age로 끊김 판단, WAL 메인파일만 scp, 경계 모호성.
* 다음 단계(Next): Cursor 구현(STEP4)로 이동.
* SSOT/Task 위치: SSOT v3.4 Decision Log에 DEC-028~030 누적.

---

### E) STEP 3 — SSOT/Task 갱신용 "붙여넣기 블록"

SSOT Decision Log에 아래를 그대로 누적:

* DEC-028: DB 소스는 SSH Pull snapshot(RO)
* DEC-029: 동기화 A 확정, 중기 B 가능(이번 범위 금지)
* DEC-030: UI 표기는 "거래없음", 시장정적 금지. last_message_age는 신선도 지표.
* DEC-031: Upbit API 키는 Cloud의 freqtrade config.json에서 SSH로 읽고, dry_run으로 주문 기능 게이트(키 평문 저장/로그 금지, PuTTY .ppk 그대로 사용).
* DEC-032: LIVE_ACTIVE에서 볼륨 막대도 틱 단위로 누적/갱신(렌더는 coalesce).
* DEC-033: SSH 로그인/연결 설정 UI(앱 시작 시 1회, 미설정/실패 시 재요청), passphrase 저장 금지, Cancel/실패 시 안전한 폴백 및 안내(블로킹 금지). 실패 시 로컬 스냅샷 폴백.
* DEC-PC-031: PuTTY Portable 번들(puttygen/pscp)로 .ppk 지원, pip 의존성 추가 없음(설치/PATH 강제 금지).
* DEC-PC-032: Strategy A 유지 + A+(cutover_ts=next bucket) 고정, DB 다운로드 시간 갭 허용,중기 B 가능 명시(이번 범위 구현 금지).
* DEC-PC-033: 실행 중 DB 교체는 Close→Swap(atomic)→Reopen 강제(Windows 파일 잠금 대응).
* DEC-PC-034: Passphrase GUI 입력 + Worker 처리, 이번 실행 동안만 메모리 보관(디스크 저장 금지).
* DEC-PC-036: SSH timeout(연결 3s/전체 8s) 고정, 무한 대기/무한 재시도 금지(백오프만 허용).

Risk Register 업데이트(요약):

* RISK-PC-007: SQLite WAL 스냅샷 불일관 → "원격 snapshot 생성 후 pull"로 완화
* RISK-PC-008: cutover 경계 모호성 → `<`/`>=` 경계 규칙을 문서로 고정하여 완화
* RISK-PC-009: 알람 피로 → L1/L2/L3 분리 + 3초 디바운싱으로 완화
* RISK-ORDER-KEY-001: Upbit 키 유출/로컬 저장 → "메모리 전용 + 마스킹 + 로그 금지 + dry_run LOCK"으로 완화
* RISK-SSH-LOGIN-001: SSH passphrase 취급 오류/평문 저장/로그 노출 → "저장 금지 + 마스킹 + 로그 금지 + UI/Worker 분리"로 완화
* RISK-SSH-DEP-001: SSH/PPK 처리에서 숨은 의존성/설치 문제 → "PuTTY Portable 번들 + 절대경로 호출(설치/PATH 금지)"로 완화(DEC-PC-031)
* RISK-SSH-HANG-001: SSH Pull 무한 대기/프리징 → "타임아웃(3s/8s) + 무한 재시도 금지 + 백오프"로 완화(DEC-PC-036)
* RISK-ORDER-KEY-002: config.json 필드 변동/누락 → "필드 경로 고정 + 예외처리(누락/타입/빈값) + exchange.name 강제(upbit) + dry_run 게이트 + 누락 시 안전 LOCK + UI 원인 코드 표기"로 완화
* RISK-PC-VOL-001: LIVE 볼륨 갱신이 끊겨 체감 저하 → "tick 누적 + coalesce 렌더"로 완화

Open Questions(남기기):

* 스냅샷 pull 주기(버튼/주기/조건부)
* "거래없음" 표기 임계치(색/표현 수준 포함)
* 키 로딩 트리거/주기: 앱 시작 1회인지, 주문 탭 진입 시인지, N분 갱신인지(보안/UX 균형)
* PuTTY passphrase UX: 매 실행 입력 vs Pageant 권장 안내 문구

---

### F) STEP 5 — Claude 혹독 리뷰 체크리스트(구조화)

**Must Fix**

* L1/L2/L3 분리 위반(특히 last_message_age로 연결 경고)
* cutover 경계 규칙이 코드에서 흔들림(<=, < 혼재)
* SSH/DB I/O가 UI 스레드 블로킹
* 스냅샷 교체가 원자적이지 않아 "중간 파일"을 잡을 가능성
* generation_id/context_id mismatch가 렌더링에 반영되지 않음
* Upbit API 키가 로그/예외/디버그 출력으로 유출될 가능성
* dry_run=true 인데 ORDER가 READY로 뜨는 상태(게이트 우회)
* LIVE 볼륨이 cutover 병합/스냅샷 갱신으로 인해 이중집계(2배)되거나, 반대로 멈춰 보이는 현상

**Should Fix**

* 경고 디바운싱 누락/부정확(깜빡임)
* 스냅샷 pull 실패 시 폴백/표기 미흡
* 로그 스팸(레이트리밋 부족)
* 키 로딩 실패/DB pull 실패가 구분되지 않아 진단이 어려움
* ORDER 상태 표기가 과도한 경고색/깜빡임으로 "알람 피로" 유발

**Questions**

* 스냅샷 pull 주기/트리거 정책은 무엇인가?
* "거래없음" 표기 임계치/표현은 어디에 고정할 것인가?
* 키 로딩(SSH) 방식은 plink/pscp 기반으로 고정할 것인가(=ppk 그대로), 또는 paramiko가 ppk를 직접 읽는 버전 고정이 가능한가?

**Risks**

* 스냅샷 주기가 과하면 네트워크/디스크 부담
* 너무 잦은 UI 갱신 + 락 경합 → 프리징 가능성(향후 P2 최적화 필요)
* 키 로딩을 너무 자주 하면 보안/UX 악화(패스프레이즈 반복 입력), 너무 적게 하면 운영 중 키 변경 반영 지연

---

### G) STEP 8 — 운영 체크(경량) 5+5+5

#### P0 테스트 시나리오

1. 거래 공백(>30초)인데 WS는 살아있음 → 경고 뜨면 실패("거래없음"만 표시)
2. WS 강제 끊김 → 3초 지속 후 경고 1회 표시(깜빡임 없음)
3. 스냅샷 pull 성공 → DB history 표시 후 LIVE 전환, 중복/섞임 없음
4. 스냅샷 pull 실패 → 기존 로컬 DB로 정상 구동(폴백), UI에 실패 표기
5. WS 재연결 반복 → generation_id 증가, 이전 generation 데이터 렌더 금지
6. `dry_run=true` 인 서버 config.json → ORDER가 반드시 LOCK, 키가 로드/표시/로그로 새지 않음
7. `dry_run=false` + 키 존재 → ORDER READY(마스킹), 키 로딩 실패 시 ERROR로 전환되며 앱은 계속 구동
8. LIVE_ACTIVE에서 볼륨 막대가 틱마다 증가(가격만 움직이고 볼륨이 멈춰 보이면 실패)

#### 관측성 체크

1. WS 연결 상태(L1/L2)와 거래없음(L3)이 분리 표기되는가
2. reconnect_attempts / connected_since 기록되는가
3. snapshot pull 성공/실패 로그(레이트리밋) 있는가
4. cutover_ts 값이 진단 패널/로그로 확인 가능한가
5. DB 오픈이 항상 RO로 되는가
6. ORDER 상태(LOCK/READY/ERROR)와 원인 코드가 로그/진단 패널에서 확인 가능한가(키 평문 제외)

#### 운영 문서 5줄

1. DB는 "원격 snapshot 생성 후 pull"만 허용(메인 파일 단독 복사 금지)
2. pull 실패 시: 기존 로컬 DB 유지 + 재시도는 수동/주기 정책에 따름
3. WS 경고가 아닌데 "거래없음"이 길면: 시장 소강일 수 있음(연결 칩 확인)
4. WS 경고 발생 시: 디바운싱 후 표시된 경고만 장애로 간주
5. cutover 경계는 `<`/`>=` 규칙을 변경하면 중복/유령 캔들이 생길 수 있으니 금지
6. 주문 키는 Cloud의 Freqtrade config.json에서만 읽고, PC 로컬 저장 금지(메모리 전용). dry_run=true면 항상 주문 잠금.
7. SSH passphrase는 저장하지 않으며, 가능하면 Pageant(에이전트) 사용으로 입력 부담을 줄인다

---

### 마지막: "한 큐 실행" 순서(실제 운영 흐름)

1. **이 문서의 STEP2(v2 확정본)**을 Cursor에 전달 → 구현(STEP4)
2. 구현 산출물을 Claude로 STEP5 혹독 리뷰
3. ChatGPT가 STEP6 통합결정 → Cursor가 STEP7 재적용
4. STEP8 경량 운영 체크로 마무리

---

### 핸드오프 6줄(이 문서에 대한)

* 무엇을 했다(변경점): DEC-028/029/030 확정 후, 실행 패키지를 STEP1~8 한 문서로 통합했다.
* 왜 이렇게 했나(결정 근거): 한 번에 실행 가능하도록 "지시서/QA/리뷰/SSOT갱신/운영체크"를 묶어 드리프트를 차단하기 위함.
* 유지해야 할 방향(Keep): SSH snapshot RO, A전략 cutover 경계 고정, L1/L2/L3 분리, "거래없음" 표기.
* 피해야 할 함정(Avoid): last_message_age로 끊김 판정, WAL 메인파일만 scp, 경계 모호성, UI 스레드 I/O.
* 다음 단계(Next): Cursor 구현(STEP4) 진행.
* SSOT/Task 위치: SSOT v3.4 Decision Log + PC App Pending 항목에 DEC/Task로 누적.

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

### 중기
- PC 앱 Pending 기능 (BURST, cutover, 재연결 강화)
- freqtrade Web UI 연동, Android 알람 앱

### 장기
- REST API, CSV/Parquet 내보내기, 데이터 분석

---

## 🔄 UPDATE HISTORY

**상세 변경 이력**: `ssot_update_history.md` 참조

**최근 주요 변경**:
- **v3.5 (2026-02-15)**: Phase 2.5 DETAILED WORK ORDER (STEP 1~8) 통합
  - DEC-028~033 추가 (SSH Pull snapshot, API 키 연동, LIVE 볼륨 틱 갱신)
  - DEC-PC-031~036 추가 (PuTTY 번들, Strategy A+, DB 교체 시퀀스, passphrase GUI, SSH timeout)
  - DEC-027을 v1/v2로 구분 (기존 테마 규칙 유지 + 상세 작업지시서 추가)
  - RISK-PC-007~009, RISK-ORDER-KEY-001~002, RISK-SSH-* 추가
  - AC/DoD에 SSH, API 키, LIVE 볼륨 관련 항목 추가
  - "바로 실행 가능한 패키지(STEP 1~8)" 문서 전체 통합
- v3.3 (2026-02-12): diff-최소 가드레일 + PC 앱 Light/Dark 테마 규칙
- v3.2 (2026-02-01): PC 앱 UI 보강 (축/좌표/DB 로드)
- v3.1 (2026-01-28): Phase 2 P0 안정화 (PK 분리/flush 레이스/비공개 API)
- v3.0 (2026-01-28): Phase 2.5 PC 앱 전체 명세 추가
- v2.0~v2.4: Phase 2 명세/리팩토링/간소화
- Phase 0/1 상세: `update_history.txt`

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

**Cloud (Phase 2):**
```bash
python collector.py                         # 기본
python collector.py --pairs KRW-BTC,KRW-ETH # pair 지정
python collector.py --http-port 8000        # HTTP 활성화
```

**PC 앱 (Phase 2.5):**
```bash
python pc_app_main.py  # config.json 기반 실행
```

### 종료

**Cloud**: Ctrl+C (5초 이내 graceful shutdown)  
**PC 앱**: 창 닫기 (스레드/소켓 정리)

### 운영

**Cloud**: 24시간+ 무중단, 9시간 주기 재연결, 로그 `logs/collector.log`  
**PC 앱**: LIVE 모드 일시적, DB는 Cloud 동기화, 로그 `%LOCALAPPDATA%/UpbitRealTimeChart/logs/app.log`

---

## 📚 참조 문서

**Cloud (Phase 2)**
- `update_history.txt` (Phase 0/1 상세 이력)

**PC 앱 (Phase 2.5)**
- `pc_app/README.md`
- `pc_app/DESIGN_DUAL_MONITOR.md`
- `pc_app/WEBSOCKET_OPTIMIZATION.md`
- `docs/DUAL_WINDOW_UI_REDESIGN_WORK_ORDER_UPDATED.md` (최신 UI 작업지시서)

**변경 이력**
- `ssot_update_history.md` (SSOT 업데이트 이력)

---

**마지막 업데이트**: 2026-02-15 (v3.5)  
**다음 단계**: Phase 2.5 PC 앱 구현 (SSH Pull, API 키, LIVE 볼륨, WS 경고 오탐 제거) → Phase 2 Cloud 구현  
**상태**: Phase 2 구현 대기 🚧, Phase 2.5 작업지시서 완료 ✅