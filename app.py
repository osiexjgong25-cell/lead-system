from flask import Flask, redirect, request
import sqlite3, datetime, re, requests

app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
c = conn.cursor()

# ===== 初始化 + 自动修复 =====
def init_db():
    c.execute('''
    CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    contact TEXT,
    area TEXT,
    phone TEXT,
    score INTEGER,
    level TEXT,
    reason TEXT,
    probability INTEGER,
    plan TEXT,
    status TEXT,
    owner TEXT,
    last_contact TEXT,
    note TEXT
    )
    ''')
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT)')
    conn.commit()

def fix_db():
    fields = ["contact","area","probability","plan","owner","note","last_contact"]
    for f in fields:
        try:
            c.execute(f"ALTER TABLE companies ADD COLUMN {f} TEXT")
        except:
            pass
    conn.commit()

init_db()
fix_db()

# ===== 提取信息 =====
def extract_all(text):
    phone = re.search(r'1[3-9]\d{9}|0\d{2,3}-?\d{7,8}', text)
    phone = phone.group() if phone else ""

    area_match = re.search(r'(南山|宝安|福田|龙岗|龙华|罗湖|盐田)', text)
    area = area_match.group() if area_match else ""

    contact_match = re.search(r'[\u4e00-\u9fa5]{2,3}', text)
    contact = contact_match.group() if contact_match else ""

    name = text
    for x in [phone, area, contact]:
        name = name.replace(x, "")

    name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9（）()]', '', name)
    return name[:40], contact, area, phone

# ===== 基础评分 =====
def base_score(name):
    score = 0
    reasons = []

    if "工程" in name or "项目" in name:
        score += 20; reasons.append("项目")
    if "扩产" in name or "投资" in name:
        score += 20; reasons.append("扩张")
    if "融资" in name:
        score += 15; reasons.append("融资")
    if "制造" in name or "科技" in name:
        score += 10; reasons.append("产业")
    if "被执行" in name:
        score -= 20; reasons.append("风险")

    return score, reasons

# ===== 联网分析 =====
def fetch_info(name):
    try:
        url = f"https://api.duckduckgo.com/?q={name}&format=json"
        res = requests.get(url, timeout=3).json()
        text = str(res)
        return text
    except:
        return ""

def analyze_text(text):
    score = 0
    tags = []

    keywords = {
        "扩张":["扩产","建厂","投资"],
        "融资":["融资","募资"],
        "项目":["中标","工程"],
        "风险":["被执行","诉讼"],
        "招聘":["招聘"]
    }

    for k,v in keywords.items():
        if any(x in text for x in v):
            score += 10
            tags.append(k)

    return score, tags

# ===== 概率 + 方案 =====
def calc_prob(score):
    return min(95, max(10, int(score)))

def get_plan(tags):
    if "扩张" in tags: return "股权融资 / 项目融资"
    if "项目" in tags: return "过桥 / 垫资"
    if "融资" in tags: return "债权优化"
    if "风险" in tags: return "短期过桥"
    return "综合融资"

def get_level(score):
    if score>=70:return "A"
    if score>=40:return "B"
    return "C"

# ===== 首页（北欧风）=====
@app.route("/")
def home():
    data = c.execute("SELECT * FROM companies ORDER BY score DESC").fetchall()

    html = """
    <html><style>
    body{font-family:sans-serif;background:#f5f5f5;padding:20px;}
    .card{background:#fff;padding:15px;margin:10px;border-radius:10px;box-shadow:0 2px 5px #ddd;}
    button{background:#222;color:#fff;border:none;padding:6px 10px;border-radius:6px;}
    textarea{width:100%;padding:10px;}
    </style><body>

    <h2>📊 FA融资系统（终极版）</h2>

    <form action="/import" method="post">
    <textarea name="data" placeholder="粘贴任何数据"></textarea>
    <button>导入</button>
    </form><br>

    <a href="/tasks">今日任务</a> | <a href="/stats">转化统计</a><br><br>
    """

    for d in data:
        html+=f"""
        <div class="card">
        <b>{d[1]}</b><br>
        联系人：{d[2]} ｜ 地区：{d[3]}<br>
        电话：{d[4]}<br>

        评分：{d[5]}（{d[6]}）<br>
        原因：{d[7]}<br>

        融资概率：{d[8]}%<br>
        推荐：{d[9]}<br>

        状态：{d[10]} ｜ 负责人：{d[11] or '未分配'}<br>

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

    return html+"</body></html>"

# ===== 导入 =====
@app.route("/import", methods=["POST"])
def import_data():
    raw=request.form.get("data","")

    for line in raw.split("\n"):
        try:
            if not line.strip():continue

            name,contact,area,phone=extract_all(line)
            if not phone or len(name)<3:continue

            bs,reason=base_score(name)
            text=fetch_info(name)
            es,tags=analyze_text(text)

            total=bs+es
            prob=calc_prob(total)
            plan=get_plan(tags)
            level=get_level(total)

            c.execute("""
            INSERT INTO companies
            (name,contact,area,phone,score,level,reason,probability,plan,status,owner,last_contact,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,(name,contact,area,phone,total,level,"+".join(reason),prob,plan,"未联系","","",""))

        except:
            continue

    conn.commit()
    return redirect("/")

# ===== 更新 =====
@app.route("/update/<id>",methods=["POST"])
def update(id):
    status=request.form["status"]
    note=request.form.get("note","")
    now=datetime.date.today().isoformat()

    c.execute("UPDATE companies SET status=?,note=?,last_contact=? WHERE id=?",
              (status,note,now,id))
    conn.commit()
    return redirect("/")

# ===== 今日任务 =====
@app.route("/tasks")
def tasks():
    data=c.execute("SELECT * FROM companies WHERE probability>=60 ORDER BY score DESC").fetchall()
    html="<h3>🔥 今日必打</h3><a href='/'>返回</a><br>"
    for d in data[:20]:
        html+=f"<p>{d[1]} | {d[4]} | 概率:{d[8]}%</p>"
    return html

# ===== 转化统计 =====
@app.route("/stats")
def stats():
    total=c.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    deal=c.execute("SELECT COUNT(*) FROM companies WHERE status='已成交'").fetchone()[0]
    rate=round(deal/total*100,2) if total else 0
    return f"<h3>统计</h3>总:{total}<br>成交:{deal}<br>转化:{rate}%<br><a href='/'>返回</a>"

app.run(host="0.0.0.0",port=8080)
