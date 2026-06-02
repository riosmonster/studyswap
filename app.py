import os
import re
import sys
import uuid
import sqlite3
import webbrowser
import threading
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask import (
    Flask, request, jsonify, session, redirect, url_for,
    render_template, flash, g, send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", Path(__file__).parent)
    return Path(base) / rel


BASE_DIR   = Path(__file__).parent
DATA_DIR   = Path(os.environ.get("DATA_DIR", BASE_DIR))
UPLOAD_DIR = DATA_DIR / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "studyswap.db"

# Matrícula IBMEC: 4 dígitos de ano (20xx) + dígitos extras @ alunos.ibmec.edu.br
IBMEC_EMAIL_RE = re.compile(r"^20\d{2}\d+@alunos\.ibmec\.edu\.br$")
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "gif", "webp"}

SUBJECTS = [
    "Cálculo I", "Cálculo II", "Álgebra Linear",
    "Estatística", "Probabilidade e Estatística",
    "Microeconomia", "Macroeconomia",
    "Contabilidade I", "Contabilidade II",
    "Finanças Corporativas", "Mercado de Capitais",
    "Marketing", "Gestão de Pessoas",
    "Direito Empresarial", "Direito Civil",
    "Programação", "Banco de Dados",
    "Gestão de Projetos", "Empreendedorismo",
    "Design Thinking", "Inglês", "Outro",
]

MATERIAL_TYPES = ["Resumo", "Lista de Exercícios", "Mapa Mental", "Fichamento"]

