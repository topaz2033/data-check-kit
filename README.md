# data-check-kit — 데이터 검증 킷

다운로드한 원자료를 클리닝·결합할 때, 단계마다 **무엇을 숫자로 확인해야 하는지** 정해 둔 Claude 스킬입니다.
행·키·결측·코드체계·결합 회계·분포를 점검하고, 마지막에 표본 흐름표와 독립 감사 결과를 남깁니다.

```
원자료 ─▶ 1 로딩 점검 ─▶ 2 코드체계 ─▶ 3 결합 규칙 ─▶ 4 클리닝(단계 기록) ─▶ 5 결합 회계 ─▶ 6 분포·대조 ─▶ 7 의미 점검 ─▶ 8 흐름표 + 독립 감사
```

## 들어 있는 것

| 경로 | 내용 |
|---|---|
| `skills/data-check-kit/SKILL.md` | 작업 순서와 절대 규칙 |
| `skills/data-check-kit/scripts/dck.py` | 점검 함수(pandas만 사용) |
| `skills/data-check-kit/references/` | 결합 규칙 양식, 의미 점검 질문 |
| `agents/data-auditor.md` | 코드를 짠 쪽과 분리된 감사 에이전트 |
| `examples/` | 공공데이터 예제 노트북 |
| `tests/test_dck.py` | 합성 자료로 함정을 잡는지 확인하는 시험 |

## 설치

### Claude Code (권장 — 감사 에이전트까지 쓸 수 있음)

macOS / Linux
```bash
git clone https://github.com/topaz2033/data-check-kit.git
cp -r data-check-kit/skills/data-check-kit ~/.claude/skills/
mkdir -p ~/.claude/agents && cp data-check-kit/agents/data-auditor.md ~/.claude/agents/
```

Windows (PowerShell)
```powershell
git clone https://github.com/topaz2033/data-check-kit.git
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse data-check-kit\skills\data-check-kit "$HOME\.claude\skills\"
New-Item -ItemType Directory -Force "$HOME\.claude\agents" | Out-Null
Copy-Item data-check-kit\agents\data-auditor.md "$HOME\.claude\agents\"
```

Claude Code를 다시 열고 `/data-check-kit`을 입력하거나 "이 CSV 클리닝하고 검증해줘"라고 요청하면 됩니다.

### claude.ai (웹·데스크톱 앱)

`skills/data-check-kit` 폴더를 zip으로 묶어 **설정 → 기능 → 스킬**에서 업로드합니다.
이 경우 감사 에이전트는 따로 돌지 않으므로, 8단계 감사는 새 대화에서 `agents/data-auditor.md` 내용을 붙여 요청하세요.

### 함수만 쓰기 (Colab 등)

`dck.py` 한 파일만 작업 폴더에 복사해 `import dck`로 씁니다.

## 사용 예

```python
import dck
flow = dck.Flow()

raw = dck.read_csv("data/raw/시장.csv", dtype={"시군구코드": str})
dck.profile(raw, "시장", key=["시도", "시군구", "시장명"])
flow.start(raw, "원자료", "data.go.kr, 2026-10-19 내려받음")

df = flow.step(raw, raw.drop_duplicates(), "완전 중복 제거", "같은 행 반복")

merged, rep, unmatched = dck.merge_audit(df, pop, on=["시도", "시군구"],
                                         validate="many_to_one", names=("시장", "인구"))
flow.table()
```

## 시험

```bash
python tests/test_dck.py
```

## 출처

이 킷은 국문 실증논문 운영체계(kci-paper)의 데이터 검증 단계(파일 인벤토리·키 진단·결합 계약·결합 회계·분포 진단·의미 검증)를 떼어내 일반 사용자용으로 정리한 것입니다.

## 라이선스

MIT
