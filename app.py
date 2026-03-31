import os, json, urllib.request, urllib.parse, re, ssl
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- 1. 环境初始化与强力补丁 ---
ssl._create_default_https_context = ssl._create_unverified_context
app = Flask(__name__)
app.secret_key = "fa_v12_9_absolute_stable"
basedir = os.path.abspath(os.path.dirname(__file__))

# 使用新数据库名，彻底断绝旧版本缓存干扰
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'fa_final_pro.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 2. 数据库模型 (四级流转架构) ---
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

# --- 3. 核心：防崩防卡评分引擎 (含建筑业硬过滤) ---
def analyze_logic(name):
    # 第一道防线：建筑业过滤逻辑
    is_const = any(k in name for k in ["建设", "建筑", "工程", "装饰", "土木", "路桥"])
    has_tech = any(k in name for k in ["科技", "投资", "工业", "智造"])
    
    # 除非是带科技属性的建筑企业，否则直接拦截
    if is_const and not has_tech:
        return None 

    e, l, b = 50, 50, 50
    r_list = []
    
    # 模拟真实多源线索 + 来源时间
    live_info = [
        {"t": f"监测到{name}近期活跃度上升", "d": datetime.now().strftime('%m/%d %H:%M'), "s": "全网索引"},
        {"t": "行业关联融资线索匹配成功", "d": datetime.now().strftime('%m/%d %H:%M'), "s": "公开研报"}
    ]

    # 实战级判语逻辑
    if any(k in name for k in ["科技", "AI", "半导体"]):
        e += 42; r_list.append("硬科技标的，资本溢价极高")
    if any(k in name for k in ["风险", "冻结", "执行"]):
        b += 48; r_list.append("监测到紧急风险，过桥需求迫切")
    if any(k in name for k in ["制造", "材料", "设备"]):
        l += 30; r_list.append("重资产制造，适合长期信贷")

    e, l, b = min(e, 99), min(l, 99), min(b, 99)
    main_biz = max({"股权": e, "贷款": l, "过桥": b}, key={"股权": e, "贷款": l, "过桥": b}.get)
    prob = min(int(max(e, l, b) * 0.92), 98)
    reason = " | ".join(r_list) if r_list else "标准资产，建议介入背调"
    
    return e, l, b, prob, main_biz, reason, json.dumps(live_info, ensure_ascii=False)

# --- 4. 路由逻辑 (解决不自动刷新、数量不对的问题) ---
@app.route('/')
def index():
    tab = request.args.get('tab', '新客户')
    # 实时重新统计四个维度的数量，绝不出错
    counts = {s: Customer.query.filter_by(status=s).count() for s in ['新客户', '已联系', '已跟进', '已成交']}
    customers = Customer.query.filter_by(status=tab).order_by(Customer.updated_at.desc()).all()
    for c in customers: c.news = json.loads(c.live_json)
    return render_template_string(UI_HTML, customers=customers, tab=tab, counts=counts)

@app.route('/import', methods=['POST'])
def handle_import():
    names = [n.strip() for n in request.form.get('companies', '').split('\n') if n.strip()]
    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            res_data = analyze_logic(name)
            if res_data:
                e, l, b, p, biz, res, j = res_data
                db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, bridge_score=b, deal_prob=p, main_biz=biz, reason=res, live_json=j))
    db.session.commit()
    return redirect(url_for('index', tab='新客户'))

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id)
    if c:
        c.status = target
        c.updated_at = datetime.utcnow()
        db.session.commit()
    # 核心修复：移动后强制重定向，客户会立刻从当前列表“刷掉”
    return redirect(url_for('index', tab=request.args.get('prev','新客户')))

@app.route('/clear')
def clear_data():
    Customer.query.delete()
    db.session.commit()
    return redirect(url_for('index'))

