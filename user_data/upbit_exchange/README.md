# Upbit Exchange OHLCV Collector

## 프로젝트 구조

```
upbit_exchange/
├── common/                      # Cloud/PC 앱 공통 모듈
│   ├── __init__.py
│   ├── constants.py            # 공통 상수 및 기본값
│   ├── dedup_cache.py          # 중복 제거 캐시 (POL-006)
│   ├── reconnect_limiter.py    # 전역 재연결 레이트 리미터
│   ├── tick_aggregator.py      # Tick 기반 aggregator
│   └── timeframe_aggregator.py # Timeframe 기반 aggregator
│
├── cloud/                       # Cloud 전용 WebSocket Collector
│   ├── __init__.py
│   ├── collector.py            # 메인 Collector (WS 연결, 재연결, HTTP)
│   ├── ohlcv_writer.py         # SQLite3 Writer (WAL, UPSERT, batch)
│   └── multi_aggregator.py     # Multi/Derived aggregator 관리
│
├── pc_app/                      # PC 차트 앱 전용 (Phase 2.5+)
│   ├── __init__.py
│   ├── state_machine.py        # 앱 상태 관리 (초기화/실행/정지/종료)
│   ├── live_engine.py          # 실시간 데이터 수신 & 차트 업데이트
│   ├── db_reader.py            # SQLite DB 읽기 및 캐싱
│   └── ui/                     # UI 컴포넌트 (차트, 컨트롤)
│
├── docs/                        # 문서
│   └── ssot/                   # SSOT 및 history
│
├── collector.py                 # 래퍼 (cloud/collector.py 실행)
├── config_upbit_exchange.yml   # 설정 파일
├── requirements_collector.txt  # Python 의존성
└── run_collector.sh            # 실행 스크립트
```

## 아키텍처 원칙 (DEC-014)

### common/ - 공통 모듈
- **목적**: Cloud와 PC 앱이 동일한 정책/로직을 공유
- **포함**: Aggregator, 중복 제거, 재연결 정책, 상수
- **규칙**: 외부 의존성 최소화, 순수 로직만 포함

### cloud/ - Cloud Collector
- **목적**: 24/7 WebSocket 수신 및 DB 저장
- **특징**: 재연결, graceful shutdown, HTTP stats/health
- **의존성**: common 모듈 사용

### pc_app/ - PC 차트 앱
- **목적**: 로컬 DB 읽기 + 실시간 차트 표시
- **특징**: 상태 머신, UI, 사용자 인터랙션
- **의존성**: common 모듈 사용 (aggregator 로직 재사용)

## 실행 방법

### Cloud Collector
```bash
# 기본 실행 (config_upbit_exchange.yml 사용)
python collector.py

# CLI 옵션으로 실행
python collector.py --pairs KRW-BTC,KRW-ETH --http-port 8080
```

### PC 차트 앱 (미구현)
```bash
# Phase 2.5+ 구현 예정
python -m pc_app.main
```

## 개발 현황

- ✅ **Phase 0/1**: 기본 구조, 단일 Collector 프로토타입
- ✅ **Phase 2 v2.0**: Multi-collector, 재연결, graceful shutdown, HTTP
- ✅ **DEC-014**: common/cloud/pc_app 디렉토리 분리 (2026-01-28)
- 🔄 **Phase 2.5**: PC 차트 앱 개발 진행 예정

## SSOT 문서

자세한 설계/정책/결정사항은 `docs/ssot/SSOT_freqtrade_upbit_exchange_realtime_ohlcv_collector_claudev.md` 참조
