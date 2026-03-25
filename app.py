from flask import Flask, redirect, Response
import sqlite3, datetime, requests, re

app = Flask(__name__)

# ===== 填KEY =====
KAIDANGUO_KEY = "你的开单果KEY"
QCC_KEY = "你的企查查KEY"

conn = sqlite3.connect('fa_final_real.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
industry TEXT,
legal_person TEXT,
phone TEXT,
phone_source TEXT,
source TEXT,
score INTEGER,
level TEXT,
status TEXT,
reason TEXT,
script TEXT,
created TEXT
)
''')

conn.commit()

# ===== 开单果API =====
def get_kaidanguo_data(keyword="深圳"):
    try:
        url = "https://api.kaidanguo.com/company/search"  # 示例地址（需替换真实接口）
        headers = {
            "Authorization": KAIDANGUO_KEY
        }
        params = {"keyword": keyword}

        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()

        result = []
        for item in data.get("data", []):
            result.append({
                "name": item.get("companyName"),
                "industry": item.get("industry"),
                "legal": item.get("legalPerson"),
                "phone": item.get("phone"),
                "source": "开单果"
            })

        return result

    except Exception as e:
        print("开单果错误:", e)
        return []

# ===== 企查查 =====
def get_qcc_data(name):
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

# ===== 电话整合 =====
def get_phone(data):
    if data.get("phone"):
        return data["phone"], "开单果"

    qcc = get_qcc_data(data["name"])
    if qcc["phone"]:
        return qcc["phone"], "企查查"

    web = get_web_phone(data["name"])
    if web:
        return web, "官网"

    return "", "无"

# ===== 评分 =====
def score_model(d):
    score = 0
    reason = []

    if d.get("industry") in ["建筑","工程"]:
        score += 50
        reason.append("工程行业")

    if d.get("source") in ["开单果","招投标"]:
        score += 40
        reason.append("数据源强")

    if score >= 80:
        level = "A"
    elif score >= 60:
        level = "B"
    else:
        level = "C"

    return score, level, "；".join(reason)

# ===== AI话术 =====
def make_script(name, legal):
    if legal:
        return f"{legal}总您好，我们看到您公司近期业务活跃，想对接融资合作。"
    return f"{name}您好，我们这边有资金渠道，想和您对接合作。"

# ===== 主流程 =====
def process():
    data = get_kaidanguo_data()

    for d in data:
        if not d.get("name"):
            continue

        exists = c.execute("SELECT id FROM customers WHERE name=?", (d["name"],)).fetchone()
        if exists:
            continue

        phone, p_source = get_phone(d)

        score, level, reason = score_model(d)
        script = make_script(d["name"], d.get("legal"))

        c.execute("""
        INSERT INTO customers
        (name,industry,legal_person,phone,phone_source,source,score,level,status,reason,script,created)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
            d["name"],
            d.get("industry",""),
            d.get("legal",""),
            phone,
            p_source,
            d.get("source",""),
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
    来源:{d[6]}<br>
    ⭐{d[7]} 等级:{d[8]}<br>
    💡{d[10]}<br>
    📣{d[11]}<br>

    <a href='tel:{d[4]}'>📞拨号</a>
    </div>
    """

def html(body):
    return f"<html><body style='font-family:-apple-system;background:#f2f2f7'>{body}</body></html>"

@app.route("/")
def home():
    return html("""
    <h2>FA成交系统（开单果版）</h2>
    <a href='/run'>抓真实数据</a><br><br>
    <a href='/list'>客户列表</a>
    """)

@app.route("/run")
def run():
    process()
    return redirect("/list")

@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()
    return html("".join([render(d) for d in data]))

app.run(host="0.0.0.0", port=8080)
