# STEP4 Codex 구현 혹독 검증 보고서

- 검증일: 2026-02-15
- 검증자: Claude (Opus 4.6)
- 대상 커밋: 현재 HEAD (main)
- 기준 문서:
  - `docs/ssot/SSOT_...claudev.md` (v3.5)
  - `docs/ssot/STEP2_work_plan.md` (v2 확정본)
- 대상 파일:
  - `pc_app/engine.py` (1242줄)
  - `pc_app/ui.py` (1128줄)
  - `pc_app/pc_app_main.py` (131줄)

---

## 총평

핵심 인프라(엔진 상태모델, A+ 병합, SSH 파이프라인, ORDER 게이트)는 SSOT 스펙을 충실히 구현했다.
그러나 UI 기능 일부 누락, 보안 규칙 위반 2건, Hard No 위반 1건이 존재하며,
AC(Acceptance Criteria) 체크리스트 기준 미충족 항목이 14개로 "배포 가능" 수준은 아니다.

| 등급 | 건수 | 설명 |
|------|------|------|
| CRITICAL | 3 | 스펙 위반 / 보안 / Hard No |
| HIGH | 11 | AC 미충족 / 누락 기능 |
| MEDIUM | 6 | 부분 구현 / 편차 |
| LOW | 4 | 코드 품질 / 잔여물 |

---

## CRITICAL (즉시 수정 필수)

### C-1. PuTTY PATH fallback — Hard No 위반

- 위치: `engine.py:922-929` — `_resolve_putty_binary` 메서드
- 현상: 번들 디렉토리에 바이너리가 없으면 `shutil.which()`로 시스템 PATH를 탐색하여 fallback
- 위반 규칙:
  - SSOT DEC-PC-031: "설치/PATH 요구(금지) — 번들 exe 절대경로로만 호출"
  - STEP1 Hard No: "PuTTY 설치/PATH 요구(금지)"
- 위험: 시스템에 설치된 다른 버전의 plink/pscp가 호출될 수 있음. 버전 불일치, 보안 탬퍼 위험.
- 수정안: PATH fallback 로직 전체 제거. 번들 경로에 없으면 None → 에러 처리.

---

### C-2. passphrase가 프로세스 명령줄 인자로 노출

- 위치: `engine.py:943-944` — `_build_putty_common_args` 메서드
- 현상: passphrase를 PuTTY의 `-pw` 인자로 전달. `subprocess.run()` 실행 시 `ps aux`에 전체 명령줄이 노출됨
- 위반 규칙:
  - SSOT DEC-PC-034: "passphrase는 이번 실행 동안만 메모리 보관"
  - STEP1 6.6: "passphrase/키/명령어 전문 출력 금지"
- 위험: 같은 머신의 다른 사용자가 프로세스 목록에서 passphrase를 확인 가능
- 수정안: Pageant 우선 사용을 강제하고, `-pw` fallback 사용 시 경고 표시. 또는 stdin pipe 방식 검토.

---

### C-3. `-timeout` 플래그는 plink/pscp에 존재하지 않음

- 위치: `engine.py:939-940` — `_build_putty_common_args` 메서드
- 현상: plink/pscp 호출 시 `-timeout 3` 인자를 전달하지만, PuTTY 도구에 해당 옵션이 없음
- 문제:
  - plink에서 "알 수 없는 옵션" 에러 발생 가능
  - 또는 원격 명령의 일부로 잘못 해석될 수 있음
- 실질적 영향: `subprocess.run(timeout=8)` 로 프로세스 레벨 타임아웃은 걸려 있어서 완전 무방비는 아님. 그러나 plink 실행 자체가 실패할 수 있음.
- 수정안: `-timeout` 인자 제거. 타임아웃은 subprocess의 timeout 매개변수에만 의존.

---

## HIGH (AC 미충족 — 배포 전 해결 필요)

### H-1. 버튼 3개 (LIVE 시작, DB 전환, ACK) 미구현

- AC 기준: AC-PC-001 — "버튼 3개 (LIVE 시작, DB 전환, ACK) 정상 동작"
- 현상: 현재 UI에 모드 전환 버튼이 없음. 사용자가 수동으로 DB_ONLY ↔ LIVE_ACTIVE를 전환할 수 없음. engine에 `set_symbol_mode()` 메서드는 존재하지만 UI에서 호출하는 버튼이 없음.

