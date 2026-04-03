#!/usr/bin/env python3
"""Rewrite workspace.py scaffold_project with production-grade templates."""
from pathlib import Path

WS = Path("/Users/krishtyagi/Desktop/untitled folder/magic/app/workspace.py")
lines = WS.read_text().splitlines(keepends=True)

pre = lines[:120]   # everything before scaffold_project
post = lines[188:]   # everything after the old function (patch_workspace_file onward)

SCAFFOLD = r'''def scaffold_project(name: str, kind: str = "website", prompt: str = "") -> str:
    project_dir = _next_available_project_dir(name)
    project_dir.mkdir(parents=True, exist_ok=False)
    title = name.replace("-", " ").title()
    tagline = prompt or "Built with Magic"

    if kind == "website":
        _SITE_CSS = (
            "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}\n"
            ":root{--bg:#0a0d14;--surface:rgba(255,255,255,0.04);--border:rgba(255,255,255,0.08);"
            "--text:#f1f5f9;--muted:#94a3b8;--accent:#38bdf8}\n"
            "body{font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--text);"
            "line-height:1.6;overflow-x:hidden}\n"
            ".nav{position:fixed;top:0;width:100%;display:flex;justify-content:space-between;"
            "align-items:center;padding:18px 40px;backdrop-filter:blur(16px);"
            "background:rgba(10,13,20,0.7);border-bottom:1px solid var(--border);z-index:100}\n"
            ".nav-brand{font-size:20px;font-weight:800}\n"
            ".nav-links{display:flex;gap:24px;align-items:center}\n"
            ".nav-links a{color:var(--muted);text-decoration:none;font-size:14px;transition:color .2s}\n"
            ".nav-links a:hover{color:var(--text)}\n"
            ".btn-nav{background:var(--accent);color:#0a0d14!important;padding:8px 18px;"
            "border-radius:999px;font-weight:600}\n"
            ".hero{min-height:100vh;display:flex;align-items:center;justify-content:center;"
            "text-align:center;padding:120px 20px 80px;"
            "background:radial-gradient(ellipse at top,rgba(56,189,248,0.12),transparent 60%)}\n"
            ".hero-tag{text-transform:uppercase;letter-spacing:.15em;font-size:12px;"
            "color:var(--accent);margin-bottom:16px;font-weight:600}\n"
            ".hero h1{font-size:clamp(2.5rem,6vw,5rem);font-weight:800;letter-spacing:-0.04em;"
            "line-height:1.1;max-width:800px;margin:0 auto 20px}\n"
            ".hero-sub{font-size:18px;color:var(--muted);max-width:520px;margin:0 auto 36px}\n"
            ".hero-actions{display:flex;gap:16px;justify-content:center}\n"
            ".btn-primary{background:var(--text);color:var(--bg);padding:14px 32px;"
            "border-radius:16px;font-weight:700;text-decoration:none;transition:transform .2s}\n"
            ".btn-primary:hover{transform:translateY(-2px)}\n"
            ".btn-outline{border:1px solid var(--border);color:var(--text);padding:14px 32px;"
            "border-radius:16px;text-decoration:none;transition:background .2s}\n"
            ".btn-outline:hover{background:var(--surface)}\n"
            ".features,.about{max-width:1100px;margin:0 auto;padding:100px 20px}\n"
            ".features h2,.about h2{font-size:36px;font-weight:800;margin-bottom:48px;text-align:center}\n"
            ".card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}\n"
            ".card{background:var(--surface);border:1px solid var(--border);border-radius:24px;"
            "padding:36px 28px;transition:transform .25s}\n"
            ".card:hover{transform:translateY(-4px);border-color:rgba(56,189,248,0.3)}\n"
            ".card-icon{font-size:32px;margin-bottom:16px}\n"
            ".card h3{font-size:20px;margin-bottom:10px;font-weight:700}\n"
            ".card p{color:var(--muted);font-size:14px;line-height:1.7}\n"
            ".about p{color:var(--muted);font-size:16px;max-width:640px;margin:0 auto;text-align:center}\n"
            ".footer{text-align:center;padding:40px 20px;border-top:1px solid var(--border);"
            "color:var(--muted);font-size:13px}\n"
            "@media(max-width:640px){.nav-links a:not(.btn-nav){display:none}.hero h1{font-size:2.2rem}}"
        )
        _SITE_JS = (
            "document.querySelectorAll('.card').forEach(c=>{"
            "c.style.opacity=0;c.style.transform='translateY(20px)';"
            "c.style.transition='opacity .6s ease,transform .6s ease';"
            "new IntersectionObserver(e=>{e.forEach(x=>{if(x.isIntersecting){"
            "x.target.style.opacity=1;x.target.style.transform='translateY(0)'"
            "}})},{threshold:0.1}).observe(c)});"
        )
        html_parts = [
            '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
            '<title>', title, '</title>\n',
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n',
            '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">\n',
            '<link rel="stylesheet" href="styles.css">\n</head>\n<body>\n',
            '<nav class="nav"><div class="nav-brand">', title, '</div>',
            '<div class="nav-links"><a href="#features">Features</a><a href="#about">About</a>',
            '<a href="#contact" class="btn-nav">Get Started</a></div></nav>\n',
            '<header class="hero"><div class="hero-content">',
            '<p class="hero-tag">Introducing ', title, '</p>\n',
            '<h1>', tagline, '</h1>\n',
            '<p class="hero-sub">A beautifully crafted experience.</p>\n',
            '<div class="hero-actions"><a href="#features" class="btn-primary">Explore</a>',
            '<a href="#about" class="btn-outline">Learn More</a></div></div></header>\n',
            '<section id="features" class="features"><h2>Features</h2><div class="card-grid">',
            '<div class="card"><div class="card-icon">&#10024;</div><h3>Beautiful Design</h3>',
            '<p>Modern aesthetics with glassmorphism.</p></div>',
            '<div class="card"><div class="card-icon">&#9889;</div><h3>Lightning Fast</h3>',
            '<p>Optimized for speed.</p></div>',
            '<div class="card"><div class="card-icon">&#128274;</div><h3>Secure</h3>',
            '<p>Built with security best-practices.</p></div></div></section>\n',
            '<section id="about" class="about"><h2>About</h2><p>', prompt or "Scaffolded by Magic.", '</p></section>\n',
            '<footer class="footer"><p>&copy; 2026 ', title, '. Crafted with Magic.</p></footer>\n',
            '<script src="script.js"></script>\n</body>\n</html>',
        ]
        (project_dir / "index.html").write_text("".join(html_parts), encoding="utf-8")
        (project_dir / "styles.css").write_text(_SITE_CSS, encoding="utf-8")
        (project_dir / "script.js").write_text(_SITE_JS, encoding="utf-8")
        run_hint = "python3 -m http.server 4173"
    elif kind == "slides":
        sl = [
            '<!DOCTYPE html>\n<html><head><title>', title,
            '</title><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/reveal.min.css">',
            '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/theme/black.min.css">',
            '</head><body><div class="reveal"><div class="slides">',
            '<section><h1>', title, '</h1><p>', tagline, '</p></section>',
            '<section><h2>Agenda</h2><ul><li>Problem</li><li>Solution</li><li>Features</li><li>Results</li><li>Next Steps</li></ul></section>',
            '<section><h2>Problem</h2><p>Describe the core challenge.</p></section>',
            '<section><h2>Solution</h2><p>Present your approach.</p></section>',
            '<section><h2>Features</h2><ul><li>Feature 1</li><li>Feature 2</li><li>Feature 3</li></ul></section>',
            '<section><h2>Results</h2><p>Share metrics.</p></section>',
            '<section><h2>Next Steps</h2><p>Outline the roadmap.</p></section>',
            '<section><h1>Thank You</h1></section>',
            '</div></div><script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/reveal.min.js"></script>',
            '<script>Reveal.initialize({hash:true,transition:"slide"});</script></body></html>',
        ]
        (project_dir / "index.html").write_text("".join(sl), encoding="utf-8")
        run_hint = "python3 -m http.server 4173"
    elif kind == "document":
        import datetime as _dt
        doc = "\n".join([
            "# " + title, "", "> " + tagline, "",
            "## Table of Contents", "1. Abstract", "2. Introduction", "3. Body", "4. Conclusion", "", "---", "",
            "## Abstract", "", prompt or "Summary goes here.", "",
            "## Introduction", "", "Introduce the topic, context, and objectives.", "",
            "## Body", "", "### Section 1", "First major point.", "",
            "### Section 2", "Second major point.", "",
            "## Conclusion", "", "Key takeaways and next steps.", "", "---", "",
            "*Generated by Magic on " + _dt.datetime.now().strftime("%Y-%m-%d") + "*", "",
        ])
        (project_dir / "document.md").write_text(doc, encoding="utf-8")
        run_hint = "open document.md"
    elif kind in ("csv", "spreadsheet"):
        gen = "\n".join([
            "import csv, random",
            "from datetime import datetime, timedelta",
            "",
            "# Spec: " + (prompt or "Sample dataset"),
            "",
            "HEADERS = ['id','name','email','department','salary','joined','active']",
            "DEPTS = ['Engineering','Marketing','Sales','Design','Operations','Finance']",
            "FIRST = ['Alex','Jordan','Morgan','Casey','Taylor','Riley','Quinn','Avery']",
            "LAST = ['Smith','Chen','Patel','Kim','Garcia','Mueller','Tanaka','Silva']",
            "",
            "def row(i):",
            "    f, l = random.choice(FIRST), random.choice(LAST)",
            "    d = datetime(2020,1,1) + timedelta(days=random.randint(0, 1800))",
            "    return [i, f'{f} {l}', f'{f.lower()}.{l.lower()}@company.com',",
            "           random.choice(DEPTS), round(random.uniform(55000, 180000), 2),",
            "           d.strftime('%Y-%m-%d'), random.choice(['Yes','Yes','Yes','No'])]",
            "",
            "with open('data.csv', 'w', newline='') as f:",
            "    w = csv.writer(f)",
            "    w.writerow(HEADERS)",
            "    for i in range(1, 101):",
            "        w.writerow(row(i))",
            "",
            "print('Generated data.csv with 100 rows.')",
            "",
        ])
        (project_dir / "data_generator.py").write_text(gen, encoding="utf-8")
        run_hint = "python3 data_generator.py"
    elif kind == "image":
        img = "\n".join([
            "from PIL import Image, ImageDraw, ImageFont",
            "import math",
            "",
            "# Spec: " + (prompt or "Professional gradient image"),
            "",
            "W, H = 1200, 800",
            "img = Image.new('RGB', (W, H))",
            "draw = ImageDraw.Draw(img)",
            "for y in range(H):",
            "    t = y / H",
            "    draw.line([(0, y), (W, y)], fill=(int(10+20*t), int(15+10*t), int(30+40*(1-t))))",
            "",
            "for i in range(8):",
            "    cx = 100 + i * 140",
            "    cy = H // 2 + int(60 * math.sin(i * 0.8))",
            "    r = 30 + i * 8",
            "    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(56+i*20, 189, 248), width=2)",
            "",
            "try:",
            "    font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 48)",
            "except Exception:",
            "    font = ImageFont.load_default()",
            "draw.text((60, 60), '" + title + "', fill=(241, 245, 249), font=font)",
            "img.save('output.png')",
            "print('Saved output.png (1200x800)')",
            "",
        ])
        (project_dir / "generate_image.py").write_text(img, encoding="utf-8")
        run_hint = "pip install Pillow && python3 generate_image.py && open output.png"
    elif kind == "pdf":
        (project_dir / "report.md").write_text("# " + title + "\n\n## Abstract\n" + prompt + "\n\n## Content\nExpand based on specs.\n", encoding="utf-8")
        (project_dir / "generate_pdf.py").write_text("import markdown\nhtml = markdown.markdown(open('report.md').read())\nopen('report.html','w').write('<html><head><style>body{font-family:sans-serif;margin:40px auto;max-width:800px;line-height:1.6}</style></head><body>'+html+'</body></html>')\nprint('Generated report.html')\n", encoding="utf-8")
        run_hint = "pip install markdown && python3 generate_pdf.py && open report.html"
    elif kind == "react":
        (project_dir / "package.json").write_text('{\n  "name": "magic-react",\n  "scripts": {"dev": "vite", "build": "vite build"},\n  "dependencies": {"react": "^18.2.0", "react-dom": "^18.2.0"},\n  "devDependencies": {"@vitejs/plugin-react": "^4.0.0", "vite": "^4.4.0"}\n}', encoding="utf-8")
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        (project_dir / "index.html").write_text('<!DOCTYPE html>\n<html><head><meta charset="UTF-8"><title>' + title + '</title></head><body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body></html>', encoding="utf-8")
        (src_dir / "main.jsx").write_text("import React from 'react';\nimport ReactDOM from 'react-dom/client';\nimport App from './App.jsx';\nimport './index.css';\nReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);", encoding="utf-8")
        (src_dir / "App.jsx").write_text("export default function App() {\n  return <div className='app'><h1>" + title + "</h1><p>" + tagline + "</p></div>;\n}", encoding="utf-8")
        (src_dir / "index.css").write_text("body{margin:0;font-family:system-ui,sans-serif;background:#0f1420;color:#f4f2ff}\n.app{padding:2rem}", encoding="utf-8")
        run_hint = "npm install && npm run dev"
    elif kind == "fastapi-auth":
        (project_dir / "requirements.txt").write_text("fastapi\nuvicorn\npydantic\npython-multipart\npython-jose[cryptography]\npasslib[bcrypt]\nsqlalchemy", encoding="utf-8")
        app_dir = project_dir / "app"
        app_dir.mkdir(exist_ok=True)
        (app_dir / "__init__.py").write_text("", encoding="utf-8")
        (app_dir / "database.py").write_text("from sqlalchemy import create_engine, Column, Integer, String\nfrom sqlalchemy.orm import declarative_base, sessionmaker\n\nengine = create_engine('sqlite:///./app.db', connect_args={'check_same_thread': False})\nSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\nBase = declarative_base()\n\nclass User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer, primary_key=True, index=True)\n    username = Column(String, unique=True, index=True)\n    hashed_password = Column(String)\n\nBase.metadata.create_all(bind=engine)\n", encoding="utf-8")
        (app_dir / "main.py").write_text("from datetime import datetime, timedelta\nfrom fastapi import FastAPI, Depends, HTTPException\nfrom fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm\nfrom sqlalchemy.orm import Session\nfrom jose import JWTError, jwt\nfrom passlib.context import CryptContext\nfrom .database import SessionLocal, User\n\nSECRET_KEY = 'magic-secret-key'\nALGORITHM = 'HS256'\napp = FastAPI(title='Magic Auth API')\noauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')\npwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')\n\ndef get_db():\n    db = SessionLocal()\n    try: yield db\n    finally: db.close()\n\ndef create_access_token(data):\n    to_encode = data.copy()\n    to_encode.update({'exp': datetime.utcnow() + timedelta(minutes=30)})\n    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)\n\n@app.post('/register')\ndef register(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):\n    if db.query(User).filter(User.username == form_data.username).first():\n        raise HTTPException(status_code=400, detail='Already registered')\n    user = User(username=form_data.username, hashed_password=pwd_context.hash(form_data.password))\n    db.add(user); db.commit()\n    return {'message': 'User created'}\n\n@app.post('/token')\ndef login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):\n    user = db.query(User).filter(User.username == form_data.username).first()\n    if not user or not pwd_context.verify(form_data.password, user.hashed_password):\n        raise HTTPException(status_code=401, detail='Bad credentials')\n    return {'access_token': create_access_token({'sub': user.username}), 'token_type': 'bearer'}\n\n@app.get('/users/me')\ndef me(token: str = Depends(oauth2_scheme)):\n    try:\n        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n        if not payload.get('sub'): raise HTTPException(status_code=401)\n    except JWTError: raise HTTPException(status_code=401, detail='Invalid token')\n    return {'user': payload['sub']}\n", encoding="utf-8")
        run_hint = "uvicorn app.main:app --reload --port 8010"
    else:
        run_hint = "cd " + str(project_dir)

    (project_dir / "README.md").write_text(
        "# " + title + "\n\nType: " + kind + "\n\nGoal:\n" + prompt +
        "\n\nThis project is ready. Ask Magic to customize it further.",
        encoding="utf-8",
    )

    return "Created " + kind + " project at " + str(project_dir) + ".\nRun with: `" + run_hint + "`"

'''

new_content = "".join(pre) + "\n" + SCAFFOLD + "\n" + "".join(post)
WS.write_text(new_content)
print(f"Done. workspace.py is now {len(new_content.splitlines())} lines.")
