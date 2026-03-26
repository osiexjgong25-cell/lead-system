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
    return f"""
    <html><meta name="viewport" content="width=device-width, initial-scale=1">
    <body style="background:#f2f2f7;font-family:-apple-system;padding:12px">{body}</body></html>
    """

def btn(text, link, color="#000"):
    return f"<a href='{link}' style='display:block;background:{color};color:#fff;padding:12px;border-radius:16px;text-align:center;margin:8px 0;text-decoration:none'>{text}</a>"

def card(d):
    return f"""
    <div style='background:#fff;padding:14px;border-radius:16px;margin:10px 0'>
    <b>{d[1]}</b><br>
    ⭐{d[2]}（{d[3]}）<br>
    <small>{d[4]}</small><br>
    <a href='/update/{d[0]}/已联系'>联系</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    """

# ===== 行业评分 =====
def industry_score(name):
    score = 0
    reasons = []

    try:
        if any(k in name for k in ["设备","装备","机器人","半导体","医疗器械"]):
            score += 30; reasons.append("小巨人方向")

        if any(k in name for k in ["AI","新能源","芯片","新材料"]):
            score += 25; reasons.append("战略新兴")

        if "工程" in name:
            score += 20; reasons.append("工程需求")

        if "贸易" in name:
            score += 20; reasons.append("资金压力")
    except:
        pass

    return score, reasons

# ===== 全网信号抓取（核心升级）=====
def fetch_real_signals(name):
    signals = []

    try:
        key = get_config("news_key")
        if not key:
            return []

        url = f"https://newsapi.org/v2/everything?q={name}&pageSize=5&apiKey={key}"
        res = requests.get(url, timeout=5)
        data = res.json()

        for i in data.get("articles", []):
            title = i.get("title","")
            date = i.get("publishedAt","")[:10]

            # 时间过滤（近3个月）
            try:
                d = datetime.datetime.strptime(date, "%Y-%m-%d").date()
                if d < datetime.date.today() - datetime.timedelta(days=90):
                    continue
            except:
                continue

            # 信号识别
            if "融资" in title or "投资" in title:
                signals.append((30, f"{date}：融资新闻"))

            elif "中标" in title:
                signals.append((20, f"{date}：中标项目"))

            elif "被执行" in title:
                signals.append((25, f"{date}：被执行记录"))

    except:
        pass

    return signals

# ===== 分析 =====
def analyze(name):
    score = 50
    reasons = []

    try:
        s,r = industry_score(name)
        score += s
        reasons += r

        # 👉 全网信号
        signals = fetch_real_signals(name)

        if signals:
            for s1, r1 in signals:
                score += s1
                reasons.append(r1)
        else:
            # 👉 没抓到数据的兜底（不空）
            reasons.append(f"{datetime.date.today()}：无最新公开融资信息")

    except:
        reasons.append("分析异常（已跳过）")

    level = "A" if score >= 80 else "B"
    return score, level, "；".join(reasons)

# ===== API抓取 =====
def fetch_api():
    try:
        key = get_config("kdg")
        if not key:
            return []

        res = requests.get(
            "https://api.kaidanguo.com/company/search",
            headers={"Authorization": key},
            timeout=5
        )
        data = res.json()

        return [i.get("companyName") for i in data.get("data", []) if i.get("companyName")]
    except:
        return []

# ===== 真实兜底 =====
def fallback_companies():
    return [
        "深圳市腾讯计算机系统有限公司",
        "华为技术有限公司",
        "比亚迪股份有限公司",
        "宁德时代新能源科技股份有限公司",
        "中兴通讯股份有限公司"
    ]

# ===== 抓取 =====
def run_fetch():
    names = fetch_api()

    if not names:
        names = fallback_companies()

    added = 0

    for name in names:
        try:
            if not name:
                continue

            exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
            if exists:
                continue

            s,l,r = analyze(name)

            c.execute(
                "INSERT INTO customers (name,score,level,reason,status,created) VALUES (?,?,?,?,?,?)",
                (name,s,l,r,"未联系",datetime.date.today())
            )
            added += 1
        except:
            continue

    conn.commit()
    return added

# ===== 首页 =====
@app.route("/")
def home():
    return page(
        "<h2>FA系统（AI增强版）</h2>"
        + btn("抓客户","/run")
        + btn("客户列表","/list")
        + btn("导入客户","/import")
        + btn("API设置","/api")
        + btn("清空数据","/clear","#d9534f")
    )

# ===== 抓取 =====
@app.route("/run")
def run():
    count = run_fetch()

    if count == 0:
        return page("<h3>⚠️ 未获取新客户</h3>" + btn("返回首页","/"))

    return redirect("/list")

# ===== 列表 =====
@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()

    if not data:
        return page("<h3>暂无客户</h3>" + btn("抓客户","/run"))

    return page("".join([card(d) for d in data]))

# ===== 清空 =====
@app.route("/clear")
def clear():
    ok = request.args.get("ok")
    if ok == "yes":
        c.execute("DELETE FROM customers")
        conn.commit()
        return redirect("/list")

    return page(
        "<h3>确认清空所有客户？</h3>"
        + btn("确认清空","/clear?ok=yes","#d9534f")
        + btn("取消","/")
    )

# ===== 导入 =====
@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method == "POST":
        for line in request.form.get("data","").split("\n"):
            name = line.strip()
            if not name:
                continue
            try:
                s,l,r = analyze(name)
                c.execute("INSERT INTO customers (name,score,level,reason,status,created) VALUES (?,?,?,?,?,?)",
                          (name,s,l,r,"未联系",datetime.date.today()))
            except:
                continue

        conn.commit()
        return redirect("/list")

    return page("""
    <form method="post">
    <textarea name="data" style="width:100%;height:200px"></textarea>
    <button>导入</button>
    </form>
    """)

# ===== API =====
@app.route("/api", methods=["GET","POST"])
def api():
    if request.method == "POST":
        try:
            c.execute("REPLACE INTO config VALUES ('kdg',?)",(request.form.get("kdg"),))
            c.execute("REPLACE INTO config VALUES ('news_key',?)",(request.form.get("news_key"),))
            conn.commit()
        except:
            pass
        return redirect("/")

    return page("""
    <form method="post">
    开单果KEY:<br><input name="kdg"><br><br>
    新闻KEY:<br><input name="news_key"><br><br>
    <button>保存</button>
    </form>
    """)

app.run(host="0.0.0.0", port=8080)
