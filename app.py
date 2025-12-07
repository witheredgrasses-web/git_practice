from flask import Flask, render_template, request, redirect, url_for, flash, g, session
import sqlite3
import os
from functools import wraps 


app = Flask(__name__)
app.secret_key = "change_this_to_random_string"  # フラッシュメッセージ用（適当に変更してOK）

# プロジェクト直下の cafe_management.db を使う
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "cafe_management.db")


# ====== DB 接続まわり ======
def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row  # 行を dict っぽく扱えるようにする
        conn.execute("PRAGMA foreign_keys = ON;")
        g.db = conn
    return g.db

@app.before_request
def load_logged_in_user():
    """リクエストごとに「今ログインしているユーザー」を g.user にセットする。"""
    user_id = session.get("user_id")

    if user_id is None:
        g.user = None
    else:
        db = get_db()
        user = db.execute(
            "SELECT id, username, role FROM USERS WHERE id = ?",
            (user_id,)
        ).fetchone()
        g.user = user

def login_required(view):
    """ログインしていない場合は /login にリダイレクトするデコレータ。"""
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("このページを見るにはログインが必要です。", "error")
            return redirect(url_for("login"))
        return view(**kwargs)
    return wrapped_view

def role_required(role):
    """指定した role 以外はアクセスできないデコレータ。"""
    def decorator(view):
        @wraps(view)
        def wrapped_view(**kwargs):
            # 未ログインならログイン画面へ
            if g.user is None:
                flash("ログインが必要です。", "error")
                return redirect(url_for("login"))

            # ロールが違えばトップへ戻す
            if g.user["role"] != role:
                flash("この操作を行う権限がありません。", "error")
                return redirect(url_for("item_list"))

            return view(**kwargs)
        return wrapped_view
    return decorator


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

@app.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("ユーザー名とパスワードを入力してください。", "error")
            return render_template("login.html")

        # ユーザーをDBから検索
        user = db.execute(
            "SELECT * FROM USERS WHERE username = ?",
            (username,)
        ).fetchone()

        if user is None:
            flash("ユーザー名かパスワードが違います。", "error")
            return render_template("login.html")

        # いったん「password_hash に平文パスワードが入っている」前提
        # （あとでハッシュチェックに変更する）
        if user["password_hash"] != password:
            flash("ユーザー名かパスワードが違います。", "error")
            return render_template("login.html")

        # ログイン成功 → セッションに保存
        session.clear()
        session["user_id"] = user["id"]
        session["role"] = user["role"]
        session["username"] = user["username"]

        flash(f"ログインしました。（{user['username']}）", "success")
        return redirect(url_for("item_list"))

    # GET のときはログインフォームを表示
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("ログアウトしました。", "success")
    return redirect(url_for("login"))


# ====== 商品一覧 ======
@app.route("/")
@login_required
def item_list():
    db = get_db()

    # 商品一覧
    items = db.execute(
        """
        SELECT
            ITEMS.id,
            ITEMS.name,
            ITEMS.unit,
            ITEMS.stock,
            ITEMS.threshold,
            CATEGORIES.name AS category_name,
            SUPPLIERS.name AS supplier_name
        FROM ITEMS
        LEFT JOIN CATEGORIES ON ITEMS.category_id = CATEGORIES.id
        LEFT JOIN SUPPLIERS ON ITEMS.supplier_id = SUPPLIERS.id
        WHERE ITEMS.is_active = 1
        ORDER BY 
            CATEGORIES.name ASC,   -- カテゴリ名で並べ替え
            ITEMS.name ASC         -- 同じカテゴリ内は商品名順
        """
    ).fetchall()

    # 商品登録フォーム用
    categories = db.execute(
        "SELECT id, name FROM CATEGORIES ORDER BY name"
    ).fetchall()
    suppliers = db.execute(
        "SELECT id, name FROM SUPPLIERS ORDER BY name"
    ).fetchall()

    return render_template(
        "items.html",
        items=items,
        categories=categories,
        suppliers=suppliers
    )



@app.route("/movements")
@login_required
@role_required("admin")
def movement_list():
    db = get_db()
    movements = db.execute(
        """
        SELECT 
            STOCKMOVEMENTS.id,
            STOCKMOVEMENTS.item_id,
            STOCKMOVEMENTS.user_id,
            STOCKMOVEMENTS.quantity_change,
            STOCKMOVEMENTS.movement_type,
            STOCKMOVEMENTS.memo,
            STOCKMOVEMENTS.created_at,
            ITEMS.name AS item_name,
            USERS.username AS user_name
        FROM STOCKMOVEMENTS
        LEFT JOIN ITEMS ON STOCKMOVEMENTS.item_id = ITEMS.id
        LEFT JOIN USERS ON STOCKMOVEMENTS.user_id = USERS.id
        ORDER BY STOCKMOVEMENTS.created_at DESC
        """
    ).fetchall()

    return render_template("movements.html", movements=movements)



# ====== 商品登録（新規） ======
@app.route("/items/new", methods=["POST"])
@login_required
@role_required("admin")
def item_create():
    db = get_db()

    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "").strip()
    stock = int(request.form.get("stock", "0"))
    threshold = int(request.form.get("threshold", "0"))
    category_id = request.form.get("category_id") or None
    supplier_id = request.form.get("supplier_id") or None

    if not name or not unit:
        flash("商品名と単位は必須です。", "error")
        return redirect(url_for("item_list"))

    db.execute(
        """
        INSERT INTO ITEMS
            (name, unit, stock, threshold, is_active, category_id, supplier_id)
        VALUES
            (?, ?, ?, ?, 1, ?, ?)
        """,
        (name, unit, stock, threshold, category_id, supplier_id),
    )
    db.commit()

    flash("商品を登録しました！", "success")
    return redirect(url_for("item_list"))


def create_stock_movement(db, item_id, user_id, quantity_change, movement_type, memo=""):
    # STOCKMOVEMENTS に追加
    db.execute(
        """
        INSERT INTO STOCKMOVEMENTS
            (item_id, user_id, quantity_change, movement_type, memo)
        VALUES
            (?, ?, ?, ?, ?)
        """,
        (item_id, user_id, quantity_change, movement_type, memo),
    )

    # ITEMS.stock を更新
    db.execute(
        "UPDATE ITEMS SET stock = stock + ? WHERE id = ?",
        (quantity_change, item_id)
    )

@app.route("/items/<int:item_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def item_delete(item_id):
    db = get_db()
    db.execute(
        "UPDATE ITEMS SET is_active = 0 WHERE id = ?",
        (item_id,),
    )
    db.commit()
    flash("商品を論理削除しました。", "info")
    return redirect(url_for("item_list"))

@app.route("/items/update_stock", methods=["POST"])
@login_required
def update_stock():
    db = get_db()

    item_id = int(request.form["item_id"])
    quantity = int(request.form["quantity"])
    memo = request.form.get("memo", "")
    action = request.form.get("action")

    user_id = g.user["id"]


    if action == "in":
        change = quantity
        movement_type = "IN"
    elif action == "out":
        change = -quantity
        movement_type = "OUT"
    else:
        flash("不明な操作です。", "error")
        return redirect(url_for("item_list"))

    create_stock_movement(
        db,
        item_id=item_id,
        user_id=user_id,
        quantity_change=change,
        movement_type=movement_type,
        memo=memo,
    )

    db.commit()
    flash("在庫を更新しました。", "success")
    return redirect(url_for("item_list"))

if __name__ == "__main__":
    # ローカルで動かすとき用
    app.run(host="0.0.0.0", port=5000, debug=True)
