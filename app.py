from flask import Flask, redirect, request
import sqlite3
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS companies (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
status TEXT
)
''')
conn.commit()

@app.route("/")
def home():
    data = c.execute("SELECT * FROM companies").fetchall()

    html = "<h3>融资客户系统</h3>"
    html += '<a href="/run">抓客户</a><br><br>'

    for d in data:
        html += f"""
        <div style="border:1px solid #ccc;padding:10px;margin:10px;">
        {d[1]}<br>
        状态：{d[2]}<br>
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

@app.route("/run")
def run():
    url = "https://news.baidu.com/"
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")

    for item in soup.select(".hotnews a")[:10]:
        title = item.text.strip()
        c.execute("INSERT INTO companies (name, status) VALUES (?, ?)", (title, "未联系"))

    conn.commit()
    return redirect("/")

@app.route("/update/<id>", methods=["POST"])
def update(id):
    status = request.form["status"]
    c.execute("UPDATE companies SET status=? WHERE id=?", (status, id))
    conn.commit()
    return redirect("/")

app.run(host="0.0.0.0", port=8080)
