import os, csv, json, io
from flask import Flask, render_template_string, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = "fa_ultra_v12_automated"

# --- 数据库配置 ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///fa_v12_pro.db')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 数据模型 ---
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    equity_score = db.Column(db.Integer, default=50)
    loan_score = db.Column(db.Integer, default=50)
    bridge_score = db.Column(db.Integer, default=50)
    deal_prob = db.Column(db.Integer, default=30)
    main_biz = db.Column(db.String(50))
    # 存储多条原因的JSON字符串: [{"text": "...", "time": "...", "source": "..."}, ...]
    reasons_json = db.Column(db.Text, default='[]') 
    status = db.Column(db.String(50), default='新客户')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 核心逻辑引擎：多数据源模拟与评分 ---
def financing_model(name):
    """
    模拟多源抓取 (1. 行业库 2. 公共公告库 3. 司法风险库)
    """
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    e, l, b = 50, 50, 50
    results = []

    # 1. 模拟 CNINFO/公共公告抓取 (关键词匹配)
    announcements = [
        ("增发", "股权", 30, "来源：公共公告库 - 拟进行股权融资"),
        ("战略投资", "股权", 40, "来源：新闻快讯 - 头部机构入场"),
        ("抵押", "贷款", 25, "来源：登记系统 - 资产活跃度高"),
        ("中标", "贷款", 20, "来源：招投标平台 - 经营现金流需求"),
    ]
    for key, typ, score, src in announcements:
        if key in name:
            if typ == "股权": e += score
            if typ == "贷款": l += score
            results.append({"text": f"匹配到【{key}】关键字", "time": now_str, "source": src})

    # 2. 行业硬属性逻辑
    if any(k in name for k in ["科技", "生物", "芯片"]):
        e += 15
        results.append({"text": "硬科技行业属性", "time": now_str, "source": "行业分类模型"})
    
    # 3. 司法风险/救急抓取 (过桥触发)
    if any(k in name for k in ["纠纷", "冻结", "执行"]):
        b += 45
        results.append({"text": "监测到司法冻结风险", "time": now_str, "source": "风险监控中心"})

    # 封顶与定性
    e, l, b = min(e, 100), min(l, 100), min(b, 100)
    scores = {"股权": e, "贷款": l, "过桥": b}
    main_biz = max(scores, key=scores.get)
    prob = min(int(max(e, l, b) * 0.85), 99)

    return e, l, b, prob, main_biz, json.dumps(results), datetime.utcnow()

# --- 自动化任务：每日更新评分 ---
def daily_refresh():
    with app.app_context():
        customers = Customer.query.all()
        for c in customers:
            e, l, b, prob, biz, res, up = financing_model(c.company_name)
            c.equity_score, c.loan_score, c.bridge_score = e, l, b
            c.deal_prob, c.main_biz, c.reasons_json, c.updated_at = prob, biz, res, up
        db.session.commit()
        print(f"[{datetime.now()}] 每日融资报告已自动更新")

scheduler = BackgroundScheduler()
scheduler.add_job(func=daily_refresh, trigger="cron", hour=2, minute=0) # 每天凌晨2点
scheduler.start()

# --- 路由 ---

@app.route('/')
def index():
    status = request.args.get('status', '新客户')
    customers = Customer.query.filter_by(status=status).order_by(Customer.deal_prob.desc()).all()
    # 解析JSON原因供前端显示
    for c in customers:
        c.parsed_reasons = json.loads(c.reasons_json) if c.reasons_json else []
    return render_template_string(UI_HTML, customers=customers, status=status)

