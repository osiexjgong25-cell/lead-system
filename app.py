from flask import Flask, redirect, Response
import sqlite3, datetime, requests, re

app = Flask(__name__)

# ===== 填你的KEY =====
QCC_KEY = "你的企查查KEY"
TYC_KEY = "你的天眼查KEY"

conn = sqlite3.connect('fa_real.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
industry TEXT,
legal_person TEXT,
phone TEXT,
phone_source TEXT,
score INTEGER,
level TEXT,
status TEXT,
reason TEXT,
script TEXT,
created TEXT
)
''')

conn.commit()

# ===== 企业API（企查查示例）=====
def get_company_api(name):
    try:
        url = f"https://api.qichacha.com/ECI/GetDetails?key={QCC_KEY}&keyword={name}"
        res = requests.get(url, timeout=5)
        data = res.json()

        return {
            "legal": data.get("Result",{}).get("OperName",""),
            "phone": data.get("Result",{}).get("ContactNumber","")
        }
    except:
        return {"legal":"","phone":""}

# ===== 官网抓电话 =====
def get_web_phone(name):
    try:
        html = requests.get(f"https://www.baidu.com/s?wd={name}", timeout=5).text
        p = re.search(r'0\d{2,3}-\d{7,8}', html)
        return p.group() if p else ""
    except:
        return ""

# ===== 招聘电话 =====
def get_job_phone(name):
    try:
        html = requests.get(f"https://www.baidu.com/s?wd={name}+招聘", timeout=5).text
        p = re.search(r'1[3-9]\d{9}', html)
        return p.group() if p else ""
    except:
        return ""

# ===== 电话整合 =====
def get_best_phone(name):
    api = get_company_api(name)
    if api["phone"]:
        return api["phone"], "企业API"

    web = get_web_phone(name)
    if web:
        return web, "官网"

    job = get_job_phone(name)
    if job:
        return job, "招聘"

    return "", "无"

# ===== 评分 =====
def score_model(d):
    score = 0
    reason = []

    if d["industry"] == "建筑":
        score += 50
        reason.append("工程行业")

    if d["source"] in ["招投标","被执行"]:
        score += 40
        reason.append("强融资信号")

    if score >= 80:
        level = "A"
    elif score >= 60:
        level = "B"
    else:
        level = "C"

    return score, level, "；".join(reason)

# ===== AI话术 =====
def make_script(name, legal):
    return f"{legal}总您好，我们这边是做企业融资的，看到你们公司近期项目比较多，想简单沟通下资金合作。"

# ===== 数据源（可替换）=====
def fetch_data():
    return [
        {"name":"深圳市中建南方工程有限公司","industry":"建筑","source":"招投标"},
        {"name":"深圳某贸易公司","industry":"贸易","source":"被执行"}
    ]

# ===== 主流程 =====
def process():
    for d in fetch_data():

        exists = c.execute("SELECT id FROM customers WHERE name=?", (d["name"],)).fetchone()
        if exists:
            continue

        info = get_company_api(d["name"])
        phone, source = get_best_phone(d["name"])

        score, level, reason = score_model(d)
        script = make_script(d["name"], info["legal"])

        c.execute("""
        INSERT INTO customers
        (name,industry,legal_person,phone,phone_source,score,level,status,reason,script,created)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,(
            d["name"],
            d["industry"],
            info["legal"],
            phone,
            source,
            score,
            level,
            "未联系",
            reason,
            script,
            datetime.date.today()
        ))

    conn.commit()

# ===== UI =====
def render(d):
    return f"""
    <div style='background:white;padding:15px;margin:10px;border-radius:12px'>
    <b>{d[1]}</b><br>
    👤 法人:{d[3] or "未知"}<br>
    📞 电话:{d[4] or "未获取"}（{d[5]}）<br>
    ⭐{d[6]} 等级:{d[7]}<br>
    状态:{d[8]}<br>
    💡{d[9]}<br>
    📣{d[10]}<br>

    <a href='tel:{d[4]}'>📞拨号</a> |
    <a href='/update/{d[0]}/已联系'>已联系</a> |
    <a href='/update/{d[0]
