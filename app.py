import os, json, urllib.request, urllib.parse, re, ssl
from flask import Flask, render_template_string, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- 1. 配置与初始化 ---
ssl._create_default_https_context = ssl._create_unverified_context
app = Flask(__name__)
app.secret_key = "fa_v12_7_pro"
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'fa_pro_v12_7.db')
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
    status = db.Column(db.String(50), default='新客户')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 3. 真联网抓取 (带时间戳) ---
def fetch_live_info(name):
    results = []
    try:
        query = urllib.parse.quote(f"{name} 融资 经营风险")
        url = f"https://www.bing.com/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            html = resp.read().decode('utf-8')
            titles = re.findall(r'<h2><a .*?>(.*?)</a></h2>', html)
            for t in titles[:2]:
                clean_t = re.sub('<[^<]+?>', '', t)
                results.append({"t": clean_t[:45], "d": datetime.now().strftime('%m/%d %H:%M')})
    except: pass
    return results

# --- 4. 实战级评分引擎 (理由大幅强化) ---
def analyze_logic(name):
    e, l, b = 50, 50, 50
    live_info = fetch_live_info(name)
    r_list = []
    
    # 股权判定 (辛辣版)
    if any(k in name for k in ["科技", "AI", "半导体", "生物"]):
        e += 40; r_list.append("硬科技稀缺标的，资本溢价极高")
    # 贷款判定 (辛辣版)
    if any(k in name for k in ["建设", "建筑", "工程", "贸易"]):
        l += 35; r_list.append("重资产/长周期，传统信贷刚需")
    # 过桥判定 (毒舌版)
    if any(k in name for k in ["风险", "被执行", "纠纷", "冻结"]):
        b += 48; r_list.append("监测到紧急风险，过桥需求迫切")

    e, l, b = min(e, 99), min(l, 99), min(b, 99)
    scores = {"股权": e, "贷款": l, "过桥": b}
    main_biz = max(scores, key=scores.get)
    prob = min(int(max(e, l, b) * 0.92), 98)
    reason = " | ".join(r_list) if r_list else "常规资产，需进一步挖掘需求"
    
    return e, l, b, prob, main_biz, reason, json.dumps(live_info, ensure_ascii=False)

# --- 5. 交互路由 ---
@app.route('/')
def index():
    tab = request.args.get('tab', '新客户')
    filter_type = request.args.get('filter', '全部') # 股权/贷款/过桥 筛选
    
    query = Customer.query.filter_by(status=tab)
    if filter_type != '全部':
        query = query.filter(Customer.main_biz == filter_type)
        
    customers = query.order_by(Customer.updated_at.desc()).all()
    for c in customers: c.news = json.loads(c.live_json)
    
    counts = {s: Customer.query.filter_by(status=s).count() for s in ['新客户', '已联系', '成交']}
    return render_template_string(UI_HTML, customers=customers, tab=tab, filter=filter_type, counts=counts)

@app.route('/import', methods=['POST'])
def handle_import():
    names = [n.strip() for n in request.form.get('companies', '').split('\n') if n.strip()]
    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            e, l, b, p, biz, res, j = analyze_logic(name)
            db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, bridge_score=b, deal_prob=p, main_biz=biz, reason=res, live_json=j))
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/clear')
def clear_data():
    Customer.query.delete()
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id); c.status = target; db.session.commit()
    return redirect(url_for('index', tab=request.args.get('prev','新客户')))

