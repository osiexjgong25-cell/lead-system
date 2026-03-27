import os
import pandas as pd
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fa_pro_ultra_2026")

# --- 数据库持久化配置 ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///fa_ultimate_v4.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 核心数据模型 ---
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    
    # 金融三要素分值 (0-100)
    equity_score = db.Column(db.Integer, default=60)    # 股权融资意向
    loan_score = db.Column(db.Integer, default=50)      # 银行贷款资质
    bridge_score = db.Column(db.Integer, default=20)    # 过桥资金急需度
    
    deal_prob = db.Column(db.Integer, default=40)      # 成交概率
    priority = db.Column(db.String(20))                # 高 / 中 / 普通
    main_biz = db.Column(db.String(50))                # 判定业务：股权/贷款/过桥
    reason = db.Column(db.Text)                        # 评分原因（带时间戳）
    status = db.Column(db.String(50), default='未联系') # 未联系 / 已联系 / 成交
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- FA 智能分析引擎 ---
def smart_analyze(name):
    # 基础分设定
    e, l, b = 60, 50, 20
    reasons = []
    
    # 行业语义分析逻辑 (真实业务规则)
    if any(k in name for k in ["科技", "生物", "芯片", "半导体", "智能"]):
        e += 25
        reasons.append("高新硬科技，股权融资意向极强")
    if any(k in name for k in ["建设", "工程", "贸易", "供应链"]):
        l += 35
        reasons.append("有明显经营现金流，适配银行贷款")
    if any(k in name for k in ["实业", "投资", "控股"]):
        b += 45
        reasons.append("资产重，存在潜在过桥缺口")

    # 判定主推业务
    scores = {"股权": e, "贷款": l, "过桥": b}
    recommend_biz = max(scores, key=scores.get)
    max_val = scores[recommend_biz]
    
    # 成交概率推算
    d_prob = min(int(max_val * 0.85), 95)
    prio = "高" if max_val > 80 else ("中" if max_val > 65 else "普通")
    reason_str = f"[{datetime.now().strftime('%m-%d')}] " + (" | ".join(reasons) if reasons else "常规业务库导入")
    
    return e, l, b, d_prob, prio, recommend_biz, reason_str

# --- 业务路由 ---

@app.route('/')
def index():
    biz = request.args.get('biz', '全部')
    status = request.args.get('status', '全部')
    
    query = Customer.query
    if biz != '全部': query = query.filter_by(main_biz=biz)
    if status != '全部': query = query.filter_by(status=status)
    
    # 核心：按成交概率降序，把最容易开单的推在前面
    customers = query.order_by(Customer.deal_prob.desc()).all()
    return render_template_string(UI_HTML, customers=customers, current_biz=biz, current_status=status)

@app.route('/import', methods=['POST'])
def handle_import():
    raw_text = request.form.get('companies', '')
    names = [n.strip() for n in raw_text.split('\n') if n.strip()]
    
    file = request.files.get('file')
    if file and file.filename.endswith(('.xlsx', '.xls')):
        try:
            df = pd.read_excel(file)
            names.extend(df.iloc[:, 0].astype(str).tolist())
        except: pass

    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            e, l, b, dp, p, biz, res = smart_analyze(name)
            new_c = Customer(company_name=name, equity_score=e, loan_score=l, bridge_score=b,
                             deal_prob=dp, priority=p, main_biz=biz, reason=res)
            db.session.add(new_c)
    db.session.commit()
    return redirect('/')

@app.route('/update/<int:id>/<new_status>')
def update(id, new_status):
    c = Customer.query.get(id)
    if c:
        c.status = new_status
        db.session.commit()
    return redirect('/')

@app.route('/clear', methods=['POST'])
def clear():
    Customer.query.delete()
    db.session.commit()
    return redirect('/')

