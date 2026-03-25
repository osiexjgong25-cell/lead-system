from flask import Flask, redirect, request
import sqlite3, datetime, re, requests

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 初始化数据库 =====
def init_db():
    c.execute('''
    CREATE TABLE IF NOT EXISTS import_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, contact TEXT, area TEXT, phone TEXT UNIQUE,
    score INTEGER, reason TEXT, probability INTEGER, plan TEXT,
    created_at TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS auto_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, area TEXT, phone TEXT,
    score INTEGER, reason TEXT, probability INTEGER, plan TEXT,
    created_at TEXT
    )
    ''')
    conn.commit()

init_db()

# ===== 信息提取 =====
def extract(text):
    phone = re.search(r'1[3-9]\d{9}', text)
    phone = phone.group() if phone else ""

    areas = ["南山","宝安","福田","龙岗","龙华"]
    area = next((a for a in areas if a in text), "")

    name = re.sub(r'\d+|南山|宝安|福田|龙岗|龙华', '', text)
    name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', name)

    return name[:30], area, phone

# ===== 高级评分模型 =====
def score_model(text):
    score = 0
    reasons = []

    if any(x in text for x in ["中标","工程","项目"]):
        score += 30
        reasons.append("存在项目/中标，通常需要垫资或资金周转")

    if any(x in text for x in ["扩产","投资","开店"]):
        score += 25
        reasons.append("企业扩张阶段，存在主动融资需求")

    if "招聘" in text:
        score += 20
        reasons.append("人员扩张，业务增长需要资金支持")

    if any(x in text for x in ["被执行","冻结","资金紧张"]):
        score += 20
        reasons.append("存在资金压力或风险，可能短期融资")

    if any(x in text for x in ["科技","制造","贸易"]):
        score += 10
        reasons.append("行业具备融资活跃度")

    prob = min(95, max(10, score))

    if score >= 70:
        plan = "股权融资 / 项目融资"
    elif score >= 50:
        plan = "过桥资金 / 垫资"
    else:
        plan = "债权优化 / 流贷"

    return score, "；".join(reasons), prob, plan

# ===== 数据源（高质量模拟）=====
def fetch_bid_data():
    return ["深圳建筑公司中标工程项目","南山工程公司中标项目"]

def fetch_hiring_data():
    return ["深圳科技公司扩招团队","宝安制造企业扩产招聘"]

def fetch_risk_data():
    return ["深圳贸易公司被执行","某供应链公司资金紧张"]

# ===== 首页 =====
@app.route("/")
def home():
    return """
    <h2>🚀 FA融资系统（双引擎）</h2>
    <a href="/import_page">📥 我的客户</a><br><br>
    <a href="/auto_page">🔥 系统找客户</a>
    """

# ===== 我的客户 =====
@app.route("/import_page")
def import_page():
    data = c.execute("SELECT * FROM import_data ORDER BY score DESC").fetchall()

    html = """
    <h3>📥 我的客户</h3>
    <form action="/import" method="post">
    <textarea name="data" style="width:100%;height:80px;"></textarea><br>
    <button>导入</button>
    </form><br>
    """

    for d in data:
        html += f"""
        <div style="background:#fff;padding:10px;margin:10px;border-radius:8px">
        <b>{d[1]}</b><br>
        📞 {d[4]}<br>
        ⭐评分：{d[5]}<br>
        📊概率：{d[7]}%<br>
        💡{d[8]}<br>
        🧠{d[6]}<br>
        </div>
        """

    return html + "<br><a href='/'>返回</a>"

# ===== 自动客户 =====
@app.route("/auto_page")
def auto_page():
    data = c.execute("""
    SELECT * FROM auto_data 
    WHERE score >= 50
    ORDER BY score DESC
    """).fetchall()

    html = "<h3>🔥 系统高质量客户</h3>"
    html += "<a href='/auto_fetch'>🔄 刷新抓取</a><br><br>"

    for d in data:
        html += f"""
        <div style="background:#fff;padding:10px;margin:10px;border-radius:8px">
        <b>{d[1]}</b><br>
        📍{d[2]}<br>
        ⭐评分：{d[4]}<br>
        📊概率：{d[6]}%<br>
        💡{d[7]}<br>
        🧠{d[5]}<br>
        </div>
        """

    return html + "<br><a href='/'>返回</a>"

# ===== 导入 =====
@app.route("/import", methods=["POST"])
def import_data():
    raw = request.form.get("data","")

    for line in raw.split("\n"):
        try:
            name, area, phone = extract(line)
            if not phone: continue

            exists = c.execute("SELECT id FROM import_data WHERE phone=?",(phone,)).fetchone()
            if exists: continue

            score, reason, prob, plan = score_model(line)

            c.execute("""
            INSERT INTO import_data (name,area,phone,score,reason,probability,plan,created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,(name,area,phone,score,reason,prob,plan,datetime.date.today()))

        except:
            continue

    conn.commit()
    return redirect("/import_page")

# ===== 自动抓取 =====
@app.route("/auto_fetch")
def auto_fetch():
    data = fetch_bid_data() + fetch_hiring_data() + fetch_risk_data()

    for text in data:
        try:
            name, area, phone = extract(text)

            exists = c.execute("SELECT id FROM auto_data WHERE name=?",(name,)).fetchone()
            if exists: continue

            score, reason, prob, plan = score_model(text)

            c.execute("""
            INSERT INTO auto_data (name,area,phone,score,reason,probability,plan,created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,(name,area or "深圳","",score,reason,prob,plan,datetime.date.today()))

        except:
            continue

    conn.commit()
    return redirect("/auto_page")

# ===== 今日必打 =====
@app.route("/tasks")
def tasks():
    data = c.execute("""
    SELECT * FROM auto_data
    WHERE score >= 60
    ORDER BY score DESC
    """).fetchall()

    html = "<h3>🔥 今日必打</h3>"

    for d in data[:20]:
        html += f"<p>{d[1]} | 概率:{d[6]}%</p>"

    return html + "<br><a href='/'>返回</a>"

app.run(host="0.0.0.0", port=8080)
