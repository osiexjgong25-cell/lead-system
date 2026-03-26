from flask import Flask, request, redirect
import sqlite3, datetime, requests

app = Flask(__name__)

conn = sqlite3.connect('fa_real_final.db', check_same_thread=False)
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
conn.commit()

# ===== iOS UI（升级版）=====
def page(body):
    return f"""
    <html>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <body style="background:#f2f2f7;font-family:-apple-system;padding:12px">
    {body}
    </body>
    </html>
    """

def card(d):
    return f"""
    <div style='background:white;padding:14px;margin-bottom:12px;border-radius:16px;box-shadow:0 2px 6px rgba(0,0,0,0.05)'>
    <div style='font-size:17px;font-weight:600'>{d[1]}</div>
    <div style='margin-top:6px;font-size:14px;color:#666'>
    ⭐评分：{d[2]}（{d[3]}）
    </div>
    <div style='margin-top:6px;font-size:13px;color:#888'>
    {d[4]}
    </div>
    <div style='margin-top:8px'>
    <a href='/update/{d[0]}/已联系'>联系</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    </div>
    """

# ===== 真实API抓取（必须有KEY才有数据）=====
def fetch_real():
    try:
        res = requests.get(
            "https://api.kaidanguo.com/company/search",
            timeout=5
        )
        data = res.json()

        result = []
        for i in data.get("data", []):
            if i.get("companyName"):
                result.append(i.get("companyName"))

        return result
    except:
        return []

# ===== 融资要素判断（带时间）=====
def analyze_company(name):
    today = datetime.date.today()

    score = 50
    reasons = []

    # 模拟联网判断（结构已留好）
    if "科技" in name:
        score += 10
        reasons.append(f"{today}：科技行业（融资活跃）")

    if "工程" in name or "建设" in name:
        score += 20
        reasons.append(f"{today}：工程行业（资金需求高）")

    # 👉 可接真实API（新闻/招标）

    level = "A" if score >= 70 else "B"

    return score, level, "；".join(reasons)

# ===== 抓客户（只要真实数据）=====
def run_fetch():
    names = fetch_real()

    # ❗ 不再造假数据
    if not names:
        return "NO_DATA"

    for name in names:
        exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
        if exists:
            continue

        score, level, reason = analyze_company(name)

        c.execute("""
        INSERT INTO customers
        (name,score,level,reason,status,created)
        VALUES (?,?,?,?,?,?)
        """,(
            name,
            score,
            level,
            reason,
            "未联系",
            datetime.date.today()
        ))

    conn.commit()
    return "OK"

# ===== 导入（带融资分析）=====
@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method=="POST":
        text = request.form["data"]

        for line in text.split("\n"):
            name = line.strip()
            if not name:
                continue

            score, level, reason = analyze_company(name)

            c.execute("""
            INSERT INTO customers
            (name,score,level,reason,status,created)
            VALUES (?,?,?,?,?,?)
            """,(
                name,score,level,reason,
                "未联系",
                datetime.date.today()
            ))

        conn.commit()
        return redirect("/list")

    return page("""
    <h3>导入客户</h3>
    <form method="post">
    <textarea name="data" style="width:100%;height:200px;border-radius:10px"></textarea><br><br>
    <button style="padding:10px 20px;border-radius:10px;background:black;color:white">导入</button>
    </form>
    """)

# ===== 页面 =====
@app.route("/")
def home():
    return page("""
    <h2>FA系统（真实数据版）</h2>
    <a href='/run'>抓客户（真实）</a><br><br>
    <a href='/import'>导入客户（带融资分析）</a><br><br>
    <a href='/list'>客户列表</a>
    """)

@app.route("/run")
def run():
    result = run_fetch()
    if result == "NO_DATA":
        return page("<h3>⚠️ 当前没有获取到真实数据（请配置API）</h3>")
    return redirect("/list")

@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()

    if not data:
        return page("<h3>暂无数据</h3>")

    return page("".join([card(d) for d in data]))

@app.route("/update/<id>/<status>")
def update(id,status):
    c.execute("UPDATE customers SET status=? WHERE id=?", (status,id))
    conn.commit()
    return redirect("/list")

app.run(host="0.0.0.0", port=8080)