### H-2. 갭 마커 / "LIVE 시작" 마커 미구현

- AC 기준: AC-PC-001 — "갭 표시 규칙 준수 (보간 없음, 장애 갭 마커)"
- SSOT 기준: "UI에는 cutover_ts 기준으로 'LIVE 시작' 마커/텍스트를 남긴다"
- 현상: 캔들 차트 위젯의 렌더링에 cutover_ts 기준 마커가 없음. cutover_ts 값은 snapshot에 포함되지만 차트에서 활용하지 않음.

### H-3. 3틱봉 인덱스축 + KST 툴팁 미구현

- AC 기준: AC-PC-001 — "3틱봉 인덱스축 + KST 툴팁"
- 현상: TickAggregator 클래스는 존재하고 데이터를 수집하지만, UI에서 3틱봉 차트를 렌더링하는 위젯이 없음. KST 툴팁도 미구현.

### H-4. 드랍 우선순위 (1~5) 미구현

- AC 기준: AC-PC-002 — "드랍 우선순위 (1~5) 작동"
- 현상: 폭주 시 어떤 데이터를 우선 드랍할지의 정책이 전혀 없음. coalesce만 존재(50ms UI 타이머).

### H-5. 듀얼 모니터 핫플러그 미대응

- AC 기준: AC-PC-002 — "듀얼 모니터 핫플러그 대응 (자동 폐)"
- 현상: QScreen 변경 시그널(screenAdded/screenRemoved)을 구독하지 않음. 모니터를 분리/연결해도 창이 자동 재배치되지 않음.

### H-6. DB catch-up barrier 미구현

- AC 기준: AC-PC-004 — "DB catch-up barrier 복귀 동작"
- 현상: DB 스냅샷 갱신 후 cutover_ts를 재산출하여 DB↔LIVE 경계를 갱신하는 "catch-up" 로직이 DB_ONLY 심볼에만 있고, LIVE_ACTIVE 심볼에는 적용되지 않음.

### H-7. partial/global silent 구분 미구현

- AC 기준: AC-PC-005 — "partial/global silent 구분"
- 현상: 모든 심볼의 WS 상태를 동일하게 취급함. 하나만 끊긴 partial silence와 전체 끊긴 global silence를 구분하지 않음. 대응 전략도 동일(전체 reconnect).

### H-8. 단계적 대응 (재구독→재연결) 미구현

- AC 기준: AC-PC-005 — "단계적 대응 (재구독→재연결)"
- 현상: WS 장애 시 무조건 전체 연결 재시작만 수행. SSOT이 요구하는 "먼저 재구독 시도 → 실패 시 재연결" 단계적 대응이 없음.

### H-9. Upbit 레이트리밋 명시적 준수 미구현

- AC 기준: AC-PC-005 — "Upbit 레이트리밋 준수 (연결 5회/초, 구독 5회/초 + 100회/분)"
- 현상: backoff/jitter는 있지만, 명시적 레이트리밋 카운터(5회/초, 100회/분)가 없음. 빠른 재연결 반복 시 레이트리밋 위반 가능.

### H-10. LIVE overlay bounded 정책 — 시간 제한 누락

- AC 기준: AC-PC-004 — "bounded 정책 (시간 + 개수 2중 제한)"
- 현상: TimeframeAggregator는 max_store=1000(개수 제한)만 있음. 시간 기반 제한(예: 최근 N시간분만 유지)이 없어서, 장기 운영 시 1분봉 1000개(약 16시간)가 쌓일 수 있음.

### H-11. ORDER 상태 칩 문구 불일치

- SSOT 기준: `dry_run=true` → `ORDER: LOCKED (DRY_RUN)` 고정 표기
- 현상: UI에서 `ORDER LOCKED`로만 표시. SSOT이 요구하는 구체적 사유 코드 `(DRY_RUN)`, `(KEY LOAD)` 등이 칩 텍스트에 반영되지 않음.
- 위치: `ui.py:569`

---

## MEDIUM (부분 구현 / 편차)

### M-1. AlertStrip 클래스 잔존 (dead code)

- 위치: `ui.py:370-397`
- 현상: 이전 디자인의 AlertStrip 클래스가 정의되어 있지만 어디서도 인스턴스화되지 않음. check_alert()이 HeaderBar로 이관된 후 삭제되지 않은 잔여물.

### M-2. DB swap 후 LIVE_ACTIVE 심볼의 cutover 미갱신

