업비트 실시간 OHLCV 수집기 - SSOT (Single Source of Truth)
프로젝트: Freqtrade_upbit Real-time OHLCV Collector
버전: v1.2
생성일: 2026-01-26
최종 업데이트: 2026-01-26 (v1.2 긴급 업데이트)

🚨 긴급 수정 사항 (v1.2)
CRITICAL-001: WebSocket 19시간 후 재연결 실패
발견 날짜: 2026-01-26
증상:

19시간 연속 실행 후 업비트 서버가 연결 강제 종료 (opcode=8, b'\x83\xe8')
재연결 로직이 작동하지 않음 (재연결 시도 로그 없음)
프로그램이 종료되지 않고 대기 상태로 방치됨

우선순위: 🔴 최우선 (P0)
수정 필요 사항:


재연결 로직 점검 (collector.py의 on_close() 핸들러)

self.running 상태가 재연결 중 False로 변경되는지 확인
재연결 시도 로그가 출력되는지 확인
재연결 카운터가 정상 작동하는지 확인



주기적 재연결 추가

12시간마다 의도적으로 WebSocket 재연결
업비트 서버의 장시간 연결 종료 정책 회피
타이머 기반 재연결 스케줄링



종료 코드 파싱

b'\x83\xe8' 디코딩하여 정확한 종료 이유 파악
업비트 공식 문서에서 종료 코드 의미 확인
종료 이유별 대응 로직 추가



재연결 강화

ping_timeout 조정 (현재 10초 → 30초 검토)
재연결 시도 간격 조정 (현재 5초 → 지수 백오프 검토)
최대 재연결 횟수 증가 (현재 10회 → 무제한 또는 100회 검토)



영향도:

장기 운영 시 데이터 수집 중단
수동 재시작 필요 (모니터링 부재 시 데이터 손실)

테스트 방법:

24시간 연속 실행 테스트
재연결 로그 모니터링
네트워크 강제 차단 후 재연결 확인


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
⚠️ 자동 재연결 (현재 작동 불안정 - CRITICAL-001)

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

알려진 이슈 (Known Issues)

⚠️ 19시간 후 재연결 실패 (CRITICAL-001)
✅ XRP 추가는 정상 작동 확인됨


🔒 불변 규칙 (IMMUTABLE RULES)
IR-001: SSOT 원칙

모든 결정사항은 이 Task에만 기록
Task 외부의 추가 요구사항 금지
새로운 결정 필요 시 코드로 때우지 말고 Task에 질문 등록

IR-002: 파일 수정 범위
현재 수정 가능 파일 (5개):

collector.py ⚠️ 긴급 수정 필요
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
⚠️ 장기 운영 중 재연결 실패 방지 (CRITICAL-001)

IR-004: 장기 운영 대응

메모리 누수 방지 (오래된 데이터 자동 flush)
DB 연결 재사용 (매번 열고 닫지 않음)
⚠️ 재연결 로직 강화 필요 (CRITICAL-001)
⚠️ 주기적 재연결 추가 필요 (12시간마다)

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
⚠️ 24시간+ 무중단 운영 (CRITICAL-001 해결 필요)

❌ Out-of-Scope (현재 버전)

데이터 분석/시각화
백테스팅 엔진
트레이딩 로직
REST API 서버
Web UI
다른 거래소 지원 (업비트 전용)


🎯 ACCEPTANCE CRITERIA (완료 기준)
AC-001: 기능 동작

[ ] 최소 24시간 무중단 실행 가능 ⚠️ 현재 19시간에서 중단됨 (CRITICAL-001)
[ ] WebSocket 연결 끊김 시 자동 재연결 (무제한 또는 100회 이내) ⚠️ 현재 작동 안 함
[ ] Ctrl+C 입력 후 5초 이내 종료 ✅
[ ] 0.5초봉, 1초봉, 3틱봉 모두 정상 생성 ✅
[ ] 12시간마다 주기적 재연결 (장기 연결 종료 방지) ⚠️ 미구현

AC-002: 데이터 품질

[ ] 중복 데이터 0건 (PRIMARY KEY 보장)
[ ] 데이터 손실률 < 0.1% (네트워크 문제 제외)
[ ] 타임스탬프 순서 보장 (ORDER BY ts)

AC-003: 성능

