#!/usr/bin/env python3
"""
ARIA dashboard refresh engine.
Reads 8 raw Supermetrics query outputs (raw_*.txt, saved verbatim by the
refresh session) and rewrites the DATA blob inside ../index.html with fresh
numbers. The design/layout/insa-logic in index.html is untouched — only the
`const DATA={...};` block is replaced, so every widget + ARIA insight
recomputes from the new numbers on load.

Run:  python3 build_dashboard.py
See REFRESH.md for the exact queries that produce the raw_*.txt files.
"""
import json, csv, io, re, os, calendar, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "..", "index.html")
MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def parse(fn):
    """Parse a Supermetrics compressed text block -> list of data rows (header dropped)."""
    rows = []
    with open(os.path.join(HERE, fn), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*-\s*\[\d+,\]:\s?(.*)$", line.rstrip("\n"))
            if not m:
                continue
            rows.append(next(csv.reader(io.StringIO(m.group(1)))))
    return rows[1:]  # drop the header (labels) row

def fnum(x):
    x = (x or "").strip()
    if x in ("", "null", "None"):
        return 0.0
    return float(x)

# ---- load raw ----
D_daily   = parse("raw_daily.txt")
D_monthly = parse("raw_monthly.txt")
D_prod    = parse("raw_products.txt")
D_chan    = parse("raw_channels.txt")
D_cust    = parse("raw_customers.txt")
D_city    = parse("raw_cities.txt")
BD90      = parse("raw_bd90.txt")[0]
BD30      = parse("raw_bd30.txt")[0]

# ---- daily ----
daily = []
for r in D_daily:
    rev, o = fnum(r[1]), int(fnum(r[2]))
    daily.append({"d": r[0], "rev": round(rev, 2), "ord": o,
                  "aov": round(rev / o, 2) if o else 0,
                  "disc": round(fnum(r[3]), 2), "ret": round(fnum(r[4]), 2)})
daily.sort(key=lambda d: d["d"])

# ---- channels (friendly names, sorted) ----
REN = {"Created by Shopflo": "Shopflo checkout", "Draft Orders": "Draft orders (bulk/B2B)"}
channels = [{"name": REN.get(r[0], r[0]), "sales": round(fnum(r[1]), 2), "orders": int(fnum(r[2]))}
            for r in D_chan]
channels.sort(key=lambda c: -c["sales"])
total90 = round(sum(c["sales"] for c in channels), 2)

# ---- customers ----
def crow(val):
    for r in D_cust:
        if r[0].strip().lower() == val:
            return r
    return ["", "0", "0"]
nw, rt = crow("false"), crow("true")
customers = [{"type": "New", "sales": round(fnum(nw[1]), 2), "orders": int(fnum(nw[2]))},
             {"type": "Returning", "sales": round(fnum(rt[1]), 2), "orders": int(fnum(rt[2]))}]

# ---- products (top 20 real products) ----
SKIP = {"standard", "shipping charges", "tip", "gift card"}
prods = []
for r in D_prod:
    title, qty = r[0], (r[2] or "").strip()
    if qty in ("", "null", "None"):
        continue
    if title.strip().lower() in SKIP:
        continue
    prods.append({"title": title, "sales": round(fnum(r[1]), 2), "qty": int(fnum(qty))})
prods.sort(key=lambda p: -p["sales"])
prods = prods[:20]
for p in prods:
    p["gp"] = p["sales"]
    p["share"] = round(p["sales"] / total90 * 100, 1)

# ---- monthly ----
monthly = []
for r in D_monthly:
    y, m = r[0].split("|")
    rev, o = fnum(r[1]), int(fnum(r[2]))
    monthly.append({"y": int(y), "m": int(m), "rev": round(rev, 2), "ord": o,
                    "aov": round(rev / o) if o else 0})
monthly.sort(key=lambda x: (x["y"], x["m"]))

def getm(y, m):
    for r in monthly:
        if r["y"] == y and r["m"] == m:
            return r
    return None
def pct(a, b):
    return round((a - b) / b * 100, 1) if b else None

# current period anchored to the latest month present in the data
cy, cm = monthly[-1]["y"], monthly[-1]["m"]

# ---- yoy ----
yoy = []
for m in range(1, cm + 1):
    a, b = getm(cy, m), getm(cy - 1, m)
    if a and b:
        yoy.append({"m": m, "rev26": a["rev"], "rev25": b["rev"], "pct": pct(a["rev"], b["rev"])})

# ---- ym (year-over-year rollups; labels in HTML are Aug/Sept-oriented) ----
def mrev(y, m):
    r = getm(y, m); return r["rev"] if r else 0
def maov(y, m):
    r = getm(y, m); return r["aov"] if r else 0
ytd_range = range(1, cm)  # Jan .. prev month
ytd26 = sum(mrev(cy, m) for m in ytd_range)
ytd25 = sum(mrev(cy - 1, m) for m in ytd_range)
o26 = sum((getm(cy, m) or {"ord": 0})["ord"] for m in ytd_range)
o25 = sum((getm(cy - 1, m) or {"ord": 0})["ord"] for m in ytd_range)
ym = {
    "aug_yoy": pct(mrev(cy, 8), mrev(cy - 1, 8)),
    "aug26": mrev(cy, 8), "aug25": mrev(cy - 1, 8),
    "aug_aov26": maov(cy, 8), "aug_aov25": maov(cy - 1, 8),
    "jul_yoy": pct(mrev(cy, 7), mrev(cy - 1, 7)),
    "jun_yoy": pct(mrev(cy, 6), mrev(cy - 1, 6)),
    "may_yoy": pct(mrev(cy, 5), mrev(cy - 1, 5)),
    "sep25": mrev(cy - 1, cm),
    "ytd26": round(ytd26, 2), "ytd25": round(ytd25, 2), "ytd_yoy": pct(ytd26, ytd25),
    "ytd_aov26": round(ytd26 / o26) if o26 else 0, "ytd_aov25": round(ytd25 / o25) if o25 else 0,
}

# ---- summary (rolling windows off daily) ----
def agg(days):
    rev = sum(d["rev"] for d in days); o = sum(d["ord"] for d in days)
    return {"rev": round(rev, 2), "orders": o, "aov": (rev / o if o else 0),
            "disc": round(sum(d["disc"] for d in days), 2),
            "returns": round(sum(d["ret"] for d in days), 2)}
def gr(a, b):
    return (a - b) / b * 100 if b else 0
b7, bp7 = agg(daily[-7:]), agg(daily[-14:-7])
b30, bp30 = agg(daily[-30:]), agg(daily[-60:-30])

curkey = f"{cy}-{cm:02d}"
cur_days = [d for d in daily if d["d"][:7] == curkey]
mtd_days = len(cur_days)
sep_rev = round(sum(d["rev"] for d in cur_days), 2)
sep_orders = sum(d["ord"] for d in cur_days)
aug_same = [d for d in daily if d["d"][:7] == f"{cy}-{cm-1:02d}" and int(d["d"][8:10]) <= mtd_days]
aug_same_rev = round(sum(d["rev"] for d in aug_same), 2)
aug_rev = mrev(cy, cm - 1); aug_orders = (getm(cy, cm - 1) or {"ord": 0})["ord"]
dim = calendar.monthrange(cy, cm)[1]
proj_rev = round(sep_rev / mtd_days * dim, 2) if mtd_days else 0
proj_orders = round(sep_orders / mtd_days * dim, 2) if mtd_days else 0

last30 = daily[-30:]
best = max(last30, key=lambda d: d["rev"])
worst = min((d for d in last30 if d["ord"] > 0), key=lambda d: d["rev"])
gross30 = fnum(BD30[0])

today = datetime.date.today()
def fmt(dstr):
    dt = datetime.date.fromisoformat(dstr); return f"{MON[dt.month]} {dt.day}"

S = {
    "currency": "INR", "store": "Amar Chitra Katha",
    "date_start": daily[0]["d"], "date_end": daily[-1]["d"],
    "refreshed": f"{MON[today.month]} {today.day}, {today.year}",
    "window": f"{fmt(daily[0]['d'])} – {fmt(daily[-1]['d'])}, {cy}",
    "mtd_days": mtd_days, "mtd_dim": dim,
    "mtd_month": calendar.month_name[cm], "mtd_prev_label": f"{MON[cm-1]} 1–{mtd_days}",
    "b7": b7, "bp7": bp7, "b30": b30, "bp30": bp30,
    "wow_rev": gr(b7["rev"], bp7["rev"]), "wow_orders": gr(b7["orders"], bp7["orders"]),
    "wow_aov": gr(b7["aov"], bp7["aov"]),
    "mom30_rev": gr(b30["rev"], bp30["rev"]), "mom30_orders": gr(b30["orders"], bp30["orders"]),
    "sep_rev": sep_rev, "sep_orders": sep_orders, "aug_rev": aug_rev, "aug_orders": aug_orders,
    "aug_same_rev": aug_same_rev, "mtd_pace_rev": gr(sep_rev, aug_same_rev),
    "proj_rev": proj_rev, "proj_orders": proj_orders, "proj_vs_aug": gr(proj_rev, aug_rev),
    "best": {"date": best["d"], "total_sales": best["rev"], "orders": best["ord"], "aov": best["aov"]},
    "worst": {"date": worst["d"], "total_sales": worst["rev"], "orders": worst["ord"], "aov": worst["aov"]},
    "ret_rate30": (fnum(BD30[2]) / gross30 * 100) if gross30 else 0,
    "months": {f'{r["y"]}-{r["m"]:02d}': {"rev": r["rev"], "orders": r["ord"]} for r in monthly[-7:]},
}

# ---- breakdown ----
def bd(r):
    return {"gross": round(fnum(r[0]), 2), "disc": round(fnum(r[1]), 2), "returns": round(fnum(r[2]), 2),
            "net": round(fnum(r[3]), 2), "total": round(fnum(r[4]), 2), "orders": int(fnum(r[5]))}
breakdown = {"b30": bd(BD30), "b90": bd(BD90)}

# ---- cities (heuristic normalisation of case/spelling variants) ----
ALIAS = [
    ("bangalor", "Bangalore"), ("bengaluru", "Bangalore"), ("banglore", "Bangalore"),
    ("hyderabad", "Hyderabad"), ("secunderabad", "Hyderabad"),
    ("navi mumbai", "Navi Mumbai"), ("mumbai", "Mumbai"), ("bombay", "Mumbai"),
    ("chennai", "Chennai"), ("chenai", "Chennai"), ("chrnnai", "Chennai"),
    ("gurgaon", "Gurgaon"), ("gurugram", "Gurgaon"), ("gurgoan", "Gurgaon"),
    ("new delhi", "Delhi"), ("delhi", "Delhi"),
    ("pune", "Pune"), ("kolkata", "Kolkata"), ("coimbatore", "Coimbatore"),
    ("ahmedabad", "Ahmedabad"), ("ahemdabad", "Ahmedabad"),
    ("thiruvananthapuram", "Thiruvananthapuram"), ("trivandrum", "Thiruvananthapuram"),
    ("noida", "Noida"), ("ghaziabad", "Ghaziabad"), ("thane", "Thane"), ("jaipur", "Jaipur"),
    ("mysore", "Mysore"), ("mysuru", "Mysore"),
    ("ernakulam", "Kochi"), ("cochin", "Kochi"), ("kochi", "Kochi"),
    ("vijayawada", "Vijayawada"), ("visakhapatnam", "Visakhapatnam"), ("vizag", "Visakhapatnam"),
    ("vishakapatnam", "Visakhapatnam"), ("lucknow", "Lucknow"), ("bhopal", "Bhopal"),
    ("indore", "Indore"), ("nagpur", "Nagpur"),
    ("mangalore", "Mangalore"), ("mangaluru", "Mangalore"), ("surat", "Surat"), ("vadodara", "Vadodara"),
]
def canon(name):
    n = re.sub(r"\s+", " ", name.strip().lower())
    if n == "":
        return None
    for k, v in ALIAS:
        if k in n:
            return v
    return name.strip().title()

cagg = {}
unspec = {"sales": 0.0, "orders": 0}
for r in D_city:
    c = canon(r[0]); s = fnum(r[1]); o = int(fnum(r[2]))
    if c is None:
        unspec["sales"] += s; unspec["orders"] += o; continue
    a = cagg.setdefault(c, {"sales": 0.0, "orders": 0}); a["sales"] += s; a["orders"] += o
ranked = sorted(cagg.items(), key=lambda kv: -kv[1]["sales"])
top = [{"name": k, "sales": round(v["sales"], 2), "orders": v["orders"]} for k, v in ranked[:10]]
cities = {
    "top": top,
    "othersSales": round(sum(v["sales"] for k, v in ranked[10:]), 2),
    "othersOrders": sum(v["orders"] for k, v in ranked[10:]),
    "cityTotal": round(sum(v["sales"] for k, v in ranked), 2),
    "cityOrders": sum(v["orders"] for k, v in ranked),
    "unspecified": {"sales": round(unspec["sales"], 2), "orders": unspec["orders"]},
}

# ---- assemble + splice ----
DATA = {"daily": daily, "summary": S, "products": prods, "channels": channels,
        "customers": customers, "total90": total90, "monthly": monthly,
        "yoy": yoy, "ym": ym, "cities": cities, "breakdown": breakdown}

html = open(INDEX, encoding="utf-8").read()
blob = "const DATA=" + json.dumps(DATA, ensure_ascii=False) + ";"
html, n = re.subn(r"const DATA=\{.*?\};", lambda m: blob, html, count=1, flags=re.S)
assert n == 1, "DATA block not found in index.html"
open(INDEX, "w", encoding="utf-8").write(html)
print(f"OK  refreshed={S['refreshed']}  window={S['window']}  "
      f"sep_rev={sep_rev}  b7_rev={b7['rev']}  cities_top={len(top)}  products={len(prods)}")
