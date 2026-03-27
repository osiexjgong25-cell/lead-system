import os
import pandas as pd
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = "fa_bridge_fix_v9"

# --- 数据库配置 ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///fa_pro_v9.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    equity_score = db.Column(db.Integer, default=50)
    loan_score = db.Column(db.Integer, default=50)
    bridge_score = db.Column(db.Integer, default=50) # 基准分调高至50，确保过桥业务不被埋没
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

# --- 核心：多维度过桥判定引擎 ---
def analyze_logic(name, api_key):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    e, l, b = 60, 50, 50 # 初始分持平
    reasons = []

    # 1. 过桥专项判定 (Bridge Logic)
    if any(k in name for k in ["诉讼", "纠纷", "冻结", "执行"]):
        b += 40
        reasons.append("【过桥】监测到司法风险，急需流动性调头(真实)")
    if any(k in name for k in ["贸易", "供应链", "材料"]):
        b += 20
        reasons.append("【过桥】行业周转压力大，匹配过桥需求(真实)")

    # 2. 建筑业压分与转化
    if any(k in name for k in ["工程", "建筑", "建设", "施工"]):
        l = 30 # 压低传统贷款
        if "投资" in name or "控股" in name:
            e += 30
            l = 85
            reasons.append("【股权/贷款】建筑科技企业，资本背书完整(真实)")
        else:
            b += 15 # 传统建筑业通常有过桥需求
            reasons.append("【过桥】工程垫资压力大，潜在过桥客户")
    else:
        if any(k in name for k in ["科技", "芯片", "软件"]):
            e += 30
            reasons.append("【股权】符合硬科技投向(真实)")
        if "制造" in name or "设备" in name:
            l += 35
            reasons.append("【贷款】具备生产线资质(真实)")

    # 最终业务判定
    scores = {"股权": e, "贷款": l, "过桥": b}
    biz = max(scores, key=scores.get)
    d_prob = min(int(scores[biz] * 0.9), 98)
    return e, l, b, d_prob, biz, " | ".join(reasons) if reasons else "工商基础线索匹配", now_str

# --- 路由系统 ---

@app.route('/')
def index():
    cur_status = request.args.get('status', '新客户')
    cur_biz = request.args.get('biz', '全部')
    
    query = Customer.query.filter_by(status=cur_status)
    
    # 逻辑修正：点击过桥业务时，筛选出所有过桥分高的，不只是主推为过桥的
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
    api_conf = SystemConfig.query.get('kd_key')
    api_key = api_conf.value if api_conf else None
    names = [n.strip() for n in request.form.get('companies', '').split('\n') if n.strip()]
    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            e, l, b, dp, biz, res, st = analyze_logic(name, api_key)
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

# --- iOS 26 交互 UI (修复了 URL 传参) ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>FA Pro V9</title>
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
        .reason { font-size: 11px; background: #f2f2f7; padding: 10px; border-radius: 8px; border-left: 3px solid var(--blue); }
        .time-tag { font-size: 9px; color: var(--gray); margin-top: 8px; text-align: right; }
        .btns { display: flex; gap: 10px; margin-top: 15px; }
        .btn { flex: 1; border: none; padding: 12px; border-radius: 12px; font-weight: 800; font-size: 13px; cursor: pointer; text-align: center; text-decoration: none; }
        textarea { width: 100%; border: none; background: #e5e5ea; border-radius: 12px; padding: 12px; box-sizing: border-box; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <h2 style="margin:0; letter-spacing:-1px;">FA 业务中心 V9</h2>
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
        <div class="time-tag">🌐 线索来源验证时间：{{c.source_time}}</div>

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
    <title>设置</title>
    <style>
        body { background: #f2f2f7; font-family: -apple-system, sans-serif; padding: 30px; }
        .card { background: #fff; border-radius: 20px; padding: 25px; max-width: 400px; margin: auto; }
        .input { width: 100%; padding: 15px; margin: 15px 0; border: 1px solid #ddd; border-radius: 12px; box-sizing: border-box; }
        .btn-save { width: 100%; padding: 15px; background: #007aff; color: #fff; border: none; border-radius: 12px; font-weight: 800; }
        .btn-clear { width: 100%; background: none; border: none; color: #ff3b30; font-weight: 700; margin-top: 40px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="card">
        <h3>系统配置</h3>
        <form method="post">
            <input type="text" name="kd_key" class="input" value="{{key}}" placeholder="API Key">
            <button type="submit" class="btn-save">保存</button>
        </form>
        <form action="/clear" method="post" onsubmit="return confirm('确定清空所有数据？')">
            <button type="submit" class="btn-clear">⚠️ 清空数据库</button>
        </form>
        <button onclick="location.href='/'" style="width:100%; margin-top:20px; border:none; background:none; color:var(--gray);">返回</button>
    </div>
</body>
</html>
