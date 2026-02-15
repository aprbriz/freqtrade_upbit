# STEP2 작업계획서 (SSOT 기반, v2 확정본)

- 작성일: 2026-02-15
- 기준 문서:
  - `user_data/upbit_exchange/docs/ssot/SSOT_freqtrade_upbit_exchange_realtime_ohlcv_collector_claudev.md`
  - STEP 1: `1151~1367`
  - STEP 2(v2): `1590~1613`
  - 불변 규칙/범위/완료기준: `37~210`

## 1) Goal (목표)

1. STEP1 설계를 STEP2(v2) 확정본으로 고정하여 STEP4 구현에 즉시 착수 가능한 실행 지시로 정리한다.
2. 핵심 축인 `A+ cutover 경계`, `SSH snapshot RO 파이프라인`, `L1/L2/L3 상태 분리`, `ORDER dry_run 게이트`를 운영 사고 없이 구현 가능하게 봉인한다.
3. 범위 확장 없이 SSOT 결정사항(DEC/DEC-PC)만 반영한다.

## 2) Scope / Non-scope (범위)

### In-scope

1. `user_data/upbit_exchange/pc_app/engine.py`
2. `user_data/upbit_exchange/pc_app/ui.py`
3. `user_data/upbit_exchange/pc_app/pc_app_main.py`
4. (사전 승인 후) `user_data/upbit_exchange/pc_app/third_party/putty/*` 번들 추가

### Non-scope

1. `user_data/upbit_exchange/cloud/*` 수정 금지
2. DB 스키마 변경 금지
3. Strategy B 구현 금지(문서 명시만 허용)
4. REST 갭 복구/원격 API 추가 금지
5. 자동 주문/전략 자동화 구현 금지

## 3) Risks (운영 리스크)

1. WS 오탐: `last_message_age`를 연결 상태로 쓰면 오탐/알람 피로 발생
2. 데이터 무결성: `cutover_ts` 경계 불명확 시 DB/LIVE 중복 및 섞임 발생
3. Windows 파일 잠금: DB open 상태 rename/swap 시 실패 위험
4. UI 프리징: SSH/DB I/O가 메인 스레드를 블로킹하면 화면 멈춤
5. 보안: passphrase/API 키 평문 저장 또는 로그 노출 위험
6. 재시도 폭주: SSH 무한 대기/무한 재시도 시 운영 불안정

## 4) 고정 결정 (STEP2 v2 누적사항)

1. DEC-029: 우선 Strategy A, 중기 Strategy B 가능(이번 구현 금지)
2. DEC-030: UI 문구는 "시장정적" 금지, "거래없음" 사용
3. SSH 파이프라인: 원격 snapshot 생성 후 pull 강제(WAL 일관성)
4. DEC-PC-031: `.ppk`는 PuTTY Portable 번들(`puttygen/pscp`) + subprocess
5. DEC-PC-032: A+ 규칙 고정 (`cutover_ts = last_db_bucket_start + tf_ms`)
6. DEC-PC-033: DB 교체는 Close -> Swap(atomic) -> Reopen 강제
7. DEC-PC-034: passphrase GUI 입력 + Worker 처리, 실행 중 메모리 보관만
8. DEC-PC-036: SSH timeout 고정(연결 3s / 전체 8s), 무한 재시도 금지
9. Q7: `exchange.name != "upbit"`이면 Fatal
10. Q8: DB 없는 Cold Start는 LIVE_ONLY, `cutover_ts=None`
11. Q9: SSH/ppk 불일치 시 "설정 불일치/검증 필요" 배지 + 재검증

## 5) 구현 순서 (STEP4 착수용)

1. `engine.py` 상태모델 정리
   - WS 상태를 L1(Connection), L2(Protocol health), L3(Data freshness)로 분리
   - `last_message_age`는 L3(신선도) 전용으로 제한
2. `engine.py` 병합 규칙 고정
   - A+ 기준으로 `cutover_ts` 산출
   - 경계 고정:
     - `bucket_start < cutover_ts` -> DB만 표시
     - `bucket_start >= cutover_ts` -> LIVE overlay만 표시
3. `engine.py` 섞임 방지
   - `context_id=(symbol,generation_id)` 관리
   - reconnect 시 generation 증가, mismatch 데이터 즉시 폐기
4. `engine.py` SSH snapshot 파이프라인
   - 원격 snapshot 생성 -> pull(RO) -> 검증 -> 로컬 atomic swap
   - 실패 시 기존 로컬 DB 유지
5. `engine.py` DB 교체 시퀀스
   - 반드시 Close -> Swap -> Reopen
   - 실패/성공은 1줄 상태로 UI 전달(스팸 방지)
6. `engine.py` ORDER 게이트
   - `dry_run=true` -> `ORDER_LOCKED_DRYRUN`
   - `dry_run=false` + 키 정상 -> `ORDER_KEYS_READY`
   - 키 로딩 실패/누락 -> `ORDER_KEYS_ERROR`
   - 키/passphrase 로그 금지, 평문 저장 금지
7. `ui.py` 표시 규칙
   - "거래없음 n초" 표기 적용(중립 색상)
   - WS 경고는 L1/L2 실패 기준 + 3초 디바운싱
   - ORDER 상태 칩(`LOCKED/READY/ERROR`) 반영