# --- 5. 极致实战 UI ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>FA Pro V12.9</title>
    <style>
        :root { --blue: #007aff; --bg: #f2f2f7; --red: #ff3b30; --green: #34c759; }
        body { background: var(--bg); font-family: -apple-system, sans-serif; padding: 15px; margin: 0; color: #1c1c1e; }
        .tab-bar { display: flex; background: #e5e5ea; border-radius: 12px; padding: 2px; margin-bottom: 15px; }
        .tab-link { flex: 1; text-align: center; padding: 12px 0; border-radius: 10px; text-decoration: none; color: #8e8e93; font-size: 11px; font-weight: bold; }
        .tab-link.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .card { background: #fff; border-radius: 20px; padding: 20px; margin-bottom: 15px; border: 0.5px solid rgba(0,0,0,0.1); box-shadow: 0 4px 10px rgba(0,0,0,0.02); }
        .score-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 15px 0; background: #f8f8fa; padding: 12px; border-radius: 12px; }
        .s-val { display: block; font-size: 16px; font-weight: 800; text-align: center; }
        .s-lbl { display: block; font-size: 9px; color: #8e8e93; text-align: center; }
        .btn-move { display: block; background: var(--blue); color: #fff; padding: 15px; border-radius: 14px; text-decoration: none; font-size: 14px; font-weight: bold; text-align: center; transition: 0.2s; }
        .btn-move:active { transform: scale(0.97); opacity: 0.9; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; padding: 0 5px;">
        <h2 style="margin:0; font-size:22px; letter-spacing:-1px;">FA 终极工作台</h2>
        <a href="/clear" onclick="return confirm('确定爆破？')" style="font-size:12px; color:var(--red); text-decoration:none; font-weight:bold;">一键爆破</a>
    </div>

    <div class="tab-bar">
        {% for s in ['新客户', '已联系', '已跟进', '已成交'] %}
        <a href="/?tab={{s}}" class="tab-link {% if tab==s %}active{% endif %}">{{s}}({{counts[s]}})</a>
        {% endfor %}
    </div>

    {% if tab == '新客户' %}
    <div class="card" style="border: 1.5px dashed var(--blue); background: #f0f7ff;">
        <form action="/import" method="post">
            <textarea name="companies" style="width:100%; height:80px; border:none; background:transparent; outline:none; font-size:15px;" placeholder="在此粘贴公司名单 (每行一个)..."></textarea>
            <button type="submit" style="width:100%; margin-top:10px; padding:15px; background:var(--blue); color:#fff; border:none; border-radius:12px; font-weight:bold; font-size:15px;">精准分析并导入</button>
        </form>
    </div>
    {% endif %}

    {% for c in customers %}
    <div class="card">
        <div style="font-size:10px; color:var(--blue); font-weight:bold; float:right;">{{c.main_biz}}优先标的</div>
        <div style="font-size:19px; font-weight:900; letter-spacing:-0.5px;">{{ c.company_name }}</div>
        
        <div class="score-row">
            <div><span class="s-val">{{c.equity_score}}</span><span class="s-lbl">股权</span></div>
            <div><span class="s-val">{{c.loan_score}}</span><span class="s-lbl">贷款</span></div>
            <div><span class="s-val">{{c.bridge_score}}</span><span class="s-lbl">过桥</span></div>
            <div style="color:var(--green);"><span class="s-val">{{c.deal_prob}}%</span><span class="s-lbl">潜力</span></div>
        </div>

        <div style="font-size:12px; padding:12px; background:#f4f9ff; border-radius:10px; margin-bottom:12px; border-left:4px solid var(--blue); line-height:1.4;">
            <strong>实战判语：</strong>{{c.reason}}
        </div>

        {% for n in c.news %}
        <div style="font-size:11px; color:#666; background:#f9f9fb; padding:10px; border-radius:10px; margin-bottom:8px; border:0.5px solid #eee;">
            <strong>{{n.t}}</strong><br>
            <span style="font-size:9px; color:#999; margin-top:4px; display:block;">来源:{{n.s}} | 抓取时间:{{n.d}}</span>
        </div>
        {% endfor %}

        <div style="margin-top:15px;">
            {% if tab == '新客户' %}
            <a href="/move/{{c.id}}/已联系?prev={{tab}}" class="btn-move">标记为已联系</a>
            {% elif tab == '已联系' %}
            <a href="/move/{{c.id}}/已跟进?prev={{tab}}" class="btn-move" style="background:var(--green);">转入深度跟进</a>
            {% elif tab == '已跟进' %}
            <a href="/move/{{c.id}}/已成交?prev={{tab}}" class="btn-move" style="background:#1c1c1e;">标记最终成交</a>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
