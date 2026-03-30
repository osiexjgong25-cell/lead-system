import os
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = "fa_pro_v11_perfect_stable"

# --- 数据库配置 ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///fa_ultimate_v11.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

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
    reason = db.Column(db.Text)
    source_time = db.Column(db.String(50)) 
    status = db.Column(db.String(50), default='新客户')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class SystemConfig(db.Model):
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(500))

with app.app_context():
    db.create_all()

# --- 逻辑引擎验证：确保三大融资需求不冲突 ---
def analyze_logic(name):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    e, l, b = 50, 50, 50 # 初始分持平，公平竞争
    reasons = []

    # A. 建筑/工程业：压分 + 转化检测
    is_con = any(k in name for k in ["工程", "建筑", "建设", "施工"])
    if is_con:
        l = 30 # 强制压低银行贷款分
        if any(k in name for k in ["投资", "股权", "创投", "资本"]):
            e, l = 85, 80
            reasons.append("【优质建筑】资本入场，激活股权/贷款双向需求")
        else:
            b += 15 # 建筑业默认潜在过桥需求
            reasons.append("【传统工程】常规垫资压力，贷款意向已压低")
    else:
        # B. 科技/制造需求
        if any(k in name for k in ["科技", "生物", "芯片", "软件"]):
            e += 35
            reasons.append("【股权】符合硬科技投向")
        if any(k in name for k in ["制造", "装备", "设备", "流水线"]):
            l += 35
            reasons.append("【贷款】实业经营，具备流水资质")

    # C. 过桥强触发逻辑 (司法/救急)
    if any(k in name for k in ["诉讼", "纠纷", "冻结", "执行", "查封"]):
        b += 45 # 强制推高过桥分
        reasons.append("【救急】监测到司法风险，急需过桥调头")

    scores = {"股权": e, "贷款": l, "过桥": b}
    biz = max(scores, key=scores.get)
    d_prob = min(int(scores[biz] * 0.9), 98)
    return e, l, b, d_prob, biz, " | ".join(reasons) if reasons else "互联网公开要素匹配", now_str

# --- 路由逻辑 ---

@app.route('/')
def index():
    cur_status = request.args.get('status', '新客户')
    cur_biz = request.args.get('biz', '全部')
    query = Customer.query.filter_by(status=cur_status)
    
    # 核心修复：穿透式业务筛选
    if cur_biz == '过桥': query = query.filter(Customer.bridge_score >= 60)
    elif cur_biz == '贷款': query = query.filter(Customer.loan_score >= 60)
    elif cur_biz == '股权': query = query.filter(Customer.equity_score >= 60)
    
    customers = query.order_by(Customer.deal_prob.desc()).all()
    counts = {s: Customer.query.filter_by(status=s).count() for s in ['新客户', '已联系', '成交']}
    return render_template_string(UI_HTML, customers=customers, cur_status=cur_status, cur_biz=cur_biz, counts=counts)

@app.route('/import', methods=['POST'])
def handle_import():
    names = [n.strip() for n in request.form.get('companies', '').split('\n') if n.strip()]
    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            e, l, b, dp, biz, res, st = analyze_logic(name)
            db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, 
                                     bridge_score=b, deal_prob=dp, main_biz=biz, 
                                     reason=res, source_time=st))
    db.session.commit()
    return redirect(url_for('index', status='新客户'))

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id)
    if c:
        c.status = target
        db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/clear', methods=['POST'])
def clear_all():
    Customer.query.delete()
    db.session.commit()
    return redirect('/')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        val = request.form.get('kd_key')
        conf = SystemConfig.query.get('kd_key')
        if conf: conf.value = val
        else: db.session.add(SystemConfig(key='kd_key', value=val))
        db.session.commit()
        return redirect('/')
    k = SystemConfig.query.get('kd_key')
    return render_template_string(SETTING_UI, key=k.value if k else "")

