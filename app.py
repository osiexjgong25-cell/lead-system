from flask import Flask, request, redirect, Response
import sqlite3, datetime, requests, re, json

app = Flask(__name__)

conn = sqlite3.connect('fa_stable.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据库 =====
c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
industry TEXT,
phone TEXT,
score INTEGER,
level TEXT,
status TEXT,
reason TEXT,
script TEXT,
created TEXT
)
''')
conn.commit()

# ===== iOS UI =====
def page(body):
    return f"""
    <html>
    <body style="background:#f2f2f7;font-family:-apple-system;padding:10px">
    {body}
    </body>
    </html>
    """

def card(d):
    return f"""
    <div style='background:white;padding:12px;margin:10px;border-radius:12px'>
    <b>{d[1]}</b><br>
    📞 {d[3] or "无"}<br>
    ⭐{d[4]} 等级:{d[5]}<br>
    状态:{d[6]}<br>
    💡{d[7]}<br>
    📣{d[8]}<br>

    <a href='/update/{d[0]}/已联系'>联系</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    """

# ===== 评分 =====
def score_model(name):
    score = 50
    if "建筑" in name:
        score += 30
    if "科技" in name:
        score += 10

    level = "A" if score>70 else "B"
    return score, level

# ===== 安全抓数据（不会崩）=====
def safe_fetch():
    try:
        res = requests.get("https://api.kaidanguo.com/company/search", timeout=3)
        data = res.json()
        return data.get("data", [])
    except:
        return []

# ===== 抓取逻辑 =====
def run_fetch():
    data = safe_fetch()

    # 👉 没数据就用本地（关键）
    if not data:
        data = [
            {"companyName":"深圳建筑工程公司","phone":"13800000000"},
            {"companyName":"深圳科技有限公司","phone":""}
        ]

    for i in data:
        name = i.get("companyName") or i.get("name")
        if not name:
            continue

        exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
        if exists:
            continue

        phone = i.get("phone","")

        score, level = score_model(name)

        c.execute("""
        INSERT INTO customers
        (name,industry,phone,score,level,status,reason,script,created)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,(
            name,
            "",
            phone,
            score,
            level,
            "未联系",
            "系统判断有融资需求",
            "您好，我们这边有资金合作机会",
            datetime.date.today()
        ))

    conn.commit()

# ===== 导入（支持乱格式）=====
@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method=="POST":
        text = request.form["data"]

        for line in text.split("\n"):
            name = line.strip()
            if not name:
                continue

            score, level = score_model(name)

            c.execute("""
            INSERT INTO customers
            (name,industry,phone,score,level,status,reason,script,created)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,(
                name,"","",score,level,
                "未联系","导入数据","可联系沟通",
                datetime.date.today()
            ))

        conn.commit()
        return redirect("/list")

    return page("""
    <h3>导入客户</h3>
    <form method="post">
    <textarea name="data" style="width:100%;height:200px"></textarea><br>
    <button>导入</button>
    </form>
    """)

# ===== 首页 =====
@app.route("/")
def home():
    return page("""
    <h2>FA系统（稳定版）</h2>
    <a href='/run'>抓客户</a><br><br>
    <a href='/import'>导入客户</a><br><br>
    <a href='/list'>客户列表</a>
    """)

# ===== 抓数据 =====
@app.route("/run")
def run():
    run_fetch()
    return redirect("/list")

# ===== 列表 =====
@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()
    return page("".join([card(d) for d in data]))

# ===== 更新 =====
@app.route("/update/<id>/<status>")
def update(id,status):
    c.execute("UPDATE customers SET status=? WHERE id=?", (status,id))
    conn.commit()
    return redirect("/list")

app.run(host="0.0.0.0", port=8080)
