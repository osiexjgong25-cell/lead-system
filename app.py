from flask import Flask, redirect, request
import sqlite3
import datetime

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 初始化 =====
c.execute('''
CREATE TABLE IF NOT EXISTS companies (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
phone TEXT,
contact TEXT,
area TEXT,
industry TEXT,
size TEXT,
stage TEXT,
score INTEGER,
level TEXT,
tag TEXT,
status TEXT,
last_contact TEXT,
note TEXT
)
''')
conn.commit()


# ===== 行业识别 =====
def detect_industry(name):
    mapping = {
        "工程": ["工程", "建设", "施工"],
        "制造": ["制造", "工厂"],
        "科技": ["科技", "软件"],
        "新能源": ["新能源", "光伏"],
        "贸易": ["贸易", "进出口"],
    }
    for k, v in mapping.items():
        if any(x in name for x in v):
            return k
    return "其他"


# ===== 体量识别 =====
def detect_size(name):
    if "集团" in name:
        return "大"
    elif "有限公司" in name:
        return "中"
    else:
        return "小"


# ===== 融资阶段 =====
def detect_stage(name):
    if "融资" in name:
        return "融资中"
    elif any(k in name for k in ["扩产", "建厂"]):
        return "扩张"
    else:
        return "未知"


# ===== 评分系统 =====
def calculate_score(name):
    score = 0
    tag = []

    if "工程" in name or "项目" in name:
        score += 5
        tag.append("项目")

    if any(k in name for k in ["扩产", "投资"]):
        score += 4
        tag.append("扩张")

    if "融资" in name:
        score += 4
        tag.append("融资")

    if any(k in name for k in ["科技", "制造"]):
        score += 2

    if any(k in name for k in ["被执行", "失信"]):
        score -= 4
        tag.append("风险")

    return score, ",".join(tag)


# ===== 客户等级 =====
def get_level(score):
    if score >= 8:
        return "A"
    elif score >= 5:
        return "B"
    else:
        return "C"


# ===== 智能话术 =====
def get_script(industry, size, stage):
    if stage == "融资中":
        return "直接切融资方案：我们这边有更低成本资金渠道，可以帮你优化现有融资结构。"

    if stage == "扩张":
        return "切扩张资金：很多企业在扩产阶段会做融资，你们这块有规划吗？"

    if industry == "工程":
        return "切项目垫资：做工程项目资金压力大，我们可以做过桥/垫资。"

    if size == "大":
        return "切资本合作：我们有机构资金，可以配合你做结构化融资。"

    return "通用话术：我们这边做企业融资优化，可以帮你降低资金成本。"


# ===== 首页 =====
@app.route("/")
def home():
    data = c.execute("SELECT * FROM companies ORDER BY score DESC").fetchall()

    html = "<h3>🔥 FA客户管理系统（职业版）</h3>"

    html += """
    <form action="/import" method="post">
    <textarea name="data" placeholder="公司,电话,联系人,地区"></textarea><br>
    <button>导入</button>
    </form><br>
    """

    html += """
    <a href="/tasks">📊 今日任务</a> |
    <a href="/priority">🔥 A类客户</a><br><br>
    """

    for d in data:
        html += f"""
        <div style="border:1px solid #ccc;margin:10px;padding:10px;">
        <b>{d[1]}</b><br>
        行业：{d[5]} | 体量：{d[6]} | 阶段：{d[7]}<br>
        电话：{d[2]}<br>
        评分：{d[8]} | 等级：{d[9]}<br>
        标签：{d[10]}<br>
        状态：{d[11]}<br>
        备注：{d[13]}<br>

        <form action="/update/{d[0]}" method="post">
        <select name="status">
        <option>未联系</option>
        <option>已联系</option>
        <option>已成交</option>
        </select>
        <input name="note" placeholder="备注">
        <button>更新</button>
        </form>

        <a href="/script/{d[0]}">📞 话术</a>
        </div>
        """

    return html


# ===== 导入 =====
@app.route("/import", methods=["POST"])
def import_data():
    for line in request.form["data"].split("\n"):
        if not line.strip():
            continue

        p = line.split(",")
        name = p[0].strip()
        phone = p[1].strip()

        exists = c.execute("SELECT id FROM companies WHERE name=? AND phone=?", (name, phone)).fetchone()
        if exists:
            continue

        industry = detect_industry(name)
        size = detect_size(name)
        stage = detect_stage(name)
        score, tag = calculate_score(name)
        level = get_level(score)

        c.execute("""
        INSERT INTO companies (name, phone, contact, area, industry, size, stage, score, level, tag, status, last_contact, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, phone, "", "", industry, size, stage, score, level, tag, "未联系", "", ""))

    conn.commit()
    return redirect("/")


# ===== 更新 =====
@app.route("/update/<id>", methods=["POST"])
def update(id):
    status = request.form["status"]
    note = request.form.get("note", "")
    now = datetime.date.today().isoformat()

    c.execute("UPDATE companies SET status=?, note=?, last_contact=? WHERE id=?",
              (status, note, now, id))
    conn.commit()
    return redirect("/")


# ===== 今日任务 =====
@app.route("/tasks")
def tasks():
    data = c.execute("SELECT * FROM companies ORDER BY score DESC").fetchall()

    html = "<h3>📊 今日任务</h3><a href='/'>返回</a><br>"

    for d in data[:20]:
        html += f"<p>{d[1]} | 电话：{d[2]} | 优先级：{d[8]}</p>"

    return html


# ===== A类客户 =====
@app.route("/priority")
def priority():
    data = c.execute("SELECT * FROM companies WHERE level='A'").fetchall()

    html = "<h3>🔥 A类客户</h3><a href='/'>返回</a><br>"

    for d in data:
        html += f"<p>{d[1]} | 电话：{d[2]}</p>"

    return html


# ===== 话术 =====
@app.route("/script/<id>")
def script(id):
    d = c.execute("SELECT * FROM companies WHERE id=?", (id,)).fetchone()
    text = get_script(d[5], d[6], d[7])

    return f"<h3>话术</h3><a href='/'>返回</a><br>{text}"


app.run(host="0.0.0.0", port=8080)
