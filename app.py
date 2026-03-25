from flask import Flask, redirect, Response
import sqlite3, datetime, requests, re

app = Flask(__name__)

# ===== KEY（可空）=====
KAIDANGUO_KEY = ""
QCC_KEY = ""

conn = sqlite3.connect('fa_final_pro.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据库 =====
c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
clean_name TEXT,
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

# ===== 名称清洗（防重复）=====
def clean_name(name):
    return re.sub(r"(有限公司|集团|股份|控股)", "", name or "").strip()

# ===== 开单果 =====
def get_kaidanguo():
    if not KAIDANGUO_KEY:
        return []

    try:
        res = requests.get(
            "https://api.kaidanguo.com/company/search",
            headers={"Authorization": KAIDANGUO_KEY},
            timeout=5
        )
        data = res.json()

        result = []
        for i in data.get("data", []):
            result.append({
                "name": i.get("companyName"),
                "industry": i.get("industry",""),
                "legal": i.get("legalPerson",""),
                "phone": i.get("phone",""),
                "source": "开单果"
            })
        return result

    except:
        return []

# ===== 企查查 =====
def get_qcc(name):
    if not QCC_KEY:
        return {}

    try:
        url = f"https://api.qichacha.com/ECI/GetDetails?key={QCC_KEY}&keyword={name}"
        r = requests.get(url, timeout=5).json()

        return {
            "legal": r.get("Result",{}).get("OperName",""),
            "phone": r.get("Result",{}).get("ContactNumber","")
        }
    except:
        return {}

# ===== 官网电话 =====
def get_web_phone(name):
    try:
        html = requests.get(f"https://www.baidu.com/s?wd={name}", timeout=5).text
        m = re.search(r'1[3-9]\d{9}|0\d{2,3}-\d{7,8}', html)
        return m.group() if m else ""
    except:
        return ""

# ===== 电话融合 =====
def get_phone(d):
    if d.get("phone"):
        return d["phone"], "开单果"

    q = get_qcc(d["name"])
    if q.get("phone"):
        return q["phone"], "企查查"

    w = get_web_phone(d["name"])
    if w:
        return w, "官网"

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
        reason.append("强数据源")

    if score >= 80:
        level = "A"
    elif score >= 60:
        level = "B"
    else:
        level = "C"

    return score, level, "；".join(reason)

# ===== AI话术 =====
def make_script(d):
    legal = d.get("legal","")
    base = f"{legal+'总' if legal else ''}您好，"

    if d.get("industry") == "建筑":
        base += "你们项目垫资压力应该不小，"

    base += "我们可以帮你对接资金渠道，简单沟通一下？"
    return base

# ===== 本地兜底数据（保证系统必有数据）=====
def fallback_data():
    return [
        {"name":"深圳市中建南方工程有限公司","industry":"建筑","legal":"","phone":"","source":"本地"},
        {"name":"深圳某贸易公司","industry":"贸易","legal":"","phone":"","source":"本地"}
    ]

# ===== 主流程 =====
def process():
    data = get_kaidanguo()

    # 👉 没API数据就用本地
    if not data:
        data = fallback_data()

    for d in data:
        cname = clean_name(d.get("name"))
        if not cname:
            continue

        exists = c.execute("SELECT id FROM customers WHERE clean_name=?", (cname,)).fetchone()
        if exists:
            continue

        phone, p_source = get_phone(d)

        score, level, reason = score_model(d)
        script = make_script(d)

        c.execute("""
        INSERT INTO customers
        (name,clean_name,industry,legal_person,phone,phone_source,source,score,level,status,reason,script,created)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
            d.get("name"),
            cname,
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
    <div style='background:white;margin:10px;padding:12px;border-radius:10px'>
    <b>{d[1]}</b><br>
    👤 法人:{d[4] or "未知"}<br>
    📞 {d[5] or "无"}（{d[6]}）<br>
    来源:{d[7]}<br>
    ⭐{d[8]} 等级:{d[9]}<br>
    状态:{d[10]}<br>
    💡{d[11]}<br>
    📣{d[12]}<br>

    <a href='tel:{d[5]}'>📞拨号</a> |
    <a href='/update/{d[0]}/已联系'>已联系</a> |
    <a href='/update/{d[0]}/跟进中'>跟进</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    """

def html(body):
    return f"<html><body style='font-family:-apple-system;background:#f2f2f7'>{body}</body></html>"

@app.route("/")
def home():
    return html("""
    <h2>FA成交系统（最终版）</h2>
    <a href='/run'>抓客户</a><br><br>
    <a href='/list'>客户池</a><br><br>
    <a href='/today'>今日必打</a>
    """)

@app.route("/run")
def run():
    process()
    return redirect("/list")

@app.route("/list")
def list_data():
    data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()
    return html("".join([render(d) for d in data]))

@app.route("/today")
def today():
    data = c.execute("SELECT * FROM customers WHERE level='A' ORDER BY score DESC LIMIT 10").fetchall()
    return html("<h3>今日必打</h3>" + "".join([render(d) for d in data]))

@app.route("/update/<id>/<status>")
def update(id,status):
    c.execute("UPDATE customers SET status=? WHERE id=?", (status,id))
    conn.commit()
    return redirect("/list")

@app.route("/export")
def export():
    data = c.execute("SELECT name,phone,script FROM customers WHERE level='A'").fetchall()
    return Response("\n".join([f"{d[0]} {d[1]} {d[2]}" for d in data]), mimetype="text/plain")

app.run(host="0.0.0.0", port=8080)
