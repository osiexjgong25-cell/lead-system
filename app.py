from flask import Flask, request, redirect
import sqlite3, re, datetime, random

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据库 =====
c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
contact TEXT,
area TEXT,
phone TEXT,
status TEXT,
score INTEGER,
prob INTEGER,
plan TEXT,
reason TEXT,
source TEXT,
created TEXT
)
''')
conn.commit()

# ===== 工具函数 =====
def clean_name(text):
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'(深圳|有限公司|科技|工程|贸易)', '', text)
    return text[:20]

def extract(text):
    phone = re.search(r'1[3-9]\d{9}', text)
    phone = phone.group() if phone else ""

    areas = ["南山","宝安","福田","龙岗","龙华"]
    area = next((a for a in areas if a in text), "深圳")

    name = clean_name(text)
    contact = random.choice(["张总","李总","王总","陈总","赵总"])

    return name, contact, area, phone

def score_model(text):
    score = 0
    reasons = []

    if "中标" in text or "工程" in text:
        score += 30
        reasons.append("有项目，资金需求大")

    if "扩产" in text or "招聘" in text:
        score += 25
        reasons.append("扩张期")

    if "资金" in text or "紧张" in text:
        score += 20
        reasons.append("资金压力")

    if "科技" in text:
        score += 10
        reasons.append("融资活跃行业")

    prob = min(95, score)

    if score >= 60:
        plan = "过桥 / 股权"
    elif score >= 40:
        plan = "债权 / 流贷"
    else:
        plan = "观察"

    return score, prob, plan, "；".join(reasons)

def generate_data():
    base = [
        "深圳建筑公司中标项目",
        "南山科技公司招聘扩张",
        "宝安制造企业扩产",
        "福田贸易公司资金紧张"
    ]
    return [random.choice(base)+str(i) for i in range(30)]

# ===== UI组件 =====
def render_card(d):
    return f"""
    <div style='background:white;padding:15px;margin:12px;border-radius:16px;
    box-shadow:0 2px 6px rgba(0,0,0,0.06)'>

    <div style="font-size:18px;font-weight:600">{d[1]}</div>

    <div style="color:#666;margin-top:5px">
    👤 {d[2]} ｜ 📍 {d[3]}
    </div>

    <div style="margin-top:5px">📞 {d[4]}</div>

    <div style="margin-top:8px">
    ⭐ {d[6]} ｜ 📊 {d[7]}%
    </div>

    <div style="color:#007aff;margin-top:5px">
    💡 {d[8]}
    </div>

    <div style="color:#999;margin-top:5px">
    🧠 {d[9]}
    </div>

    <div style="margin-top:10px">
    状态：<b>{d[5]}</b>
    </div>

    <div style="margin-top:10px">
    <a href='/update/{d[0]}/未联系'>🟡</a>
    <a href='/update/{d[0]}/已联系'>🔵</a>
    <a href='/update/{d[0]}/跟进中'>🟠</a>
    <a href='/update/{d[0]}/成交'>🟢</a>
    </div>

    </div>
    """

def base_html(content):
    return f"""
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
    body{{margin:0;background:#f2f2f7;font-family:-apple-system}}
    textarea{{width:100%;height:80px;border-radius:10px;border:1px solid #ccc}}
    button{{padding:10px 15px;border-radius:10px;background:#007aff;color:white;border:none}}
    .btn{{display:block;margin:15px;padding:12px;text-align:center;
    background:#34c759;color:white;border-radius:12px;text-decoration:none}}
    </style>
    </head>
    <body>
    {content}
    </body>
    </html>
    """

# ===== 首页 =====
@app.route("/")
def home():
    return base_html("""
    <div style="padding:20px;font-size:22px;font-weight:bold">📊 融资客户系统</div>

    <div style="background:white;margin:15px;padding:15px;border-radius:15px">
        <a class="btn" href="/import_page">📥 我的客户</a>
        <a class="btn" href="/auto_page">🔥 自动客户</a>
    </div>
    """)

# ===== 我的客户 =====
@app.route("/import_page")
def import_page():
    data = c.execute("SELECT * FROM customers WHERE source='import' ORDER BY score DESC").fetchall()

    html = """
    <h3 style="padding:15px">📥 我的客户</h3>

    <form method="post" action="/import" style="padding:15px">
    <textarea name="data"></textarea><br><br>
    <button>导入</button>
    </form>
    """

    for d in data:
        html += render_card(d)

    return base_html(html)

# ===== 自动客户 =====
@app.route("/auto_page")
def auto_page():
    data = c.execute("SELECT * FROM customers WHERE source='auto' ORDER BY score DESC").fetchall()

    html = """
    <h3 style="padding:15px">🔥 自动客户</h3>
    <a class="btn" href="/auto_fetch">刷新抓取</a>
    """

    for d in data:
        html += render_card(d)

    return base_html(html)

# ===== 更新状态 =====
@app.route("/update/<id>/<status>")
def update(id, status):
    c.execute("UPDATE customers SET status=? WHERE id=?", (status, id))
    conn.commit()
    return redirect(request.referrer or "/")

# ===== 导入 =====
@app.route("/import", methods=["POST"])
def import_data():
    raw = request.form.get("data","")

    for line in raw.split("\n"):
        try:
            name, contact, area, phone = extract(line)
            if not phone: continue

            exists = c.execute("SELECT id FROM customers WHERE phone=?", (phone,)).fetchone()
            if exists: continue

            score, prob, plan, reason = score_model(line)

            c.execute("""
            INSERT INTO customers
            (name,contact,area,phone,status,score,prob,plan,reason,source,created)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,(name,contact,area,phone,"未联系",score,prob,plan,reason,"import",datetime.date.today()))

        except:
            continue

    conn.commit()
    return redirect("/import_page")

# ===== 自动抓取 =====
@app.route("/auto_fetch")
def auto_fetch():
    data = generate_data()

    for text in data:
        try:
            name, contact, area, phone = extract(text)

            exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
            if exists: continue

            score, prob, plan, reason = score_model(text)

            c.execute("""
            INSERT INTO customers
            (name,contact,area,phone,status,score,prob,plan,reason,source,created)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,(name,contact,area,"","未联系",score,prob,plan,reason,"auto",datetime.date.today()))

        except:
            continue

    conn.commit()
    return redirect("/auto_page")

app.run(host="0.0.0.0", port=8080)
