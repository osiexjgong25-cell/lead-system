from flask import Flask, redirect, request
import sqlite3
import datetime
import re

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 初始化数据库 =====
def init_db():
    c.execute('''
    CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    industry TEXT,
    score INTEGER,
    level TEXT,
    status TEXT,
    owner TEXT,
    last_contact TEXT,
    note TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
    )
    ''')

    conn.commit()

init_db()

# ===== 防字段缺失（兼容旧库）=====
def fix_db():
    fields = ["owner", "note", "last_contact"]
    for f in fields:
        try:
            c.execute(f"ALTER TABLE companies ADD COLUMN {f} TEXT")
        except:
            pass
    conn.commit()

fix_db()

# ===== 评分系统 =====
def calculate_score(name):
    score = 0

    if any(k in name for k in ["工程","项目"]): score += 5
    if any(k in name for k in ["扩产","投资"]): score += 4
    if "融资" in name: score += 4
    if any(k in name for k in ["科技","制造"]): score += 2
    if any(k in name for k in ["失信","被执行"]): score -= 4

    return score

def get_level(score):
    if score >= 8: return "A"
    if score >= 5: return "B"
    return "C"

# ===== 提取电话（超强）=====
def extract_phone(text):
    mobile = re.search(r'1[3-9]\d{9}', text)
    if mobile:
        return mobile.group()

    tel = re.search(r'0\d{2,3}-?\d{7,8}', text)
    if tel:
        return tel.group()

    return None

# ===== 清洗公司名 =====
def clean_name(text):
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9（）()]', '', text)
    return text[:50]

# ===== 首页 =====
@app.route("/")
def home():
    users = c.execute("SELECT * FROM users").fetchall()
    data = c.execute("SELECT * FROM companies ORDER BY score DESC").fetchall()

    html = "<h3>🔥 FA团队系统（终极版）</h3>"

    # 添加成员
    html += """
    <h4>添加团队成员</h4>
    <form action="/add_user" method="post">
    <input name="name" placeholder="名字">
    <button>添加</button>
    </form><br>
    """

    # 导入
    html += """
    <h4>导入客户（支持乱格式）</h4>
    <form action="/import" method="post">
    <textarea name="data" rows="6" cols="35" placeholder="随便粘数据"></textarea><br>
    <button>导入</button>
    </form><br>
    """

    # 功能入口
    html += """
    <a href="/tasks">📊 今日任务</a> |
    <a href="/stats">📈 转化统计</a><br><br>
    """

    # 客户列表
    for d in data:
        html += f"""
        <div style="border:1px solid #ccc;margin:10px;padding:10px;">
        <b>{d[1]}</b><br>
        电话：{d[2]}<br>
        评分：{d[4]} | 等级：{d[5]}<br>
        状态：{d[6]}<br>
        负责人：{d[7] or '未分配'}<br>
        备注：{d[9] or ''}<br>

        <form action="/assign/{d[0]}" method="post">
        <select name="owner">
        {''.join([f"<option>{u[1]}</option>" for u in users])}
        </select>
        <button>分配</button>
        </form>

        <form action="/update/{d[0]}" method="post">
        <select name="status">
        <option>未联系</option>
        <option>已联系</option>
        <option>已成交</option>
        </select>
        <input name="note" placeholder="备注">
        <button>更新</button>
        </form>
        </div>
        """

    return html

# ===== 添加成员 =====
@app.route("/add_user", methods=["POST"])
def add_user():
    name = request.form.get("name","").strip()
    if name:
        c.execute("INSERT INTO users (name) VALUES (?)", (name,))
        conn.commit()
    return redirect("/")

# ===== 超强容错导入 =====
@app.route("/import", methods=["POST"])
def import_data():
    raw = request.form.get("data", "")

    success = 0
    skip = 0

    for line in raw.split("\n"):
        try:
            if not line.strip():
                continue

            phone = extract_phone(line)
            if not phone:
                skip += 1
                continue

            name_part = line.replace(phone, "")
            name = clean_name(name_part)

            if len(name) < 4:
                skip += 1
                continue

            exists = c.execute(
                "SELECT id FROM companies WHERE phone=?",
                (phone,)
            ).fetchone()

            if exists:
                skip += 1
                continue

            score = calculate_score(name)
            level = get_level(score)

            c.execute("""
            INSERT INTO companies (name, phone, industry, score, level, status, owner, last_contact, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, phone, "", score, level, "未联系", "", "", ""))

            success += 1

        except:
            skip += 1
            continue

    conn.commit()

    return f"""
    <h3>导入完成</h3>
    成功：{success} 条<br>
    跳过：{skip} 条<br><br>
    <a href="/">返回</a>
    """

# ===== 分配 =====
@app.route("/assign/<id>", methods=["POST"])
def assign(id):
    owner = request.form.get("owner","")
    c.execute("UPDATE companies SET owner=? WHERE id=?", (owner, id))
    conn.commit()
    return redirect("/")

# ===== 更新 =====
@app.route("/update/<id>", methods=["POST"])
def update(id):
    status = request.form.get("status","未联系")
    note = request.form.get("note","")
    now = datetime.date.today().isoformat()

    c.execute("""
    UPDATE companies SET status=?, note=?, last_contact=? WHERE id=?
    """, (status, note, now, id))

    conn.commit()
    return redirect("/")

# ===== 今日任务 =====
@app.route("/tasks")
def tasks():
    users = c.execute("SELECT * FROM users").fetchall()
    html = "<h3>📊 今日任务</h3><a href='/'>返回</a><br>"

    for u in users:
        data = c.execute(
            "SELECT * FROM companies WHERE owner=? ORDER BY score DESC",
            (u[1],)
        ).fetchall()

        html += f"<h4>{u[1]}</h4>"
        for d in data[:10]:
            html += f"<p>{d[1]} | {d[2]} | 评分:{d[4]}</p>"

    return html

# ===== 转化统计 =====
@app.route("/stats")
def stats():
    total = c.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    deal = c.execute("SELECT COUNT(*) FROM companies WHERE status='已成交'").fetchone()[0]

    rate = round(deal/total*100,2) if total else 0

    return f"""
    <h3>📈 转化统计</h3>
    <a href="/">返回</a><br><br>
    总客户：{total}<br>
    已成交：{deal}<br>
    成交率：{rate}%
    """

app.run(host="0.0.0.0", port=8080)
