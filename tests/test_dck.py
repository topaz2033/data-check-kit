"""합성 자료로 dck 함수가 함정을 잡는지 확인한다. 실행: python tests/test_dck.py"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "data-check-kit" / "scripts"))
import dck

# 시장 자료: 같은 시장 중복 1건, '중구'가 두 시도에, 점포수 결측코드
mkt = pd.DataFrame({
    "시장명": ["A시장", "A시장", "B시장", "C시장", "D시장", "E시장"],
    "시도": ["서울특별시", "서울특별시", "부산광역시", "경기도", "경기도", "대구광역시"],
    "시군구": ["중구", "중구", "중구", "수원시", "수원시", "군위군"],
    "점포수": [120, 120, 80, -9, 45, 30],
    "시군구코드": [11140, 11140, 26110, 41110, 41110, 47720],  # 군위군 옛 코드
})
# 인구 자료: 시와 구가 함께, 출장소 0
pop = pd.DataFrame({
    "시도": ["서울특별시", "부산광역시", "경기도", "경기도", "경기도", "대구광역시", "경기도"],
    "시군구": ["중구", "중구", "수원시", "장안구", "권선구", "군위군", "송탄출장소"],
    "인구": [117558, 36306, 1185770, 269984, 360286, 22622, 0],
})

flow = dck.Flow()
t = dck.profile(mkt, "시장", key=["시장명", "시도", "시군구"])
assert "선행 0" in t.loc["시군구코드", "경고"]
assert "결측 코드" in t.loc["점포수", "경고"]

k = dck.key_check(pop, "시군구", "인구(시군구만)")
assert k["중복키_관측치"] == 2                      # 중구 두 개
assert dck.key_check(pop, ["시도", "시군구"], "인구")["중복키_관측치"] == 0

flow.start(mkt, "원자료")
m1 = flow.step(mkt, mkt.drop_duplicates(), "완전 중복 제거", "같은 행 2번", expect=5)
assert len(m1) == 5

# 이름만으로 머지하면 N:M 발생
_, rep, _ = dck.merge_audit(m1, pop, on="시군구", names=("시장", "인구"))
assert rep["관계_N:M"] == 1 and rep["회계식"] == "일치"
assert rep["키_중복_증폭"] > 1

# 올바른 키
pop2 = pop[pop["인구"] > 0]
mg, rep2, um = dck.merge_audit(m1, pop2, on=["시도", "시군구"], validate="many_to_one",
                                names=("시장", "인구"))
assert rep2["관계_N:M"] == 0 and rep2["merged_rows"] == 5
assert set(um.loc[um.쪽 == "인구에만", "시군구"]) == {"장안구", "권선구"}   # 시·구 이중 단위가 드러남
# left join이어도 오른쪽 미매칭 행 수는 원자료 기준으로 센다(left join 결과에는 오른쪽에만 있는 행이 없다)
assert rep2["인구_only_rows"] == 2 and rep2["시장_only_rows"] == 0
assert rep2["인구_매칭률%"] == round(100 * 4 / 6, 2)

# 기대 행 수와 다르면 멈춘다
try:
    flow.step(m1, m1.head(3), "기대값 시험", expect=5)
    raise SystemExit("expect 불일치를 통과시킴")
except ValueError:
    pass

try:
    m1.merge(pop, on="시군구", validate="many_to_one")
    raise SystemExit("validate가 막지 못함")
except pd.errors.MergeError:
    pass

d = dck.truncation_flags(dck.dist(m1, "점포수"))
assert d.loc[0, "min"] == -9
print(flow.table().to_string())
assert dck.total_check(pop2, "인구", 1992526)
print("\nALL TESTS PASSED")