# --- 6. 极致 UI 模板 ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>FA Pro V12.7</title>
    <style>
        :root { --blue: #007aff; --bg: #f2f2f7; --red: #ff3b30; --green: #34c759; }
        body { background: var(--bg); font-family: -apple-system, sans-serif; padding: 15px; margin: 0; }
        .tab-bar { display: flex; background: #e5e5ea; border-radius: 12px; padding: 2px; margin-bottom: 10px; }
        .tab-link { flex: 1; text-align: center; padding: 10px; border-radius: 10px; text-decoration: none; color: #8e8e93; font-size: 13px; font-weight: bold; }
        .tab-link.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        
        .filter-bar { display: flex; gap: 8px; margin-bottom: 15px; overflow-x: auto; padding-bottom: 5px; }
        .filter-btn { padding: 6px 14px; background: #fff; border-radius: 20px; font-size: 11px; text-decoration: none; color: #666; border: 0.5px solid #ddd; }
        .filter-btn.active { background: var(--blue); color: #fff; border: none; }

        .card { background: #fff; border-radius: 20px; padding: 20px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); }
        .btn { display: block; background: var(--blue); color: #fff; text-align: center; padding: 14px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 15px; border:none; width:100%; }
        
        .score-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 15px 0; background: #f8f8fa; padding: 12px; border-radius: 12px; }
        .s-val { display: block; font-size: 17px; font-weight: 800; text-align: center; }
        .s-lbl { display: block; font-size: 10px; color: #8e8e93; text-align: center; margin-top: 2px; }
        
        .reason-box { font-size: 12px; padding: 12px; border-left: 4px solid var(--blue); background: #f0f7ff; border-radius: 6px; margin-bottom: 10px; color: #333; line-height: 1.4; }
        .news-item { font-size: 11px; color: #666; background: #f9f9fb; padding: 8px; border-radius: 8px; margin-top: 5px; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <h2 style="margin:0; letter-spacing:-1px;">FA Pro 工作台</h2>
        <a href="/clear" onclick="return confirm('确定清空所有数据？')" style="font-size:12px; color:var(--red); text-decoration:none; font-weight:bold;">一键爆破数据</a>
    </div>

    <div class="tab-bar">
        {% for s in ['新客户', '已联系', '成交'] %}
        <a href="/?tab={{s}}" class="tab-link {% if tab==s %}active{% endif %}">{{s}} ({{counts[s]}})</a>
        {% endfor %}
    </div>

    <div class="filter-bar">
        {% for f in ['全部', '股权', '贷款', '过桥'] %}
        <a href="/?tab={{tab}}&filter={{f}}" class="filter-btn {% if filter==f %}active{% endif %}">{{f}}类优先</a>
        {% endfor %}
    </div>

    {% if tab == '新客户' %}
    <div class="card" style="border: 1.5px dashed var(--blue); background: #f0f7ff; margin-bottom:20px;">
        <form action="/import" method="post">
            <textarea name="companies" style="width:100%; height:100px; border:none; background:transparent; outline:none;" placeholder="在此粘贴公司全名列表 (每行一个)..."></textarea>
            <button type="submit" class="btn">精准分析并导入</button>
        </form>
    </div>
    {% endif %}

    {% for c in customers %}
    <div class="card">
        <div style="font-size:10px; color:var(--blue); font-weight:bold; float:right;">{{c.main_biz}}优先标的</div>
        <div style="font-size:19px; font-weight:900;">{{ c.company_name }}</div>
        
        <div class="score-row">
            <div><span class="s-val">{{c.equity_score}}</span><span class="s-lbl">股权</span></div>
            <div><span class="s-val">{{c.loan_score}}</span><span class="s-lbl">贷款</span></div>
            <div><span class="s-val">{{c.bridge_score}}</span><span class="s-lbl">过桥</span></div>
            <div style="color:var(--green);"><span class="s-val">{{c.deal_prob}}%</span><span class="s-lbl">潜力值</span></div>
        </div>

        <div class="reason-box"><strong>实战判语：</strong>{{c.reason}}</div>

        {% for n in c.news %}
        <div class="news-item">
            <strong>{{n.t}}</strong><br>
            <span style="color:#999; font-size:10px;">{{n.d}} | 互联网实时快讯</span>
        </div>
        {% endfor %}

        <div style="margin-top:15px; display:flex; gap:10px;">
            <a href="/move/{{c.id}}/已联系?prev={{tab}}" class="btn" style="flex:1;">移动至已联系</a>
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