@app.route('/import_customers', methods=['POST'])
def import_customers():
    file = request.files.get('file')
    if file and file.filename.endswith('.csv'):
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        for row in reader:
            name = row.get('company_name') or row.get('name')
            if name and not Customer.query.filter_by(company_name=name).first():
                e, l, b, dp, biz, res, up = financing_model(name)
                db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, 
                                        bridge_score=b, deal_prob=dp, main_biz=biz, 
                                        reasons_json=res, updated_at=up))
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/download_report')
def download_report():
    def generate():
        data = io.StringIO()
        writer = csv.writer(data)
        writer.writerow(['公司名称', '主营业务', '股权分', '贷款分', '过桥分', '成交概率', '更新时间'])
        for c in Customer.query.all():
            writer.writerow([c.company_name, c.main_biz, c.equity_score, c.loan_score, c.bridge_score, f"{c.deal_prob}%", c.updated_at])
        yield data.getvalue()

    return Response(generate(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=FA_Report.csv"})

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id)
    if c:
        c.status = target
        db.session.commit()
    return redirect(url_for('index', status=request.args.get('prev','新客户')))

# --- UI 模板 ---
UI_HTML = '''
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FA Pro V12 - 自动化版</title>
    <style>
        body { background:#f2f2f7; font-family:-apple-system, sans-serif; padding:15px; margin:0; color:#1c1c1e; }
        .header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }
        .card { background:#fff; border-radius:16px; padding:15px; margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }
        .tag { font-size:10px; padding:2px 8px; border-radius:4px; background:#e5e5ea; color:#3a3a3c; font-weight:bold; }
        .score-row { display:flex; justify-content:space-between; margin-top:10px; background:#f8f8fa; padding:8px; border-radius:10px; }
        .score-item { text-align:center; flex:1; }
        .score-val { font-size:16px; font-weight:800; display:block; }
        .score-lbl { font-size:9px; color:gray; }
        .reason-box { margin-top:10px; border-top:1px solid #eee; padding-top:8px; }
        .reason-item { font-size:11px; margin-bottom:5px; padding-left:8px; border-left:2px solid #007aff; }
        .reason-time { font-size:9px; color:#8e8e93; display:block; }
        .btn { text-decoration:none; color:#fff; background:#007aff; padding:10px; border-radius:10px; display:inline-block; font-size:12px; font-weight:bold; }
        .import-section { background:#fff; padding:15px; border-radius:16px; border:1px dashed #007aff; margin-bottom:20px; }
    </style>
</head>
<body>
    <div class="header">
        <h2 style="margin:0;">FA 自动化流水线</h2>
        <a href="/download_report" class="btn" style="background:#34c759;">导出 CSV 报告</a>
    </div>

    <div class="import-section">
        <form action="/import_customers" method="post" enctype="multipart/form-data">
            <span style="font-size:12px; color:#8e8e93;">导入客户名单 (CSV, 列名需包含 company_name)</span>
            <input type="file" name="file" accept=".csv" style="margin:10px 0; display:block; font-size:12px;">
            <button type="submit" class="btn" style="width:100%;">批量导入并启动自动化模型</button>
        </form>
    </div>

    <div style="margin-bottom:15px;">
        <a href="/?status=新客户" style="margin-right:15px; font-weight:{% if status=='新客户' %}800{% else %}400{% endif %};">新客户</a>
        <a href="/?status=已联系" style="font-weight:{% if status=='已联系' %}800{% else %}400{% endif %};">已联系</a>
    </div>

    {% for c in customers %}
    <div class="card">
        <div style="display:flex; justify-content:space-between;">
            <span style="font-weight:900; font-size:17px;">{{c.company_name}}</span>
            <span class="tag" style="background:#007aff22; color:#007aff;">{{c.main_biz}}类推荐</span>
        </div>
        
        <div class="score-row">
            <div class="score-item"><span class="score-val">{{c.equity_score}}</span><span class="score-lbl">股权</span></div>
            <div class="score-item"><span class="score-val">{{c.loan_score}}</span><span class="score-lbl">贷款</span></div>
            <div class="score-item"><span class="score-val">{{c.bridge_score}}</span><span class="score-lbl">过桥</span></div>
            <div class="score-item" style="color:#34c759;"><span class="score-val">{{c.deal_prob}}%</span><span class="score-lbl">潜力值</span></div>
        </div>

        <div class="reason-box">
            {% for r in c.parsed_reasons %}
            <div class="reason-item">
                <strong>{{r.text}}</strong>
                <span class="reason-time">{{r.time}} | {{r.source}}</span>
            </div>
            {% endfor %}
        </div>
        
        <div style="margin-top:12px; display:flex; gap:10px;">
            {% if c.status == '新客户' %}
            <a href="/move/{{c.id}}/已联系?prev={{status}}" class="btn" style="flex:1; text-align:center;">标记为已跟进</a>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
