from flask import Flask, redirect, request
import sqlite3

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

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


# ===== 模拟真实客户数据（先跑通系统）=====
def get_demo_data():
    return [
        ("深圳市XX建设工程有限公司", "13800138000", "张经理", 8),
        ("深圳某新能源科技公司", "0755-12345678", "李总", 7),
        ("深圳某制造企业", "13900001111", "", 6),
        ("深圳某投资公司", "待补", "", 5),
    ]


# ===== 抓客户（先用模拟数据）=====
@app.route("/run")
def run():
    data = get_demo_data()

    for d in data:
        c.execute(
            "INSERT INTO companies (name, phone, contact, score, status) VALUES (?, ?, ?, ?, ?)",
            (d[0], d[1], d[2], d[3], "未联系")
        )

    conn.commit()
    return redirect("/")


# ===== 首页 =====
@app.route("/")
def home():
    data = c.execute("SELECT * FROM companies ORDER BY score DESC").fetchall()

    html = "<h3>🔥 深圳融资客户（测试版）</h3>"
    html += '<a href="/run">抓客户</a><br><br>'

    for d in data:
        contact_display = d[3] if d[3] else "无"
        level = "🔥高意向" if d[4] >= 7 else "普通"

        html += f"""
        <div style="border:1px solid #ccc;padding:10px;margin:10px;">
        <b>{d[1]}</b><br>
        联系人：{contact_display}<br>
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


@app.route("/update/<id>", methods=["POST"])
def update(id):
    status = request.form["status"]
    c.execute("UPDATE companies SET status=? WHERE id=?", (status, id))
    conn.commit()
    return redirect("/")


app.run(host="0.0.0.0", port=8080)
