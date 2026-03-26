from flask import Flask, request, redirect
import sqlite3, datetime, requests

app = Flask(__name__)

# ===== 数据库 =====
conn = sqlite3.connect('fa.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
score INTEGER,
level TEXT,
reason TEXT,
status TEXT,
created TEXT
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS config (
key TEXT PRIMARY KEY,
value TEXT
)
''')
conn.commit()

# ===== 工具 =====
def get_config(key):
    try:
        r = c.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return r[0] if r else ""
    except:
        return ""

# ===== UI =====
def page(body):
    return f"<html><meta name='viewport' content='width=device-width, initial-scale=1'><body style='background:#f2f2f7;font-family:-apple-system;padding:12px'>{body}</body></html>"

def btn(t,l,c="#000"):
    return f"<a href='{l}' style='display:block;background:{c};color:#fff;padding:12px;border-radius:16px;text-align:center;margin:8px 0;text-decoration:none'>{t}</a>"

def card(d):
    return f"<div style='background:#fff;padding:14px;border-radius:16px;margin:10px 0'><b>{d[1]}</b><br>⭐{d[2]}（{d[3]}）<br><small>{d[4]}</small></div>"

# ===== 行业评分 =====
def industry_score(name):
    score = 0
    reasons = []

    if any(k in name for k in ["设备","机器人","半导体","医疗器械"]):
        score += 30; reasons.append("小巨人方向")

    if any(k in name for k in ["AI","新能源","芯片"]):
        score += 25; reasons.append("战略新兴")

    if "工程" in name:
        score += 20; reasons.append("工程需求")

    if "贸易" in name:
        score += 20; reasons.append("资金压力")

    return score, reasons

# ===== 百度搜索信号 =====
def fetch_baidu_signals(name):
    signals = []
    try:
        api_key = get_config("baidu_key")
        if not api_key:
            return []

        url = f"https://api.baidu.com/search?q={name}"
        res = requests.get(url, timeout=5).json()

        for item in res.get("data", [])[:5]:
            title = item.get("title","")
            date = str(datetime.date.today())

            if "融资" in title or "投资" in title:
                signals.append((30, f"{date}：百度→融资"))

            elif "中标" in title:
                signals.append((20, f"{date}：百度→中标"))

    except:
        pass

    return signals

# ===== 新闻信号 =====
def fetch_news_signals(name):
    signals = []
    try:
        key = get_config("news_key")
        if not key:
            return []

        url = f"https://newsapi.org/v2/everything?q={name}&apiKey={key}&pageSize=5"
        res = requests.get(url, timeout=5).json()

        for i in res.get("articles", []):
            title = i.get("title","")[:30]
            date = i.get("publishedAt","")[:10]

            if "融资" in title:
                signals.append((30, f"{date}：新闻→融资"))

            elif "中标" in title:
                signals.append((20, f"{date}：新闻→中标"))

    except:
        pass

    return signals

# ===== 开单果（公司抓取）=====
def fetch_kdg():
    try:
        key = get_config("kdg_key")
        if not key:
            return []

        res = requests.get(
            "https://api.kaidanguo.com/company/search",
            headers={"Authorization": key},
            timeout=5
        ).json()

        return [i.get("companyName") for i in res.get("data", []) if i.get("companyName")]

    except:
        return []

# ===== 分析 =====
def analyze(name):
    score = 50
    reasons = []

    s,r = industry_score(name)
    score += s
    reasons += r

    # 新闻
    for s1,r1 in fetch_news_signals(name):
        score += s1; reasons.append(r1)

    # 百度
    for s1,r1 in fetch_baidu_signals(name):
        score += s1; reasons.append(r1)

    if not reasons:
        reasons.append("无明显融资信号")

    level = "A" if score >= 80 else "B"
    return score, level, "；".join(reasons)

# ===== 兜底公司 =====
def fallback():
    return [
        "华为技术有限公司",
        "腾讯科技有限公司",
        "比亚迪股份有限公司",
        "宁德时代新能源科技股份有限公司"
    ]

# ===== 抓取 =====
def run_fetch():
    names = fetch_kdg()
    if not names:
        names = fallback()

    added = 0

    for name in names:
        if not name:
            continue

        exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
        if exists:
            continue

        s,l,r = analyze(name)

        c.execute("INSERT INTO customers (name,score,level,reason,status,created) VALUES (?,?,?,?,?,?)",
                  (name,s,l,r,"未联系",datetime.date.today()))
        added += 1

    conn.commit()
    return added

# ===== 页面 =====
@app.route("/")
def home():
    return page(
        "<h2>FA系统（多源版）</h2>"
        + btn("抓客户","/run")
        + btn("客户列表","/list")
        + btn("API设置","/api")
        + btn("清空数据","/clear","#d9534f")
    )

@app.route("/run")
def run():
    run_fetch()
    return redirect("/list")

@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()
    if not data:
        return page("暂无数据"+btn("抓客户","/run"))
    return page("".join([card(d) for d in data]))

@app.route("/clear")
def clear():
    ok = request.args.get("ok")
    if ok=="yes":
        c.execute("DELETE FROM customers")
        conn.commit()
        return redirect("/list")
    return page(btn("确认清空","/clear?ok=yes","#d9534f")+btn("取消","/"))

# ===== API设置 =====
@app.route("/api", methods=["GET","POST"])
def api():
    if request.method=="POST":
        c.execute("REPLACE INTO config VALUES ('kdg_key',?)",(request.form.get("kdg"),))
        c.execute("REPLACE INTO config VALUES ('news_key',?)",(request.form.get("news"),))
        c.execute("REPLACE INTO config VALUES ('baidu_key',?)",(request.form.get("baidu"),))
        conn.commit()
        return redirect("/")

    return page("""
    <form method="post">
    开单果KEY:<br><input name="kdg"><br><br>
    新闻KEY:<br><input name="news"><br><br>
    百度KEY:<br><input name="baidu"><br><br>
    <button>保存</button>
    </form>
    """)
    
app.run(host="0.0.0.0", port=8080)
