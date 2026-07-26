# 아파트 통근·투자 스크리너

네이버 부동산 **아파트 매매** 매물을 모으고, 아래를 반영해 순위를 매깁니다.

1. **지하철역까지 도보 시간**
2. **강남역 지하철 출근 시간** (기본: 역별 소요표, 선택: [ODsay](https://www.odsay.com) API)
3. **SK하이닉스 이천 통근 셔틀** 정류장까지 도보 + 셔틀 탑승 시간

> 투자 권유가 아닙니다. 스크리닝 보조 도구입니다.

## 왜 이런 구조인가

- 하이닉스 **공식 셔틀 노선표는 사내앱/인트라넷**이라 외부에서 완전한 좌표·시간표를 받을 수 없습니다.
- 그래서 도구는  
  - 공개적으로 반복 언급되는 **거점 정류장 seed JSON**  
  - 공개 웹 **언급 힌트 수집** (`fetch-shuttle`)  
  - 사용자가 사내표로 정리한 **CSV 덮어쓰기**  
  를 합쳐 씁니다.

## 설치

```bash
cd apt_screener
python3 -m pip install -r requirements.txt
export PYTHONPATH=src
```

## 웹 UI (추천)

지도·랭킹·통근 점수 막대를 한 화면에서 봅니다.

```bash
bash scripts/run_web.sh
# 또는
export PYTHONPATH=src
python3 -m apt_screener web --port 8000
```

브라우저에서 `http://localhost:8000` 접속.  
기본은 데모 데이터이며, 상단 토글로 라이브(네이버) 수집을 시도할 수 있습니다.

## 빠른 데모 (CLI)

```bash
bash scripts/run_demo.sh
# 또는
python3 -m apt_screener screen --demo --offline
```

결과는 `output/screen_results.csv` / `.xlsx` 에 저장됩니다.

## 실제 네이버 매물 수집

`config.yaml` 의 `regions` 에 법정동 코드(`cortarNo`)를 넣고:

```bash
python3 -m apt_screener screen --top 20
```

- 네이버는 공식 Open API가 없어 웹이 쓰는 `new.land.naver.com` JSON을 호출합니다.
- 요청 간 `request_delay_sec` 간격을 두고, 과도한 호출은 피하세요.
- 일부 클라우드/해외 IP에서는 `new.land` / `m.land` 가 타임아웃될 수 있습니다. 그 경우 집/한국 IP에서 실행하세요.

## 하이닉스 셔틀 데이터

### 1) seed + 온라인 힌트

```bash
python3 -m apt_screener fetch-shuttle
```

공개 페이지에서 정류장 키워드 언급을 스캔해 seed에 `online_mention` 태그를 붙입니다.  
**새 좌표를 자동 생성하지는 않습니다.**

### 2) 사내 노선표 → CSV (권장)

`data/hynix_shuttle_user.example.csv` 형식으로 저장한 뒤:

```yaml
hynix_shuttle:
  user_csv: data/my_hynix_stops.csv
```

또는

```bash
python3 -m apt_screener fetch-shuttle --user-csv data/my_hynix_stops.csv
```

컬럼: `route_name,stop_name,lat,lon,ride_minutes_to_hynix,source`

## 강남 통근 정밀화 (선택)

[ODsay](https://www.odsay.com/devCenter/main.do) API 키를 `config.yaml` 의 `odsay_api_key` 또는 `--odsay-key` 로 넣으면, 단지→강남역 대중교통 실소요를 사용합니다.

## 점수 의미

| 항목 | 의미 |
|------|------|
| walk_to_subway | 지하철 도보 (짧을수록↑) |
| gangnam_commute | 강남 총 통근 (짧을수록↑) |
| hynix_shuttle_commute | 셔틀도보+탑승 (짧을수록↑) |
| price_value | 배치 내 평단가 상대 가치 |
| complex_quality | 세대수·연식 프록시 |

듀얼 통근(강남 지하철 + 하이닉스 셔틀)에 맞도록 기본 가중치는 통근 항목 비중이 큽니다.

## 프로젝트 구조

```
apt_screener/
  config.yaml
  data/hynix_shuttle_routes.json   # 셔틀 seed
  data/subway_stations.json        # 역·강남 소요 추정치
  data/sample_complexes.json       # 데모 매물
  src/apt_screener/                # 라이브러리 + CLI
  output/                          # 실행 결과
```
