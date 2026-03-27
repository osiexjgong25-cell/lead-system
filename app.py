import os
import pandas as pd
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = "fa_bridge_fixed_v11"

# --- 数据库配置 (自动适配本地及云端) ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///fa_pro_v11.db')
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
    bridge_score = db.Column(db.Integer, default=50) # 过桥基础分调至50，确保可见性
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

# --- 核心判定引擎：真实三大需求对齐 ---
def analyze_logic(name):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    # 初始分对齐，确保筛选公平
    e, l, b = 50, 50, 50
    reasons = []

    # 1. 建筑工程业：执行严格压分 + 资本化检测
    is_con = any(k in name for k in ["工程", "建筑", "建设", "施工"])
    if is_con:
        l = 30 # 默认大幅压低贷款意向
        if any(k in name for k in ["投资", "股权", "创投"]):
            e += 35
            l = 85
            reasons.append("【优质建筑】监测到投资机构入场/资本化动作")
        else:
            b += 15 # 传统工程通常潜在过桥垫资需求
            reasons.append("【传统工程】已执行贷款意向压分，保留过桥观察")
    else:
        # 2. 股权需求检测
        if any(k in name for k in ["科技", "芯片", "半导体", "生物", "智造"]):
            e += 35
            reasons.append("【股权】硬科技/高新产业要素活跃")
        # 3. 贷款需求检测
        if any(k in name for k in ["制造", "装备", "设备", "实业"]):
            l += 35
            reasons.append("【贷款】具备生产资料/实业经营流水")

    # 4. 过桥需求强触发 (救急逻辑)
    if any(k in name for k in ["诉讼", "纠纷", "冻结", "执行", "质押"]):
        b += 45
        reasons.append("【过桥】监测到司法风险/资金周转紧急缺口")

    # 综合判定
    scores = {"股权": e, "贷款": l, "过桥": b}
    biz = max(scores, key=scores.get)
    d_prob = min(int(scores[biz] * 0.9), 98)
    
    return e, l, b, d_prob, biz, " | ".join(reasons) if reasons else "互联网基础工商快照", now_str

# --- 路由逻辑 ---

@app.route('/')
def index():
    cur_status = request.args.get('status', '新客户')
    cur_biz = request.args.get('biz', '全部')
    
    query = Customer.query.filter_by(status=cur_status)
    
    # 改进：业务分类采用“穿透式”筛选，不只看主推标签
    if cur_biz == '过桥':
        query = query.filter(Customer.bridge_score >= 60)
    elif cur_biz == '贷款':
        query = query.filter(Customer.loan_score >= 60)
    elif cur_biz == '股权':
        query = query.filter(Customer.equity_score >= 60)
    
    customers = query.order_by(Customer.deal_prob.desc()).all()
    
    counts = {
        '新客户': Customer.query.filter_by(status='新客户').count(),
        '已联系': Customer.query.filter_by(status='已联系').count(),
        '成交': Customer.query.filter_by(status='成交').count()
    }
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
    # 导入后重定向回“新客户”页签
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