[ ] CPU 사용률 < 10% (유휴 시)
[ ] 메모리 사용량 < 1000MB (24시간 기준)
[ ] DB 파일 크기: 30일 약 700MB 이하
[ ] 참고: H/W 스펙 - 오라클 클라우드 ARM Core 3, RAM 23GB, HDD 200GB

AC-004: 운영 안정성

[ ] 로그로 모든 에러 추적 가능 ✅
[ ] 한 pair 실패 시 다른 pair 계속 동작 ✅
[ ] DB 저장 실패 시 재시도 없이 로그만 (무한 재시도 방지) ✅
[ ] 재연결 시도 로그 출력 ⚠️ 현재 출력 안 됨 (CRITICAL-001)
[ ] 서버 종료 코드 파싱 및 로깅 ⚠️ 미구현

AC-005: 코드 품질

[ ] 모든 public 메서드에 docstring
[ ] 코드에 꼼꼼히 초보자도 쉽게 이해할 수 있도록 한글 주석 추가
[ ] 모든 외부 I/O에 try-except
[ ] logging 사용 (print 금지)
[ ] 타입 힌트 권장


✅ CHECKLIST (구현 체크리스트)
Phase 0: 긴급 수정 (최우선) 🚨

[ ] CRITICAL-001 수정: WebSocket 재연결 로직 점검 및 강화

[ ] on_close() 핸들러에서 재연결 시도 로그 출력 확인
[ ] self.running 상태 유지 확인
[ ] 재연결 카운터 작동 확인


[ ] 주기적 재연결 추가: 12시간마다 의도적 재연결

[ ] 타이머 기반 스케줄링
[ ] 재연결 전 현재 데이터 flush
[ ] 재연결 후 구독 재설정


[ ] 종료 코드 파싱: b'\x83\xe8' 디코딩 및 로깅

[ ] 업비트 종료 코드 문서 확인
[ ] 종료 이유별 대응 로직


[ ] 재연결 설정 강화:

[ ] ping_timeout 조정 검토
[ ] 재연결 간격 지수 백오프 검토
[ ] 최대 재연결 횟수 증가 (무제한 또는 100회)


[ ] 24시간 연속 테스트: 실제 운영 환경에서 검증

Phase 1: 핵심 기능 (완료 ✅)

[x] WebSocket 연결 및 체결 데이터 수신
[x] 0.5초봉, 1초봉 집계
[x] 3틱봉 집계
[x] SQLite 저장 (pair별 테이블)
[x] Ctrl+C 안전 종료
[x] 배치 처리 (성능 최적화)
[x] ⚠️ 자동 재연결 (작동 불안정 - CRITICAL-001)
[x] 에러 처리 강화
[x] freqtrade Strategy 연동: ../strategies/UpbitMicroStructureStrategy.py
[x] XRP 페어 추가 (정상 작동 확인)

Phase 2: 단기 개선 (예정)

[ ] 1초봉 → 5초/10초/33초/57초/1분 합성 로직 (메모리에서만 처리)
[ ] 10초봉, 1분봉, 10분봉용 별도 WebSocket 연결 및 DB 파일 생성
[ ] 통계 정보 출력 (실시간 모니터링)
[ ] 설정 파일 분리 (config_upbit_exchange.yml)
[ ] CLI 인자 지원 (pairs, timeframes)
[ ] 헬스체크 엔드포인트 (simple HTTP)
[ ] 데이터 정합성 검증 로직

Phase 3: 장기 확장 (백로그)

[ ] REST API 서버
[ ] freqtrade Web UI에 연동 (대시보드, 기존 freqtrade Web UI에 신규 탭 추가 형태)
[ ] 데이터 분석 모듈


⚠️ RISK REGISTER (리스크 관리)
RISK-001: WebSocket 장기 연결 불안정
설명: 업비트 WebSocket이 예고 없이 끊길 수 있음
완화: 자동 재연결 로직 (최대 10회, 5초 간격)
상태: 🔴 심각 (CRITICAL-001 발견) - 재연결 작동 안 함
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
설명: 10초봉, 1분봉, 10분봉용 별도 WebSocket이 같은 DB 파일에 쓰기 시 충돌 가능
완화: 타임프레임별 별도 DB 파일 사용 (DEC-008 참조)
상태: 🟡 설계 완료 (구현 예정)
RISK-007: 업비트 서버 측 강제 연결 종료
<!-- 신규 추가: CRITICAL-001 관련 -->
설명: 업비트 서버가 19시간 후 연결 강제 종료 (opcode=8, b'\x83\xe8')
완화:

