"""dck — data-check-kit 점검 함수 모음 (pandas만 사용).

노트북 맨 위에서 한 번 불러 쓴다.

    import sys; sys.path.append("경로/data-check-kit/scripts")
    import dck
    flow = dck.Flow()

원칙
- 원자료 파일은 읽기만 한다. 고친 결과는 새 파일로 저장한다.
- 모든 판정은 계산한 숫자로 남긴다. 눈으로 보고 "일치"라고 쓰지 않는다.
- 표본을 바꾸는 연산(필터·중복 제거·머지) 뒤에는 반드시 flow.step()을 부른다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

MISSING_CODES = (-9, -99, -999, 9999, 99999, 999999)
QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)


# ---------------------------------------------------------------- 0. 읽기
def read_csv(path, **kw) -> pd.DataFrame:
    """인코딩을 utf-8 → utf-8-sig → cp949 순으로 시도한다. 코드 열은 dtype=str로 넘길 것."""
    last = None
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            df = pd.read_csv(path, encoding=enc, **kw)
            print(f"[read] {Path(path).name}  encoding={enc}  rows={len(df):,}  cols={df.shape[1]}")
            return df
        except UnicodeDecodeError as e:
            last = e
    raise last


def file_hash(path, n=12) -> str:
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return h[:n]


# ---------------------------------------------------------------- 1. 로딩 직후 점검
def profile(df: pd.DataFrame, name: str = "df", key=None) -> pd.DataFrame:
    """행·열·결측·고유값·중복 키를 한 번에 보고하고, 열별 표를 돌려준다."""
    print(f"== profile: {name} ==")
    print(f"rows={len(df):,}  cols={df.shape[1]}  완전중복행={df.duplicated().sum():,}")
    if key is not None:
        key_check(df, key, name)
    tab = pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "결측수": df.isna().sum(),
        "결측률%": (df.isna().mean() * 100).round(2),
        "고유값수": df.nunique(dropna=True),
        "예시": df.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else None),
    })
    flags = []
    for c in df.columns:
        f = []
        s = df[c]
        if any(w in str(c) for w in ("코드", "code", "Code", "ID", "id", "번호")) and pd.api.types.is_numeric_dtype(s):
            f.append("코드가 숫자로 읽힘(선행 0 소실 의심)")
        if pd.api.types.is_numeric_dtype(s) and s.isin(MISSING_CODES).any():
            f.append(f"결측 코드 의심값 {int(s.isin(MISSING_CODES).sum())}건")
        if s.dtype == object and s.astype(str).str.strip().ne(s.astype(str)).any():
            f.append("앞뒤 공백")
        if s.dtype == object and s.isin(["", "-", "없음", "NA", "N/A", "null"]).any():
            f.append("빈 문자열·대체 결측 표기")
        flags.append("; ".join(f))
    tab["경고"] = flags
    return tab


def key_check(df: pd.DataFrame, key, name: str = "df") -> dict:
    """키 유일성: 결측키 수, 중복키 수(관측치 기준), 중복 키 예시."""
    key = [key] if isinstance(key, str) else list(key)
    na = df[key].isna().any(axis=1).sum()
    dup_mask = df.duplicated(key, keep=False)
    out = {"name": name, "key": key, "rows": len(df), "결측키": int(na),
           "중복키_관측치": int(dup_mask.sum()), "고유키": int(df[key].drop_duplicates().shape[0])}
    status = "유일" if out["중복키_관측치"] == 0 and na == 0 else "유일하지 않음"
    print(f"[key] {name} {key}: {status}  결측키={na:,}  중복키 관측치={out['중복키_관측치']:,}")
    if out["중복키_관측치"]:
        others = [c for c in df.columns if c not in key][:3]
        print(df.loc[dup_mask, key + others].sort_values(key).head(10).to_string())
    return out


# ---------------------------------------------------------------- 2. 코드체계 점검
def code_name_map(df: pd.DataFrame, code: str, name: str) -> pd.DataFrame:
    """코드↔명칭이 1:1인지. 한 코드에 여러 명칭, 한 명칭에 여러 코드를 찾아낸다."""
    pairs = df[[code, name]].drop_duplicates()
    c2n = pairs.groupby(code)[name].nunique()
    n2c = pairs.groupby(name)[code].nunique()
    bad_c = c2n[c2n > 1]
    bad_n = n2c[n2c > 1]
    print(f"[code] {code}↔{name}: 코드 {len(c2n):,}개, 명칭 {len(n2c):,}개 | "
          f"한 코드-여러 명칭 {len(bad_c)}건, 한 명칭-여러 코드 {len(bad_n)}건")
    rows = pairs[pairs[code].isin(bad_c.index) | pairs[name].isin(bad_n.index)]
    return rows.sort_values([name, code])


# ---------------------------------------------------------------- 3. 표본 흐름
class Flow:
    """표본을 바꾸는 모든 단계를 기록하고 마지막에 흐름표로 만든다."""

    def __init__(self):
        self.rows = []

    def start(self, df: pd.DataFrame, label: str, source: str = ""):
        self.rows.append({"단계": label, "전": None, "후": len(df), "변화": None, "사유": source})
        print(f"[flow] 시작 {label}: {len(df):,}행")
        return df

    def step(self, before: pd.DataFrame, after: pd.DataFrame, label: str, reason: str = "",
             expect: int | None = None):
        b, a = len(before), len(after)
        self.rows.append({"단계": label, "전": b, "후": a, "변화": a - b, "사유": reason})
        msg = f"[flow] {label}: {b:,} → {a:,} ({a - b:+,})"
        if expect is not None:
            msg += "  기대값 일치" if a == expect else f"  [!] 기대값 {expect:,}과 다름"
        print(msg)
        return after

    def table(self) -> pd.DataFrame:
        t = pd.DataFrame(self.rows)
        for c in ("전", "후", "변화"):
            t[c] = t[c].astype("Int64")
        return t


# ---------------------------------------------------------------- 4. 결합 회계
def merge_audit(left: pd.DataFrame, right: pd.DataFrame, on, how: str = "left",
                validate: str | None = None, names=("left", "right"), show: int = 15):
    """머지 전에 관계(1:1·1:N·N:1·N:M)를 세고, 머지 후 행 수 회계식과 미매칭 목록을 낸다.

    돌려주는 값: (merged, report dict, 미매칭 표)
    validate는 pandas 규칙("one_to_one", "many_to_one" 등). 어기면 여기서 멈춘다.
    """
    on = [on] if isinstance(on, str) else list(on)
    ln, rn = names
    lk = left.groupby(on, dropna=False).size().rename("n_l")
    rk = right.groupby(on, dropna=False).size().rename("n_r")
    both = pd.concat([lk, rk], axis=1, join="inner")
    rel = pd.Series({
        "1:1": int(((both.n_l == 1) & (both.n_r == 1)).sum()),
        "N:1": int(((both.n_l > 1) & (both.n_r == 1)).sum()),
        "1:N": int(((both.n_l == 1) & (both.n_r > 1)).sum()),
        "N:M": int(((both.n_l > 1) & (both.n_r > 1)).sum()),
    })
    expected = int((both.n_l * both.n_r).sum())
    if how in ("left", "outer"):
        expected += int(lk[~lk.index.isin(both.index)].sum())
    if how in ("right", "outer"):
        expected += int(rk[~rk.index.isin(both.index)].sum())

    merged = left.merge(right, on=on, how=how, validate=validate, indicator=True)
    cnt = merged["_merge"].value_counts()
    rep = {
        f"{ln}_rows": len(left), f"{rn}_rows": len(right), "merged_rows": len(merged),
        "expected_rows": expected, "회계식": "일치" if expected == len(merged) else "불일치",
        "matched_rows": int(cnt.get("both", 0)), f"{ln}_only_rows": int(cnt.get("left_only", 0)),
        f"{rn}_only_rows": int(cnt.get("right_only", 0)),
        # 왼쪽 관측치 가운데 오른쪽 키를 하나라도 찾은 비율
        f"{ln}_매칭률%": round(100 * left.merge(right[on].drop_duplicates(), on=on).shape[0] / max(len(left), 1), 2),
        # 결합 후 행 수 ÷ 왼쪽 행 수. 1을 넘으면 오른쪽 키 중복 때문에 왼쪽 행이 복제된 것
        "키_중복_증폭": round(len(merged) / max(len(left), 1), 4) if how == "left" else None,
        **{f"관계_{k}": v for k, v in rel.items()},
    }
    print(f"== merge_audit {ln} LEFT JOIN {rn} on {on} (how={how}) ==")
    for k, v in rep.items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    if rel["N:M"]:
        print("  [!] N:M 키가 있다. 결합 규칙에서 금지했다면 여기서 멈춘다.")

    lo = left.merge(right[on].drop_duplicates(), on=on, how="left", indicator=True)
    lo = lo.loc[lo._merge == "left_only", on].drop_duplicates().assign(쪽=f"{ln}에만")
    ro = right.merge(left[on].drop_duplicates(), on=on, how="left", indicator=True)
    ro = ro.loc[ro._merge == "left_only", on].drop_duplicates().assign(쪽=f"{rn}에만")
    unmatched = pd.concat([lo, ro], ignore_index=True)
    if len(unmatched):
        print(f"  미매칭 키 {len(unmatched)}개 (앞 {min(show, len(unmatched))}개)")
        print(unmatched.head(show).to_string(index=False))
    return merged, rep, unmatched


# ---------------------------------------------------------------- 5. 분포·절단
def dist(df: pd.DataFrame, cols, by=None) -> pd.DataFrame:
    """분위수·0 비율·결측률·최댓값 집중도. by가 있으면 집단별로."""
    cols = [cols] if isinstance(cols, str) else list(cols)
    g = [(None, df)] if by is None else list(df.groupby(by))
    out = []
    for k, d in g:
        for c in cols:
            s = pd.to_numeric(d[c], errors="coerce")
            v = s.dropna()
            row = {"집단": k, "변수": c, "N": int(v.size), "결측률%": round(100 * s.isna().mean(), 2),
                   "평균": v.mean(), "표준편차": v.std(), "min": v.min()}
            row.update({f"p{int(q * 100)}": v.quantile(q) for q in QUANTILES})
            row["max"] = v.max()
            row["0비율%"] = round(100 * (v == 0).mean(), 2) if v.size else None
            row["최댓값_동일건수"] = int((v == v.max()).sum()) if v.size else 0
            out.append(row)
    t = pd.DataFrame(out)
    return t if by is not None else t.drop(columns="집단")


def truncation_flags(t: pd.DataFrame) -> pd.DataFrame:
    """dist() 결과에 절단 의심 신호를 붙인다(판정이 아니라 '들여다볼 곳' 표시)."""
    f = []
    for _, r in t.iterrows():
        x = []
        if r["N"] and r["최댓값_동일건수"] / r["N"] > 0.01 and r["최댓값_동일건수"] >= 5:
            x.append("최댓값에 1% 넘게 몰림(상한 코딩?)")
        if pd.notna(r["p99"]) and r["max"] and r["p99"] >= 0.98 * r["max"]:
            x.append("p99가 최댓값에 바짝 붙음")
        if r.get("0비율%") and r["0비율%"] > 30:
            x.append("0이 30% 넘음(진짜 0인지 미응답인지)")
        f.append("; ".join(x))
    return t.assign(점검신호=f)


# ---------------------------------------------------------------- 6. 집계 대조
def total_check(df: pd.DataFrame, col: str, official: float, label: str = "", tol: float = 0.0):
    """합계를 공표값과 대조한다. tol은 허용 상대오차(0.001 = 0.1%)."""
    s = pd.to_numeric(df[col], errors="coerce").sum()
    gap = (s - official) / official if official else float("nan")
    ok = abs(gap) <= tol
    print(f"[total] {label or col}: 계산 {s:,.0f} vs 공표 {official:,.0f}  차이 {gap:+.4%}  "
          f"{'일치' if ok else '[!] 불일치'}")
    return ok
