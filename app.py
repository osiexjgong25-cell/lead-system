from flask import Flask, redirect, request
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据表（已包含联系人）=====
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


# ===== 评分系统 =====
def calculate_score(text):
    score = 0

    if any(k in text for k in ["中标", "项目"]):
        score += 5
    if any(k in text for k in ["扩产", "投资"]):
        score += 4
    if "融资" in text:
        score += 4
    if any(k in text for k in ["科技", "工程", "制造"]):
        score += 2
    if any(k in text for k in ["被执行", "失信"]):
        score -= 3

    return score


# ===== 提取电话 =====
def extract_phone(html):
    phones = re.findall(r'1[3-9]\d{9}', html)
    tels = re.findall(r'0\d{2,3}-\d{7,8}', html)

    if phones:
        return phones[0]
    if tels:
        return tels[0]

    return None


# ===== 提取联系人（升级点）=====
def extract_contact(html):
    # 常见：联系人：张三
    match = re.findall(r'联系人[:：]\s?([\u4e00-\u9fa5]{2,4})', html)

    if match:
        return match[0]

    # 常见：项目负责人：李四
    match2 = re.findall(r'(负责人|经理|联系人)[:：]\s?([\u4e00-\u9fa5]{2,4})', html)
    if match2:
        return match2[0][1]

    return ""


# ===== 找电话 + 联系人 =====
def find_info(name):
    headers = {"User-Agent": "Mozilla/5.0"}

    keywords = [
        name + " 电话",
        name + " 联系方式",
        name + " 官网"
    ]

    for kw in keywords:
        try:
            url = f"https://www.baidu.com/s?wd={kw}"
            res = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")

            for link in soup.select("h3 a"):
                href = link.get("href")

                try:
                    html = requests.get(href, headers=headers, timeout=5).text

                    phone = extract_phone(html)
                    contact = extract_contact(html)

                    if phone:
                        return phone, contact

                except:
                    continue

        except:
            continue

        time.sleep(1)

    return "待补", ""


# ===== 抓客户 =====
@app.route("/run")
def run():
    headers = {"User-Agent": "Mozilla/5.0"}

    url = "https://www.baidu.com/s?wd=深圳 公司 中标 项目"
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    for item in soup.select("h3"):
        text = item.text.strip()

        if "深圳" not in text:
            continue

        score = calculate_score(text)

        if score < 4:
            continue

        name = text[:30]

        phone, contact = find_info(name)

        c.execute(
            "INSERT INTO companies (name, phone, contact, score, status) VALUES (?, ?, ?, ?, ?)",
            (name, phone, contact, score, "未联系")
        )

    conn.commit()
    return redirect("/")


# ===== 首页 =====
@app.route("/")
def home():
    data = c.execute("SELECT * FROM companies ORDER BY score DESC").fetchall()

    html = "<h3>🔥 深圳融资客户（带联系人）</h3>"
    html += '<a href="/run">抓客户</a><br><br>'

    for d in data:
        level = "🔥高意向" if d[4] >= 7 else "普通"

        contact_display = d[3] if d[3] else "无"

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


# ===== 更新状态 =====
@app.route("/update/<id>", methods=["POST"])
def update(id):
    status = request.form["status"]
    c.execute("UPDATE companies SET status=? WHERE id=?", (status, id))
    conn.commit()
    return redirect("/")


app.run(host="0.0.0.0", port=8080)
