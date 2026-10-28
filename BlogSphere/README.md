# BlogSphere — Blogging Platform with Comments

A beginner-friendly full-stack blog website built with HTML, CSS, JavaScript, Python Flask, and SQLite.

## Features
- Register, log in, and log out
- Passwords stored as hashes (not plain text)
- Create, read, edit, and delete blog posts
- Attach JPG, PNG, GIF, or WebP photos to stories (up to 5 MB)
- Only the owner of a post can edit or delete it
- Logged-in users can comment on posts
- Public profiles with follow and unfollow
- Mention registered users with `@username` in posts
- Share story links using your device's share menu or copy-link fallback
- Published stories and profiles are public and can be viewed without logging in
- SQLite database created automatically
- JSON REST API to read posts and comments
- Responsive layout for desktop and mobile

## Requirements
- Python 3.10 or newer
- VS Code (recommended)

## Setup in VS Code

1. Extract the ZIP file.
2. Open the `BlogSphere` folder in VS Code.
3. Open **Terminal → New Terminal**.
4. Create a virtual environment (recommended):

   **Windows**
   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   ```

   If `py` is unavailable, use `python` instead.

5. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```

6. Start the app:
   ```bash
   python app.py
   ```

7. Open this address in your browser:
   http://127.0.0.1:5000

The SQLite database is created as `database.db` the first time the app starts. You do not need to create it yourself.

## Quick test
1. Click **Get started** and register a user with a password of at least 8 characters.
2. Log in.
3. Click **Write a post**, enter a title and content, and publish it.
4. Open the post and add a comment.
5. Edit or delete the post while logged in as its author.
6. Register a second user to test commenting and ownership restrictions.
7. Visit a writer's profile to follow them, and try mentioning their `@username` in a story.

## REST API examples
- `GET http://127.0.0.1:5000/api/posts` — list all posts as JSON
- `GET http://127.0.0.1:5000/api/posts/1` — one post and its comments as JSON

The API routes are read-only examples; the website's HTML form routes handle creating, editing, deleting, and commenting.

## Important before deployment
- Replace `SECRET_KEY` in `app.py` with a long, random secret stored in an environment variable.
- Turn off Flask debug mode in production.
- Use HTTPS and add CSRF protection before deploying a public production site.
- SQLite is suitable for learning and local demos. For some hosting platforms, use persistent storage or a managed database so data survives redeploys.
