from __future__ import annotations

import re
import shlex
import subprocess
import os
import difflib
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


try:
    from app.backend_gen import generate_fastapi_backend
except ImportError:
    generate_fastapi_backend = None

@dataclass
class WorkspaceRunResult:
    ok: bool
    output: str


@dataclass
class BuildSpec:
    title: str
    tagline: str
    feature_list: list[str]
    section_list: list[str]
    palette: list[str]
    data_fields: list[str]
    call_to_action: str


_COLOR_WORDS = (
    "blue",
    "cyan",
    "teal",
    "purple",
    "violet",
    "pink",
    "gold",
    "yellow",
    "orange",
    "green",
    "red",
    "black",
    "white",
    "indigo",
)


def _split_phrase_list(text: str, limit: int = 6) -> list[str]:
    if not text.strip():
        return []
    normalized = re.sub(r"\band\b", ",", text, flags=re.IGNORECASE)
    items = [part.strip(" .:-") for part in normalized.split(",")]
    return [item for item in items if item][:limit]


def _extract_match(prompt: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _extract_build_spec(name: str, prompt: str) -> BuildSpec:
    prompt = (prompt or "").strip()
    default_title = name.replace("-", " ").title()
    title = _extract_match(
        prompt,
        (
            r"(?:called|named|title(?:d)?)\s+['\"]?([^'\"\n.,]+)",
            r"(?:for|about)\s+['\"]?([^'\"\n.,]{3,50})",
        ),
    ) or default_title
    tagline = _extract_match(
        prompt,
        (
            r"(?:tagline|headline|hero text|slogan)\s*[:\-]?\s*['\"]?([^'\"\n]+)",
            r"(?:that says|saying)\s+['\"]?([^'\"\n]+)",
        ),
    ) or (prompt[:120].strip() if prompt else f"{default_title} built with Magic")
    feature_text = _extract_match(
        prompt,
        (
            r"(?:features?|include|with)\s+(.+?)(?:\.|$)",
            r"(?:should have)\s+(.+?)(?:\.|$)",
        ),
    )
    section_text = _extract_match(
        prompt,
        (
            r"(?:sections?|pages?|screens?)\s+(.+?)(?:\.|$)",
            r"(?:with sections?|with pages?)\s+(.+?)(?:\.|$)",
        ),
    )
    field_text = _extract_match(
        prompt,
        (
            r"(?:columns?|fields?)\s+(.+?)(?:\.|$)",
            r"(?:data model|schema)\s+(.+?)(?:\.|$)",
        ),
    )
    palette = [word for word in _COLOR_WORDS if re.search(rf"\b{re.escape(word)}\b", prompt, re.IGNORECASE)]
    features = _split_phrase_list(feature_text) or ["Premium experience", "Fast workflows", "Clean delivery"]
    sections = _split_phrase_list(section_text) or ["Overview", "Features", "Proof", "Contact"]
    data_fields = _split_phrase_list(field_text) or ["id", "name", "status", "created_at"]
    call_to_action = "Get Started"
    if "book" in prompt.lower():
        call_to_action = "Book a Demo"
    elif "download" in prompt.lower():
        call_to_action = "Download Now"
    return BuildSpec(
        title=title,
        tagline=tagline,
        feature_list=features[:6],
        section_list=sections[:6],
        palette=palette[:4],
        data_fields=data_fields[:8],
        call_to_action=call_to_action,
    )


def workspace_root() -> Path:
    root = get_settings().magic_workspace_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_slug(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return lowered[:48] or "magic-project"


def resolve_workspace_path(raw_path: str | None = None) -> Path:
    root = workspace_root()
    text = (raw_path or ".").strip()
    candidate = Path(text).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"path must stay inside {root}") from exc
    return resolved


def describe_workspace_tree(raw_path: str | None = None, recursive: bool = True, limit: int = 160) -> str:
    target = resolve_workspace_path(raw_path)
    if not target.exists():
        return f"{target} does not exist yet."
    if target.is_file():
        return f"FILE {target.relative_to(workspace_root())}"

    lines = [f"Workspace root: {workspace_root()}", f"Listing: {target.relative_to(workspace_root()) or '.'}"]
    if recursive:
        items = sorted(target.rglob("*"))
    else:
        items = sorted(target.iterdir())
    shown = 0
    for item in items:
        if shown >= limit:
            lines.append(f"...and {len(items) - shown} more")
            break
        rel = item.relative_to(workspace_root())
        marker = "/" if item.is_dir() else ""
        lines.append(f"- {rel}{marker}")
        shown += 1
    if shown == 0:
        lines.append("(empty)")
    return "\n".join(lines)


def workspace_snapshot(limit: int = 40) -> str:
    root = workspace_root()
    if not root.exists():
        return "(workspace unavailable)"
    items = sorted(root.rglob("*"))
    if not items:
        return f"Workspace root: {root}\n(empty)"

    lines = [f"Workspace root: {root}"]
    for item in items[:limit]:
        rel = item.relative_to(root)
        suffix = "/" if item.is_dir() else ""
        lines.append(f"- {rel}{suffix}")
    if len(items) > limit:
        lines.append(f"...and {len(items) - limit} more")
    return "\n".join(lines)


def read_workspace_file(raw_path: str) -> str:
    target = resolve_workspace_path(raw_path)
    if not target.exists():
        raise ValueError(f"{target.name} does not exist")
    if not target.is_file():
        raise ValueError(f"{target.name} is not a file")
    text = target.read_text(encoding="utf-8")
    if len(text) > 14000:
        text = text[:13900].rstrip() + "\n...[truncated]"
    return text


def write_workspace_file(raw_path: str, content: str, overwrite: bool = True) -> str:
    target = resolve_workspace_path(raw_path)
    if target.exists() and target.is_dir():
        raise ValueError(f"{target.name} is a directory")
    if target.exists() and not overwrite:
        raise ValueError(f"{target.name} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {target.relative_to(workspace_root())}"


def _next_available_project_dir(name: str) -> Path:
    root = workspace_root()
    base = root / _safe_slug(name)
    if not base.exists():
        return base
    for idx in range(2, 100):
        candidate = root / f"{base.name}-{idx}"
        if not candidate.exists():
            return candidate
    raise ValueError("could not find an available project folder name")


def _write_website_scaffold(project_dir: Path, spec: BuildSpec, prompt: str) -> None:
    """Write a full glassmorphic dark-mode landing page with nav, hero, cards, footer."""
    title = spec.title
    tagline = spec.tagline
    feature_cards = "".join(
        f'<div class="card"><div class="card-icon">&#10024;</div><h3>{feature}</h3>'
        f'<p>{feature} for a polished production-ready experience.</p></div>'
        for feature in spec.feature_list[:3]
    )
    nav_links = "".join(
        f'<a href="#section-{idx + 1}">{section}</a>'
        for idx, section in enumerate(spec.section_list[:3])
    )
    sections = "".join(
        f'<section id="section-{idx + 1}" class="about"><h2>{section}</h2><p>{prompt or tagline}</p></section>\n'
        for idx, section in enumerate(spec.section_list)
    )
    html_parts = [
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
        f'<title>{title}</title>\n',
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n',
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">\n',
        '<link rel="stylesheet" href="styles.css">\n</head>\n<body>\n',
        f'<nav class="nav"><div class="nav-brand">{title}</div>',
        f'<div class="nav-links">{nav_links}<a href="#contact" class="btn-nav">{spec.call_to_action}</a></div></nav>\n',
        '<header class="hero"><div class="hero-content">',
        f'<p class="hero-tag">Introducing {title}</p>\n',
        f'<h1>{tagline}</h1>\n',
        f'<p class="hero-sub">{prompt or "A beautifully crafted experience, built to impress."}</p>\n',
        '<div class="hero-actions"><a href="#features" class="btn-primary">Explore</a>',
        f'<a href="#contact" class="btn-outline">{spec.call_to_action}</a></div></div></header>\n',
        '<section id="features" class="features"><h2>Features</h2><div class="card-grid">',
        feature_cards,
        '</div></section>\n',
        sections,
        f'<section id="contact" class="about"><h2>Next Step</h2><p>{spec.call_to_action} to move this project forward.</p></section>\n',
        f'<footer class="footer"><p>&copy; 2026 {title}. Crafted with Magic.</p></footer>\n',
        '<script src="script.js"></script>\n</body>\n</html>',
    ]
    css = (
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
    js = (
        "document.querySelectorAll('.card').forEach(c=>{"
        "c.style.opacity=0;c.style.transform='translateY(20px)';"
        "c.style.transition='opacity .6s ease,transform .6s ease';"
        "new IntersectionObserver(e=>{e.forEach(x=>{if(x.isIntersecting){"
        "x.target.style.opacity=1;x.target.style.transform='translateY(0)'"
        "}})},{threshold:0.1}).observe(c)});"
    )
    (project_dir / "index.html").write_text("".join(html_parts), encoding="utf-8")
    (project_dir / "styles.css").write_text(css, encoding="utf-8")
    (project_dir / "script.js").write_text(js, encoding="utf-8")


def _write_slides_scaffold(project_dir: Path, spec: BuildSpec) -> None:
    """Write a proper 8-slide Reveal.js deck."""
    title = spec.title
    tagline = spec.tagline
    feature_bullets = "".join(f"<li>{item}</li>" for item in spec.feature_list[:4])
    sl = [
        f'<!DOCTYPE html>\n<html><head><title>{title}</title>',
        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/reveal.min.css">',
        '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/theme/black.min.css">',
        '</head><body><div class="reveal"><div class="slides">',
        f'<section><h1>{title}</h1><p>{tagline}</p></section>',
        '<section><h2>Agenda</h2><ul><li>Problem</li><li>Solution</li><li>Features</li><li>Results</li><li>Next Steps</li></ul></section>',
        '<section><h2>Problem</h2><p>Describe the core challenge.</p></section>',
        '<section><h2>Solution</h2><p>Present your approach.</p></section>',
        f'<section><h2>Features</h2><ul>{feature_bullets}</ul></section>',
        '<section><h2>Results</h2><p>Share metrics.</p></section>',
        '<section><h2>Next Steps</h2><p>Outline the roadmap.</p></section>',
        '<section><h1>Thank You</h1></section>',
        '</div></div><script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.3.1/reveal.min.js"></script>',
        '<script>Reveal.initialize({hash:true,transition:"slide"});</script></body></html>',
    ]
    (project_dir / "index.html").write_text("".join(sl), encoding="utf-8")


def _write_document_scaffold(project_dir: Path, spec: BuildSpec, prompt: str) -> None:
    """Write a rich markdown document with table of contents and proper structure."""
    import datetime as _dt
    title = spec.title
    tagline = spec.tagline
    sections = "\n\n".join(f"## {section}\n\nExpand this section with project-specific detail." for section in spec.section_list[:4])
    doc = "\n".join([
        f"# {title}", "", f"> {tagline}", "",
        "## Table of Contents", "1. Abstract", "2. Introduction", "3. Key Sections", "4. Conclusion", "", "---", "",
        "## Abstract", "", prompt or "Summary goes here.", "",
        "## Introduction", "", "Introduce the topic, context, and objectives.", "",
        sections, "",
        "## Conclusion", "", "Key takeaways and next steps.", "", "---", "",
        f"*Generated by Magic on {_dt.datetime.now().strftime('%Y-%m-%d')}*", "",
    ])
    (project_dir / "document.md").write_text(doc, encoding="utf-8")


def _write_csv_scaffold(project_dir: Path, spec: BuildSpec, prompt: str) -> None:
    """Write a fully functional CSV data generator script."""
    fields = spec.data_fields or ["id", "name", "status", "created_at"]
    headers_repr = repr(fields)
    gen = "\n".join([
        "import csv, random",
        "from datetime import datetime, timedelta",
        "",
        f"# Spec: {prompt or 'Sample dataset'}",
        "",
        f"HEADERS = {headers_repr}",
        "DEPTS = ['Engineering', 'Marketing', 'Sales', 'Design', 'Operations', 'Finance']",
        "FIRST = ['Alex', 'Jordan', 'Morgan', 'Casey', 'Taylor', 'Riley', 'Quinn', 'Avery']",
        "LAST = ['Smith', 'Chen', 'Patel', 'Kim', 'Garcia', 'Mueller', 'Tanaka', 'Silva']",
        "",
        "def row(i):",
        "    f, l = random.choice(FIRST), random.choice(LAST)",
        "    d = datetime(2020, 1, 1) + timedelta(days=random.randint(0, 1800))",
        "    values = {",
        "        'id': i,",
        "        'name': f'{f} {l}',",
        "        'email': f'{f.lower()}.{l.lower()}@company.com',",
        "        'department': random.choice(DEPTS),",
        "        'salary': round(random.uniform(55000, 180000), 2),",
        "        'joined': d.strftime('%Y-%m-%d'),",
        "        'active': random.choice(['Yes', 'Yes', 'Yes', 'No']),",
        "        'status': random.choice(['New', 'Active', 'Paused', 'Closed']),",
        "        'created_at': d.strftime('%Y-%m-%d'),",
        "    }",
        "    return [values.get(h, '') for h in HEADERS]",
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


def _write_image_scaffold(project_dir: Path, spec: BuildSpec, prompt: str) -> None:
    """Write a professional image generator with gradient background and decorative elements."""
    title = spec.title
    img = "\n".join([
        "from PIL import Image, ImageDraw, ImageFont",
        "import math",
        "",
        f"# Spec: {prompt or 'Professional gradient image'}",
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
        f"draw.text((60, 60), '{title}', fill=(241, 245, 249), font=font)",
        "img.save('output.png')",
        "print('Saved output.png (1200x800)')",
        "",
    ])
    (project_dir / "generate_image.py").write_text(img, encoding="utf-8")


def scaffold_project(name: str, kind: str = "website", prompt: str = "", spec: dict | None = None) -> str:
    spec = spec or {}
    project_dir = _next_available_project_dir(name)
    project_dir.mkdir(parents=True, exist_ok=False)
    build_spec = _extract_build_spec(name, prompt)
    _title = build_spec.title
    _tagline = build_spec.tagline

    if kind == "website":
        _write_website_scaffold(project_dir, build_spec, prompt)
        run_hint = "python3 -m http.server 4173"
    elif kind == "react":
        (project_dir / "package.json").write_text('{\n  "name": "magic-react",\n  "version": "1.0.0",\n  "scripts": {\n    "dev": "vite",\n    "build": "vite build"\n  },\n  "dependencies": {\n    "react": "^18.2.0",\n    "react-dom": "^18.2.0"\n  },\n  "devDependencies": {\n    "@vitejs/plugin-react": "^4.0.0",\n    "vite": "^4.4.0"\n  }\n}', encoding="utf-8")
        (project_dir / "index.html").write_text('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Magic React App</title>\n</head>\n<body>\n<div id="root"></div>\n<script type="module" src="/src/main.jsx"></script>\n</body>\n</html>', encoding="utf-8")
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "main.jsx").write_text("import React from 'react';\nimport ReactDOM from 'react-dom/client';\nimport App from './App.jsx';\nimport './index.css';\n\nReactDOM.createRoot(document.getElementById('root')).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>,\n);", encoding="utf-8")
        (src_dir / "App.jsx").write_text("import React from 'react';\n\nfunction App() {\n  return (\n    <div className=\"app\">\n      <h1>Hello from React</h1>\n      <p>Built by Magic</p>\n    </div>\n  );\n}\nexport default App;", encoding="utf-8")
        (src_dir / "index.css").write_text("body { margin: 0; font-family: system-ui, sans-serif; background: #0f1420; color: #f4f2ff; }\n.app { padding: 2rem; }", encoding="utf-8")
        run_hint = "npm install && npm run dev"
    elif kind == "react-tailwind":
        (project_dir / "package.json").write_text('{\n  "name": "magic-tailwind",\n  "version": "1.0.0",\n  "scripts": {\n    "dev": "vite",\n    "build": "vite build"\n  },\n  "dependencies": {\n    "react": "^18.2.0",\n    "react-dom": "^18.2.0"\n  },\n  "devDependencies": {\n    "@vitejs/plugin-react": "^4.0.0",\n    "autoprefixer": "^10.4.14",\n    "postcss": "^8.4.27",\n    "tailwindcss": "^3.3.3",\n    "vite": "^4.4.0"\n  }\n}', encoding="utf-8")
        (project_dir / "tailwind.config.js").write_text('/** @type {import("tailwindcss").Config} */\nexport default {\n  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],\n  theme: {\n    extend: {},\n  },\n  plugins: [],\n}', encoding="utf-8")
        (project_dir / "postcss.config.js").write_text('export default {\n  plugins: {\n    tailwindcss: {},\n    autoprefixer: {},\n  },\n}', encoding="utf-8")
        (project_dir / "index.html").write_text('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>React + Tailwind</title>\n</head>\n<body class="bg-slate-900 text-white">\n<div id="root"></div>\n<script type="module" src="/src/main.jsx"></script>\n</body>\n</html>', encoding="utf-8")
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "index.css").write_text('@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\nbody { margin: 0; font-family: system-ui, sans-serif; }', encoding="utf-8")
        (src_dir / "main.jsx").write_text("import React from 'react';\nimport ReactDOM from 'react-dom/client';\nimport App from './App.jsx';\nimport './index.css';\n\nReactDOM.createRoot(document.getElementById('root')).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>,\n);", encoding="utf-8")
        app_jsx = "export default function App() {\n  return (\n    <div className=\"min-h-screen bg-slate-900 text-slate-50 font-sans\">\n      <nav className=\"border-b border-slate-800 p-4 flex justify-between items-center\">\n        <div className=\"text-xl font-bold text-cyan-400\">MagicApp</div>\n        <div className=\"space-x-4\">\n          <a href=\"#\" className=\"hover:text-cyan-300\">Home</a>\n          <a href=\"#\" className=\"hover:text-cyan-300\">Features</a>\n          <a href=\"#\" className=\"bg-cyan-500 text-slate-900 px-4 py-2 rounded-full font-medium hover:bg-cyan-400 transition\">Get Started</a>\n        </div>\n      </nav>\n      <main className=\"max-w-6xl mx-auto px-4 py-20 text-center\">\n        <h1 className=\"text-6xl font-extrabold mb-6 tracking-tight\">\n          Build faster with <span className=\"text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500\">Magic</span>\n        </h1>\n        <p className=\"text-xl text-slate-400 mb-10 max-w-2xl mx-auto\">\n          Your fully styled React and Tailwind CSS application is ready to go. Edit this page to start building your masterpiece.\n        </p>\n        <div className=\"grid grid-cols-1 md:grid-cols-3 gap-6 mt-16 text-left\">\n          {[1, 2, 3].map(i => (\n            <div key={i} className=\"p-6 rounded-2xl bg-slate-800 border border-slate-700 hover:border-cyan-500/50 transition\">\n              <div className=\"w-12 h-12 bg-cyan-500/10 rounded-xl flex items-center justify-center text-cyan-400 mb-4 text-2xl\">✨</div>\n              <h3 className=\"text-lg font-bold mb-2\">Feature {i}</h3>\n              <p className=\"text-slate-400 text-sm\">Description of this awesome feature goes here. Replace this with your actual product details.</p>\n            </div>\n          ))}\n        </div>\n      </main>\n    </div>\n  );\n}"
        (src_dir / "App.jsx").write_text(app_jsx, encoding="utf-8")
        run_hint = "npm install && npm run dev"
    elif kind == "fastapi-auth":
        import jinja2
        db_type = spec.get("database", "sqlite")
        auth_type = spec.get("auth_type", "jwt") if spec.get("auth") == "yes" else "none"
        reqs = ["fastapi", "uvicorn", "pydantic", "pytest"]
        if auth_type == "jwt":
            reqs.extend(["python-multipart", "python-jose[cryptography]", "passlib[bcrypt]"])
        if db_type in ("sqlite", "postgresql"):
            reqs.append("sqlalchemy")
            if db_type == "postgresql":
                reqs.append("psycopg2-binary")
        elif db_type == "mongodb":
            reqs.append("motor")
        (project_dir / "requirements.txt").write_text("\n".join(reqs), encoding="utf-8")
        
        app_dir = project_dir / "app"
        app_dir.mkdir(exist_ok=True)
        (app_dir / "__init__.py").write_text("", encoding="utf-8")
        (app_dir / "database.py").write_text("from sqlalchemy import create_engine, Column, Integer, String\nfrom sqlalchemy.orm import declarative_base, sessionmaker\n\nengine = create_engine('sqlite:///./app.db', connect_args={'check_same_thread': False})\nSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\nBase = declarative_base()\n\nclass User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer, primary_key=True, index=True)\n    username = Column(String, unique=True, index=True)\n    hashed_password = Column(String)\n\nBase.metadata.create_all(bind=engine)\n", encoding="utf-8")
        
        main_template = """from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
{% if auth_type == 'jwt' %}
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
{% endif %}
{% if db_type in ('sqlite', 'postgresql') %}
from sqlalchemy.orm import Session
from .database import SessionLocal, User
{% endif %}

app = FastAPI(title="Magic Auth API")

@app.get('/')
def read_root():
    return {"message": "Welcome to your scaffolded API"}
"""
        template = jinja2.Template(main_template)
        main_py = template.render(auth_type=auth_type, db_type=db_type)
        (app_dir / "main.py").write_text(main_py, encoding="utf-8")
        run_hint = "uvicorn app.main:app --reload --port 8010"
    elif kind == "backend" and generate_fastapi_backend is not None:
        spec["project_name"] = name
        run_hint = generate_fastapi_backend(project_dir, spec)
    elif kind == "slides":
        _write_slides_scaffold(project_dir, build_spec)
        run_hint = "python3 -m http.server 4173"
    elif kind == "document":
        _write_document_scaffold(project_dir, build_spec, prompt)
        run_hint = "open document.md"
    elif kind == "csv" or kind == "spreadsheet":
        _write_csv_scaffold(project_dir, build_spec, prompt)
        run_hint = "python3 data_generator.py"
    elif kind == "pdf":
        (project_dir / "report.md").write_text(f"# {name}\n\n## Abstract\n{prompt}\n\n## Content\nAsk Magic to expand this document based on the exact specifications.\n", encoding="utf-8")
        (project_dir / "generate_pdf.py").write_text(f"import markdown, os\n\n# Spec: {prompt}\nhtml = markdown.markdown(open('report.md').read())\nopen('report.html','w').write(f'<html><head><style>body{{font-family:sans-serif;margin:40px auto;max-width:800px;line-height:1.6;}}</style></head><body>{{html}}</body></html>')\nprint('Generated report.html (Open in browser and Print to PDF)')\n", encoding="utf-8")
        run_hint = "pip install markdown && python3 generate_pdf.py && open report.html"
    elif kind == "image":
        _write_image_scaffold(project_dir, build_spec, prompt)
        run_hint = "pip install Pillow && python3 generate_image.py && open output.png"
    else:
        run_hint = "cd " + str(project_dir)

    (project_dir / "README.md").write_text(
        f"# {_title}\n\nType: {kind}\n\nGoal:\n{prompt}\n\nSpec summary:\n- tagline: {build_spec.tagline}\n- sections: {', '.join(build_spec.section_list)}\n- features: {', '.join(build_spec.feature_list)}\n- data fields: {', '.join(build_spec.data_fields)}\n\nThis project is ready. Ask Magic to customize it further.",
        encoding="utf-8",
    )
    artifact_paths = sorted(
        str(path.relative_to(project_dir))
        for path in project_dir.rglob("*")
        if path.is_file()
    )
    primary_file = "README.md"
    for candidate in ("index.html", "src/App.jsx", "app/main.py", "document.md", "data_generator.py", "generate_image.py"):
        if (project_dir / candidate).exists():
            primary_file = candidate
            break
    artifacts_block = "\n".join(f"- {item}" for item in artifact_paths[:12])
    return (
        f"Successfully created a {kind} project at `{project_dir}`.\n"
        f"Primary file: `{project_dir / primary_file}`\n"
        f"To preview or run this, use: `{run_hint}`\n"
        f"Artifacts generated:\n{artifacts_block}"
    )

def patch_workspace_file(raw_path: str, op: str, search_text: str, replace_text: str) -> tuple[str, str]:
    target = resolve_workspace_path(raw_path)
    if not target.exists() or not target.is_file():
        raise ValueError(f"{target.name} does not exist or is not a file")
    
    content = target.read_text(encoding="utf-8")
    
    if op in ("search_replace", "replace_block"):
        if search_text not in content:
            raise ValueError("search_text not found in the file. Ensure exact match.")
        new_content = content.replace(search_text, replace_text, 1)
    elif op == "insert_before":
        if search_text not in content:
            raise ValueError("search_text not found in the file. Ensure exact match.")
        new_content = content.replace(search_text, replace_text + "\n" + search_text, 1)
    elif op == "insert_after":
        if search_text not in content:
            raise ValueError("search_text not found in the file. Ensure exact match.")
        new_content = content.replace(search_text, search_text + "\n" + replace_text, 1)
    else:
        raise ValueError(f"Unknown patch op: {op}")
        
    diff_lines = list(difflib.unified_diff(content.splitlines(keepends=True), new_content.splitlines(keepends=True), fromfile=target.name, tofile=target.name))
    diff_str = "".join(diff_lines)
    target.write_text(new_content, encoding="utf-8")
    return f"Patched {target.relative_to(workspace_root())} using {op}", diff_str


def run_workspace_command(command: str, cwd: str | None = None, detach: bool = False) -> WorkspaceRunResult:
    settings = get_settings()
    text = (command or "").strip()
    if not text:
        return WorkspaceRunResult(ok=False, output="workspace command is empty")

    try:
        argv = shlex.split(text)
    except Exception as exc:  # noqa: BLE001
        return WorkspaceRunResult(ok=False, output=f"could not parse workspace command: {exc}")

    first = argv[0] if argv else ""
    if first not in settings.workspace_run_allowed_commands:
        return WorkspaceRunResult(ok=False, output=f"'{first}' is not allowed in workspace runner")

    workdir = resolve_workspace_path(cwd or ".")
    if not workdir.exists():
        workdir.mkdir(parents=True, exist_ok=True)
    if not workdir.is_dir():
        return WorkspaceRunResult(ok=False, output=f"{workdir} is not a folder")

    env = os.environ.copy()
    env["PATH"] = ":".join(
        [
            str(Path("/usr/bin")),
            str(Path("/bin")),
            str(Path("/usr/local/bin")),
            str(Path("/opt/homebrew/bin")),
            env.get("PATH", ""),
        ]
    )
    try:
        if detach:
            logs_dir = workspace_root() / ".runs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            slug = _safe_slug(workdir.name or "run")
            log_path = logs_dir / f"{slug}.log"
            handle = log_path.open("a", encoding="utf-8")
            process = subprocess.Popen(  # noqa: S603
                argv,
                cwd=str(workdir),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
            return WorkspaceRunResult(
                ok=True,
                output=f"Started background command in {workdir} with PID {process.pid}. Logs: {log_path}",
            )

        completed = subprocess.run(  # noqa: S603
            argv,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        output = ((completed.stdout or "") + (completed.stderr or "")).strip() or "ok"
        return WorkspaceRunResult(ok=completed.returncode == 0, output=output)
    except Exception as exc:  # noqa: BLE001
        return WorkspaceRunResult(ok=False, output=str(exc))
