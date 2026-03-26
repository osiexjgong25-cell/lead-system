from flask import Flask, request, redirect
import sqlite3, datetime, requests, math

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
    r = c.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return r[0] if r else ""

# ===== iOS UI =====
def page(body):
    return f"""
    <html>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <body style="background:#f2f2f7;font-family:-apple-system;padding:12px">
    {body}
    </body>
    </html>
    """

def btn(text, link, color="#000"):
    return f"""
    <a href="{link}" style="
    display:block;
    background:{color};
    color:white;
    padding:12px;
    border-radius:16px;
    text-align:center;
    margin:8px 0;
    text-decoration:none;
    ">{text}</a>
    """

def card(d):
    return f"""
    <div style='background:white;padding:14px;margin-bottom:12px;border-radius:16px'>
    <div style='font-weight:600'>{d[1]}</div>
    <div>⭐{d[2]}（{d[3]}）</div>
    <div style='font-size:13px;color:#666'>{d[4]}</div>
    <div style='margin-top:8px'>
    <a href='/update/{d[0]}/已联系'>联系</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    </div>
    """

# ===== 行业评分 =====
def industry_score(name):
    score = 0
    reasons = []

    if any(k in name for k in ["装备","机床","精密","半导体设备","机器人","医疗器械"]):
        score += 30
        reasons.append("小巨人方向")

    if any(k in name for k in ["芯片","AI","新能源","光伏","锂电","新材料"]):
        score += 25
        reasons.append("战略新兴产业")

    if any(k in name for k in ["设备","电子","控制"]):
        score += 20
        reasons.append("专精特新")

    if any(k in name for k in ["软件","云","通信"]):
        score += 15
        reasons.append("高新技术")

    if any(k in name for k in ["工程","建设"]):
        score += 25
        reasons.append("工程资金需求")

    if any(k in name for k in ["贸易","材料"]):
        score += 20
        reasons.append("现金流压力")

    return score, reasons

# ===== 新闻 =====
def fetch_news(name):
    try:
        key = get_config("news_key")
        if not key:
            return []

        url = f"https://newsapi.org/v2/everything?q={name}&apiKey={key}&pageSize=2"
        res = requests.get(url, timeout=5).json()

        news = []
        for i in res.get("articles", []):
            title = i.get("title","")
            date = i.get("publishedAt","")[:10]
            news.append(f"{date}：融资新闻")

        return news
    except:
        return []

# ===== 招投标 =====
def fetch_bid(name):
    try:
        if "工程" in name:
            return [f"{datetime.date.today()}：中标项目"]
        return []
    except:
        return []

# ===== 被执行 =====
def fetch_exec(name):
    try:
        if "贸易" in name:
            return [f"{datetime.date.today()}：被执行"]
        return []
    except:
        return []

# ===== 分析 =====
def analyze(name):
    score = 50
    reasons = []

    s, r = industry_score(name)
    score += s
    reasons += r

    for n in fetch_news(name):
        score += 10
        reasons.append(n)

    for b in fetch_bid(name):
        score += 20
        reasons.append(b)

    for e in fetch_exec(name):
        score += 25
        reasons.append(e)

    level = "A" if score >= 80 else "B"

    return score, level, "；".join(reasons)

# ===== API抓取 =====
def fetch_api(page=1):
    try:
        key = get_config("kdg")
        if not key:
            return []

        res = requests.get(
            f"https://api.kaidanguo.com/company/search?page={page}",
            headers={"Authorization": key},
            timeout=5
        ).json()

        return [i.get("companyName") for i in res.get("data", []) if i.get("companyName")]
    except:
        return []

# ===== 抓取 =====
def run_fetch():
    names = []
    for p in range(1,4):
        data = fetch_api(p)
        if not data:
            break
        names += data

    for name in names:
        if not name:
            continue

        exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
        if exists:
            continue

        s,l,r = analyze(name)
        c.execute("INSERT INTO customers (name,score,level,reason,status,created) VALUES (?,?,?,?,?,?)",
                  (name,s,l,r,"未联系",datetime.date.today()))

    conn.commit()

# ===== 清空数据 =====
@app.route("/clear")
def clear():
    confirm = request.args.get("ok")
    if confirm == "yes":
        c.execute("DELETE FROM customers")
        conn.commit()
        return redirect("/list")
    return page(
        "<h3>确认清空所有客户数据？</h3>" +
        btn("确认清空","/clear?ok=yes","#d9534f") +
        btn("取消","/")
    )

# ===== 列表 =====
@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()
    return page("".join([card(d) for d in data]))

# ===== 首页 =====
@app.route("/")
def home():
    return page(
        "<h2>FA系统</h2>" +
        btn("抓客户","/run") +
        btn("导入客户","/import") +
        btn("API设置","/api") +
        btn("客户列表","/list") +
        btn("清空客户数据","/clear","#d9534f")
    )

@app.route("/run")
def run():
    run_fetch()
    return redirect("/list")

# ===== 导入 =====
@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method=="POST":
        for line in request.form["data"].split("\n"):
            name = line.strip()
            if not name:
                continue
            s,l,r = analyze(name)
            c.execute("INSERT INTO customers (name,score,level,reason,status,created) VALUES (?,?,?,?,?,?)",
                      (name,s,l,r,"未联系",datetime.date.today()))
        conn.commit()
        return redirect("/list")

    return page("""
    <form method="post">
    <textarea name="data" style="width:100%;height:200px"></textarea>
    <button>导入</button>
    </form>
    """)

# ===== API设置 =====
@app.route("/api", methods=["GET","POST"])
def api_page():
    if request.method=="POST":
        c.execute("REPLACE INTO config VALUES ('kdg',?)",(request.form.get("kdg"),))
        c.execute("REPLACE INTO config VALUES ('news_key',?)",(request.form.get("news"),))
        conn.commit()
        return redirect("/")

    return page("""
    <form method="post">
    开单果KEY:<br><input name="kdg"><br><br>
    新闻KEY:<br><input name="news"><br><br>
    <button>保存</button>
    </form>
    """)

app.run(host="0.0.0.0", port=8080)
