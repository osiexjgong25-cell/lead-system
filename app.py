from flask import Flask, request, redirect, Response
import sqlite3, datetime, requests, re

app = Flask(__name__)

conn = sqlite3.connect('fa_stable_pro.db', check_same_thread=False)
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
reason TEXT,
status TEXT,
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
    💡评分原因：{d[6]}<br>
    状态:{d[7]}<br>
    📣{d[8]}<br>

    <a href='/update/{d[0]}/已联系'>联系</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    """

# ===== 评分（带原因）=====
def score_model(name, phone, source):
    score = 0
    reason = []

    if "建筑" in name or "工程" in name:
        score += 30
        reason.append("工程行业（资金需求高）")

    if phone:
        score += 20
        reason.append("有电话（可触达）")

    if source == "API":
        score += 20
        reason.append("真实数据源")

    if "科技" in name:
        score += 10
        reason.append("科技行业（融资活跃）")

    level = "A" if score >= 60 else "B"

    return score, level, "；".join(reason)

# ===== 安全API =====
def safe_fetch():
    try:
        res = requests.get("https://api.kaidanguo.com/company/search", timeout=3)
        data = res.json()

        result = []
        for i in data.get("data", []):
            result.append({
                "name": i.get("companyName",""),
                "phone": i.get("phone",""),
                "industry": i.get("industry",""),
                "source": "API"
            })

        return result
    except:
        return []

# ===== 官网电话补充 =====
def get_web_phone(name):
    try:
        html = requests.get(f"https://www.baidu.com/s?wd={name}", timeout=3).text
        m = re.search(r'1[3-9]\d{9}', html)
        return m.group() if m else ""
    except:
        return ""

# ===== 主抓取 =====
def run_fetch():
    data = safe_fetch()

    # 👉 防崩：没数据用本地
    if not data:
        data = [
            {"name":"深圳建筑工程公司","phone":"","industry":"建筑","source":"本地"},
            {"name":"深圳科技有限公司","phone":"","industry":"科技","source":"本地"}
        ]

    for i in data:
        name = i.get("name")
        if not name:
            continue

        exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
        if exists:
            continue

        phone = i.get("phone") or get_web_phone(name)

        score, level, reason = score_model(name, phone, i.get("source"))

        script = f"{name}您好，我们这边有资金渠道可以合作"

        c.execute("""
        INSERT INTO customers
        (name,industry,phone,score,level,reason,status,script,created)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,(
            name,
            i.get("industry",""),
            phone,
            score,
            level,
            reason,
            "未联系",
            script,
            datetime.date.today()
        ))

    conn.commit()

# ===== 导入（不崩）=====
@app.route("/import", methods=["GET","POST"])
def import_data():
    if request.method=="POST":
        text = request.form["data"]

        for line in text.split("\n"):
            name = line.strip()
            if not name:
                continue

            score, level, reason = score_model(name,"","导入")

            c.execute("""
            INSERT INTO customers
            (name,industry,phone,score,level,reason,status,script,created)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,(
                name,"","",score,level,reason,
                "未联系","导入客户",
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

# ===== 页面 =====
@app.route("/")
def home():
    return page("""
    <h2>FA系统（稳定+真实数据版）</h2>
    <a href='/run'>抓客户</a><br><br>
    <a href='/import'>导入客户</a><br><br>
    <a href='/list'>客户列表</a>
    """)

@app.route("/run")
def run():
    run_fetch()
    return redirect("/list")

@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()
    return page("".join([card(d) for d in data]))

@app.route("/update/<id>/<status>")
def update(id,status):
    c.execute("UPDATE customers SET status=? WHERE id=?", (status,id))
    conn.commit()
    return redirect("/list")

app.run(host="0.0.0.0", port=8080)
