from flask import Flask, request, redirect
import sqlite3, datetime, requests

app = Flask(__name__)

# ===== 数据库 =====
conn = sqlite3.connect('fa.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
score INTEGER,
level TEXT,
reason TEXT,
status TEXT,
created TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS config (
key TEXT PRIMARY KEY,
value TEXT
)''')

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

def btn(t, l, c="#000"):
    return f"<a href='{l}' style='display:block;background:{c};color:#fff;padding:12px;border-radius:18px;text-align:center;margin:8px 0;text-decoration:none'>{t}</a>"

def card(d):
    return f"""
    <div style='background:#fff;padding:14px;border-radius:18px;margin:10px 0'>
    <b>{d[1]}</b><br><br>
    {d[4]}<br><br>
    状态：<b>{d[5]}</b><br><br>
    <a href='/update?id={d[0]}&s=未联系'>未联系</a> |
    <a href='/update?id={d[0]}&s=已联系'>已联系</a> |
    <a href='/update?id={d[0]}&s=成交'>成交</a>
    </div>
    """

# ===== 建筑过滤 =====
def is_bad_building(name):
    if any(k in name for k in ["建筑","工程","建设","施工"]):
        return True
    return False

def allow_building(signals):
    for _, t in signals:
        if t in ["融资"]:
            return True
    return False

# ===== 新闻信号（防崩）=====
def fetch_news(name):
    signals = []
    try:
        key = get_config("news_key")
        if not key:
            return []
        url = f"https://newsapi.org/v2/everything?q={name}&pageSize=3&apiKey={key}"
        res = requests.get(url, timeout=5).json()
        for i in res.get("articles", []):
            title = i.get("title","")
            date = i.get("publishedAt","")[:10]
            if "融资" in title:
                signals.append((date,"融资"))
    except:
        pass
    return signals

# ===== 分析 =====
def analyze(name):
    score = 50
    reasons = []
    today = str(datetime.date.today())

    signals = fetch_news(name)

    # 建筑过滤
    if is_bad_building(name) and not allow_building(signals):
        score -= 40
        reasons.append("建筑行业降权")

    # 融资信号
    for d,t in signals:
        score += 30
        reasons.append(f"{d}:{t}")

    if not reasons:
        reasons.append(f"{today}:无融资信号")

    score = max(0, min(score,100))

    level = "🔥高" if score>80 else "⭐中" if score>60 else "普通"

    return score, level, f"融资概率:{score}%<br>原因:{'；'.join(reasons)}"

# ===== 万能API（核心）=====
def universal_fetch(url):
    names = []
    try:
        try:
            res = requests.get(url, timeout=6).json()
        except:
            res = requests.post(url, timeout=6).json()

        def extract(obj):
            if isinstance(obj, dict):
                for k,v in obj.items():
                    if isinstance(v,str) and any(x in k.lower() for x in ["name","company","title"]):
                        if len(v)>3:
                            names.append(v)
                    else:
                        extract(v)
            elif isinstance(obj,list):
                for i in obj:
                    extract(i)

        extract(res)
    except:
        pass

    return list(set(names))

# ===== 抓取 =====
def run_fetch():
    url = get_config("universal_api")
    names = []

    if url:
        names = universal_fetch(url)

    if not names:
        names = [i[0] for i in c.execute("SELECT name FROM customers").fetchall()]

    if not names:
        return 0

    added = 0

    for name in names:
        if not name:
            continue

        s,l,r = analyze(name)

        exist = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()

        if exist:
            c.execute("UPDATE customers SET score=?,level=?,reason=?,created=? WHERE name=?",
                      (s,l,r,str(datetime.date.today()),name))
        else:
            c.execute("INSERT INTO customers VALUES(NULL,?,?,?,?,?,?)",
                      (name,s,l,r,"未联系",str(datetime.date.today())))
            added += 1

    conn.commit()
    return added

# ===== 路由 =====
@app.route("/")
def home():
    return page(
        "<h2>FA系统（最终稳定版）</h2>"
        + btn("抓客户","/run")
        + btn("客户列表","/list")
        + btn("导入客户","/import")
        + btn("万能API接口","/uapi")
        + btn("清空数据","/clear","#d9534f")
    )

@app.route("/uapi", methods=["GET","POST"])
def uapi():
    if request.method=="POST":
        c.execute("REPLACE INTO config VALUES('universal_api',?)",(request.form.get("url"),))
        conn.commit()
        return redirect("/")
    return page("""
    <h3>万能API接口</h3>
    <form method="post">
    API链接:<br>
    <input name="url" style="width:100%"><br><br>
    <button>保存并抓取</button>
    </form>
    """)

@app.route("/run")
def run():
    n = run_fetch()
    if n==0:
        return page("未抓新数据，已刷新评分"+btn("查看客户","/list"))
    return redirect("/list")

@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()
    return page("".join([card(d) for d in data]) if data else "暂无数据")

@app.route("/update")
def update():
    try:
        c.execute("UPDATE customers SET status=? WHERE id=?",
                  (request.args.get("s"),request.args.get("id")))
        conn.commit()
    except:
        pass
    return redirect("/list")

@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method=="POST":
        for line in request.form["data"].split("\n"):
            name=line.strip()
            if not name:
                continue
            s,l,r=analyze(name)
            c.execute("INSERT INTO customers VALUES(NULL,?,?,?,?,?,?)",
                      (name,s,l,r,"未联系",str(datetime.date.today())))
        conn.commit()
        return redirect("/list")
    return page("<form method='post'><textarea name='data' style='width:100%;height:200px'></textarea><button>导入</button></form>")

@app.route("/clear")
def clear():
    if request.args.get("ok")=="yes":
        c.execute("DELETE FROM customers")
        conn.commit()
        return redirect("/list")
    return page(btn("确认清空","/clear?ok=yes","#d9534f")+btn("取消","/"))

app.run(host="0.0.0.0", port=8080)