# --- UI 模板 (完美兼容 iOS 26) ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>FA Pro V11</title>
    <style>
        :root { --bg: #f2f2f7; --blue: #007aff; --green: #34c759; --red: #ff3b30; --gray: #8e8e93; }
        body { background: var(--bg); font-family: -apple-system, sans-serif; margin: 0; padding: 15px; }
        .tab-bar { display: flex; background: #e5e5ea; border-radius: 12px; padding: 2px; margin-bottom: 15px; }
        .tab-link { flex: 1; text-align: center; padding: 10px; border-radius: 10px; font-size: 12px; font-weight: 700; text-decoration: none; color: var(--gray); }
        .tab-link.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .biz-scroll { display: flex; gap: 8px; overflow-x: auto; margin-bottom: 15px; padding-bottom: 5px; }
        .biz-btn { border: none; padding: 8px 15px; border-radius: 8px; background: #fff; font-size: 11px; font-weight: 700; white-space: nowrap; text-decoration: none; color: #000; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .biz-btn.active { background: var(--blue); color: #fff; }
        .card { background: #fff; border-radius: 18px; padding: 16px; margin-bottom: 15px; border: 0.5px solid rgba(0,0,0,0.1); }
        .score-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 15px 0; background: #f8f8fa; padding: 10px; border-radius: 12px; }
        .s-val { display: block; font-size: 16px; font-weight: 800; text-align: center; }
        .s-lbl { display: block; font-size: 9px; color: var(--gray); text-align: center; }
        .reason { font-size: 11px; background: #f2f2f7; padding: 10px; border-radius: 8px; border-left: 3px solid var(--blue); }
        .btn-act { display: block; background: var(--blue); color: #fff; text-align: center; padding: 12px; border-radius: 12px; text-decoration: none; font-weight: 800; margin-top: 15px; font-size: 14px; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <h2 style="margin:0; letter-spacing:-1px;">FA 工作台 V11</h2>
        <a href="/settings" style="text-decoration:none;">⚙️</a>
    </div>

    <div class="tab-bar">
        {% for s in ['新客户', '已联系', '成交'] %}
        <a href="/?status={{s}}&biz={{cur_biz}}" class="tab-link {% if cur_status==s %}active{% endif %}">{{s}} ({{counts[s]}})</a>
        {% endfor %}
    </div>

    <div class="biz-scroll">
        {% for b in ['全部', '股权', '贷款', '过桥'] %}
        <a href="/?status={{cur_status}}&biz={{b}}" class="biz-btn {% if cur_biz==b %}active{% endif %}">{{b}}业务</a>
        {% endfor %}
    </div>

    {% if cur_status == '新客户' %}
    <div class="card" style="border: 1px dashed var(--blue); background:#f0f5ff;">
        <form action="/import" method="post">
            <textarea name="companies" rows="1" placeholder="粘贴公司名名单..." style="width:100%; border:none; background:none;"></textarea>
            <button type="submit" style="width:100%; background:var(--blue); color:#fff; border:none; padding:10px; border-radius:10px; margin-top:10px; font-weight:800;">批量导入分析</button>
        </form>
    </div>
    {% endif %}

    {% for c in customers %}
    <div class="card">
        <div style="font-size:10px; color:var(--blue); font-weight:800; float:right;">{{c.main_biz}}类推荐</div>
        <div style="font-size:18px; font-weight:900;">{{ c.company_name }}</div>
        <div class="score-grid">
            <div><span class="s-val">{{c.equity_score}}</span><span class="s-lbl">股权</span></div>
            <div><span class="s-val">{{c.loan_score}}</span><span class="s-lbl">贷款</span></div>
            <div><span class="s-val">{{c.bridge_score}}</span><span class="s-lbl">过桥</span></div>
            <div style="border-left:1px solid #ddd; color:var(--green);"><span class="s-val">{{c.deal_prob}}%</span><span class="s-lbl">概率</span></div>
        </div>
        <div class="reason">{{c.reason}}</div>
        {% if cur_status == '新客户' %}
        <a href="/move/{{c.id}}/已联系" class="btn-act">标记已联系</a>
        {% elif cur_status == '已联系' %}
        <a href="/move/{{c.id}}/成交" class="btn-act" style="background:var(--green);">确认成交</a>
        {% endif %}
    </div>
    {% endfor %}
</body>
</html>
'''

SETTING_UI = '''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>设置</title></head>
<body style="background:#f2f2f7; font-family:sans-serif; padding:20px;">
    <div style="background:#fff; border-radius:20px; padding:20px; max-width:400px; margin:auto;">
        <h3>配置中心</h3>
        <form method="post">
            <input type="text" name="kd_key" value="{{key}}" placeholder="API Key" style="width:100%; padding:12px; margin:10px 0; border:1px solid #ddd; border-radius:10px;">
            <button type="submit" style="width:100%; padding:12px; background:#007aff; color:#fff; border:none; border-radius:10px; font-weight:bold;">保存</button>
        </form>
        <form action="/clear" method="post" style="margin-top:30px;">
            <button type="submit" style="width:100%; background:none; border:none; color:red; font-weight:bold;">⚠️ 清空所有数据</button>
        </form>
        <button onclick="location.href='/'" style="width:100%; margin-top:20px; border:none; background:none; color:gray;">返回</button>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
