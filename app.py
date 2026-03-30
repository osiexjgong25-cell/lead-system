import os, csv, json, io, urllib.request, urllib.parse, re, ssl
from flask import Flask, render_template_string, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# --- 1. 环境与 SSL 补丁 ---
ssl._create_default_https_context = ssl._create_unverified_context
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'fa_pro_v12_5.db')

app = Flask(__name__)
app.secret_key = "fa_v11_fixed_final"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 2. 数据库模型 ---
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), unique=True, nullable=False)
    equity_score = db.Column(db.Integer, default=50)
    loan_score = db.Column(db.Integer, default=50)
    bridge_score = db.Column(db.Integer, default=50)
    deal_prob = db.Column(db.Integer, default=30)
    main_biz = db.Column(db.String(50))
    reason = db.Column(db.Text) # 存储基础逻辑原因
    live_reasons_json = db.Column(db.Text, default='[]') # 存储互联网新闻+时间
    status = db.Column(db.String(50), default='新客户')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- 3. 真联网抓取模块 ---
def fetch_live_signals(company_name):
    results = []
    try:
        query = urllib.parse.quote(f"{company_name} 融资 动态")
        url = f"https://www.bing.com/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=2.5) as response:
            html = response.read().decode('utf-8')
            # 改进正则，确保能抓到更多真实标题
            titles = re.findall(r'<h2><a .*?>(.*?)</a></h2>', html)
            if titles:
                for t in titles[:2]: # 抓取前2条增加真实感
                    clean_title = re.sub('<[^<]+?>', '', t)
                    results.append({
                        "text": clean_title[:40], 
                        "time": datetime.now().strftime('%m-%d %H:%M'), 
                        "source": "互联网实时检索"
                    })
    except:
        pass
    return results

# --- 4. 评分引擎 ---
def financing_model(name):
    e, l, b = 50, 50, 50
    live_data = fetch_live_signals(name)
    v11_reasons = []

    # 找回逻辑原因
    if any(k in name for k in ["科技", "AI", "芯片", "半导体"]): e += 35; v11_reasons.append("高新硬科技背景")
    if any(k in name for k in ["建设", "工程", "建筑"]): l += 20; v11_reasons.append("传统基建资金缺口")
    if any(k in name for k in ["纠纷", "诉讼", "执行"]): b += 45; v11_reasons.append("监测到紧急流动性风险")
    
    e, l, b = min(e, 99), min(l, 99), min(b, 99)
    scores = {"股权": e, "贷款": l, "过桥": b}
    main_biz = max(scores, key=scores.get)
    prob = min(int(max(e, l, b) * 0.9), 98)

    reason_txt = " | ".join(v11_reasons) if v11_reasons else "常规要素匹配"
    return e, l, b, prob, main_biz, reason_txt, json.dumps(live_data, ensure_ascii=False)

# --- 5. 路由 ---
@app.route('/')
def index():
    status = request.args.get('status', '新客户')
    counts = {s: Customer.query.filter_by(status=s).count() for s in ['新客户', '已联系', '成交']}
    customers = Customer.query.filter_by(status=status).order_by(Customer.updated_at.desc()).all()
    for c in customers:
        # 核心修复：确保前端能读到新闻JSON
        c.live_signals = json.loads(c.live_reasons_json) if c.live_reasons_json else []
    return render_template_string(UI_HTML, customers=customers, status=status, counts=counts)

@app.route('/import', methods=['POST'])
def handle_import():
    names_raw = request.form.get('companies', '')
    names = [n.strip() for n in names_raw.split('\n') if n.strip()]
    for name in set(names):
        if not Customer.query.filter_by(company_name=name).first():
            e, l, b, dp, biz, res_txt, res_json = financing_model(name)
            db.session.add(Customer(company_name=name, equity_score=e, loan_score=l, bridge_score=b, deal_prob=dp, main_biz=biz, reason=res_txt, live_reasons_json=res_json))
    db.session.commit()
    return redirect(url_for('index', status='新客户'))

@app.route('/move/<int:id>/<target>')
def move(id, target):
    c = Customer.query.get(id); c.status = target; db.session.commit()
    return redirect(url_for('index', status=request.args.get('prev','新客户')))

# --- 6. UI 模板 (100% 找回原因与时间显示) ---
UI_HTML = '''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>FA Pro</title>
<style>
    :root { --blue: #007aff; --bg: #f2f2f7; --gray: #8e8e93; --red: #ff3b30; }
    body { background: var(--bg); font-family: -apple-system, sans-serif; padding: 15px; margin: 0; }
    .tab-bar { display: flex; background: #e5e5ea; border-radius: 12px; padding: 2px; margin-bottom: 15px; }
    .tab-link { flex: 1; text-align: center; padding: 10px; border-radius: 10px; text-decoration: none; color: var(--gray); font-size: 13px; font-weight: bold; }
    .tab-link.active { background: #fff; color: #000; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
    .card { background: #fff; border-radius: 18px; padding: 18px; margin-bottom: 15px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); }
    textarea { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 12px; box-sizing: border-box; margin-bottom: 10px; font-size: 13px; }
    .btn { display: block; background: var(--blue); color: #fff; text-align: center; padding: 14px; border-radius: 12px; text-decoration: none; font-weight: bold; border: none; width: 100%; font-size: 15px; }
    .score-grid { display: grid; grid-template-columns: repeat(4, 1fr
