업비트 실시간 OHLCV 수집기 - SSOT (Single Source of Truth)
프로젝트: Freqtrade_upbit Real-time OHLCV Collector
버전: v1.1
생성일: 2026-01-26
최종 업데이트: 2026-01-26 (v1.1 업데이트)

📸 SNAPSHOT (현재 상태)
완료된 핵심 모듈 (5개)

collector.py - WebSocket 수집기 메인
multi_aggregator.py - 멀티 aggregator 관리자
ohlcv_writer.py - SQLite DB Writer
tick_aggregator.py - 틱 기반 봉 생성기
timeframe_aggregator.py - 시간 기반 봉 생성기

완료된 연동 모듈 (1개)

../strategies/UpbitMicroStructureStrategy.py - freqtrade Strategy

현재 기능

업비트 WebSocket 실시간 체결 데이터 수신 (BTC, ETH, XRP 3개 pair)
0.5초봉, 1초봉 자동 생성 및 저장
3틱봉 생성 및 저장
SQLite DB 저장 (pair별 테이블, WAL 모드)
Ctrl+C 안전 종료
배치 처리 (100건씩 commit)
자동 재연결

현재 기술 스택

Python 3.8+
websocket-client
SQLite3
threading

현재 DB 구조
파일: ohlcv.sqlite (단일 파일)
테이블명: ohlcv_{QUOTE}_{BASE}
  - ts (INTEGER, PRIMARY KEY): 밀리초 timestamp
  - open, high, low, close, volume (REAL)
  - timeframe_ms (INTEGER): 500, 1000, -3


🔒 불변 규칙 (IMMUTABLE RULES)
IR-001: SSOT 원칙

모든 결정사항은 이 Task에만 기록
Task 외부의 추가 요구사항 금지
새로운 결정 필요 시 코드로 때우지 말고 Task에 질문 등록

IR-002: 파일 수정 범위
현재 수정 가능 파일 (5개):

collector.py
multi_aggregator.py
ohlcv_writer.py
tick_aggregator.py
timeframe_aggregator.py

수정 금지:

위 5개 외 모든 파일
새 파일 추가 시 반드시 Task에 승인 요청

IR-003: 안정성 우선

한 모듈의 에러가 전체 시스템을 멈추지 않음
모든 외부 I/O(WebSocket, DB)는 예외 처리 필수
로깅으로 에러 추적 가능해야 함

IR-004: 장기 운영 대응

메모리 누수 방지 (오래된 데이터 자동 flush)
DB 연결 재사용 (매번 열고 닫지 않음)
재연결 로직 (최대 10회 시도)

IR-005: 데이터 무결성

중복 저장 방지 (PRIMARY KEY 활용)
잘못된 데이터 필터링 (price ≤ 0, volume < 0)
타임스탬프 기준 정렬 보장


📋 SCOPE (범위)
✅ In-Scope

업비트 KRW 마켓 실시간 체결 데이터 수집 (BTC, ETH, XRP 단 3개 pair)
다중 타임프레임 OHLCV 생성 (ms 단위, 3틱 단위)
SQLite DB 저장 및 관리
안정적인 장기 운영 (재연결, 에러 처리)
Ctrl+C 즉시 종료 (데이터 손실 최소화)
freqtrade Strategy 연동 (UpbitMicroStructureStrategy.py)

❌ Out-of-Scope (현재 버전)

데이터 분석/시각화
백테스팅 엔진
트레이딩 로직
REST API 서버
Web UI
다른 거래소 지원 (업비트 전용)


🎯 ACCEPTANCE CRITERIA (완료 기준)
AC-001: 기능 동작

[ ] 최소 24시간 무중단 실행 가능
[ ] WebSocket 연결 끊김 시 자동 재연결 (10회 이내)
[ ] Ctrl+C 입력 후 5초 이내 종료
[ ] 0.5초봉, 1초봉, 3틱봉 모두 정상 생성

AC-002: 데이터 품질

[ ] 중복 데이터 0건 (PRIMARY KEY 보장)
[ ] 데이터 손실률 < 0.1% (네트워크 문제 제외)
[ ] 타임스탬프 순서 보장 (ORDER BY ts)

AC-003: 성능

[ ] CPU 사용률 < 10% (유휴 시)
[ ] 메모리 사용량 < 1000MB (24시간 기준)
<!-- 수정: 500MB → 1000MB (사용자 요청) -->
[ ] DB 파일 크기: 30일 약 700MB 이하
<!-- 수정: 1일 100MB → 30일 700MB (사용자 요청) -->
[ ] 참고: H/W 스펙 - 오라클 클라우드 ARM Core 3, RAM 23GB, HDD 200GB
<!-- 추가: 하드웨어 환경 명시 (사용자 요청) -->

AC-004: 운영 안정성

[ ] 로그로 모든 에러 추적 가능
[ ] 한 pair 실패 시 다른 pair 계속 동작
[ ] DB 저장 실패 시 재시도 없이 로그만 (무한 재시도 방지)

AC-005: 코드 품질

