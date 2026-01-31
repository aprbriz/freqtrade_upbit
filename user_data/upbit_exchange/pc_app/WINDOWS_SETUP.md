# Windows PC 앱 설치 및 실행 가이드

## 📋 시스템 요구사항

- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.8 이상
- **메모리**: 4GB 이상 (권장 8GB)
- **모니터**: 듀얼 모니터 권장 (단일 모니터 폴백 지원)

---

## 🚀 빠른 시작

### 1단계: Python 설치 확인

PowerShell 또는 CMD에서:

```powershell
python --version
```

Python 3.8 이상이 설치되어 있어야 합니다. 없다면 https://www.python.org/downloads/ 에서 다운로드.

### 2단계: 저장소 클론

```powershell
# Git이 있는 경우
git clone https://github.com/aprbriz/freqtrade_upbit.git
cd freqtrade_upbit\user_data\upbit_exchange\pc_app

# 또는 ZIP 다운로드 후 압축 해제
```

### 3단계: 의존성 설치

```powershell
pip install -r requirements.txt
```

**문제 발생 시:**

```powershell
# PyQt5 설치 실패 시 PySide6 시도
pip uninstall PyQt5
pip install PySide6
```

### 4단계: 실행

```powershell
python pc_app_main.py
```

---

## 📁 DB 파일 동기화 (선택)

PC 앱은 Oracle Cloud의 DB를 읽기 전용으로 조회합니다.

### 방법 1: SCP (권장)

```powershell
# PowerShell에서
scp opc@your-server:/home/opc/python/ft_userdata_upbit/user_data/upbit_exchange/*.sqlite .
```

### 방법 2: WinSCP / FileZilla

GUI 도구로 다음 파일들을 다운로드:
- `ohlcv_short.sqlite`
- `ohlcv_10s_1m.sqlite` (Phase 2 완료 후)
- `ohlcv_10m.sqlite` (Phase 2 완료 후)

### PC 앱에서 DB 경로 설정

`config.json` 파일 생성 (첫 실행 시 자동 생성):

```json
{
  "db_path": "C:\\path\\to\\your\\ohlcv_short.sqlite",
  "ws_url": "wss://api.upbit.com/websocket/v1",
  "symbols": ["KRW-XRP", "KRW-BTC", "KRW-ETH"]
}
```

---

## 🖥️ 듀얼 모니터 설정

### 자동 감지

PC 앱은 듀얼 모니터를 자동 감지하여 배치합니다:

- **모니터 1**: XRP + BTC 차트
- **모니터 2**: ETH 차트 + 진단 패널

### 단일 모니터

단일 모니터 환경에서는 창이 상하 분할로 자동 배치됩니다.

### 수동 배치

창 위치는 `config.json`에 저장됩니다. 원하는 위치로 이동 후 앱을 종료하면 다음 실행 시 동일한 위치에 표시됩니다.

---

## 🔧 설정 파일 위치

- **실행 디렉토리**: `config.json` (우선)
- **대안**: `%APPDATA%\UpbitRealTimeChart\config.json`

### 로그 위치

`%LOCALAPPDATA%\UpbitRealTimeChart\logs\app.log`

예: `C:\Users\YourName\AppData\Local\UpbitRealTimeChart\logs\app.log`

---

## ⚡ 사용 방법

### 기본 조작

1. **타임프레임 선택**: 상단 드롭다운에서 1분/5분/15분/1시간/일봉 선택
2. **심볼 선택**: XRP/BTC/ETH 전환
3. **LIVE 모드**: 우측 진단 패널에서 "LIVE 시작" 버튼 클릭
4. **DB 전환**: "DB로 전환(안정)" 버튼으로 평시 모드 복귀

### 상태 칩

- **MODE**: `DB_ONLY` / `LIVE_ACTIVE` / `LIVE_WARMUP` / `LIVE_COOLDOWN`
- **WS**: `OK` / `RECONNECTING` / `DEGRADED`
- **BURST**: `NORMAL` / `CANDIDATE` / `ACTIVE`

### 진단 패널

3개 심볼의 통합 상태를 실시간 표시:
- 연결 상태
- 마지막 틱 시각
- BURST 지표
- 최근 갭 이벤트

---

## 🐛 문제 해결

### PyQt5 설치 실패

```powershell
# Microsoft Visual C++ 재배포 패키지 필요
# https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist

# 또는 PySide6 사용
pip uninstall PyQt5
pip install PySide6
```

### "config.json을 찾을 수 없음" 경고

정상입니다. 첫 실행 시 자동 생성됩니다.

### 차트가 표시되지 않음

1. DB 파일 경로 확인: `config.json`의 `db_path`
2. DB 파일이 존재하는지 확인
3. 로그 확인: `%LOCALAPPDATA%\UpbitRealTimeChart\logs\app.log`

### WS 연결 실패

1. 인터넷 연결 확인
2. 방화벽 확인 (WSS 443 포트 허용)
3. Upbit 레이트리밋 확인 (연결 5회/초 제한)

---

## 📊 성능 팁

### 메모리 사용량 줄이기

`config.json`에서 오버레이 범위 조정:

```json
{
  "overlay_max_count": 500,
  "overlay_max_duration_s": 300
}
```

### 드랍 우선순위 조정

폭주 시 UI 프리징 방지를 위해 중간 프레임을 자동으로 건너뜁니다. 하단 티커에 안내 메시지가 표시됩니다.

---

## 🔄 업데이트

```powershell
cd freqtrade_upbit
git pull origin main
cd user_data\upbit_exchange\pc_app
python pc_app_main.py
```

---

## 📚 추가 문서

- `README.md`: PC 앱 개요
- `DESIGN_DUAL_MONITOR.md`: 듀얼 모니터 UI 상세 설계
- `WEBSOCKET_OPTIMIZATION.md`: WebSocket 최적화 전략
- `../docs/ssot/SSOT_*.md`: 전체 프로젝트 SSOT

---

## 💡 참고

- **PC 앱은 읽기 전용입니다**: DB 수정하지 않음
- **Cloud Collector가 정본입니다**: PC 앱은 조회/모니터링 전용
- **LIVE 모드는 일시적입니다**: BURST 종료 후 자동으로 DB 모드 복귀
- **24/7 실행 비권장**: PC 앱은 트레이딩 시간 동안만 실행 권장

---

**문제가 계속되면 이슈 등록:** https://github.com/aprbriz/freqtrade_upbit/issues
