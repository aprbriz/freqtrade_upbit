업비트 실시간 OHLCV 수집기 - SSOT (Single Source of Truth)
프로젝트: Freqtrade_upbit Real-time OHLCV Collector
버전: v1.0
생성일: 2026-01-26
최종 업데이트: 2026-01-26

📸 SNAPSHOT (현재 상태)
완료된 핵심 모듈 (5개)

collector.py - WebSocket 수집기 메인
multi_aggregator.py - 멀티 aggregator 관리자
ohlcv_writer.py - SQLite DB Writer
tick_aggregator.py - 틱 기반 봉 생성기
timeframe_aggregator.py - 시간 기반 봉 생성기

현재 기능

업비트 WebSocket 실시간 체결 데이터 수신
0.5초봉, 1초봉 자동 생성 및 저장
3틱봉 생성 및 저장
SQLite DB 저장 (pair별 테이블, WAL 모드)
Ctrl+C 안전 종료
배치 처리 (100건씩 commit)
자동 재연결

현재 기술 스택

Python 3.x
websocket-client
SQLite3
threading

현재 DB 구조
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

업비트 KRW 마켓 실시간 체결 데이터 수집 (BTC,EHT,XRP 단 3개 pair)
다중 타임프레임 OHLCV 생성 (ms 단위, 3틱 단위)
SQLite DB 저장 및 관리
안정적인 장기 운영 (재연결, 에러 처리)
Ctrl+C 즉시 종료 (데이터 손실 최소화)

❌ Out-of-Scope (현재 버전)

데이터 분석/시각화
백테스팅 엔진
트레이딩 로직
REST API 서버
Web UI
freqtrade 연동 (별도 모듈로 추후 개발)


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
[ ] DB 파일 크기: 30일 약 700MB 이하
[ ] 참고 : H/W (spec) 오라클 클라우드 arm core 3, RAM 23GB, hdd 200GB

AC-004: 운영 안정성

[ ] 로그로 모든 에러 추적 가능
[ ] 한 pair 실패 시 다른 pair 계속 동작
[ ] DB 저장 실패 시 재시도 없이 로그만 (무한 재시도 방지)

AC-005: 코드 품질

[ ] 모든 public 메서드에 docstring
[ ] 코드에 꼼꼼히 초보자도 쉽게 이해할 수 있도록 한글 주석 추가
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
[x] freqtrade Strategy 연동 : ../strategies/UpbitMicroStructureStrategy.py

Phase 2: 단기 개선 (예정)

[ ] 1초봉 → 5초/10초/33초/57초/1분 합성 로직
[ ] 통계 정보 출력 (실시간 모니터링)
[ ] 설정 파일 분리 (config_upbit_exchange.yml)
[ ] CLI 인자 지원 (pairs, timeframes)
[ ] 헬스체크 엔드포인트 (simple HTTP)
[ ] 데이터 정합성 검증 로직

Phase 3: 장기 확장 (백로그)

[ ] REST API 서버
[ ] freqtrade Web UI 에 연동 (대시보드, 기존 freqtrade web UI 에 신규탭을 추가하는 형태로 구현)
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

❓ OPEN QUESTIONS (미결정 사항)
Q-001: 타임프레임 추가 요청 시 정책
질문: 사용자가 2초봉, 5초봉 등 추가 요청 시 어떻게 처리?
옵션:

A) 설정 파일에서 동적 추가
B) 코드 수정 필요
C) 최대 개수 제한 (성능 고려)
상태: 🔴 미결정 (보류)


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

DEC-006: 여러 거래소 지원 계획
결정: 업비트만 (전용 설계)
이유: 

binance는 freqtrade 100% 사용.
우리는 장기적으로 freqtrade fork 할 예정임
상태: ✅ 확정

DEC-007: 데이터 백업 정책
결정:수동 백업 (사용자 책임)
이유:

장기적으로 필요가 절실할 경우가 되면 추가
상태: ✅ 확정


📦 BACKLOG (향후 작업)
단기 (1주)

BL-001: 실시간 통계 출력 (초당 체결 수, 저장 속도 등)
BL-002: config.yaml 설정 파일 분리
BL-003: CLI 인자 지원 (--pairs BTC,ETH --timeframes 500,1000)
BL-004: 헬스체크 HTTP 엔드포인트 (/health, /stats)
BL-005: 데이터 정합성 검증 스크립트

중기 (1개월)

BL-006: REST API 서버 (FastAPI)
BL-007: 일반 이용자용 Web UI (조회, 통계, freqtrade와 연동한 주문입력)
BL-008: 데이터 조회 모듈 (query_ohlcv(pair, timeframe, start, end))
BL-009: CSV/Parquet 내보내기

장기 (3개월+)

BL-011: 데이터 분석 모듈 (pandas 기반)
BL-012: 실시간 알림 (Telegram, Slack)


🔄 UPDATE HISTORY (변경 이력)
v1.0 - 2026-01-26

초기 SSOT 작성
5개 핵심 모듈 스냅샷
불변 규칙 5개 정의
리스크 5개 등록
백로그 15개 항목 등록


📌 NOTES (참고사항)
개발 환경

Python 3.8+
Docker 환경 권장
로그 디렉토리: ./logs/
DB 파일: ./ohlcv.sqlite

의존성
websocket-client>=1.0.0

실행 방법
python collector.py

종료 방법
Ctrl+C  # 5초 이내 안전 종료


마지막 업데이트: 2026-01-26
다음 리뷰 예정: 단기 개선 시작 전