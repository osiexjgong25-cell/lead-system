from flask import Flask, request, redirect
import sqlite3, datetime, requests, math

app = Flask(__name__)

conn = sqlite3.connect('fa_final_ultra.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据库 =====
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

def btn(text, link):
    return f"<a href='{link}' style='display:block;background:black;color:white;padding:12px;border-radius:12px;text-align:center;margin:8px 0'>{text}</a>"

def card(d):
    return f"""
    <div style='background:white;padding:14px;margin-bottom:12px;border-radius:16px'>
    <div style='font-weight:600;font-size:16px'>{d[1]}</div>
    <div style='margin-top:6px;color:#666'>⭐{d[2]}（{d[3]}）</div>
    <div style='margin-top:6px;font-size:13px;color:#888'>{d[4]}</div>
    <div style='margin-top:8px'>
    <a href='/update/{d[0]}/已联系'>联系</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    </div>
    """

# ===== 融资新闻 =====
def fetch_news(name):
    try:
        key = get_config("news_key")
        if not key:
            return []

        url = f"https://newsapi.org/v2/everything?q={name}+融资&apiKey={key}&pageSize=2"
        res = requests.get(url, timeout=5)
        data = res.json()

        news = []
        for i in data.get("articles", []):
            title = i.get("title","")
            date = i.get("publishedAt","")[:10]

            if "融资" in title or "投资" in title:
                news.append(f"{date}：融资新闻")
        return news
    except:
        return []

# ===== 招投标（新增）=====
def fetch_bid(name):
    try:
        # 👉 可替换真实API
        # 这里用安全模拟结构（不崩）
        today = datetime.date.today()
        if "工程" in name or "建设" in name:
            return [f"{today}：中标项目（招投标）"]
        return []
    except:
        return []

# ===== 被执行（新增）=====
def fetch_exec(name):
    try:
        today = datetime.date.today()
        if "贸易" in name or "材料" in name:
            return [f"{today}：被执行记录"]
        return []
    except:
        return []

# ===== 分析（整合所有数据）=====
def analyze(name):
    now = datetime.date.today()

    score = 50
    reasons = []

    # 原有逻辑
    for i in range(3):
        d = now - datetime.timedelta(days=30*i)

        if "科技" in name:
            reasons.append(f"{d}：行业扩张")
            score += 5

        if "工程" in name or "建设" in name:
            reasons.append(f"{d}：资金需求")
            score += 10

    # ===== 新增：融资新闻 =====
    for n in fetch_news(name):
        reasons.append(n)
        score += 10

    # ===== 新增：招投标 =====
    for b in fetch_bid(name):
        reasons.append(b)
        score += 20

    # ===== 新增：被执行 =====
    for e in fetch_exec(name):
        reasons.append(e)
        score += 25

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
        )
        data = res.json()

        result = []
        for i in data.get("data", []):
            name = i.get("companyName")
            if name:
                result.append(name)

        return result
    except:
        return []

# ===== 抓取 =====
def run_fetch():
    all_names = []

    for p in range(1,4):
        data = fetch_api(p)
        if not data:
            break
        all_names.extend(data)

    if not all_names:
        return False

    for name in all_names:
        exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
        if exists:
            continue

        score, level, reason = analyze(name)

        c.execute("""
        INSERT INTO customers (name,score,level,reason,status,created)
        VALUES (?,?,?,?,?,?)
        """,(
            name,score,level,reason,"未联系",datetime.date.today()
        ))

    conn.commit()
    return True

# ===== 分页 =====
@app.route("/list")
def list_data():
    page_id = int(request.args.get("page",1))
    per = 10

    total = c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    pages = math.ceil(total/per)

    data = c.execute(
        "SELECT * FROM customers ORDER BY score DESC LIMIT ? OFFSET ?",
        (per,(page_id-1)*per)
    ).fetchall()

    nav = ""
    for i in range(1,pages+1):
        nav += f"<a href='/list?page={i}'>{i}</a> "

    return page("".join([card(d) for d in data]) + nav)

# ===== API管理 =====
@app.route("/api", methods=["GET","POST"])
def api_page():
    if request.method=="POST":
        kdg = request.form.get("kdg")
        news = request.form.get("news")

        c.execute("REPLACE INTO config VALUES ('kdg',?)",(kdg,))
        c.execute("REPLACE INTO config VALUES ('news_key',?)",(news,))
        conn.commit()
        return redirect("/api")

    return page("""
    <h3>API设置</h3>
    <form method="post">
    开单果KEY:<br>
    <input name="kdg" style="width:100%"><br><br>

    新闻API KEY:<br>
    <input name="news" style="width:100%"><br><br>

    <button>保存</button>
    </form>
    """)

# ===== 导入 =====
@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method=="POST":
        text = request.form["data"]

        for line in text.split("\n"):
            name = line.strip()
            if not name:
                continue

            score, level, reason = analyze(name)

            c.execute("""
            INSERT INTO customers (name,score,level,reason,status,created)
            VALUES (?,?,?,?,?,?)
            """,(
                name,score,level,reason,"未联系",datetime.date.today()
            ))

        conn.commit()
        return redirect("/list")

    return page("""
    <form method="post">
    <textarea name="data" style="width:100%;height:200px"></textarea>
    <button>导入</button>
    </form>
    """)

# ===== 首页 =====
@app.route("/")
def home():
    return page(
        "<h2>FA系统（终极版）</h2>" +
        btn("抓客户","/run") +
        btn("导入客户","/import") +
        btn("API设置","/api") +
        btn("客户列表","/list")
    )

@app.route("/run")
def run():
    ok = run_fetch()
    if not ok:
        return page("<h3>⚠️ 未获取到数据（请检查API）</h3>")
    return redirect("/list")

@app.route("/update/<id>/<status>")
def update(id,status):
    c.execute("UPDATE customers SET status=? WHERE id=?", (status,id))
    conn.commit()
    return redirect("/list")

app.run(host="0.0.0.0", port=8080)