app = Flask(
    __name__,
    template_folder=str(resource_path("templates")),
    static_folder=str(resource_path("static")),
)
app.secret_key = os.environ.get("SECRET_KEY", "studyswap-dev-2026-ibmec")
# Garante que url_for() gera URLs com https:// quando atrás do proxy do Render
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# ── Database ─────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                bio           TEXT    DEFAULT '',
                credits       INTEGER DEFAULT 10,
                created_at    TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS materials (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                title        TEXT    NOT NULL,
                subject      TEXT    NOT NULL,
                type         TEXT    NOT NULL,
                description  TEXT    DEFAULT '',
                content      TEXT    DEFAULT '',
                file_path    TEXT    DEFAULT NULL,
                credits_cost INTEGER DEFAULT 10,
                created_at   TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS ratings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                rating      INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
                created_at  TEXT    NOT NULL,
                UNIQUE(material_id, user_id),
                FOREIGN KEY (material_id) REFERENCES materials(id),
                FOREIGN KEY (user_id)     REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS access_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                created_at  TEXT    NOT NULL,
                UNIQUE(material_id, user_id),
                FOREIGN KEY (material_id) REFERENCES materials(id),
                FOREIGN KEY (user_id)     REFERENCES users(id)
            );
        """)


# ── Helpers ──────────────────────────────────────────────

def get_current_user():
    if "user_id" not in session:
        return None
    if "current_user_obj" in g:
        return g.current_user_obj
    user = get_db().execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if user is None:
        session.clear()   # stale session (DB was reset), force re-login
    g.current_user_obj = user
    return user


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if get_current_user() is None:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_user_rating(user_id):
    db = get_db()
    rows = db.execute(
        """SELECT AVG(r.rating) as avg
           FROM materials m
           LEFT JOIN ratings r ON r.material_id = m.id
           WHERE m.user_id = ?
           GROUP BY m.id
           HAVING avg IS NOT NULL""",
        (user_id,),
    ).fetchall()
    if not rows:
        return None
    vals = [r["avg"] for r in rows if r["avg"] is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


@app.context_processor
def inject_globals():
    return {"current_user": get_current_user()}


# ── Routes: Auth ─────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("marketplace"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("marketplace"))

    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        email   = request.form.get("email", "").strip().lower()
        pw      = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        domain = email.split("@")[-1] if "@" in email else ""

        error = None
        if not name or not email or not pw:
            error = "Preencha todos os campos."
        elif pw != confirm:
            error = "As senhas não coincidem."
        elif len(pw) < 6:
            error = "A senha deve ter no mínimo 6 caracteres."
        elif not IBMEC_EMAIL_RE.match(email):
            error = "Use seu e-mail de matrícula IBMEC. Formato: matricula@alunos.ibmec.edu.br"

        if error:
            flash(error, "error")
            return render_template("register.html", name=name, email=email)

        try:
            db = get_db()
            db.execute(
                "INSERT INTO users (name, email, password_hash, credits, created_at) VALUES (?,?,?,20,?)",
                (name, email, generate_password_hash(pw, method="pbkdf2:sha256"), datetime.utcnow().isoformat()),
            )
            db.commit()
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            session["user_id"] = user["id"]
            flash(f"Bem-vindo, {name}! Você ganhou 20 créditos de boas-vindas. 🎉", "success")
            return redirect(url_for("marketplace"))
        except sqlite3.IntegrityError:
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("register.html", name=name, email=email)

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("marketplace"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw    = request.form.get("password", "")
        db    = get_db()
        user  = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not user or not check_password_hash(user["password_hash"], pw):
            flash("E-mail ou senha incorretos.", "error")
            return render_template("login.html", email=email)

        session["user_id"] = user["id"]
        return redirect(url_for("marketplace"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ── Routes: Marketplace ──────────────────────────────────

@app.route("/marketplace")
@login_required
def marketplace():
    db      = get_db()
    subject = request.args.get("subject", "")
    mtype   = request.args.get("type", "")
    q       = request.args.get("q", "")

    sql = """
        SELECT m.*, u.name AS author_name,
               ROUND(AVG(r.rating), 1) AS avg_rating,
               COUNT(DISTINCT r.id)    AS rating_count,
               COUNT(DISTINCT a.id)    AS access_count
        FROM materials m
        JOIN  users      u ON m.user_id      = u.id
        LEFT JOIN ratings  r ON r.material_id = m.id
        LEFT JOIN access_log a ON a.material_id = m.id
        WHERE 1=1
    """
    params = []
    if subject:
        sql += " AND m.subject = ?"
        params.append(subject)
    if mtype:
        sql += " AND m.type = ?"
        params.append(mtype)
    if q:
        sql += " AND (m.title LIKE ? OR m.description LIKE ? OR u.name LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += " GROUP BY m.id ORDER BY m.created_at DESC"

    materials = db.execute(sql, params).fetchall()

    accessed = {
        r["material_id"]
        for r in db.execute(
            "SELECT material_id FROM access_log WHERE user_id = ?",
            (session["user_id"],),
        ).fetchall()
    }

    return render_template(
        "marketplace.html",
        materials=materials,
        accessed_ids=accessed,
        subjects=SUBJECTS,
        material_types=MATERIAL_TYPES,
        subject_filter=subject,
        type_filter=mtype,
        search=q,
    )


# ── Routes: Upload ───────────────────────────────────────

def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_upload(file_obj):
    ext = file_obj.filename.rsplit(".", 1)[1].lower()
    unique = f"{uuid.uuid4().hex}.{ext}"
    file_obj.save(UPLOAD_DIR / unique)
    return unique


@app.route("/uploads/<path:filename>")
@login_required
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        subject     = request.form.get("subject", "")
        mtype       = request.form.get("type", "")
        description = request.form.get("description", "").strip()
        content     = request.form.get("content", "").strip()
        cost        = int(request.form.get("credits_cost", 10))
        file_obj    = request.files.get("file")

        # Precisa de conteúdo digitado OU arquivo anexado
        has_file = file_obj and file_obj.filename
        if not title or not subject or not mtype or (not content and not has_file):
            flash("Preencha o título, matéria, tipo e adicione conteúdo ou um arquivo.", "error")
            return render_template("upload.html", subjects=SUBJECTS, material_types=MATERIAL_TYPES)

        if subject not in SUBJECTS or mtype not in MATERIAL_TYPES:
            flash("Matéria ou tipo inválidos.", "error")
            return render_template("upload.html", subjects=SUBJECTS, material_types=MATERIAL_TYPES)

        file_path = None
        if has_file:
            if not _allowed_file(file_obj.filename):
                flash("Formato não permitido. Use PDF, JPG ou PNG.", "error")
                return render_template("upload.html", subjects=SUBJECTS, material_types=MATERIAL_TYPES)
            file_path = _save_upload(file_obj)

        db = get_db()
        db.execute(
            "INSERT INTO materials (user_id,title,subject,type,description,content,file_path,credits_cost,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (session["user_id"], title, subject, mtype, description, content,
             file_path, max(10, cost), datetime.utcnow().isoformat()),
        )
        db.execute("UPDATE users SET credits = credits + 20 WHERE id = ?", (session["user_id"],))
        db.commit()
        flash("Material publicado com sucesso! +20 créditos adicionados.", "success")
        return redirect(url_for("marketplace"))

    return render_template("upload.html", subjects=SUBJECTS, material_types=MATERIAL_TYPES)


# ── Routes: Material ─────────────────────────────────────

@app.route("/material/<int:mid>")
@login_required
def material(mid):
    db  = get_db()
    mat = db.execute(
        "SELECT m.*, u.name AS author_name, u.id AS author_id FROM materials m JOIN users u ON m.user_id=u.id WHERE m.id=?",
        (mid,),
    ).fetchone()

    if not mat:
        flash("Material não encontrado.", "error")
        return redirect(url_for("marketplace"))

    is_owner   = mat["user_id"] == session["user_id"]
    has_access = is_owner or bool(
        db.execute(
            "SELECT 1 FROM access_log WHERE material_id=? AND user_id=?",
            (mid, session["user_id"]),
        ).fetchone()
    )
    avg = db.execute(
        "SELECT ROUND(AVG(rating),1) AS avg, COUNT(*) AS cnt FROM ratings WHERE material_id=?",
        (mid,),
    ).fetchone()
    user_rating_row = db.execute(
        "SELECT rating FROM ratings WHERE material_id=? AND user_id=?",
        (mid, session["user_id"]),
    ).fetchone()

    return render_template(
        "material.html",
        mat=mat,
        is_owner=is_owner,
        has_access=has_access,
        avg_rating=avg,
        user_rating=user_rating_row["rating"] if user_rating_row else None,
    )


@app.route("/material/<int:mid>/access", methods=["POST"])
@login_required
def access_material(mid):
    db  = get_db()
    mat = db.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
    if not mat:
        return jsonify({"ok": False, "message": "Material não encontrado."}), 404
    if mat["user_id"] == session["user_id"]:
        return jsonify({"ok": False, "message": "Você é o autor deste material."}), 400

    if db.execute(
        "SELECT 1 FROM access_log WHERE material_id=? AND user_id=?",
        (mid, session["user_id"]),
    ).fetchone():
        return jsonify({"ok": True, "already": True})

    user = db.execute("SELECT credits FROM users WHERE id=?", (session["user_id"],)).fetchone()
    cost = mat["credits_cost"]
    if user["credits"] < cost:
        return jsonify({"ok": False, "message": f"Créditos insuficientes. Você tem {user['credits']} e este material custa {cost}."}), 400

    db.execute("UPDATE users SET credits = credits - ? WHERE id = ?", (cost, session["user_id"]))
    db.execute("UPDATE users SET credits = credits + 10 WHERE id = ?", (mat["user_id"],))
    db.execute(
        "INSERT INTO access_log (material_id, user_id, created_at) VALUES (?,?,?)",
        (mid, session["user_id"], datetime.utcnow().isoformat()),
    )
    db.commit()
    new_credits = db.execute("SELECT credits FROM users WHERE id=?", (session["user_id"],)).fetchone()["credits"]
    return jsonify({"ok": True, "credits": new_credits})


@app.route("/material/<int:mid>/rate", methods=["POST"])
@login_required
def rate_material(mid):
    db  = get_db()
    mat = db.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
    if not mat:
        return jsonify({"ok": False, "message": "Material não encontrado."}), 404
    if mat["user_id"] == session["user_id"]:
        return jsonify({"ok": False, "message": "Você não pode avaliar seu próprio material."}), 400
    if not db.execute(
        "SELECT 1 FROM access_log WHERE material_id=? AND user_id=?",
        (mid, session["user_id"]),
    ).fetchone():
        return jsonify({"ok": False, "message": "Acesse o material antes de avaliar."}), 403

    data   = request.get_json(silent=True) or {}
    rating = data.get("rating")
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        return jsonify({"ok": False, "message": "Avaliação inválida (1–5)."}), 400

    db.execute(
        "INSERT OR REPLACE INTO ratings (material_id, user_id, rating, created_at) VALUES (?,?,?,?)",
        (mid, session["user_id"], rating, datetime.utcnow().isoformat()),
    )
    db.commit()
    avg = db.execute(
        "SELECT ROUND(AVG(rating),1) AS avg, COUNT(*) AS cnt FROM ratings WHERE material_id=?",
        (mid,),
    ).fetchone()
    return jsonify({"ok": True, "avg": avg["avg"], "count": avg["cnt"]})


# ── Routes: Profile ──────────────────────────────────────

@app.route("/profile")
@login_required
def own_profile():
    return redirect(url_for("profile", uid=session["user_id"]))


@app.route("/profile/<int:uid>")
@login_required
def profile(uid):
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("marketplace"))

    materials = db.execute(
        """SELECT m.*, ROUND(AVG(r.rating),1) AS avg_rating, COUNT(DISTINCT r.id) AS rating_count
           FROM materials m
           LEFT JOIN ratings r ON r.material_id = m.id
           WHERE m.user_id=?
           GROUP BY m.id ORDER BY m.created_at DESC""",
        (uid,),
    ).fetchall()

    return render_template(
        "profile.html",
        user=user,
        materials=materials,
        user_rating=get_user_rating(uid),
        is_own=uid == session["user_id"],
    )


@app.route("/profile/edit", methods=["POST"])
@login_required
def edit_profile():
    name = request.form.get("name", "").strip()
    bio  = request.form.get("bio", "").strip()
    if not name:
        flash("O nome não pode estar vazio.", "error")
    else:
        db = get_db()
        db.execute("UPDATE users SET name=?, bio=? WHERE id=?", (name, bio, session["user_id"]))
        db.commit()
        flash("Perfil atualizado com sucesso!", "success")
    return redirect(url_for("own_profile"))


# ── Entry point ──────────────────────────────────────────

def open_browser():
    webbrowser.open("http://localhost:5000")


# Inicializa o banco sempre que o módulo é carregado
# (funciona tanto com `python app.py` quanto com gunicorn no Render)
init_db()

if __name__ == "__main__":
    print("=" * 46)
    print("  StudySwap rodando em http://localhost:5000")
    print("  Pressione Ctrl+C para encerrar")
    print("=" * 46)
    threading.Timer(0.8, open_browser).start()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
        use_reloader=False,
    )