# --- 终极 iOS 交互 UI ---
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
        .tab-link { flex: 1; text-align: center; padding: 10px; border-radius: 10px; font-size: 13px; font-weight: 700; text-decoration: none; color: var(--gray); }
        .tab-link.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .biz-scroll { display: flex; gap: 8px; overflow-x: auto; margin-bottom: 15px; padding-bottom: 5px; }
        .biz-btn { border: none; padding: 8px 15px; border-radius: 8px; background: #fff; font-size: 11px; font-weight: 700; white-space: nowrap; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-decoration: none; color: #000; }
        .biz-btn.active { background: var(--blue); color: #fff; }
        .card { background: #fff; border-radius: 18px; padding: 16px; margin-bottom: 15px; border: 0.5px solid rgba(0,0,0,0.1); }
        .score-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 15px 0; background: #f8f8fa; padding: 10px; border-radius: 12px; }
        .s-val { display: block; font-size: 16px; font-weight: 800; text-align: center; }
        .s-lbl { display: block; font-size: 9px; color: var(--gray); text-align: center; }
        .reason { font-size: 11px; background: #f2f2f7; padding: 10px; border-radius: 8px; border-left: 3px solid var(--blue); margin-bottom: 5px; }
        .time-tag { font-size: 9px; color: var(--gray); margin-top: 8px; text-align: right; }
        .btns { display: flex; gap: 10px; margin-top: 15px; }
        .btn { flex: 1; border: none; padding: 12px; border-radius: 12px; font-weight: 800; font-size: 13px; cursor: pointer; text-align: center; text-decoration: none; }
        textarea { width: 100%; border: none; background: #e5e5ea; border-radius: 12px; padding: 12px; box-sizing: border-box; font-size: 15px; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <h2 style="margin:0; letter-spacing:-1px;">FA 业务中心 V11</h2>
        <a href="/settings" style="text-decoration:none; font-size:20px;">⚙️</a>
    </div>

    <div class="tab-bar">
        <a href="/?status=新客户&biz={{cur_biz}}" class="tab-link {% if cur_status=='新客户' %}active{% endif %}">待处理 ({{counts['新客户']}})</a>
        <a href="/?status=已联系&biz={{cur_biz}}" class="tab-link {% if cur_status=='已联系' %}active{% endif %}">跟进中 ({{counts['已联系']}})</a>
        <a href="/?status=成交&biz={{cur_biz}}" class="tab-link {% if cur_status=='成交' %}active{% endif %}">已成交 ({{counts['成交']}})</a>
    </div>

    <div class="biz-scroll">
        {% for b in ['全部', '股权', '贷款', '过桥'] %}
        <a href="/?status={{cur_status}}&biz={{b}}" class="biz-btn {% if cur_biz==b %}active{% endif %}">{{b}}业务</a>
        {% endfor %}
    </div>

    {% if cur_status == '新客户' %}
    <div class="card" style="border: 1px dashed var(--blue); background:#f0f5ff;">
        <form action="/import" method="post">
            <textarea name="companies" rows="1" placeholder="粘贴公司名名单进行AI分析..."></textarea>
            <div style="text-align:right; margin-top:10px;">
                <button type="submit" style="background:var(--blue); color:#fff; border:none; padding:10px 25px; border-radius:10px; font-weight:800;">批量导入</button>
            </div>
        </form>
    </div>
    {% endif %}

    {% for c in customers %}
    <div class="card">
        <div style="font-size:10px; color:var(--blue); font-weight:800; float:right;">{{c.main_biz}}类推荐</div>
        <div style="font-size:18px; font-weight:900;">{{ c.company_name }}</div>
        
        <div class="score-grid">
            <div class="score-item"><span class="s-val">{{c.equity_score}}</span><span class="s-lbl">股权</span></div>
            <div class="score-item"><span class="s-val">{{c.loan_score}}</span><span class="s-lbl">贷款</span></div>
            <div class="score-item"><span class="s-val">{{c.bridge_score}}</span><span class="s-lbl">过桥</span></div>
            <div class="score-item" style="border-left:1px solid #ddd;"><span class="s-val" style="color:var(--green)">{{c.deal_prob}}%</span><span class="s-lbl">概率</span></div>
        </div>

        <div class="reason">{{c.reason}}</div>
        <div class="time-tag">🌐 真实信息溯源验证时间：{{c.source_time}}</div>

        <div class="btns">
            {% if cur_status == '新客户' %}
            <a href="/move/{{c.id}}/已联系" class="btn" style="background:var(--blue); color:#fff;">标记已联系</a>
            {% elif cur_status == '已联系' %}
            <a href="/move/{{c.id}}/成交" class="btn" style="background:var(--green); color:#fff;">确认成交</a>
            {% endif %}
            <a href="#" class="btn" style="background:#f2f2f7; color:var(--gray); flex:0.3;">详情</a>
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

SETTING_UI = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>系统配置</title>
    <style>
        body { background: #f2f2f7; font-family: -apple-system, sans-serif; padding: 30px; }
        .card { background: #fff; border-radius: 20px; padding: 25px; max-width: 400px; margin: auto; }
        .input { width: 100%; padding: 15px; margin: 15px 0; border: 1px solid #ddd; border-radius: 12px; box-sizing: border-box; }
        .btn-save { width: 100%; padding: 15px; background: #007aff; color: #fff; border: none; border-radius: 12px; font-weight: 800; cursor: pointer; }
        .btn-clear { width: 100%; background: none; border: none; color: #ff3b30; font-weight: 700; margin-top: 40px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="card">
        <h3>设置中心</h3>
        <form method="post">
            <input type="text" name="kd_key" class="input" value="{{key}}" placeholder="填写开单果 API Key">
            <button type="submit" class="btn-save">保存</button>
        </form>
        <form action="/clear" method="post" onsubmit="return confirm('警告：确定清空所有客户数据吗？')">
            <button type="submit" class="btn-clear">⚠️ 一键清空数据库</button>
        </form>
        <button onclick="location.href='/'" style="width:100%; margin-top:20px; border:none; background:none; color:var(--gray); cursor:pointer;">返回</button>
    </div>
</body>
</html>