- 위치: `engine.py:1127-1148`
- 현상: DB 스냅샷 교체 후 DB_ONLY 심볼만 seed를 갱신함. LIVE_ACTIVE 심볼은 이전 cutover_ts를 유지. 새 DB에 더 최근 데이터가 있어도 LIVE 심볼의 DB 히스토리가 갱신되지 않음.

### M-3. 하단 티커 coalesce/드랍 안내 부족

- AC 기준: AC-PC-002 — "하단 티커 coalesce/드랍 안내"
- 현상: FooterBar에 coalesce 상태나 드랍 발생 여부를 표시하지 않음. 50ms UI 타이머로 간접 coalesce는 되지만 사용자에게 알리지 않음.

### M-4. _apply_geometry KeyError 미방어

- 위치: `pc_app_main.py:18-19`
- 현상: window_positions 설정이 빈 dict일 때 KeyError로 크래시 가능. config.get("window1", {})가 빈 dict를 반환하면 "x", "y" 등 키가 없어서 예외 발생.

### M-5. snapshot_timer 종료 시 미정지

- 위치: `pc_app_main.py:95-98`
- 현상: _on_quit()에서 snapshot_timer.stop()을 호출하지 않음. 앱 종료 과정에서 타이머가 한 번 더 fire될 수 있음.

### M-6. WS on_error 시 L1을 CONNECTED로 유지

- 위치: `engine.py:494-496`
- 현상: WS 에러 콜백에서 L1="CONNECTED", L2="DEGRADED"로 보고. 에러 후 곧 on_close가 호출되겠지만, 일시적으로 L1/L2 조합이 부정확할 수 있음.

---

## LOW (코드 품질)

### L-1. ThemeManager._listeners 클래스 변수 mutable list

- 위치: `ui.py:100`
- 클래스 변수로 mutable list를 선언. 현재 코드에서는 실질적 문제 없으나, 서브클래스 생성 시 공유 문제 가능.

### L-2. SQL table name을 f-string으로 직접 삽입

- 위치: `engine.py:376`
- table명이 내부 생성이라 현재 injection 위험은 없으나, 외부 심볼명이 들어올 경우 위험한 패턴.

### L-3. rate KPI 타일의 "N/s" 표시가 실제 초당 아님

- 위치: `ui.py:1010`
- total_ticks는 앱 시작 이후 누적 틱 수인데 "/s"(초당)로 표시. 실제 초당 수신율과 혼동.

### L-4. volume 차트 거래대금 vs raw volume 혼동 가능

- 위치: `ui.py:702`
- volume * close로 KRW 거래대금을 계산하는데, 사용자가 raw volume으로 오해할 수 있음. 레이블이 없어서 구분 불가.

---

## AC 체크리스트 요약

### AC-PC-001 (기능 동작) — 22항목 중 3개 미충족, 2개 부분 충족

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 1 | 드롭다운 심볼/타임프레임 | PASS | |
| 2 | 듀얼 모니터 UI | PASS | |
| 3 | 단일 모니터 폴백 | PASS | |
| 4 | 상태 칩 (MODE/WS/거래없음/ORDER) | WARN | BURST 칩 없음 |
| 5 | 통합 진단 패널 | PASS | |
| 6 | 버튼 3개 (LIVE/DB/ACK) | FAIL | H-1 |
| 7 | DB_ONLY 차트 출력 | PASS | |
| 8 | LIVE_ACTIVE 틱 갱신 | PASS | |
| 9 | 갭 표시 / LIVE 마커 | FAIL | H-2 |
| 10 | 3틱봉 + KST 툴팁 | FAIL | H-3 |
| 11 | Raw Trade 단일 구독 | PASS | |
| 12 | 타임프레임 즉시 전환 | PASS | |
| 13 | Light/Dark 테마 | PASS | |
| 14 | SSH 다이얼로그 | PASS | |
| 15 | SSH 비동기 테스트 | PASS | |
| 16 | SSH Cancel 폴백 | PASS | |
| 17 | DB atomic 교체 | PASS | |
| 18 | ORDER 칩 | WARN | 사유 코드 미표시 (H-11) |
| 19 | dry_run LOCK | PASS | |
| 20 | ORDER READY | PASS | |
| 21 | LIVE 볼륨 틱 누적 | PASS | |
| 22 | WS L1/L2 + 거래없음 분리 | PASS | |

