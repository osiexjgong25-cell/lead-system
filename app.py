from flask import Flask, redirect, request
import sqlite3

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据表 =====
c.execute('''
CREATE TABLE IF NOT EXISTS companies (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
phone TEXT,
contact TEXT,
score INTEGER,
status TEXT
)
''')
conn.commit()


# ===== 自动评分（融资意向判断）=====
def calculate_score(name):
    score = 0

    if any(k in name for k in ["工程", "建设"]):
        score += 3
    if any(k in name for k in ["科技", "制造"]):
        score += 2
    if any(k in name for k in ["投资", "资本"]):
        score -= 2

    return score


# ===== 首页 =====
@app.route("/")
def home():
    data = c.execute("SELECT * FROM companies ORDER BY score DESC").fetchall()

    html = "<h3> 🇹🇼深圳融资客户系统</h3>"

    # 导入功能
    html += """
    <h4>导入客户（复制粘贴）</h4>
    <form action="/import" method="post">
    <textarea name="data" rows="6" cols="35" placeholder="公司名,电话,联系人"></textarea><br>
    <button>导入</button>
    </form>
    <br>
    """

    for d in data:
        contact = d[3] if d[3] else "无"
        level = "🔥优先打" if d[4] >= 3 else "普通"

        html += f"""
        <div style="border:1px solid #ccc;padding:10px;margin:10px;">
        <b>{d[1]}</b><br>
        联系人：{contact}<br>
        电话：{d[2]}<br>
        评分：{d[4]}（{level}）<br>
        状态：{d[5]}<br>

        <form action="/update/{d[0]}" method="post">
        <select name="status">
        <option>未联系</option>
        <option>已联系</option>
        <option>已成交</option>
        </select>
        <button>更新</button>
        </form>
        </div>
        """

    return html


# ===== 导入数据 =====
@app.route("/import", methods=["POST"])
def import_data():
    data = request.form["data"]

    lines = data.strip().split("\n")

    for line in lines:
        parts = line.split(",")

        if len(parts) >= 2:
            name = parts[0].strip()
            phone = parts[1].strip()
            contact = parts[2].strip() if len(parts) > 2 else ""

            score = calculate_score(name)

            c.execute(
                "INSERT INTO companies (name, phone, contact, score, status) VALUES (?, ?, ?, ?, ?)",
                (name, phone, contact, score, "未联系")
            )

    conn.commit()
    return redirect("/")


# ===== 更新状态 =====
@app.route("/update/<id>", methods=["POST"])
def update(id):
    status = request.form["status"]
    c.execute("UPDATE companies SET status=? WHERE id=?", (status, id))
    conn.commit()
    return redirect("/")


app.run(host="0.0.0.0", port=8080)
