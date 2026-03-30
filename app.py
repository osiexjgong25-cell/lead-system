import os, json, urllib.request, urllib.parse, re, ssl
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- 1. 初始化 ---
ssl._create_default_https_context = ssl._create_unverified_context
app = Flask(__name__)
app.secret_key = "fa_v12_8_final_fix"
basedir = os.path.abspath(os.path.dirname(__file__))
# 强制使用新数据库名，防止旧数据干扰
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'fa_data_v12_8.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 2. 数据库模型 ---
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True)
    equity_score = db.Column(db.Integer)
    loan_score = db.Column(db.Integer)
    bridge_score = db.Column(db.Integer)
    deal_prob = db.Column(db.Integer)
    main_biz = db.Column(db.String(50))
    reason = db.Column(db.Text)
    live_json = db.Column(db.Text, default='[]')
    status = db.Column(db.String(50), default='新客户') # 新客户/已联系/已跟进/已成交
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 3. 增强型分析逻辑 ---
def analyze_logic(name):
    e, l, b = 50, 50, 50
    # 模拟真联网线索（确保带时间戳）
    live_info = [{"t": f"监测到{name}近期有资金入账需求", "d": datetime.now().strftime('%m/%d %H:%M')}]
    r_list = []
    
    if any(k in name for k in ["科技", "AI", "半导体"]): e += 40; r_list.append("硬科技高溢价标的")
    if any(k in name for k in ["建设", "建筑", "工程"]): l += 35; r_list.append("基建类大额信贷需求")
    if any(k in name for k in ["风险", "冻结", "执行"]): b += 48; r_list.append("紧急流动性缺口，建议过桥")

    e, l, b = min(e, 99), min(l, 99), min(b, 99)
    scores = {"股权": e, "贷款": l, "过桥": b}
    main_biz = max(scores, key=scores.get)
    prob = min(int(max(e, l, b) * 0.92), 98)
    reason = " | ".join(r_list) if r_list else "标准资产，建议电联挖掘"
    
    return e, l, b, prob, main_biz, reason, json.dumps(live_info, ensure_ascii=False)

# --- 4. 路由逻辑（修复自动刷新与数量统计） ---
@app.route('/')
def index():
    tab = request.args.get('tab', '新客户')
    # 统计每个状态的数量（实时查询）
    counts = {
        '新客户': Customer.query.filter_by(status='新客户').count(),
        '已联系': Customer.query.filter_by(status='已联系').count(),
        '已跟进': Customer.query.filter_by(status='已跟进').count(),
        '已成交': Customer.query.filter_by(status='已成交').count()
    }
    customers = Customer.query.filter_by(status=tab).order_by(Customer.updated_at.desc()).all()
    for c in customers: c.news = json.loads(c.live_json)
    return render_template_string(UI_HTML, customers=customers, tab=tab, counts=counts)

@app.route('/import', methods=['POST'])
def handle_import():
    names = [n.strip() for n in request.form.get('companies', '').split('\n') if n.strip()]
    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            e, l, b, p, biz, res, j = analyze_logic(name)
            db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, bridge_score=b, deal_prob=p, main_biz=biz, reason=res, live_json=j))
    db.session.commit()
    # 导入后强制跳回到新客户列表页，确保刷新
    return redirect(url_for('index', tab='新客户'))

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id)
    if c:
        c.status = target
        c.updated_at = datetime.utcnow()
        db.session.commit()
    # 关键：移动后必须重定向，浏览器才会重新请求数据并“刷掉”旧卡片
    return redirect(url_for('index', tab=request.args.get('prev','新客户')))

@app.route('/clear')
def clear_data():
    Customer.query.delete()
    db.session.commit()
    return redirect(url_for('index'))

# --- 5. UI 模板 ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>FA Pro V12.8</title>
    <style>
        :root { --blue: #007aff; --bg: #f2f2f7; --red: #ff3b30; --green: #34c759; }
        body { background: var(--bg); font-family: -apple-system, sans-serif; padding: 15px; margin: 0; }
        .tab-bar { display: flex; background: #e5e5ea; border-radius: 12px; padding: 2px; margin-bottom: 20px; overflow-x: auto; }
        .tab-link { flex: 0 0 25%; text-align: center; padding: 10px 0; border-radius: 10px; text-decoration: none; color: #8e8e93; font-size: 12px; font-weight: bold; }
        .tab-link.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .card { background: #fff; border-radius: 20px; padding: 18px; margin-bottom: 15px; border: 0.5px solid rgba(0,0,0,0.1); }
        .btn-move { display: inline-block; background: var(--blue); color: #fff; padding: 12px; border-radius: 10px; text-decoration: none; font-size: 13px; font-weight: bold; text-align: center; flex: 1; }
        .score-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 15px 0; background: #f8f8fa; padding: 12px; border-radius: 12px; }
        .s-val { display: block; font-size: 16px; font-weight: 800; text-align: center; }
        .s-lbl { display: block; font-size: 9px; color: #8e8e93; text-align: center; }
        textarea { width: 100%; height: 100px; border: 1.5px solid #e5e5ea; border-radius: 12px; padding: 10px; box-sizing: border-box; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <h2 style="margin:0; letter-spacing:-1px;">FA 终极工作台</h2>
        <a href="/clear" onclick="return confirm('清空？')" style="font-size:12px; color:var(--red); text-decoration:none;">清空</a>
    </div>

    <div class="tab-bar">
        {% for s in ['新客户', '已联系', '已跟进', '成交'] %}
        <a href="/?tab={{s}}" class="tab-link {% if tab==s %}active{% endif %}">{{s}}({{counts[s]}})</a>
        {% endfor %}
    </div>

    {% if tab == '新客户' %}
    <div class="card" style="border: 1.5px dashed var(--blue); background: #f0f7ff;">
        <form action="/import" method="post">
            <textarea name="companies" placeholder="粘贴名单 (每行一个)..." required></textarea>
            <button type="submit" style="width:100%; margin-top:10px; padding:14px; background:var(--blue); color:#fff; border:none; border-radius:12px; font-weight:bold;">精准分析并导入</button>
        </form>
    </div>
    {% endif %}

    {% for c in customers %}
    <div class="card">
        <div style="font-size:10px; color:var(--blue); font-weight:bold; float:right;">{{c.main_biz}}优先</div>
        <div style="font-size:18px; font-weight:900;">{{ c.company_name }}</div>
        
        <div class="score-row">
            <div><span class="s-val">{{c.equity_score}}</span><span class="s-lbl">股权</span></div>
            <div><span class="s-val">{{c.loan_score}}</span><span class="s-lbl">贷款</span></div>
            <div><span class="s-val">{{c.bridge_score}}</span><span class="s-lbl">过桥</span></div>
            <div style="color:var(--green);"><span class="s-val">{{c.deal_prob}}%</span><span class="s-lbl">潜力</span></div>
        </div>

        <div style="font-size:12px; padding:10px; background:#f4f9ff; border-radius:6px; margin-bottom:10px;">
            <strong>判语：</strong>{{c.reason}}
        </div>

        <div style="display:flex; gap:8px;">
            {% if tab == '新客户' %}
            <a href="/move/{{c.id}}/已联系?prev={{tab}}" class="btn-move">移动至已联系</a>
            {% elif tab == '已联系' %}
            <a href="/move/{{c.id}}/已跟进?prev={{tab}}" class="btn-move">开始跟进</a>
            {% elif tab == '已跟进' %}
            <a href="/move/{{c.id}}/已成交?prev={{tab}}" class="btn-move" style="background:var(--green);">标记成交</a>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
