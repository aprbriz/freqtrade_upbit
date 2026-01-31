# PC Chart App (Phase 2.5+)

## 목적
Cloud Collector가 수집한 SQLite DB를 읽어 실시간 차트를 PC에서 표시

## 설계 원칙 (phase2 작업지시서.md.md 참조)

### 상태 머신 (4-state)
1. **초기화(INIT)**: DB 연결, 설정 로드
2. **실행(RUNNING)**: 차트 표시, 실시간 업데이트
3. **정지(PAUSED)**: 일시 정지 (DB 연결 유지)
4. **종료(STOPPED)**: 리소스 정리, 프로그램 종료

### 주요 모듈 (계획)

#### state_machine.py
- 앱 상태 관리 및 전환
- 사용자 액션 처리

#### live_engine.py
- DB 읽기 (최신 1초봉 주기적 폴링)
- common.timeframe_aggregator 사용하여 상위봉 생성
- 차트 데이터 업데이트

#### db_reader.py
- SQLite3 읽기 전용 연결
- 캐싱 및 증분 읽기

#### ui/
- 차트 위젯 (matplotlib/pyqtgraph 등)
- 컨트롤 패널 (시작/정지/종료 버튼)
- 상태 표시

## 개발 일정
- Phase 2.5+ 구현 예정
- common/ 모듈 재사용으로 일관성 보장

## 참고
- 상세 스펙: `/home/opc/python/ft_userdata_upbit/user_data/upbit_exchange_memo/phase2 작업시지서.md.md`
