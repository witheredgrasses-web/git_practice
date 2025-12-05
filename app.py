from flask import Flask, render_template, request, redirect, url_for, flash, g
import sqlite3
import os

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


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ====== 商品一覧 ======
@app.route("/")
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

@app.route("/items/<int:item_id>/in", methods=["GET", "POST"])
def stock_in(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM ITEMS WHERE id = ?", (item_id,)).fetchone()

    if not item:
        flash("商品が存在しません。", "error")
        return redirect(url_for("item_list"))

    if request.method == "POST":
        quantity = int(request.form["quantity"])
        memo = request.form.get("memo", "")

        # ★ユーザーIDは今は仮で1として登録（ログイン機能を作ったら変更）
        user_id = 1

        create_stock_movement(
            db,
            item_id=item_id,
            user_id=user_id,
            quantity_change=quantity,  # 入庫はプラス
            movement_type="IN",
            memo=memo,
        )

        db.commit()
        flash("入庫処理が完了しました。", "success")
        return redirect(url_for("item_list"))

    return render_template("stock_form.html", item=item, action_name="入庫")

@app.route("/items/<int:item_id>/out", methods=["GET", "POST"])
def stock_out(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM ITEMS WHERE id = ?", (item_id,)).fetchone()

    if not item:
        flash("商品が存在しません。", "error")
        return redirect(url_for("item_list"))

    if request.method == "POST":
        quantity = int(request.form["quantity"])
        memo = request.form.get("memo", "")

        user_id = 1  # ★仮ユーザー（後でログインと連動）

        # 出庫はマイナス
        create_stock_movement(
            db,
            item_id=item_id,
            user_id=user_id,
            quantity_change=-quantity,
            movement_type="OUT",
            memo=memo,
        )

        db.commit()
        flash("出庫処理が完了しました。", "success")
        return redirect(url_for("item_list"))

    return render_template("stock_form.html", item=item, action_name="出庫")