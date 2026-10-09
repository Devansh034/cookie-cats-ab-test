"""
Cookie Cats A/B test: does moving the first gate from level 30 to level 40
change player retention?

Run from Terminal:
    cd ~/Downloads
    python3 cookie_cats_ab_test.py
or give the CSV path:
    python3 cookie_cats_ab_test.py /path/to/cookie_cats.csv

Needs:  pip3 install pandas numpy matplotlib
Output: a folder called ab_output with charts (PNG) and results.txt
"""
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path("ab_output")
OUT.mkdir(exist_ok=True)
LINES = []
BLUE, ORANGE = "#4C78A8", "#F58518"


def say(text=""):
    print(text)
    LINES.append(str(text))


def find_csv():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser()
    home = Path.home() / "Downloads"
    for pattern in ("cookie_cats*.csv", "*ookie*ats*.csv"):
        m = sorted(home.glob(pattern)) + sorted(Path(".").glob(pattern))
        if m:
            return m[0]
    sys.exit("Could not find the Cookie Cats CSV. Pass its path: python3 cookie_cats_ab_test.py /path/to/cookie_cats.csv")


def z_test(x1, n1, x2, n2):
    """Two-proportion z-test. Returns difference (p2 - p1) and two-sided p-value."""
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return p2 - p1, p_value


path = find_csv()
df = pd.read_csv(path)
df.columns = df.columns.str.strip()
say(f"File: {path}")
say(f"Rows: {len(df)}   Columns: {list(df.columns)}")

# ---- Cleaning
say("\n--- DATA CHECKS ---")
say(f"Duplicate user IDs: {df['userid'].duplicated().sum()}")
say(f"Missing values: {int(df.isna().sum().sum())}")
for c in ("retention_1", "retention_7"):
    df[c] = df[c].astype(str).str.lower().isin(["true", "1"])
say("Players per version:")
say(df["version"].value_counts().sort_index().to_string())

# ---- Outlier check on game rounds
say("\n--- GAME ROUNDS ---")
say(f"Median rounds: {df['sum_gamerounds'].median():.0f}   Mean: {df['sum_gamerounds'].mean():.1f}   Max: {df['sum_gamerounds'].max()}")
zero = int((df["sum_gamerounds"] == 0).sum())
say(f"Players with 0 rounds (installed, never played): {zero} ({zero / len(df) * 100:.1f}%)")
cap = df["sum_gamerounds"].quantile(0.999)
clean = df[df["sum_gamerounds"] <= cap]
say(f"Removed {len(df) - len(clean)} extreme outliers (above the 99.9th percentile, {cap:.0f} rounds) for the rounds comparison only")
say("Median rounds by version:")
say(clean.groupby("version")["sum_gamerounds"].median().to_string())

# ---- Retention by version
say("\n--- RETENTION BY VERSION ---")
versions = sorted(df["version"].unique())
if len(versions) != 2:
    sys.exit(f"Expected 2 versions, found {versions}")
a, b = versions  # gate_30 (control), gate_40 (test)
res = {}
for metric, label in (("retention_1", "Day-1 retention"), ("retention_7", "Day-7 retention")):
    ga, gb = df[df["version"] == a], df[df["version"] == b]
    xa, na, xb, nb = int(ga[metric].sum()), len(ga), int(gb[metric].sum()), len(gb)
    diff, p = z_test(xa, na, xb, nb)
    # bootstrap 95% interval for the difference
    rng = np.random.default_rng(42)
    boots = (rng.binomial(nb, xb / nb, 5000) / nb) - (rng.binomial(na, xa / na, 5000) / na)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    res[metric] = (xa / na * 100, xb / nb * 100)
    say(f"\n{label}")
    say(f"  {a}: {xa / na * 100:.2f}%  ({xa:,} of {na:,})")
    say(f"  {b}: {xb / nb * 100:.2f}%  ({xb:,} of {nb:,})")
    say(f"  Difference ({b} minus {a}): {diff * 100:+.2f} percentage points")
    say(f"  95% interval for the difference: {lo * 100:+.2f} to {hi * 100:+.2f} points")
    say(f"  p-value: {p:.4f}  ->  {'statistically significant (p < 0.05)' if p < 0.05 else 'NOT statistically significant (p >= 0.05)'}")

# ---- Retention chart
fig, ax = plt.subplots(figsize=(6.5, 4.2))
x = np.arange(2)
w = 0.36
va = [res["retention_1"][0], res["retention_7"][0]]
vb = [res["retention_1"][1], res["retention_7"][1]]
b1 = ax.bar(x - w / 2, va, w, label=a, color=BLUE)
b2 = ax.bar(x + w / 2, vb, w, label=b, color=ORANGE)
for bars in (b1, b2):
    for r in bars:
        ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.6, f"{r.get_height():.1f}%", ha="center", fontsize=9)
ax.set_xticks(x)
ax.set_xticklabels(["Day-1 retention", "Day-7 retention"])
ax.set_ylabel("Players who came back (%)")
ax.set_ylim(0, max(va + vb) * 1.25)
ax.set_title("Retention by gate position", loc="left", fontsize=12)
ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
fig.savefig(OUT / "retention_by_version.png", dpi=150)
plt.close(fig)

# ---- Game rounds chart
fig, ax = plt.subplots(figsize=(6.5, 4.2))
bins = np.arange(0, 201, 10)
for ver, col in ((a, BLUE), (b, ORANGE)):
    ax.hist(clean.loc[clean["version"] == ver, "sum_gamerounds"].clip(upper=200), bins=bins,
            alpha=0.6, label=ver, color=col, density=True)
ax.set_xlabel("Game rounds played in first 14 days (capped at 200)")
ax.set_ylabel("Share of players")
ax.set_title("Game rounds by gate position", loc="left", fontsize=12)
ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
fig.savefig(OUT / "rounds_by_version.png", dpi=150)
plt.close(fig)

# ---- Day-7 retention by activity level
say("\n--- WHO COMES BACK? ---")
df["activity"] = pd.cut(df["sum_gamerounds"], bins=[-1, 0, 10, 50, 100, 10**9],
                        labels=["0 rounds", "1-10", "11-50", "51-100", "100+"])
act = df.groupby("activity", observed=True)["retention_7"].agg(["mean", "count"])
act["mean"] = (act["mean"] * 100).round(1)
act.columns = ["day7_retention_pct", "players"]
say(act.to_string())

(OUT / "results.txt").write_text("\n".join(LINES), encoding="utf-8")
say(f"\nDone. Charts and results.txt are in the folder: {OUT.resolve()}")