[ ] 모든 public 메서드에 docstring
[ ] 코드에 꼼꼼히 초보자도 쉽게 이해할 수 있도록 한글 주석 추가
<!-- 추가: 한글 주석 요구사항 (사용자 요청) -->
[ ] 모든 외부 I/O에 try-except
[ ] logging 사용 (print 금지)
[ ] 타입 힌트 권장


✅ CHECKLIST (구현 체크리스트)
Phase 1: 핵심 기능 (완료 ✅)

[x] WebSocket 연결 및 체결 데이터 수신
[x] 0.5초봉, 1초봉 집계
[x] 3틱봉 집계
[x] SQLite 저장 (pair별 테이블)
[x] Ctrl+C 안전 종료
[x] 배치 처리 (성능 최적화)
[x] 자동 재연결
[x] 에러 처리 강화
[x] freqtrade Strategy 연동: ../strategies/UpbitMicroStructureStrategy.py
<!-- 확인: 사용자가 코딩한 파일 그대로 사용 예정이므로 완료 처리 -->

Phase 2: 단기 개선 (예정)

[ ] 1초봉 → 5초/10초/33초/57초/1분 합성 로직 (메모리에서만 처리)
<!-- 추가: 메모리 처리 명시 (사용자 요청) -->
[ ] 10초봉, 1분봉, 10분봉용 별도 WebSocket 연결 및 DB 파일 생성
<!-- 추가: 신규 타임프레임 수집 방식 (DEC-008 참조) -->
[ ] 통계 정보 출력 (실시간 모니터링)
[ ] 설정 파일 분리 (config_upbit_exchange.yml)
<!-- 수정: config.yaml → config_upbit_exchange.yml (사용자 요청) -->
[ ] CLI 인자 지원 (pairs, timeframes)
[ ] 헬스체크 엔드포인트 (simple HTTP)
[ ] 데이터 정합성 검증 로직

Phase 3: 장기 확장 (백로그)

[ ] REST API 서버
[ ] freqtrade Web UI에 연동 (대시보드, 기존 freqtrade Web UI에 신규 탭 추가 형태)
<!-- 수정: 일반 Web UI → freqtrade Web UI 연동 명시 (사용자 요청) -->
[ ] 데이터 분석 모듈


⚠️ RISK REGISTER (리스크 관리)
RISK-001: WebSocket 장기 연결 불안정
설명: 업비트 WebSocket이 예고 없이 끊길 수 있음
완화: 자동 재연결 로직 (최대 10회, 5초 간격)
상태: ✅ 완화됨
RISK-002: DB 파일 크기 무한 증가
설명: 데이터 누적 시 디스크 공간 부족
완화: cleanup_old_data() 메서드 (365일 이상 삭제)
상태: ⚠️ 수동 실행 필요 (자동화 미구현)
RISK-003: 메모리 누수
설명: 장기 실행 시 메모리 증가 가능성
완화: 주기적 flush (1초마다), 오래된 캔들 자동 제거
상태: ✅ 완화됨
RISK-004: DB 락 (Lock) 문제
설명: 멀티스레드 환경에서 SQLite 동시 쓰기
완화: threading.Lock 사용, WAL 모드 활성화
상태: ✅ 완화됨
RISK-005: Ctrl+C 종료 지연
설명: WebSocket run_forever() 블로킹
완화: 별도 스레드 실행, keep_running=False 강제 설정
상태: ✅ 해결됨
RISK-006: 여러 WebSocket의 동시 DB 쓰기
<!-- 신규 추가: 10초봉/1분봉/10분봉 별도 수집 시 -->
설명: 10초봉, 1분봉, 10분봉용 별도 WebSocket이 같은 DB 파일에 쓰기 시 충돌 가능
완화: 타임프레임별 별도 DB 파일 사용 (DEC-008 참조)

ohlcv_short.sqlite: 0.5초봉, 1초봉, 3틱봉
ohlcv_10s_1m.sqlite: 10초봉, 1분봉
ohlcv_10m.sqlite: 10분봉
상태: 🟡 설계 완료 (구현 예정)


❓ OPEN QUESTIONS (미결정 사항)
~~Q-001: 타임프레임 추가 요청 시 정책~~ ✅ 해결됨
~~질문: 사용자가 2초봉, 5초봉 등 추가 요청 시 어떻게 처리?~~
→ DEC-008로 결정됨 (별도 WebSocket + 별도 DB 파일)

📝 DECISION LOG (결정 로그)
DEC-001: 2026-01-26 - DB 엔진 선정
결정: SQLite 사용
이유:

단일 파일, 설치 불필요
초단기 데이터는 로컬 성능 중요
WAL 모드로 동시성 확보
상태: ✅ 확정

DEC-002: 2026-01-26 - 배치 크기
결정: 100건마다 commit
이유:

매번 commit하면 느림 (100배 차이)
100건 손실은 허용 가능 (약 10초치 데이터)

<!-- 수정: 1초치 → 10초치 (사용자 수정 반영) -->
상태: ✅ 확정
DEC-003: 2026-01-26 - 틱봉 음수 표현
결정: timeframe_ms = -3 (3틱봉)
이유:

