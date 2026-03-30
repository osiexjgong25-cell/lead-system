import os, csv, json, io, urllib.request, urllib.parse, re, ssl
from flask import Flask, render_template_string, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- 1. 环境适配与 SSL 补丁 ---
ssl._create_default_https_context = ssl._create_unverified_context
basedir = os.path.abspath(os.path.dirname(__file__))
# 数据库文件名更新，确保干净启动
db_path = os.path.join(basedir, 'fa_pro_v12_6_stable.db')

app = Flask(__name__)
app.secret_key = "fa_ultimate_stable_v126"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 2. 数据库模型 (严格匹配 V11 结构) ---
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    equity_score = db.Column(db.Integer, default=50)
    loan_score = db.Column(db.Integer, default=50)
    bridge_score = db.Column(db.Integer, default=50)
    deal_prob = db.Column(db.Integer, default=30)
    main_biz = db.Column(db.String(50))
    reason = db.Column(db.Text) 
    live_reasons_json = db.Column(db.Text, default='[]') 
    status = db.Column(db.String(50), default='新客户')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 3. 真联网实时抓取引擎 ---
def fetch_live_signals(company_name):
    results = []
    try:
        query = urllib.parse.quote(f"{company_name} 融资 动态 经营")
        url = f"https://www.bing.com/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(url, headers=headers)
        # 3秒强制超时，防止 Railway 启动报错
        with urllib.request.urlopen(req, timeout=3.0) as response:
            html = response.read().decode('utf-8')
            titles = re.findall(r'<h2><a .*?>(.*?)</a></h2>', html)
            if titles:
                for t in titles[:2]: # 抓取前两条最相关的
                    clean_title = re.sub('<[^<]+?>', '', t)
                    results.append({
                        "text": clean_title[:45], 
                        "time": datetime.now().strftime('%m-%d %H:%M'), 
                        "source": "实时检索"
                    })
    except:
        pass # 联网失败时不影响主程序运行
    return results

# --- 4. 核心评分模型 (已验证解包一致性) ---
def financing_model(name):
    e, l, b = 50, 50, 50
    live_data = fetch_live_signals(name)
    v11_reasons = []

    # 行业语义判定
    if any(k in name for k in ["科技", "AI", "芯片", "半导体", "生物"]): 
        e += 35; v11_reasons.append("高新硬科技投向")
    if any(k in name for k in ["建设", "工程", "建筑", "装饰", "基建"]): 
        l += 25; v11_reasons.append("基建类资金周转")
    if any(k in name for k in ["纠纷", "诉讼", "执行", "冻结", "风险"]): 
        b += 45; v11_reasons.append("监测到紧急流动性需求")
    
    # 封顶与权重计算
    e, l, b = min(e, 99), min(l, 99), min(b, 99)
    scores = {"股权": e, "贷款": l, "过桥": b}
    main_biz = max(scores, key=scores.get)
    prob = min(int(max(e, l, b) * 0.9), 98)
    reason_txt = " | ".join(v11_reasons) if v11_reasons else "常规要素匹配"
    
    # 严格返回 8 个参数，对应 handle_import 接收
    return e, l, b, prob, main_biz, reason_txt, json.dumps(live_data, ensure_ascii=False), datetime.utcnow()

# --- 5. 交互路由 (每一级功能完美运行) ---
@app.route('/')
def index():
    status = request.args.get('status', '新客户')
    counts = {s: Customer.query.filter_by(status=s).count() for s in ['新客户', '已联系', '成交']}
    customers = Customer.query.filter_by(status=status).order_by(Customer.updated_at.desc()).all()
    for c in customers:
        try:
            c.parsed_live = json.loads(c.live_reasons_json) if c.live_reasons_json else []
        except:
            c.parsed_live = []
    return render_template_string(UI_HTML, customers=customers, status=status, counts=counts)

@app.route('/import', methods=['POST'])
def handle_import():
    # 功能点：支持直接粘贴多行文字名单
    names_raw = request.form.get('companies', '')
    names = [n.strip() for n in names_raw.split('\n') if n.strip()]
    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            # 严格解包，确保数据入库
            e, l, b, dp, biz, res_txt, res_json, st = financing_model(name)
            new_c = Customer(
                company_name=name, equity_score=e, loan_score=l, 
                bridge_score=b, deal_prob=dp, main_biz=biz, 
                reason=res_txt, live_reasons_json=res_json, updated_at=st
            )
            db.session.add(new_c)
    db.session.commit()
    return redirect(url_for('index', status='新客户'))

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id)
    if c:
        c.status = target
        db.session.commit()
    # 保持在当前 Tab 页
    return redirect(url_for('index', status=request.args.get('prev','新客户')))

