from flask import Flask, redirect, request
import sqlite3

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据表（已包含地区/行业）=====
c.execute('''
CREATE TABLE IF NOT EXISTS companies (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
phone TEXT,
contact TEXT,
area TEXT,
industry TEXT,
score INTEGER,
status TEXT
)
''')
conn.commit()


# ===== 评分系统（核心）=====
def calculate_score(name, industry):
    score = 0

    # 行业加分（融资需求强）
    if industry in ["工程", "建设"]:
        score += 4
    if industry in ["制造", "科技"]:
        score += 3

    # 名称关键词
    if any(k in name for k in ["工程", "建设", "项目"]):
        score += 3
    if any(k in name for k in ["投资", "资本"]):
        score -= 2

    return score


# ===== 首页 + 筛选 =====
@app.route("/")
def home():
    area = request.args.get("area", "")
    industry = request.args.get("industry", "")
    min_score = request.args.get("score", "")
    status = request.args.get("status", "")

    query = "SELECT * FROM companies WHERE 1=1"
    params = []

    if area:
        query += " AND area LIKE ?"
        params.append(f"%{area}%")

    if industry:
        query += " AND industry LIKE ?"
        params.append(f"%{industry}%")

    if min_score:
        query += " AND score >= ?"
        params.append(int(min_score))

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY score DESC"

    data = c.execute(query, params).fetchall()

    html = "<h3>🔥 深圳融资客户系统（筛选版）</h3>"

    # ===== 导入 =====
    html += """
    <h4>导入客户</h4>
    <form action="/import" method="post">
    <textarea name="data" rows="6" cols="35" placeholder="公司,电话,联系人,地区,行业"></textarea><br>
    <button>导入</button>
    </form>
    <br>
    """

    # ===== 筛选 =====
    html += f"""
    <h4>筛选</h4>
    <form method="get">
    地区：<input name="area" value="{area}" placeholder="南山"><br>
    行业：<input name="industry" value="{industry}" placeholder="工程"><br>
    最低评分：<input name="score" value="{min_score}" placeholder="3"><br>
    状态：
    <select name="status">
        <option value="">全部</option>
        <option value="未联系">未联系</option>
        <option value="已联系">已联系</option>
        <option value="已成交">已成交</option>
    </select><br>
    <button>筛选</button>
    </form>
    <br>
    """

    # ===== 清空 =====
    html += """
    <form action="/clear" method="post">
    <button style="color:red;">清空全部数据</button>
    </form>
    <br>
    """

    # ===== 列表 =====
    for d in data:
        level = "🔥优先打" if d[6] >= 5 else "普通"
        contact = d[3] if d[3] else "无"

        html += f"""
        <div style="border:1px solid #ccc;padding:10px;margin:10px;">
        <b>{d[1]}</b><br>
        联系人：{contact}<br>
        电话：{d[2]}<br>
        地区：{d[4]}<br>
        行业：{d[5]}<br>
        评分：{d[6]}（{level}）<br>
        状态：{d[7]}<br>

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


# ===== 导入 =====
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
            area = parts[3].strip() if len(parts) > 3 else ""
            industry = parts[4].strip() if len(parts) > 4 else ""

            score = calculate_score(name, industry)

            c.execute(
                "INSERT INTO companies (name, phone, contact, area, industry, score, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, phone, contact, area, industry, score, "未联系")
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


# ===== 清空 =====
@app.route("/clear", methods=["POST"])
def clear():
    c.execute("DELETE FROM companies")
    conn.commit()
    return redirect("/")


app.run(host="0.0.0.0", port=8080)
