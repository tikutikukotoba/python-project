import os
import pandas as pd
import unicodedata
from pykakasi import kakasi
from flask import Flask, render_template, request, session, redirect, url_for
import requests

app = Flask(__name__)
app.secret_key = "your-secret-key"

RAKUTEN_APP_ID = os.environ.get("RAKUTEN_APP_ID")  # 楽天アプリID（環境変数）

# === パス ===
base_dir = os.path.dirname(__file__)
CSV_PATH = os.path.join(base_dir, 'data.csv')

# === CSV ===
df = pd.read_csv(CSV_PATH, encoding='cp932')

# 列名
valid_columns = [
    '食品番号', '食品名', 'エネルギー', 'たんぱく質', '脂質', '炭水化物',
    '食物繊維総量', '食塩相当量', 'カ ル シ ウ ム', '鉄', 'ビタミンA', 'ビタミンC', '備　　考'
]

df = df[valid_columns]

# 単位
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
    return text

# 検索用ひらがな列を追加
df['foodname_hira'] = df['食品名'].apply(normalize_japanese)
df['foodname_full'] = df['食品名']  # 元の名前も保持

# =======================
#     カート操作
# =======================
def get_cart():
    if 'cart' not in session:
        session['cart'] = []
    return session['cart']

def save_cart(cart):
    session['cart'] = cart

def find_food_by_id(food_id):
    try:
        food_id = int(food_id)
    except:
        return None
    row = df[df['食品番号'] == food_id]
    if row.empty:
        return None
    return row.iloc[0]

def calc_total(cart):
    total = {
        'エネルギー': 0,
        'たんぱく質': 0,
        '脂質': 0,
        '炭水化物': 0,
        '食物繊維総量': 0,
        '食塩相当量': 0,
        'カ ル シ ウ ム': 0,
        '鉄': 0,
        'ビタミンA': 0,
        'ビタミンC': 0,
    }

    for item in cart:
        food = find_food_by_id(item['食品番号'])
        if food is None:
            continue
        ratio = item.get('量', 100) / 100.0

        for col in total.keys():
            try:
                total[col] += float(food[col]) * ratio
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

    query = ''
    results = []
    error = None

    if request.method == 'POST':
        if 'search' in request.form:
            # 検索処理
            query = request.form.get('query', '').strip()
            if query:
                q_norm = normalize_japanese(query)
                # ひらがなカラム + 元の食品名 で両方検索
                mask = df['foodname_hira'].str.contains(q_norm, na=False) | df['食品名'].str.contains(query, na=False)
                results = df[mask].copy()
            else:
                error = "検索ワードを入力してください。"

        elif 'add_cart' in request.form:
            # カート追加
            food_id = request.form.get('food_id')
            amount = request.form.get('amount', '100')
            try:
                amount_val = float(amount)
            except:
                amount_val = 100

            food = find_food_by_id(food_id)
            if food is None:
                error = "指定された食品番号が存在しません。"
            else:
                cart = get_cart()
                cart.append({
                    '食品番号': int(food['食品番号']),
                    '食品名': food['食品名'],
                    '量': amount_val
                })
                save_cart(cart)
                return redirect(url_for('index'))

        elif 'go_total' in request.form:
            return redirect(url_for('total'))

    return render_template(
        'index.html',
        query=query,
        results=results,
        cart=get_cart(),
        error=error,
        units=units
    )

# =======================
#     合計画面
# =======================
@app.route('/total', methods=['GET', 'POST'])
def total():
    cart = get_cart()

    if request.method == 'POST':
        # カート更新
        if 'update_cart' in request.form:
            new_cart = []
            for i in range(len(cart)):
                amount = request.form.get(f'amount_{i}', '100')
                try:
                    amount_val = float(amount)
                except:
                    amount_val = 100
                if amount_val <= 0:
                    continue
                new_cart.append({
                    '食品番号': cart[i]['食品番号'],
                    '食品名': cart[i]['食品名'],
                    '量': amount_val
                })
            save_cart(new_cart)
            cart = new_cart

        # 全削除
        elif 'delete_all' in request.form:
            session['cart'] = []
            cart = []

    total_val = calc_total(cart)

    return render_template(
        "total.html",
        cart=cart,
        total=total_val,
        units=units
    )

# =======================
#     料理ページ（追加）
# =======================
@app.route('/cook')
def cook():
    """
    ドラゴン料理画面。楽天レシピAPIのカテゴリ別ランキングも表示する。
    """
    recipes = []

    if RAKUTEN_APP_ID:
        try:
            res = requests.get(
                "https://app.rakuten.co.jp/services/api/Recipe/CategoryRanking/20170426",
                params={
                    "applicationId": RAKUTEN_APP_ID,
                    "categoryId": "32-339",  # 例: 煮魚カテゴリ
                    "format": "json",
                    "formatVersion": 2,
                },
                timeout=5,
            )
            res.raise_for_status()
            data = res.json()

            for item in data.get("result", []):
                recipes.append({
                    "title": item.get("recipeTitle"),
                    "url": item.get("recipeUrl"),
                    "image": (
                        item.get("smallImageUrl")
                        or item.get("mediumImageUrl")
                        or item.get("foodImageUrl")
                    ),
                    "time": item.get("recipeIndication"),
                    "cost": item.get("recipeCost"),
                    "desc": item.get("recipeDescription"),
                })
        except Exception as e:
            print("Rakuten Recipe API error:", e)

    return render_template("cook.html", recipes=recipes)


if __name__ == '__main__':
    app.run(debug=True)
