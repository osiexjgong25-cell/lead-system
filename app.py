from flask import Flask, request, redirect
import sqlite3, datetime, requests

app = Flask(__name__)

# ===== 数据库 =====
conn = sqlite3.connect('fa.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS customers (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
score INTEGER,
level TEXT,
reason TEXT,
status TEXT,
created TEXT
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS config (
key TEXT PRIMARY KEY,
value TEXT
)
''')
conn.commit()

# ===== 工具 =====
def get_config(key):
    try:
        r = c.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        return r[0] if r else ""
    except:
        return ""

# ===== UI =====
def page(body):
    return f"""
    <html>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <body style="background:#f2f2f7;font-family:-apple-system;padding:12px">
    {body}
    </body>
    </html>
    """

def btn(t, l, c="#000"):
    return f"<a href='{l}' style='display:block;background:{c};color:#fff;padding:12px;border-radius:18px;text-align:center;margin:8px 0;text-decoration:none'>{t}</a>"

def card(d):
    return f"""
    <div style='background:#fff;padding:14px;border-radius:18px;margin:10px 0'>
    <b>{d[1]}</b><br><br>

    {d[4]}<br><br>

    状态：<b>{d[5]}</b><br><br>

    <a href='/update?id={d[0]}&s=未联系' style='padding:6px 10px;background:#aaa;color:#fff;border-radius:10px;text-decoration:none'>未联系</a>
    <a href='/update?id={d[0]}&s=已联系' style='padding:6px 10px;background:#007aff;color:#fff;border-radius:10px;text-decoration:none'>已联系</a>
    <a href='/update?id={d[0]}&s=成交' style='padding:6px 10px;background:#34c759;color:#fff;border-radius:10px;text-decoration:none'>成交</a>
    </div>
    """

# ===== 新闻信号 =====
def fetch_news_signals(name):
    signals = []
    try:
        key = get_config("news_key")
        if not key:
            return []

        url = f"https://newsapi.org/v2/everything?q={name}&pageSize=5&apiKey={key}"
        res = requests.get(url, timeout=5).json()

        for i in res.get("articles", []):
            title = i.get("title","")
            date = i.get("publishedAt","")[:10]

            if not date:
                continue

            if "融资" in title or "投资" in title:
                signals.append((date, "融资"))

            elif "中标" in title:
                signals.append((date, "中标"))

            elif "被执行" in title:
                signals.append((date, "被执行"))
    except:
        pass

    return signals

# ===== 百度AI信号 =====
def fetch_baidu_ai_signals(name):
    signals = []
    try:
        api_key = get_config("baidu_api")
        secret = get_config("baidu_secret")

        if not api_key or not secret:
            return []

        token_url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={api_key}&client_secret={secret}"
        token_res = requests.get(token_url, timeout=5).json()
        token = token_res.get("access_token","")

        if not token:
            return []

        url = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions?access_token={token}"

        prompt = f"公司{name}最近是否有融资、中标或被执行情况"

        res = requests.post(url, json={
            "messages":[{"role":"user","content":prompt}]
        }, timeout=8).json()

        text = str(res)
        today = str(datetime.date.today())

        if "融资" in text:
            signals.append((today, "融资"))

        if "中标" in text:
            signals.append((today, "中标"))

        if "被执行" in text:
            signals.append((today, "被执行"))

    except:
        pass

    return signals

# ===== 核心融资模型 =====
def analyze(name):
    score = 0
    reasons = []
    today = datetime.date.today()

    # 行业
    if any(k in name for k in ["半导体","新能源","AI","机器人","医疗"]):
        score += 20; reasons.append("行业：高成长")

    if any(k in name for k in ["设备","制造","材料"]):
        score += 15; reasons.append("行业：实体产业")

    # 信号
    signals = []
    try: signals += fetch_news_signals(name)
    except: pass
    try: signals += fetch_baidu_ai_signals(name)
    except: pass

    intent = 0
    pressure = 0

    for date_str, typ in signals:
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            days = (today - d).days
        except:
            days = 30

        weight = 1.0 if days<=7 else 0.7 if days<=30 else 0.4

        if typ=="融资":
            intent += 40*weight
            reasons.append(f"{date_str}：融资")

        elif typ=="中标":
            intent += 25*weight
            reasons.append(f"{date_str}：中标")

        elif typ=="被执行":
            pressure += 30*weight
            reasons.append(f"{date_str}：被执行")

    score += intent + pressure

    # 组合逻辑
    if intent>30 and pressure>20:
        score += 30
        reasons.append("🔥扩张+缺钱")

    elif intent>40:
        score += 20
        reasons.append("🔥明确融资阶段")

    # 成交概率
    deal = 0
    if "有限公司" in name: deal += 10
    if intent>40: deal += 30
    if pressure>20: deal += 20

    finance = min(int(score),100)
    deal = min(int(deal),100)

    if finance>80 and deal>40:
        level = "🔥高优先级"
    elif finance>60:
        level = "⭐中优先级"
    else:
        level = "普通"

    if not reasons:
        reasons.append(f"{today}：无明显融资信号")

    summary = f"""
融资概率：{finance}%
成交概率：{deal}%
优先级：{level}<br>
原因：{"；".join(reasons[:5])}
"""
    return finance, level, summary

# ===== API抓取 =====
def fetch_api():
    try:
        key = get_config("kdg")
        if not key:
            return []

        r = requests.get(
            "https://api.kaidanguo.com/company/search",
            headers={"Authorization": key},
            timeout=5
        ).json()

        return [i.get("companyName") for i in r.get("data", []) if i.get("companyName")]
    except:
        return []

# ===== 抓取 =====
def run_fetch():
    names = fetch_api()

    if not names:
        existing = c.execute("SELECT name FROM customers").fetchall()
        names = [i[0] for i in existing]

    if not names:
        return 0

    added = 0

    for name in names:
        if not name:
            continue

        s,l,r = analyze(name)

        exists = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()

        if exists:
            c.execute("UPDATE customers SET score=?,level=?,reason=?,created=? WHERE name=?",
                      (s,l,r,datetime.date.today(),name))
        else:
            c.execute("INSERT INTO customers VALUES (NULL,?,?,?,?,?,?)",
                      (name,s,l,r,"未联系",datetime.date.today()))
            added += 1

    conn.commit()
    return added

# ===== 路由 =====
@app.route("/")
def home():
    return page(
        "<h2>FA系统（最终版）</h2>"
        + btn("抓客户","/run")
        + btn("客户列表","/list")
        + btn("导入客户","/import")
        + btn("API设置","/api")
        + btn("清空数据","/clear","#d9534f")
    )

@app.route("/run")
def run():
    count = run_fetch()
    if count==0:
        return page("未抓新客户，已更新评分"+btn("查看","/list"))
    return redirect("/list")

@app.route("/list")
def list_data():
    status = request.args.get("s")

    if status:
        data = c.execute("SELECT * FROM customers WHERE status=? ORDER BY score DESC",(status,)).fetchall()
    else:
        data = c.execute("SELECT * FROM customers ORDER BY score DESC").fetchall()

    if not data:
        return page("暂无数据"+btn("导入客户","/import"))

    return page(
        btn("全部","/list")
        + btn("未联系","/list?s=未联系","#aaa")
        + btn("已联系","/list?s=已联系","#007aff")
        + btn("成交","/list?s=成交","#34c759")
        + "".join([card(d) for d in data])
    )

@app.route("/update")
def update():
    try:
        c.execute("UPDATE customers SET status=? WHERE id=?",
                  (request.args.get("s"),request.args.get("id")))
        conn.commit()
    except:
        pass
    return redirect("/list")

@app.route("/clear")
def clear():
    if request.args.get("ok")=="yes":
        c.execute("DELETE FROM customers")
        conn.commit()
        return redirect("/list")
    return page(btn("确认清空","/clear?ok=yes","#d9534f")+btn("取消","/"))

@app.route("/import",methods=["GET","POST"])
def import_data():
    if request.method=="POST":
        for line in request.form["data"].split("\n"):
            name=line.strip()
            if not name: continue
            s,l,r=analyze(name)
            c.execute("INSERT INTO customers VALUES (NULL,?,?,?,?,?,?)",
                      (name,s,l,r,"未联系",datetime.date.today()))
        conn.commit()
        return redirect("/list")
    return page("<form method='post'><textarea name='data' style='width:100%;height:200px'></textarea><button>导入</button></form>")

@app.route("/api",methods=["GET","POST"])
def api():
    if request.method=="POST":
        c.execute("REPLACE INTO config VALUES ('kdg',?)",(request.form.get("kdg"),))
        c.execute("REPLACE INTO config VALUES ('news_key',?)",(request.form.get("news"),))
        c.execute("REPLACE INTO config VALUES ('baidu_api',?)",(request.form.get("baidu_api"),))
        c.execute("REPLACE INTO config VALUES ('baidu_secret',?)",(request.form.get("baidu_secret"),))
        conn.commit()
        return redirect("/")

    return page("""
    <form method="post">
    开单果KEY:<br><input name="kdg"><br><br>
    新闻KEY:<br><input name="news"><br><br>
    百度API_KEY:<br><input name="baidu_api"><br><br>
    百度SECRET_KEY:<br><input name="baidu_secret"><br><br>
    <button>保存</button>
    </form>
    """)

app.run(host="0.0.0.0",port=8080)
