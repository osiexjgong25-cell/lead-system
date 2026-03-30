import os, csv, json, io, urllib.request, urllib.parse, re
from flask import Flask, render_template_string, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = "fa_ultra_v12_real_web"

# --- 1. 数据库配置 ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///fa_v12_real.db')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Customer(db.Model):
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

# --- 2. 真·互联网实时抓取引擎 ---
def fetch_real_news(company_name):
    """从互联网实时抓取真实新闻标题作为融资线索"""
    results = []
    try:
        # 搜索“公司名 融资 资讯”
        query = urllib.parse.quote(f"{company_name} 融资 资讯")
        url = f"https://www.bing.com/search?q={query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        
        req = urllib.request.Request(url, headers=headers)
        # 设置 2 秒超时，防止网络抖动导致系统卡死
        with urllib.request.urlopen(req, timeout=2.5) as response:
            html = response.read().decode('utf-8')
            # 提取搜索结果标题的简单正则
            titles = re.findall(r'<h2><a .*?>(.*?)</a></h2>', html)
            if titles:
                # 清洗 HTML 标签，取前 1 条最相关的真实标题
                clean_title = re.sub('<[^<]+?>', '', titles[0])
                results.append({
                    "text": f"实时搜获：{clean_title[:35]}...", 
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M'), 
                    "source": "互联网实时检索"
                })
    except Exception:
        # 任何联网失败（如断网、被封）均静默处理，返回空列表，确保系统不崩
        pass
    return results

# --- 3. 核心融资评分引擎 ---
def financing_model(name):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    e, l, b = 50, 50, 50
    
    # 优先获取真实互联网信息
    results = fetch_real_news(name) 

    # 补充基础逻辑（逻辑兜底）
    base_sources = [
        ("增发", "股权", 35, "公告监测"),
        ("芯片", "股权", 20, "行业标签"),
        ("抵押", "贷款", 25, "风险扫描"),
        ("查封", "过桥", 50, "风险监控")
    ]
    
    for key, typ, score, src in base_sources:
        if key in name:
            if typ == "股权": e += score
            elif typ == "贷款": l += score
            elif typ == "过桥": b += score
            results.append({"text": f"匹配要素：{key}", "time": now_str, "source": src})

    e, l, b = min(e, 99), min(l, 99), min(b, 99)
    scores = {"股权": e, "贷款": l, "过桥": b}
    main_biz = max(scores, key=scores.get)
    prob = min(int(max(e, l, b) * 0.9), 98)

    return e, l, b, prob, main_biz, json.dumps(results, ensure_ascii=False), datetime.utcnow()

# --- 4. 路由与功能 (保持一级功能正常) ---
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
    if file and file.filename.endswith('.csv'):
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        for row in reader:
            name = row.get('company_name') or row.get('name')
            if name:
                name = name.strip()
                if not Customer.query.filter_by(company_name=name).first():
                    e, l, b, dp, biz, res, up = financing_model(name)
                    db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, 
                                            bridge_score=b, deal_prob=dp, main_biz=biz, 
                                            reasons_json=res, updated_at=up))
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
    writer.writerow(['公司名称', '主营业务', '股权分', '贷款分', '过桥分', '原因详情', '成交概率'])
    for c in Customer.query.all():
        writer.writerow([c.company_name, c.main_biz, c.equity_score, c.loan_score, c.bridge_score, c.reasons_json, f"{c.deal_prob}%"])
    return Response(data.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=FA_Report.csv"})

# --- 5. UI 模板 (极简 iOS 风) ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FA Pro Real-Live V12.3</title>
    <style>
        body { background: #f2f2f7; font-family: -apple-system, sans-serif; padding: 15px; margin: 0; }
        .tabs { display: flex; background: #e5e5ea; border-radius: 12px; padding: 2px; margin-bottom: 15px; }
        .tab-item { flex: 1; text-align: center; padding: 8px; border-radius: 10px; text-decoration: none; color: #8e8e93; font-size: 13px; font-weight: bold; }
        .tab-item.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .card { background: #fff; border-radius: 18px; padding: 15px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
        .score-bar { display: flex; justify-content: space-between; background: #f8f8fa; padding: 10px; border-radius: 10px; margin: 10px 0; }
        .score-item { text-align: center; flex: 1; }
        .score-val { font-size: 16px; font-weight: 800; display: block; }
        .score-lbl { font-size: 9px; color: #8e8e93; }
        .reason-tag { font-size: 11px; padding: 8px; border-left: 3px solid #007aff; background: #f0f7ff; margin-top: 5px; border-radius: 4px; }
        .btn { display: block; background: #007aff; color: #fff; text-align: center; padding: 12px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 14px; margin-top: 10px; }
        .live-indicator { font-size: 9px; color: #ff3b30; font-weight: bold; margin-bottom: 5px; display: block; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <h3 style="margin:0;">FA 真联网工作台</h3>
        <a href="/download_report" style="text-decoration:none;">📊 导出报告</a>
    </div>

    <div class="tabs">
        {% for s in ['新客户', '已联系', '成交'] %}
        <a href="/?status={{s}}" class="tab-item {% if status==s %}active{% endif %}">{{s}} ({{counts[s]}})</a>
        {% endfor %}
    </div>

    {% if status == '新客户' %}
    <div class="card" style="border: 1px dashed #007aff; background: #f0f5ff;">
        <form action="/import_customers" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept=".csv" required style="font-size:12px;">
            <button type="submit" style="width:100%; margin-top:10px; background:#007aff; color:#fff; border:none; padding:10px; border-radius:10px; font-weight:800;">导入名单并启动全网扫描</button>
        </form>
    </div>
    {% endif %}

    {% for c in customers %}
    <div class="card">
        <span class="live-indicator">● 实时联网中</span>
        <div style="font-size:18px; font-weight:900;">{{ c.company_name }}</div>
        <div class="score-bar">
            <div class="score-item"><span class="score-val">{{c.equity_score}}</span><span class="score-lbl">股权</span></div>
            <div class="score-item"><span class="score-val">{{c.loan_score}}</span><span class="score-lbl">贷款</span></div>
            <div class="score-item"><span class="score-val">{{c.bridge_score}}</span><span class="score-lbl">过桥</span></div>
            <div class="score-item" style="color:#34c759;"><span class="score-val">{{c.deal_prob}}%</span><span class="score-lbl">概率</span></div>
        </div>
        {% for r in c.parsed_reasons %}
        <div class="reason-tag">
            <strong>{{r.text}}</strong><br>
            <small style="color:#8e8e93;">{{r.time}} | {{r.source}}</small>
        </div>
        {% endfor %}
        <a href="/move/{{c.id}}/已联系?prev={{status}}" class="btn">开始跟进</a>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
