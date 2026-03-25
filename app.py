from flask import Flask, request, redirect, Response
import sqlite3, datetime, requests, re

app = Flask(__name__)

conn = sqlite3.connect('fa_pro.db', check_same_thread=False)
c = conn.cursor()

# ===== 数据库 =====
c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
clean_name TEXT,
industry TEXT,
amount INTEGER,
source TEXT,
legal_person TEXT,
contact TEXT,
phone TEXT,
score INTEGER,
level TEXT,
status TEXT,
reason TEXT,
script TEXT,
created TEXT
)
''')

conn.commit()

# ===== 名称清洗（集团识别）=====
def clean_name(name):
    if not name: return ""
    name = re.sub(r"(有限公司|集团|股份|控股)", "", name)
    return name.strip()

# ===== 官网电话抓取 =====
def get_phone(name):
    try:
        html = requests.get(f"https://www.baidu.com/s?wd={name}", timeout=5).text
        p = re.search(r'0\d{2,3}-\d{7,8}', html)
        return p.group() if p else ""
    except:
        return ""

# ===== API获取企业信息（可接入真实）=====
def get_company_info(name):
    # 👉 这里可以换企查查API
    return {
        "legalPerson": "",
        "contact": ""
    }

# ===== AI话术（核心升级）=====
def generate_script(d):
    script = ""

    if d["industry"] == "建筑":
        script += "你们工程项目应该有垫资压力，"

    if d["source"] == "被执行":
        script += "最近资金压力可能比较明显，"

    if d["amount"] > 5000:
        script += "而且项目金额不小，"

    script += "我们这边可以帮你对接低成本资金，看看有没有合作空间？"

    return script

# ===== 评分 =====
def score_model(d):
    score = 0
    reason = []

    if d["industry"] == "建筑":
        score += 50
        reason.append("工程行业")

    if d["amount"] > 5000:
        score += 50
        reason.append("大额项目")

    if d["source"] in ["招投标","被执行"]:
        score += 40
        reason.append("强融资信号")

    if score >= 100:
        level = "A"
    elif score >= 70:
        level = "B"
    else:
        level = "C"

    return score, level, "；".join(reason)

# ===== 模拟数据（可替换API）=====
def fetch_data():
    return [
        {"name":"深圳市中建南方工程有限公司","industry":"建筑","amount":8000,"source":"招投标"},
        {"name":"深圳市中建南方工程集团","industry":"建筑","amount":6000,"source":"被执行"},
        {"name":"深圳某科技公司","industry":"科技","amount":0,"source":"融资新闻"},
    ]

# ===== 核心处理 =====
def process():
    data = fetch_data()

    for d in data:
        cname = clean_name(d["name"])

        # 集团去重
        exists = c.execute("SELECT id FROM customers WHERE clean_name=?", (cname,)).fetchone()
        if exists:
            continue

        info = get_company_info(d["name"])

        phone = get_phone(d["name"])

        score, level, reason = score_model(d)
        script = generate_script(d)

        c.execute("""
        INSERT INTO customers
        (name,clean_name,industry,amount,source,legal_person,contact,phone,score,level,status,reason,script,created)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
            d["name"],
            cname,
            d["industry"],
            d["amount"],
            d["source"],
            info.get("legalPerson",""),
            info.get("contact",""),
            phone,
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
    👤 法人:{d[6] or "未知"}<br>
    📞 电话:{d[8] or "未获取"}<br>
    ⭐{d[9]} 等级:{d[10]}<br>
    状态:{d[11]}<br>
    💡{d[12]}<br>
    🧠{d[13]}<br>

    <a href='/update/{d[0]}/已联系'>已联系</a> |
    <a href='/update/{d[0]}/跟进中'>跟进</a> |
    <a href='/update/{d[0]}/成交'>成交</a>
    </div>
    """

def html(body):
    return f"<html><body style='font-family:-apple-system;background:#f2f2f7'>{body}</body></html>"

# ===== 页面 =====
@app.route("/")
def home():
    return html("""
    <h2>FA成交系统（终极版）</h2>
    <a href='/run'>抓数据</a><br><br>
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
