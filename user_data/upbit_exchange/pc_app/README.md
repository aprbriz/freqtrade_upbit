# PC Chart App (Phase 2.5+)

## 목적
Cloud Collector가 수집한 SQLite DB를 읽어 실시간 차트를 PC에서 표시

## 🖥️ 듀얼 모니터 기본 전제 (2026-01-28 업데이트)

### 레이아웃
- **모니터 1**: XRP + BTC 듀얼 차트 (좌우 50:50)
- **모니터 2**: ETH 차트 (좌 60%) + 통합 진단 패널 (우 40%)
- **단일 프로세스**: 2개 독립 창 관리
- **자동 폴백**: 단일 모니터 환경 시 탭/스택 모드

### 주요 특징
- 3개 심볼 동시 모니터링 (XRP, BTC, ETH)
- 폭주 시 즉시 대응 가능
- 통합 진단 패널 (전체 시스템 상태)
- 창 간 데이터 동기화 (context_id 기반)

## 설계 원칙 (phase2 작업지시서.md.md 참조)

### 상태 머신 (4-state)
1. **초기화(INIT)**: DB 연결, 설정 로드
2. **실행(RUNNING)**: 차트 표시, 실시간 업데이트
3. **정지(PAUSED)**: 일시 정지 (DB 연결 유지)
4. **종료(STOPPED)**: 리소스 정리, 프로그램 종료

### 주요 모듈 (구현)

#### engine.py (MainEngine)
- DB 읽기 (SQLite 읽기 전용)
- WS Manager (Upbit 3개 심볼 구독)
- BURST Detector (심볼별 독립)
- Overlay Manager (심볼별 메모리)
- State Machine (심볼별 + 전역)

#### ui.py (Window1/Window2 + ChartPanel)
- XRP/BTC 듀얼 차트 (좌우 50%)
- ETH 차트 + 진단 패널 (우측)
- 하단 티커 (시스템 상태)
- 캔들/거래량 렌더링 및 상태 칩

#### pc_app_main.py (엔트리포인트)
- 듀얼 모니터 배치/폴백
- 주기적 UI 업데이트 (20Hz)
- 종료 시 설정 저장

## 개발 일정
- Phase 2.5+ 진행 중
- common/ 모듈 재사용으로 일관성 보장

## 실행
```bash
python pc_app/pc_app_main.py
```

## 상세 문서
- **듀얼 모니터 설계**: `DESIGN_DUAL_MONITOR.md`
- **변경 요약**: `DUAL_MONITOR_SUMMARY.md`
- **전체 스펙**: `/home/opc/python/ft_userdata_upbit/user_data/upbit_exchange_memo/phase2 작업시지서.md.md`