주기적 재연결 (12시간마다 의도적 재연결)
재연결 로직 강화 (무제한 또는 100회 시도)
종료 코드 파싱 및 대응
상태: 🔴 긴급 수정 필요 (Phase 0)


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
결정: 타임프레임별 별도 WebSocket 연결 + 별도 DB 파일
세부 사항:

메모리 합성: 33초봉, 57초봉은 1초봉 데이터를 메모리에서 합성 (DB 저장 안 함)
별도 수집: 10초봉, 1분봉, 10분봉은 각각 별도 WebSocket 연결로 직접 수집
DB 파일 분리:

ohlcv_short.sqlite: 0.5초봉, 1초봉, 3틱봉 (기존)
ohlcv_10s_1m.sqlite: 10초봉, 1분봉 (신규)
ohlcv_10m.sqlite: 10분봉 (신규)
이유:

메모리 합성(33초, 57초)은 DB 저장 불필요 → 전략에서만 사용
직접 수집(10초, 1분, 10분)은 정확도 향상 (합성 오차 제거)
DB 파일 분리로 동시 쓰기 성능 향상 및 충돌 방지
각 타임프레임의 독립적 에러 처리 가능
상태: ✅ 확정

<!-- 신규 추가: CRITICAL-001 관련 -->
DEC-009: 2026-01-26 - 주기적 WebSocket 재연결 주기 선정
결정: 9시간마다 의도적 WebSocket 재연결 수행
이유:

업비트 WebSocket 장시간 연결 시 강제 종료(약 19시간) 패턴 사전 회피
12시간 대비 충분한 안전 마진 확보
6시간 대비 불필요한 재연결 이벤트 감소로 로그·운영 안정성 향상
CRITICAL-001(장기 연결 후 재연결 실패) 리스크 완화 목적의 예방적 조치
정상 재연결 이벤트로 분류하여 장애 탐지 로직과 혼선 방지
상태: ✅ 확정

<!-- 신규 추가: CRITICAL-001 관련 -->
DEC-010: 2026-01-26 - WebSocket 재연결 최대 횟수 정책
결정: 재연결 횟수는 무제한 허용하되, 시간 기반 제한 정책 적용
이유:

24/7 무인 운영을 전제로 프로세스의 영구 실행 보장 필요
고정 횟수 제한(예: 100회)은 재연결 실패 시 수동 개입을 유발
재연결 폭주(reconnect storm) 방지를 위해 시간 창(window) 기준 제어가 더 적합
DEC-009(9시간 주기적 정상 재연결)과 결합 시 장애/정상 재연결 구분 명확
장기 네트워크 불안정 상황에서도 로그 폭주 및 리소스 고갈 방지

상태: ✅ 확정


📦 BACKLOG (향후 작업)
긴급 (즉시) 🚨

BL-CRITICAL: CRITICAL-001 수정 - WebSocket 재연결 로직 강화
BL-CRITICAL-2: 주기적 재연결 추가 (12시간마다)
BL-CRITICAL-3: 종료 코드 파싱 및 로깅
BL-CRITICAL-4: 24시간 연속 테스트

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
v1.2 - 2026-01-26 (긴급 업데이트) 🚨
<!-- 이번 긴급 업데이트 -->

CRITICAL-001 발견: WebSocket 19시간 후 재연결 실패 이슈 등록
Phase 0 추가: 긴급 수정 체크리스트 (최우선 작업)
RISK-007 추가: 업비트 서버 측 강제 연결 종료 리스크
Q-002, Q-003 추가: 재연접 정책 관련 미결정 사항
AC-001 업데이트: 24시간 무중단 운영 현재 불가 명시
Backlog 재정렬: 긴급 수정 사항 최우선 배치
IR-003, IR-004 업데이트: 재연결 관련 불변 규칙 강화
Known Issues 추가: 알려진 이슈 섹션 신설

v1.1 - 2026-01-26

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

운영 모니터링 (긴급 추가)
⚠️ 현재 19시간마다 수동 재시작 필요

로그 모니터링: tail -f logs/collector.log
재연결 실패 감지 시 즉시 재시작
CRITICAL-001 수정 전까지 주의 필요


마지막 업데이트: 2026-01-26 (v1.2 긴급)
다음 리뷰 예정: CRITICAL-001 수정 완료 후
긴급 조치: Phase 0 체크리스트 최우선 진행