8. `pc_app_main.py` 오케스트레이션
   - 앱 시작 시 SSH 설정/검증 플로우 연결
   - Worker 기반 비동기 호출만 허용(UI 스레드 블로킹 금지)
   - 종료 시 스레드/소켓/DB 핸들 정리 보장

## 6) 검증 체크리스트 (재현 가능)

1. 실행/종료:
   - 앱 실행 후 정상 렌더 확인
   - 정상 종료(Ctrl+C 또는 창 닫기) 2회 연속 성공
2. WS 상태:
   - 거래가 없어도 경고 대신 "거래없음 n초"만 표시
   - 실제 연결 단절 시 3초 지속 후 경고 표시
3. 병합 무결성:
   - `< cutover_ts` DB only, `>= cutover_ts` LIVE only 확인
   - 중복 캔들/볼륨 2배 현상 없음
4. SSH/DB:
   - SSH 실패/취소 시 로컬 스냅샷 폴백 구동
   - DB 교체 시 Close -> Swap -> Reopen 순서 확인
5. 보안:
   - passphrase/API 키 평문이 파일/로그에 남지 않음
6. 장기 안정성:
   - 일정 시간 운영 시 메모리/스레드/핸들 증가 이상 징후 없음

## 7) 결정 필요 (STEP4 전 확정 권장)

1. 스냅샷 pull 트리거
   - Option A: 수동 버튼만
   - Option B: 주기 자동(예: 5분)
   - Option C: 수동 + 주기 병행
2. "거래없음" 임계치
   - Option A: 3초
   - Option B: 5초
   - Option C: 10초
3. 키 로딩 트리거
   - Option A: 앱 시작 1회
   - Option B: 주문 UI 진입 시
   - Option C: 시작 + 주기 갱신
4. passphrase UX
   - Option A: 매 실행 입력
   - Option B: Pageant 우선 안내
   - Option C: A+B 병행

---

## 8) STEP4 구현 리포트 (2026-02-15)

### 8.1 결정 확정값 반영

1. 스냅샷 pull 트리거: **Option B (주기 자동, 기본 300초)**
2. "거래없음" 임계치: **Option A (3초)**
3. 키 로딩 트리거: **Option A (앱 시작 1회)**
4. passphrase UX: **Option C (Pageant 우선 + 필요 시 실행마다 입력)**

### 8.2 변경 파일

1. `user_data/upbit_exchange/pc_app/engine.py`
2. `user_data/upbit_exchange/pc_app/ui.py`
3. `user_data/upbit_exchange/pc_app/pc_app_main.py`

### 8.3 구현 요약

1. `engine.py`
   - WS 상태를 L1/L2/L3로 분리하고, `last_message_age`는 신선도 표기 전용으로 제한
   - Strategy A+ 병합 경계 고정 (`< cutover_ts`=DB, `>= cutover_ts`=LIVE)
   - generation_id 기반 늦은 패킷 폐기로 섞임 방지
   - SSH snapshot 파이프라인(원격 snapshot 생성 -> pull -> 검증 -> Close->Swap->Reopen)
   - SSH timeout(3s/8s), 재연결 backoff/jitter/cooldown 반영
   - ORDER dry_run 게이트 및 `exchange.name != upbit` Fatal 정책 반영
2. `ui.py`
   - SSH 로그인/연결 설정 다이얼로그 추가(비동기 테스트/적용)
   - 헤더 상태칩을 MODE/WS/거래없음/ORDER로 분리
   - WS 경고 3초 디바운싱 적용(깜빡임/오탐 완화)
   - 대시보드/푸터에 SSH/DB snapshot 상태 반영
3. `pc_app_main.py`
   - 앱 시작 시 SSH 설정 다이얼로그 실행
   - 주기 스냅샷 타이머(300초) 연결

### 8.4 검증 실행 결과

1. 정적 문법 검증
   - 실행: `python -m py_compile user_data/upbit_exchange/pc_app/engine.py user_data/upbit_exchange/pc_app/ui.py user_data/upbit_exchange/pc_app/pc_app_main.py`
   - 결과: 통과
2. 엔진 스모크 테스트(헤드리스)
   - 실행: 엔진 `start -> snapshot/diagnostics 조회 -> stop`
   - 결과: 예외 없이 종료, ORDER 초기 상태 `ORDER_LOCKED_DRYRUN` 확인

### 8.5 남은 리스크 / 후속 검증 필요

1. 현재 환경은 GUI 없는 헤드리스라서 실제 창 렌더/상호작용 검증은 미완료
2. Windows 실환경에서 PuTTY 번들(`plink/pscp`) 경로/권한 확인 필요
3. SSH 실서버 연동(연결 테스트/스냅샷 pull/실패 폴백)은 실서버 조건에서 추가 검증 필요

### 8.6 롤백 가이드

1. 전체 롤백:
   - `git restore -- user_data/upbit_exchange/pc_app/engine.py user_data/upbit_exchange/pc_app/ui.py user_data/upbit_exchange/pc_app/pc_app_main.py`
2. 파일 단위 롤백:
   - `git restore -- <대상파일>`
