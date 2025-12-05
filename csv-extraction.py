import os
import pandas as pd
import unicodedata
from pykakasi import kakasi
from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "your-secret-key"

# === パス ===
base_dir = os.path.dirname(__file__)
CSV_PATH = os.path.join(base_dir, 'data.csv')

# === CSV ===
df = pd.read_csv(CSV_PATH, encoding='cp932')

food_col = '食品名(100g当たり)'
cols = [
    'エネルギー', 'たんぱく質', '脂質', '炭水化物',
    '食物繊維総量', '食塩相当量', 'カ ル シ ウ ム',
    '鉄', 'ビタミンA', 'ビタミンC', '備　　考'
]

units = {
    'エネルギー': 'kcal', 'たんぱく質': 'g', '脂質': 'g',
    '炭水化物': 'g', '食物繊維総量': 'g', '食塩相当量': 'g',
    'カ ル シ ウ ム': 'mg', '鉄': 'mg', 'ビタミンA': 'µg',
    'ビタミンC': 'mg', '備　　考': ''
}

# === ひらがな変換 ===
kks = kakasi()
kks.setMode('J', 'H')
kks.setMode('K', 'H')
kks.setMode('H', 'H')
kks.setMode('a', 'a')
converter = kks.getConverter()

def normalize_japanese(text):
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFKC', text)
    text = converter.do(text)
    text = text.lower().strip()
    return text

df[food_col] = df[food_col].astype(str)
df['__norm_name__'] = df[food_col].apply(normalize_japanese)


# === 合計計算（g対応 & 安全処理） ===
def calc_total(cart):
    total = {col: 0 for col in cols}

    for item in cart:
        name = item["name"]
        gram = float(item["gram"])
        ratio = gram / 100.0

        match = df[df[food_col] == name]
        if match.empty:
            continue  # ← 安定化（例外回避）

        row = match.iloc[0]

        for col in cols:
            try:
                total[col] += float(row[col]) * ratio
            except:
                pass

    return total


# =======================
#     検索画面
# =======================
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'cart' not in session:
        session['cart'] = []

    cart = session['cart']
    total = calc_total(cart)

    selected_name = None
    result = None
    candidates = None
    message = None
    food_name = None

    if request.method == 'POST':

        # 食品選択
        if 'select_name' in request.form:
            selected_name = request.form['select_name']
            row = df[df[food_col] == selected_name].iloc[0]
            result = [
                {'name': col, 'value': f"{row[col]} {units.get(col, '')}".strip()}
                for col in cols
            ]
            message = f"{selected_name} の栄養素"

        # 食品検索
        else:
            food_name = request.form.get('food_name', '').strip()
            keywords = [normalize_japanese(k)
                        for k in food_name.replace("　", " ").split() if k]

            filtered = df
            for kw in keywords:
                filtered = filtered[filtered['__norm_name__'].str.contains(kw, na=False)]

            if filtered.empty:
                message = "該当する食品がありません。"
            elif len(filtered) == 1:
                selected_name = filtered.iloc[0][food_col]
                row = filtered.iloc[0]
                result = [
                    {'name': col, 'value': f"{row[col]} {units.get(col, '')}".strip()}
                    for col in cols
                ]
                message = f"{selected_name} の栄養素"
            else:
                candidates = filtered[food_col].unique().tolist()
                message = "候補があります。"

    return render_template(
        "見た目.html",
        selected_name=selected_name,
        result=result,
        candidates=candidates,
        message=message,
        food_name=food_name,
        cart=cart,
        total=total
    )


# =======================
#     カート追加（g対応）
# =======================
@app.route('/add/<name>', methods=['POST'])
def add_cart(name):
    gram = float(request.form.get("gram", 100))

    cart = session.get('cart', [])
    cart.append({"name": name, "gram": gram})
    session['cart'] = cart

    return redirect(url_for('index'))


# =======================
#     合計画面
# =======================
@app.route('/total', methods=['GET', 'POST'])
def total_page():
    cart = session.get('cart', [])

    if request.method == 'POST':

        # 選択削除
        if 'delete_selected' in request.form:
            del_indexes = list(map(int, request.form.getlist("delete_item")))
            cart = [item for i, item in enumerate(cart) if i not in del_indexes]
            session['cart'] = cart

        # 全削除
        elif 'delete_all' in request.form:
            session['cart'] = []
            cart = []

    total = calc_total(cart)

    return render_template(
        "合計.html",
        cart=cart,
        total=total
    )


# =======================
#     料理ページ（追加）
# =======================
@app.route('/cook')
def cook():
    return render_template("料理.html")


if __name__ == '__main__':
    app.run(debug=True)