### AC-PC-002 (성능/안정성) — 17항목 중 2개 미충족, 4개 부분 충족

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 1 | UI 프리징 없음 | PASS | Worker 패턴 적용 |
| 2 | 메모리 bounded | PASS | deque maxlen |
| 3 | 드랍 우선순위 1~5 | FAIL | H-4 |
| 4 | 하단 coalesce 안내 | WARN | M-3 |
| 5 | WS 재연결 폭주 방지 | PASS | backoff/jitter/cooldown |
| 6 | 종료 시 누수 없음 | PASS | |
| 7 | config.json 정상 | PASS | |
| 8 | 로그 로테이션 | PASS | 50MB x 5 |
| 9 | SQLite RO 오픈 | PASS | mode=ro, immutable=1 |
| 10 | 듀얼 모니터 핫플러그 | FAIL | H-5 |
| 11 | SSH Worker 비동기 | PASS | |
| 12 | SSH 타임아웃 | WARN | subprocess OK, -timeout 플래그 무효 (C-3) |
| 13 | SSH 무한 재시도 금지 | PASS | |
| 14 | passphrase 평문 저장 0 | WARN | 디스크 저장 0, 단 CLI 노출 (C-2) |
| 15 | API 키 평문 저장/로그 0 | PASS | |
| 16 | Close→Swap→Reopen | PASS | |
| 17 | PuTTY Portable 번들 | WARN | PATH fallback 위반 (C-1) |

### AC-PC-003 (섞임 방지) — 3항목 전체 충족

| # | 항목 | 상태 |
|---|------|------|
| 1 | generation_id 기반 폐기 | PASS |
| 2 | 타임프레임 변경 섞임 없음 | PASS |
| 3 | context_id mismatch 폐기 | PASS |

### AC-PC-004 (LIVE 오버레이) — 3항목 중 1개 미충족, 1개 부분 충족

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 1 | cutover_ts 병합 규칙 | PASS | A+ 정확 구현 |
| 2 | bounded (시간+개수) | WARN | 개수만 (H-10) |
| 3 | DB catch-up barrier | FAIL | H-6 |

### AC-PC-005 (WS 장애 대응) — 4항목 중 2개 미충족, 1개 부분 충족

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 1 | partial/global silent | FAIL | H-7 |
| 2 | 재구독→재연결 단계적 | FAIL | H-8 |
| 3 | 파싱 실패 ≠ 재연결 | PASS | |
| 4 | Upbit 레이트리밋 | WARN | 명시적 카운터 없음 (H-9) |

---

## 잘한 점 (Keep)

1. A+ 병합 규칙 정확 구현 — cutover_ts 경계, 마지막 캔들 폐기, DB/LIVE 분리가 SSOT 그대로
2. generation_id 기반 섞임 방지 — 재연결 전후 데이터 격리 정확
3. SSH 파이프라인 완성도 — 원격 snapshot 생성 → pull → 검증 → atomic swap 전체 흐름 구현
4. ORDER 게이트 로직 — dry_run/키 로딩/Fatal 정책이 SSOT 결정사항과 일치
5. UI 스레드 블로킹 0 — SSH/DB I/O 모두 Worker 스레드로 분리
6. 3초 디바운싱 — WS 경고 깜빡임 제거 정확 구현
7. "거래없음 n초" 중립 표기 — L3 신선도와 L1/L2 연결 상태 분리 정확

---

## 결론: Must Fix 우선순위

| 순위 | ID | 작업 | 난이도 |
|------|----|------|--------|
| 1 | C-1 | PATH fallback 로직 제거 | 5분 |
| 2 | C-3 | 존재하지 않는 -timeout 플래그 제거 | 5분 |
| 3 | C-2 | -pw CLI 노출 경고 + Pageant 강제 안내 | 30분 |
| 4 | H-1 | LIVE/DB/ACK 버튼 UI 추가 | 2시간 |
| 5 | H-2 | cutover_ts LIVE 마커 차트 렌더링 | 1시간 |
| 6 | H-11 | ORDER 칩에 사유 코드 추가 | 15분 |
| 7 | H-8 | WS 단계적 대응 (재구독→재연결) | 3시간 |
| 8 | H-7 | partial/global silent 구분 | 2시간 |
| 9 | H-9 | Upbit 레이트리밋 카운터 | 1시간 |
| 10 | H-6 | DB catch-up barrier | 2시간 |

---

검증 완료. 소스 코드 수정 없음.