시간봉(양수)과 틱봉(음수) 구분 명확
쿼리 시 부호로 필터링 가능
상태: ✅ 확정

DEC-004: 2026-01-26 - pair vs symbol 명칭
결정: "pair" 사용 (일관성)
이유:

freqtrade 표준 용어
BTC/KRW 형식 명확
상태: ✅ 확정

DEC-005: 2026-01-26 - 종료 시그널 처리
결정: sys.exit(0) 강제 종료
이유:

run_forever() 블로킹 문제 해결
2초 이내 종료 보장
상태: ✅ 확정

DEC-006: 2026-01-26 - 여러 거래소 지원 계획
결정: 업비트만 (전용 설계)
이유:

Binance는 freqtrade 100% 사용
장기적으로 freqtrade fork 할 예정
상태: ✅ 확정

DEC-007: 2026-01-26 - 데이터 백업 정책
결정: 수동 백업 (사용자 책임)
이유:

장기적으로 필요가 절실할 경우 추가
상태: ✅ 확정

DEC-008: 2026-01-26 - 타임프레임 추가 정책
<!-- 신규 결정: Q-001 해결 -->
결정: 타임프레임별 별도 WebSocket 연결 + 별도 DB 파일
세부 사항:

메모리 합성: 33초봉, 57초봉은 1초봉 데이터를 메모리에서 합성 (DB 저장 안 함)
별도 수집: 10초봉, 1분봉, 10분봉은 각각 별도 WebSocket 연결로 직접 수집
DB 파일 분리:

ohlcv_short.sqlite: 0.5초봉, 1초봉, 3틱봉 (기존)
ohlcv_10s_1m.sqlite: 10초봉, 1분봉 (신규)
ohlcv_10m.sqlite: 10분봉 (신규)


동시 쓰기 문제 해결: DB 파일을 분리하여 여러 WebSocket이 동시에 다른 파일에 쓰므로 Lock 충돌 없음

이유:

메모리 합성(33초, 57초)은 DB 저장 불필요 → 전략에서만 사용
직접 수집(10초, 1분, 10분)은 정확도 향상 (합성 오차 제거)
DB 파일 분리로 동시 쓰기 성능 향상 및 충돌 방지
각 타임프레임의 독립적 에러 처리 가능

상태: ✅ 확정

📦 BACKLOG (향후 작업)
단기 (1주)

BL-001: 실시간 통계 출력 (초당 체결 수, 저장 속도 등)
BL-002: config_upbit_exchange.yml 설정 파일 분리
BL-003: CLI 인자 지원 (--pairs BTC,ETH --timeframes 500,1000)
BL-004: 헬스체크 HTTP 엔드포인트 (/health, /stats)
BL-005: 데이터 정합성 검증 스크립트

중기 (1개월)

BL-006: REST API 서버 (FastAPI)
BL-007: freqtrade Web UI 연동 (기존 UI에 신규 탭 추가)
BL-008: 데이터 조회 모듈 (query_ohlcv(pair, timeframe, start, end))
BL-009: CSV/Parquet 내보내기

장기 (3개월+)

BL-011: 데이터 분석 모듈 (pandas 기반)
BL-012: 실시간 알림 (Telegram, Slack)


🔄 UPDATE HISTORY (변경 이력)
v1.1 - 2026-01-26
<!-- 이번 업데이트 내용 -->

DEC-008 추가: 타임프레임 추가 정책 확정 (별도 WebSocket + DB 파일)
RISK-006 추가: 동시 DB 쓰기 리스크 등록
Q-001 해결: 타임프레임 추가 정책 질문 종료
AC-003 수정: 메모리 500MB→1000MB, DB 크기 1일 100MB→30일 700MB
AC-003 추가: H/W 스펙 명시 (오라클 클라우드)
AC-005 추가: 한글 주석 요구사항
Phase 1 완료 추가: freqtrade Strategy 연동 체크
Phase 2 추가: 메모리 합성 로직, 별도 WebSocket 수집
설정 파일명 변경: config.yaml → config_upbit_exchange.yml
Web UI 명확화: freqtrade Web UI 연동으로 구체화

v1.0 - 2026-01-26

초기 SSOT 작성
5개 핵심 모듈 스냅샷
불변 규칙 5개 정의
리스크 5개 등록
백로그 11개 항목 등록


📌 NOTES (참고사항)
개발 환경

Python 3.8+
Docker 환경 권장
로그 디렉토리: ./logs/
DB 파일:

./ohlcv_short.sqlite (0.5초, 1초, 3틱)
./ohlcv_10s_1m.sqlite (10초, 1분) - 향후 추가
./ohlcv_10m.sqlite (10분) - 향후 추가



의존성
websocket-client>=1.0.0

실행 방법
python collector.py

종료 방법
Ctrl+C  # 5초 이내 안전 종료


마지막 업데이트: 2026-01-26 (v1.1)
다음 리뷰 예정: Phase 2 단기 개선 시작 전