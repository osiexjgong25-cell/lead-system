import os, csv, json, io, urllib.request, urllib.parse, re, ssl
from flask import Flask, render_template_string, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- 核心补丁：解决云端联网 SSL 证书问题 ---
ssl._create_default_https_context = ssl._create_unverified_context

app = Flask(__name__)
app.secret_key = "fa_railway_stable_v12"

# --- 1. 数据库配置 (自动适配本地与云端路径) ---
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'fa_v12_live.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Customer(db.Model):
    id = db.Model.metadata.tables.get('customer') # 兼容逻辑
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    equity_score = db.Column(db.Integer, default=50)
    loan_score = db.Column(db.Integer, default=50)
    bridge_score = db.Column(db.Integer, default=50)
    deal_prob = db.Column(db.Integer, default=30)
    main_biz = db.Column(db.String(50))
    reasons_json = db.Column(db.Text, default='[]') 
    status = db.Column(db.String(50), default='新客户')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 2. 真·互联网实时抓取引擎 (超时保护防止卡死) ---
def fetch_real_news(company_name):
    results = []
    try:
        query = urllib.parse.quote(f"{company_name} 融资 动态")
        url = f"https://www.bing.com/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(url, headers=headers)
        # 限制 2 秒内必须返回，否则跳过，确保 Railway 不会因为等网页而超时报错
        with urllib.request.urlopen(req, timeout=2.0) as response:
            html = response.read().decode('utf-8')
            titles = re.findall(r'<h2><a .*?>(.*?)</a></h2>', html)
            if titles:
                clean_title = re.sub('<[^<]+?>', '', titles[0])
                results.append({
                    "text": f"互联网动态：{clean_title[:30]}...", 
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M'), 
                    "source": "实时搜索"
                })
    except:
        pass
    return results

# --- 3. 核心评分逻辑 (保留所有原版好功能) ---
def financing_model(name):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    e, l, b = 50, 50, 50
    results = fetch_real_news(name) 

    # 原有关键词硬加分逻辑
    if any(k in name for k in ["科技", "AI", "芯片"]): e += 30
    if "建设" in name or "工程" in name: l += 20; b += 10
    if "冻结" in name or "诉讼" in name: b += 40

    e, l, b = min(e, 99), min(l, 99), min(b, 99)
    scores = {"股权": e, "贷款": l, "过桥": b}
    main_biz = max(scores, key=scores.get)
    prob = min(int(max(e, l, b) * 0.9), 98)
    return e, l, b, prob, main_biz, json.dumps(results, ensure_ascii=False), datetime.utcnow()

# --- 4. 路由逻辑 (确保导入、移动、导出每一级都正常) ---
@app.route('/')
def index():
    status = request.args.get('status', '新客户')
    counts = {s: Customer.query.filter_by(status=s).count() for s in ['新客户', '已联系', '成交']}
    customers = Customer.query.filter_by(status=status).order_by(Customer.deal_prob.desc()).all()
    for c in customers:
        c.parsed_reasons = json.loads(c.reasons_json) if c.reasons_json else []
    return render_template_string(UI_HTML, customers=customers, status=status, counts=counts)

@app.route('/import_customers', methods=['POST'])
def import_customers():
    file = request.files.get('file')
    if file:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        for row in reader:
            name = (row.get('company_name') or row.get('name', '')).strip()
            if name and not Customer.query.filter_by(company_name=name).first():
                e, l, b, dp, biz, res, up = financing_model(name)
                db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, bridge_score=b, deal_prob=dp, main_biz=biz, reasons_json=res, updated_at=up))
        db.session.commit()
    return redirect(url_for('index', status='新客户'))

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id)
    if c:
        c.status = target
        db.session.commit()
    return redirect(url_for('index', status=request.args.get('prev','新客户')))

@app.route('/download_report')
def download_report():
    data = io.StringIO()
    writer = csv.writer(data)
    writer.writerow(['公司名称', '主营业务', '成交概率', '详情'])
    for c in Customer.query.all():
        writer.writerow([c.company_name, c.main_biz, f"{c.deal_prob}%", c.reasons_json])
    return Response(data.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=FA_Report.csv"})

# --- 5. UI (适配移动端，保持美观) ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>FA Pro Live</title>
<style>
    body { background:#f2f2f7; font-family:-apple-system,sans-serif; padding:15px; margin:0; }
    .tabs { display:flex; background:#e5e5ea; border-radius:12px; padding:2px; margin-bottom:15px; }
    .tab-item { flex:1; text-align:center; padding:8px; border-radius:10px; text-decoration:none; color:#8e8e93; font-size:13px; font-weight:bold; }
    .tab-item.active { background:#fff; color:#000; box-shadow:0 2px 5px rgba(0,0,0,0.1); }
    .card { background:#fff; border-radius:18px; padding:15px; margin-bottom:12px; box-shadow:0 2px 8px rgba(0,0,0,0.04); }
    .btn { display:block; background:#007aff; color:#fff; text-align:center; padding:12px; border-radius:12px; text-decoration:none; font-weight:bold; margin-top:10px; }
    .reason { font-size:11px; padding:8px; border-left:3px solid #007aff; background:#f0f7ff; margin-top:5px; border-radius:4px; }
</style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <h3 style="margin:0;">FA 真联网工作台</h3>
        <a href="/download_report" style="text-decoration:none; font-size:12px;">📊 导出报告</a>
    </div>
    <div class="tabs">
        {% for s in ['新客户', '已联系', '成交'] %}
        <a href="/?status={{s}}" class="tab-item {% if status==s %}active{% endif %}">{{s}} ({{counts[s]}})</a>
        {% endfor %}
    </div>
    {% if status == '新客户' %}
    <div class="card" style="border: 1px dashed #007aff; background: #f0f5ff;">
        <form action="/import_customers" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept=".csv" required style="font-size:12px; width:100%;">
            <button type="submit" style="width:100%; margin-top:10px; background:#007aff; color:#fff; border:none; padding:10px; border-radius:10px; font-weight:800;">开始扫描</button>
        </form>
    </div>
    {% endif %}
    {% for c in customers %}
    <div class="card">
        <div style="font-size:18px; font-weight:900;">{{ c.company_name }}</div>
        <div style="font-size:12px; color:#8e8e93; margin:5px 0;">主营：{{c.main_biz}} | 潜力：{{c.deal_prob}}%</div>
        {% for r in c.parsed_reasons %}
        <div class="reason"><strong>{{r.text}}</strong><br><small>{{r.time}} | {{r.source}}</small></div>
        {% endfor %}
        <a href="/move/{{c.id}}/已联系?prev={{status}}" class="btn">跟进客户</a>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    # 适配 Railway 端口绑定
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