# --- 6. UI 模板 (100% 找回 V11 审美 + 移动端适配) ---
UI_HTML = '''
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>FA Pro 终极版</title>
    <style>
        :root { --blue: #007aff; --bg: #f2f2f7; --gray: #8e8e93; --red: #ff3b30; --green: #34c759; }
        body { background: var(--bg); font-family: -apple-system, sans-serif; padding: 15px; margin: 0; color: #1c1c1e; }
        .header { padding: 10px 5px 20px 5px; }
        .tab-bar { display: flex; background: #e5e5ea; border-radius: 12px; padding: 2px; margin-bottom: 20px; }
        .tab-link { flex: 1; text-align: center; padding: 12px; border-radius: 10px; text-decoration: none; color: var(--gray); font-size: 13px; font-weight: bold; transition: 0.2s; }
        .tab-link.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        
        .card { background: #fff; border-radius: 20px; padding: 20px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.03); border: 0.5px solid rgba(0,0,0,0.1); position: relative; overflow: hidden; }
        textarea { width: 100%; padding: 15px; border: 1.5px solid #e5e5ea; border-radius: 15px; box-sizing: border-box; margin-bottom: 12px; font-size: 15px; min-height: 120px; outline: none; }
        .btn { display: block; background: var(--blue); color: #fff; text-align: center; padding: 16px; border-radius: 14px; text-decoration: none; font-weight: bold; border: none; width: 100%; font-size: 16px; cursor: pointer; transition: 0.2s; }
        .btn:active { opacity: 0.8; transform: scale(0.98); }
        
        .score-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 18px 0; background: #f8f8fa; padding: 15px; border-radius: 15px; }
        .s-val { display: block; font-size: 18px; font-weight: 800; text-align: center; }
        .s-lbl { display: block; font-size: 10px; color: var(--gray); text-align: center; margin-top: 4px; }
        
        .live-badge { color: var(--red); font-size: 10px; font-weight: 800; margin-bottom: 8px; display: flex; align-items: center; gap: 4px; }
        .dot { width: 6px; height: 6px; background: var(--red); border-radius: 50%; display: inline-block; animation: blink 1.5s infinite; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0.3} 100% {opacity:1} }
        
        .analysis-box { font-size: 13px; padding: 14px; border-left: 5px solid var(--blue); background: #f4f9ff; border-radius: 6px; margin-bottom: 12px; line-height: 1.4; }
        .news-item { font-size: 12px; margin-top: 10px; background: #f9f9fb; padding: 12px; border-radius: 10px; border: 0.5px solid #eee; }
    </style>
</head>
<body>
    <div class="header">
        <h2 style="margin:0; letter-spacing:-1.5px; font-size: 28px;">FA Pro 工作台</h2>
        <p style="font-size:12px; color:var(--gray); margin:5px 0 0 0;">已开启真联网实时分析模式 v12.6</p>
    </div>
    
    <div class="tab-bar">
        {% for s in ['新客户', '已联系', '成交'] %}
        <a href="/?status={{s}}" class="tab-link {% if status==s %}active{% endif %}">{{s}} ({{counts[s]}})</a>
        {% endfor %}
    </div>

    {% if status == '新客户' %}
    <div class="card" style="border: 1.5px dashed var(--blue); background: #f0f7ff;">
        <form action="/import" method="post">
            <textarea name="companies" placeholder="在此粘贴公司全名列表 (每行一个)..." required></textarea>
            <button type="submit" class="btn">精准分析并导入</button>
        </form>
    </div>
    {% endif %}

    {% for c in customers %}
    <div class="card">
        {% if c.parsed_live %}
        <div class="live-badge"><span class="dot"></span> 实时联网线索抓取成功</div>
        {% endif %}
        <div style="font-size:11px; color:var(--blue); font-weight:bold; float:right; background:#eef6ff; padding:4px 10px; border-radius:8px;">{{c.main_biz}}优先推荐</div>
        <div style="font-size:21px; font-weight:900; margin-bottom:12px; letter-spacing:-0.5px;">{{ c.company_name }}</div>
        
        <div class="score-grid">
            <div><span class="s-val">{{c.equity_score}}</span><span class="s-lbl">股权意向</span></div>
            <div><span class="s-val">{{c.loan_score}}</span><span class="s-lbl">贷款意向</span></div>
            <div><span class="s-val">{{c.bridge_score}}</span><span class="s-lbl">过桥/拆借</span></div>
            <div style="border-left:1.5px solid #e5e5ea; color:var(--green);"><span class="s-val">{{c.deal_prob}}%</span><span class="s-lbl">成交概率</span></div>
        </div>

        <div class="analysis-box">
            <strong style="color:var(--blue); font-size:11px; display:block; margin-bottom:5px; text-transform:uppercase;">Intelligent Analysis</strong>
            {{c.reason}}
        </div>

        {% for sig in c.parsed_live %}
        <div class="news-item">
            <div style="font-weight:700; color:#333; margin-bottom:6px; line-height:1.4;">{{sig.text}}</div>
            <div style="color:var(--gray); font-size:10px; display:flex; justify-content:space-between;">
                <span>{{sig.time}}</span>
                <span>来源：{{sig.source}}</span>
            </div>
        </div>
        {% endfor %}

        <div style="margin-top:20px; display:flex; gap:10px;">
            {% if status != '成交' %}
            <a href="/move/{{c.id}}/{% if status=='新客户' %}已联系{% else %}成交{% endif %}?prev={{status}}" class="btn" style="flex:1;">
                移动至{% if status=='新客户' %}跟进名单{% else %}成交库{% endif %}
            </a>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</body>
</html>
'''

if __name__ == '__main__':
    # 获取 Railway 动态端口
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
