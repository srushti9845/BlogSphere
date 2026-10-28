from datetime import datetime
import os
import re
import sqlite3
import uuid
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
from markupsafe import Markup, escape
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key-before-deploying"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
DATABASE = "database.db"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS follows (
            follower_id INTEGER NOT NULL,
            followed_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (follower_id, followed_id),
            CHECK (follower_id != followed_id),
            FOREIGN KEY(follower_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(followed_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    post_columns = {row[1] for row in db.execute("PRAGMA table_info(posts)")}
    if "image_filename" not in post_columns:
        db.execute("ALTER TABLE posts ADD COLUMN image_filename TEXT")
    db.commit()
    db.close()


def save_post_image(upload):
    if not upload or not upload.filename:
        return None

    extension = os.path.splitext(upload.filename)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Choose a JPG, PNG, GIF, or WebP image.")

    header = upload.stream.read(12)
    upload.stream.seek(0)
    if header.startswith(b"\xff\xd8\xff"):
        matching_extensions = {".jpg", ".jpeg"}
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        matching_extensions = {".png"}
    elif header.startswith((b"GIF87a", b"GIF89a")):
        matching_extensions = {".gif"}
    elif header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        matching_extensions = {".webp"}
    else:
        raise ValueError("The selected file is not a supported image.")
    if extension not in matching_extensions:
        raise ValueError("The image content does not match its file extension.")

    filename = f"{uuid.uuid4().hex}{extension}"
    upload_directory = os.path.join(app.static_folder, "uploads")
    os.makedirs(upload_directory, exist_ok=True)
    upload.save(os.path.join(upload_directory, filename))
    return filename


def remove_post_image(filename):
    if filename:
        image_path = os.path.join(app.static_folder, "uploads", filename)
        if os.path.isfile(image_path):
            os.remove(image_path)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    return {"current_username": session.get("username")}


@app.template_filter("link_mentions")
def link_mentions(content):
    mention_pattern = re.compile(r"(?<![\w])@([A-Za-z0-9_]{2,40})")
    matches = list(mention_pattern.finditer(content))
    if not matches:
        return Markup(escape(content))

    usernames = {match.group(1).casefold() for match in matches}
    placeholders = ",".join("?" for _ in usernames)
    users = get_db().execute(
        f"SELECT id, username FROM users WHERE lower(username) IN ({placeholders})",
        tuple(usernames)
    ).fetchall()
    known_users = {user["username"].casefold(): user for user in users}

    parts = []
    position = 0
    for match in matches:
        parts.append(escape(content[position:match.start()]))
        user = known_users.get(match.group(1).casefold())
        if user:
            profile_url = url_for("profile", username=user["username"])
            parts.append(Markup('<a href="{}">{}</a>').format(
                escape(profile_url), escape(f"@{user['username']}")
            ))
        else:
            parts.append(escape(match.group(0)))
        position = match.end()
    parts.append(escape(content[position:]))
    return Markup("").join(parts)


@app.errorhandler(413)
def handle_upload_too_large(error):
    flash("Photos must be 5 MB or smaller.", "danger")
    if request.endpoint == "edit_post" and request.view_args:
        return redirect(url_for("edit_post", post_id=request.view_args["post_id"]))
    if request.endpoint == "create_post" and session.get("user_id"):
        return redirect(url_for("create_post"))
    return redirect(url_for("index"))


@app.route("/")
def index():
    db = get_db()
    posts = db.execute("""
        SELECT posts.*, users.username,
        (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) AS comment_count
        FROM posts JOIN users ON users.id = posts.user_id
        ORDER BY posts.id DESC
    """).fetchall()
    return render_template("index.html", posts=posts)


@app.route("/users/<username>")
def profile(username):
    db = get_db()
    user = db.execute(
        "SELECT id, username FROM users WHERE username = ? COLLATE NOCASE",
        (username,)
    ).fetchone()
    if user is None:
        flash("That profile could not be found.", "danger")
        return redirect(url_for("index"))

    posts = db.execute("""
        SELECT posts.*,
        (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) AS comment_count
        FROM posts WHERE posts.user_id = ? ORDER BY posts.id DESC
    """, (user["id"],)).fetchall()
    follower_count = db.execute(
        "SELECT COUNT(*) FROM follows WHERE followed_id = ?", (user["id"],)
    ).fetchone()[0]
    following_count = db.execute(
        "SELECT COUNT(*) FROM follows WHERE follower_id = ?", (user["id"],)
    ).fetchone()[0]
    is_following = False
    if session.get("user_id"):
        is_following = db.execute(
            "SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?",
            (session["user_id"], user["id"])
        ).fetchone() is not None
    return render_template(
        "profile.html", profile=user, posts=posts, follower_count=follower_count,
        following_count=following_count, is_following=is_following
    )


@app.route("/users/<username>/follow", methods=["POST"])
@login_required
def follow_user(username):
    db = get_db()
    user = db.execute(
        "SELECT id, username FROM users WHERE username = ? COLLATE NOCASE",
        (username,)
    ).fetchone()
    if user is None:
        flash("That profile could not be found.", "danger")
    elif user["id"] == session["user_id"]:
        flash("You cannot follow your own account.", "warning")
    else:
        db.execute(
            "INSERT OR IGNORE INTO follows (follower_id, followed_id, created_at) VALUES (?, ?, ?)",
            (session["user_id"], user["id"], datetime.now().isoformat(timespec="seconds"))
        )
        db.commit()
        flash(f"You are now following {user['username']}.", "success")
    if user:
        return redirect(url_for("profile", username=user["username"]))
    return redirect(url_for("index"))


@app.route("/users/<username>/unfollow", methods=["POST"])
@login_required
def unfollow_user(username):
    db = get_db()
    user = db.execute(
        "SELECT id, username FROM users WHERE username = ? COLLATE NOCASE",
        (username,)
    ).fetchone()
    if user is None:
        flash("That profile could not be found.", "danger")
    elif user["id"] != session["user_id"]:
        db.execute(
            "DELETE FROM follows WHERE follower_id = ? AND followed_id = ?",
            (session["user_id"], user["id"])
        )
        db.commit()
        flash(f"You unfollowed {user['username']}.", "info")
    if user:
        return redirect(url_for("profile", username=user["username"]))
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not username or not email or len(password) < 8:
            flash("Enter all fields. Password must be at least 8 characters.", "danger")
            return render_template("register.html")
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, generate_password_hash(password))
            )
            db.commit()
        except sqlite3.IntegrityError:
            flash("That username or email is already registered.", "danger")
            return render_template("register.html")
        flash("Account created! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Welcome back!", "success")
            return redirect(url_for("index"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/post/new", methods=["GET", "POST"])
@login_required
def create_post():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("Title and content are required.", "danger")
            return render_template("create_post.html", post=None)
        try:
            image_filename = save_post_image(request.files.get("image"))
        except ValueError as error:
            flash(str(error), "danger")
            return render_template("create_post.html", post=None), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO posts (title, content, user_id, created_at, image_filename) VALUES (?, ?, ?, ?, ?)",
            (title, content, session["user_id"], datetime.now().strftime("%d %b %Y, %I:%M %p"),
             image_filename)
        )
        db.commit()
        flash("Your post has been published.", "success")
        return redirect(url_for("post_detail", post_id=cursor.lastrowid))
    return render_template("create_post.html", post=None)


@app.route("/post/<int:post_id>")
def post_detail(post_id):
    db = get_db()
    post = db.execute("""
        SELECT posts.*, users.username FROM posts
        JOIN users ON users.id = posts.user_id WHERE posts.id = ?
    """, (post_id,)).fetchone()
    if post is None:
        flash("Post not found.", "danger")
        return redirect(url_for("index"))
    comments = db.execute("""
        SELECT comments.*, users.username FROM comments
        JOIN users ON users.id = comments.user_id
        WHERE comments.post_id = ? ORDER BY comments.id ASC
    """, (post_id,)).fetchall()
    return render_template("post_detail.html", post=post, comments=comments)


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        flash("Post not found.", "danger")
        return redirect(url_for("index"))
    if post["user_id"] != session["user_id"]:
        flash("You can only edit your own posts.", "danger")
        return redirect(url_for("post_detail", post_id=post_id))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("Title and content are required.", "danger")
            return render_template("create_post.html", post=post)
        try:
            image_filename = save_post_image(request.files.get("image"))
        except ValueError as error:
            flash(str(error), "danger")
            return render_template("create_post.html", post=post), 400

        old_image = post["image_filename"]
        if image_filename is None:
            image_filename = (
                None if request.form.get("remove_image") == "yes" else old_image
            )
        db.execute(
            "UPDATE posts SET title = ?, content = ?, image_filename = ? WHERE id = ?",
            (title, content, image_filename, post_id)
        )
        db.commit()
        if old_image and image_filename != old_image:
            remove_post_image(old_image)
        flash("Post updated.", "success")
        return redirect(url_for("post_detail", post_id=post_id))
    return render_template("create_post.html", post=post)


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        flash("Post not found.", "danger")
    elif post["user_id"] != session["user_id"]:
        flash("You can only delete your own posts.", "danger")
    else:
        image_filename = post["image_filename"]
        db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        db.commit()
        remove_post_image(image_filename)
        flash("Post deleted.", "success")
    return redirect(url_for("index"))


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id):
    content = request.form.get("content", "").strip()
    db = get_db()
    exists = db.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not exists:
        flash("Post not found.", "danger")
    elif content:
        db.execute(
            "INSERT INTO comments (content, user_id, post_id, created_at) VALUES (?, ?, ?, ?)",
            (content, session["user_id"], post_id,
             datetime.now().strftime("%d %b %Y, %I:%M %p"))
        )
        db.commit()
        flash("Comment added.", "success")
    else:
        flash("Comment cannot be empty.", "danger")
    return redirect(url_for("post_detail", post_id=post_id))


# Small REST API examples for testing with a browser or API client.
@app.route("/api/posts", methods=["GET"])
def api_posts():
    posts = get_db().execute("""
        SELECT posts.id, posts.title, posts.content, posts.created_at,
               posts.image_filename, users.username
        FROM posts JOIN users ON users.id = posts.user_id ORDER BY posts.id DESC
    """).fetchall()
    return jsonify([dict(post) for post in posts])


@app.route("/api/posts/<int:post_id>", methods=["GET"])
def api_post(post_id):
    post = get_db().execute("""
        SELECT posts.id, posts.title, posts.content, posts.created_at,
               posts.image_filename, users.username
        FROM posts JOIN users ON users.id = posts.user_id WHERE posts.id = ?
    """, (post_id,)).fetchone()
    if post is None:
        return jsonify({"error": "Post not found"}), 404
    comments = get_db().execute("""
        SELECT comments.id, comments.content, comments.created_at, users.username
        FROM comments JOIN users ON users.id = comments.user_id
        WHERE comments.post_id = ? ORDER BY comments.id
    """, (post_id,)).fetchall()
    result = dict(post)
    result["comments"] = [dict(comment) for comment in comments]
    return jsonify(result)
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