# --- 真实 iOS 26 风格界面 ---
UI_HTML = '''
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>FA Pro 销售端</title>
    <style>
        :root { --bg: #f2f2f7; --blue: #007aff; --green: #34c759; --red: #ff3b30; }
        body { background: var(--bg); font-family: -apple-system, sans-serif; margin: 0; padding: 20px; color: #1c1c1e; }
        .card { background: #fff; border-radius: 16px; padding: 16px; margin-bottom: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        .flex-between { display: flex; justify-content: space-between; align-items: center; }
        .biz-badge { font-size: 11px; padding: 3px 8px; border-radius: 6px; font-weight: 800; text-transform: uppercase; }
        .biz-股权 { background: #5856d622; color: #5856d6; }
        .biz-贷款 { background: #34c75922; color: #34c759; }
        .biz-过桥 { background: #ff950022; color: #ff9500; }
        .score-box { display: flex; gap: 10px; margin: 15px 0; background: #f8f8fa; padding: 12px; border-radius: 12px; }
        .score-item { flex: 1; text-align: center; }
        .score-val { display: block; font-size: 18px; font-weight: 800; color: var(--blue); }
        .score-lbl { font-size: 10px; color: #8e8e93; }
        .btn-group { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 10px; margin-bottom: 10px; }
        .f-btn { border: none; padding: 8px 14px; border-radius: 10px; background: #e5e5ea; white-space: nowrap; font-weight: 600; cursor: pointer; }
        .f-btn.active { background: var(--blue); color: white; }
        textarea { width: 100%; border: none; background: #e5e5ea; border-radius: 12px; padding: 12px; box-sizing: border-box; font-size: 15px; }
        .prio-高 { color: var(--red); }
    </style>
</head>
<body>
    <div class="flex-between" style="margin-bottom: 20px;">
        <h2 style="margin:0; letter-spacing:-1px;">业务智能中心</h2>
        <form action="/clear" method="post" onsubmit="return confirm('确定清空？')">
            <button type="submit" style="background:none; border:none; color:var(--red); font-size:12px;">清空</button>
        </form>
    </div>

    <div class="card">
        <form action="/import" method="post" enctype="multipart/form-data">
            <textarea name="companies" rows="2" placeholder="粘贴文档公司名单或消息..."></textarea>
            <div class="flex-between" style="margin-top:10px;">
                <input type="file" name="file" id="f" style="display:none;"><label for="f" style="color:var(--blue); font-size:13px; cursor:pointer;">📁 Excel导入</label>
                <button type="submit" style="background:var(--blue); color:white; border:none; padding:8px 22px; border-radius:10px; font-weight:700;">AI 深度分析</button>
            </div>
        </form>
    </div>

    <div class="btn-group">
        {% for b in ['全部', '股权', '贷款', '过桥'] %}
        <button onclick="location.href='/?biz={{b}}&status={{current_status}}'" class="f-btn {% if current_biz==b %}active{% endif %}">{{b}}业务</button>
        {% endfor %}
    </div>

    {% for c in customers %}
    <div class="card">
        <div class="flex-between">
            <div style="font-size: 18px; font-weight: 800;">{{ c.company_name }} <span class="biz-badge biz-{{c.main_biz}}">{{c.main_biz}}类</span></div>
            <span class="prio-{{c.priority}}" style="font-size:11px; font-weight:800;">{{c.priority}}优先级</span>
        </div>
        
        <div class="score-box">
            <div class="score-item"><span class="score-val">{{c.equity_score}}</span><span class="score-lbl">股权意向</span></div>
            <div class="score-item"><span class="score-val" style="color:var(--green)">{{c.loan_score}}</span><span class="score-lbl">贷款资质</span></div>
            <div class="score-item"><span class="score-val" style="color:#ff9500">{{c.bridge_score}}</span><span class="score-lbl">过桥需求</span></div>
            <div class="score-item" style="border-left: 1px solid #ddd;"><span class="score-val" style="color:var(--blue)">{{c.deal_prob}}%</span><span class="score-lbl">成交概率</span></div>
        </div>
        
        <div style="font-size:12px; color:#636366; background:#f2f2f7; padding:12px; border-radius:10px; margin-bottom:15px;">💡 {{c.reason}}</div>
        
        <div class="flex-between" style="gap:10px;">
            <button onclick="location.href='/update/{{c.id}}/已联系'" style="flex:1; border:1px solid #ddd; padding:10px; border-radius:12px; background:none; font-weight:600;">标记跟进</button>
            <button onclick="location.href='/update/{{c.id}}/成交'" style="flex:1; background:var(--green); color:white; border:none; padding:10px; border-radius:12px; font-weight:700;">标记成交</button>
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    # 自动适配 Railway 的 PORT 环境变量
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
