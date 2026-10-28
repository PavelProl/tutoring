"""Build a lesson_kit into HTML (KaTeX + mhchem) and print it to A4 PDF.

Usage:
    python build_kit.py <content_root> kits/oge/<kit>/kit.md <out_dir>
    python build_kit.py <content_root> tests/<test>.md <out_dir>

A kit gives three pages: student.html (notes, lesson exercises, homework),
answers.html (the same exercises with solutions, for the student's self-check)
and teacher.html (plan, must_know, solutions, sources, flags).
A test gives slides.html (16:9, one question per slide, key at the end).
"""

import html
import re
import subprocess
import sys
from pathlib import Path

import markdown
import yaml

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"

MATH_RE = re.compile(r"\$\$.+?\$\$|\$[^$\n]+?\$", re.S)
FIG_RE = re.compile(r"^!\[\]\(([^)]+\.svg)\)\s*$", re.M)


def read_md(path):
    """Split a Markdown file into (front matter dict, body)."""
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        return yaml.safe_load(head) or {}, body.strip()
    return {}, text.strip()


def md(text, base=None, inline=False):
    """Markdown to HTML, keeping $...$ untouched for KaTeX and inlining SVG figures."""
    text = str(text)
    if base is not None:
        text = FIG_RE.sub(
            lambda m: '\n<div class="fig">' + (base / m.group(1)).read_text(encoding="utf-8") + "</div>\n",
            text,
        )
    stash = []

    def keep(m):
        stash.append(m.group(0))
        return f"MATHPH{len(stash) - 1}X"

    text = MATH_RE.sub(keep, text)
    out = markdown.markdown(text, extensions=["tables", "sane_lists", "nl2br"])
    if inline and out.startswith("<p>") and out.endswith("</p>") and out.count("<p>") == 1:
        out = out[3:-4]
    return re.sub(r"MATHPH(\d+)X", lambda m: html.escape(stash[int(m.group(1))], quote=False), out)


def load_exercise(root, ex_id):
    path = root / "exercises" / f"{ex_id}.md"
    meta, body = read_md(path)
    condition, _, solution = body.partition("## Решение")
    return {
        "id": ex_id,
        "meta": meta,
        "condition": md(condition.strip(), base=path.parent),
        "solution": md(solution.strip(), base=path.parent) if solution.strip() else "",
        "answer": md(meta.get("answer", ""), inline=True),
    }


def page(title, body, slides=False):
    size = "297mm 167mm" if slides else "A4"
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{KATEX}/katex.min.css">
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/mhchem.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}],throwOnError:false}})"></script>
<style>
@page {{ size: {size}; margin: {'0' if slides else '16mm 16mm 18mm'}; }}
:root {{ --accent:#e0702a; --soft:#fdf1e8; --ink:#1d1d1f; --mute:#6b6b70; --line:#e6e2dd; }}
* {{ box-sizing:border-box; }}
body {{ font-family:Inter,system-ui,sans-serif; color:var(--ink); background:#fff; font-size:10.5pt; line-height:1.5; margin:0 auto; max-width:180mm; padding:0 16px; }}
.label {{ color:var(--accent); font-size:8pt; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin-top:6mm; }}
h1 {{ font-size:22pt; line-height:1.15; margin:2mm 0 1mm; }}
.sub {{ color:var(--mute); margin-bottom:6mm; }}
.part {{ color:var(--accent); font-size:9pt; font-weight:700; letter-spacing:.1em; text-transform:uppercase; margin:9mm 0 0; border-top:2px solid var(--accent); padding-top:2mm; }}
h2 {{ font-size:14pt; margin:6mm 0 2mm; padding-bottom:1mm; border-bottom:1px solid var(--line); break-after:avoid; }}
h3 {{ font-size:11.5pt; margin:4mm 0 1mm; break-after:avoid; }}
blockquote {{ margin:3mm 0; padding:2.5mm 4mm; background:var(--soft); border-left:3px solid var(--accent); break-inside:avoid; }}
blockquote p {{ margin:0; }}
table {{ border-collapse:collapse; margin:3mm 0; width:100%; font-size:9.5pt; break-inside:avoid; }}
th {{ text-align:left; font-size:8pt; text-transform:uppercase; letter-spacing:.05em; color:var(--mute); border-bottom:1.5px solid var(--ink); padding:1.5mm 2mm; }}
td {{ border-bottom:1px solid var(--line); padding:1.5mm 2mm; vertical-align:top; }}
.ex {{ margin:4mm 0; padding-left:10mm; position:relative; break-inside:avoid; }}
.ex .num {{ position:absolute; left:0; top:0; font-weight:700; color:var(--accent); }}
.ex .src {{ color:var(--mute); font-size:8pt; }}
.ex p {{ margin:1mm 0; }}
.star {{ font-size:8pt; font-weight:700; color:var(--accent); }}
.sol {{ margin-top:2mm; padding:2mm 4mm; border-left:3px solid var(--line); background:#fafafa; }}
.ans {{ margin-top:1mm; font-weight:600; }}
.fig {{ margin:2mm 0; }}
.flag {{ color:#9a3412; font-size:9pt; }}
.katex {{ font-size:1.05em; }}
body.slides {{ max-width:none; padding:0; }}
.slide {{ width:297mm; height:167mm; padding:14mm 22mm; break-after:page; position:relative; overflow:hidden; display:flex; flex-direction:column; justify-content:center; }}
.slide .label {{ margin-top:0; font-size:11pt; }}
.slide h1 {{ font-size:30pt; }}
.slide .q {{ font-size:24pt; font-weight:600; margin:6mm 0 8mm; line-height:1.3; }}
.slide .opts {{ display:grid; grid-template-columns:1fr 1fr; gap:5mm 10mm; font-size:21pt; }}
.slide .opts div {{ padding:4mm 6mm; border:1.5px solid var(--line); border-radius:3mm; }}
.slide .opts b {{ color:var(--accent); margin-right:3mm; }}
.slide .foot {{ position:absolute; bottom:8mm; right:18mm; color:var(--mute); font-size:10pt; }}
.slide table {{ font-size:12pt; }}
@media screen {{ .slide {{ max-width:100%; height:auto; aspect-ratio:16/9; border:1px solid var(--line); margin:8px auto; }} }}
@media screen and (max-width:700px) {{ .slide .q {{ font-size:18pt; }} .slide .opts {{ font-size:15pt; grid-template-columns:1fr; }} }}
</style></head><body class="{'slides' if slides else ''}">
{body}
</body></html>
"""


def render_exercise(n, ex, role=None, solved=False, teacher=False):
    star = ' <span class="star">★ разбираем вместе</span>' if role == "worked_example" else ""
    parts = [f'<div class="ex"><span class="num">{n}</span>{star}', ex["condition"]]
    if solved or teacher:
        if ex["solution"]:
            parts.append(f'<div class="sol"><b>Решение.</b>{ex["solution"]}</div>')
        else:
            parts.append(f'<div class="ans">Ответ: {ex["answer"]}</div>')
    if teacher:
        parts.append(f'<div class="src">{html.escape("; ".join(ex["meta"].get("sources", [])))} · {ex["id"]}</div>')
    parts.append("</div>")
    return "\n".join(parts)


def topic_number(root, topic_id):
    """Find the topic's number in the course map table row `| N | `id` | ...`."""
    m = re.search(rf"^\|\s*(\d+)\s*\|\s*`{re.escape(topic_id)}`\s*\|",
                  (root / "course-map.md").read_text(encoding="utf-8"), re.M)
    if not m:
        sys.exit(f"Topic {topic_id} is not in course-map.md")
    return m.group(1)


def build_kit(root, kit_path, out):
    kit, plan = read_md(kit_path)
    lesson = [(item, load_exercise(root, item["id"])) for item in kit["lesson"]]
    homework = [load_exercise(root, ex_id) for ex_id in kit["homework"]["exercises"]]
    title = f'Тема {topic_number(root, kit["main_topic"])}. {kit["title"]}'
    head = (f'<div class="label">{{label}}</div><h1>{html.escape(title)}</h1>'
            f'<div class="sub">{html.escape(kit.get("subtitle", ""))}</div>')

    notes = []
    for i, note_path in enumerate(kit["theory_block"], 1):
        meta, body = read_md(root / note_path)
        notes.append(f'<div class="part">Часть {i}. {html.escape(meta["title"])}</div>')
        notes.append(md(body))

    def exercises(solved=False, teacher=False):
        rows = ["<h2>Задания на занятии</h2>"]
        rows += [render_exercise(n, ex, item.get("role"), solved, teacher) for n, (item, ex) in enumerate(lesson, 1)]
        rows.append("<h2>Домашнее задание</h2>")
        if not solved:
            rows.append(md(kit["homework"]["reading"]))
        rows += [render_exercise(n, ex, solved=solved, teacher=teacher) for n, ex in enumerate(homework, 1)]
        return "\n".join(rows)

    student = head.format(label="Конспект · Химия") + "\n".join(notes) + exercises()
    answers = head.format(label="Решения и ответы · Химия") + exercises(solved=True)
    flags = [(ex["id"], f) for ex in [e for _, e in lesson] + homework for f in ex["meta"].get("flags", [])]
    flag_html = ""
    if flags:
        flag_html = "<h2>Пометки к проверке</h2><ul>" + "".join(
            f'<li class="flag"><b>{i}</b>: {html.escape(f)}</li>' for i, f in flags) + "</ul>"
    teacher = head.format(label="Для преподавателя · Комплект") + md(plan) + exercises(teacher=True) + flag_html

    out.mkdir(parents=True, exist_ok=True)
    (out / "student.html").write_text(page(kit["title"], student), encoding="utf-8")
    (out / "answers.html").write_text(page(kit["title"] + " — решения", answers), encoding="utf-8")
    (out / "teacher.html").write_text(page(kit["title"] + " — преподавателю", teacher), encoding="utf-8")
    return [out / "student.html", out / "answers.html", out / "teacher.html"]


def build_test(test_path, out):
    test, _ = read_md(test_path)
    qs = test["questions"]
    slides = [f'<section class="slide"><div class="label">Тест · Химия</div><h1>{html.escape(test["title"])}</h1>'
              f'<div class="q" style="font-size:16pt;font-weight:400">{html.escape(test["subtitle"])}</div>'
              '<div class="q" style="font-size:16pt;font-weight:400">В каждом вопросе один верный ответ. Записывай номер вопроса и номер ответа.</div></section>']
    for n, q in enumerate(qs, 1):
        opts = "".join(f"<div><b>{k}</b>{md(o, inline=True)}</div>" for k, o in enumerate(q["options"], 1))
        slides.append(f'<section class="slide"><div class="label">Вопрос {n} из {len(qs)}</div>'
                      f'<div class="q">{md(q["q"], inline=True)}</div><div class="opts">{opts}</div></section>')
    key = "".join(f"<tr><td>{n}</td><td><b>{q['answer']}</b></td><td>{html.escape(q['checks'])}</td></tr>"
                  for n, q in enumerate(qs, 1))
    scale = "".join(f"<tr><td><b>{s['range']}</b></td><td>{html.escape(s['meaning'])}</td></tr>" for s in test["scale"])
    slides.append('<section class="slide"><h1>Ответы</h1>'
                  f'<div style="display:flex;gap:10mm"><table><tr><th>№</th><th>Ответ</th><th>Что проверяет</th></tr>{key}</table>'
                  f'<table><tr><th>Баллы</th><th>Что это значит</th></tr>{scale}</table></div></section>')
    for n, q in enumerate(qs, 1):
        if q.get("explain"):
            items = "".join(f'<li style="margin:2mm 0">{md(e, inline=True)}</li>' for e in q["explain"])
            slides.append(f'<section class="slide"><div class="label">Разбор вопроса {n}</div>'
                          f'<div class="q" style="font-size:18pt;margin:2mm 0 4mm">{md(q["q"], inline=True)}</div>'
                          f'<ul style="font-size:13.5pt;line-height:1.45;padding-left:6mm;margin:0">{items}</ul></section>')
    out.mkdir(parents=True, exist_ok=True)
    path = out / "slides.html"
    path.write_text(page(test["title"], "\n".join(slides), slides=True), encoding="utf-8")
    return [path]


def slide_images(pdf):
    """One 1920x1080 PNG per slide, for showing slides one by one."""
    folder = pdf.parent / "slides"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()
    subprocess.run(["pdftoppm", "-png", "-scale-to-x", "1920", "-scale-to-y", "1080",
                    str(pdf), str(folder / "slide")], check=True)
    return folder


def print_pdf(html_path):
    pdf = html_path.with_suffix(".pdf")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=20000", f"--print-to-pdf={pdf}", html_path.resolve().as_uri()],
                   check=True, capture_output=True)
    return pdf


def main():
    root, src, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    pages = build_test(root / src, out) if src.parts[0] == "tests" else build_kit(root, root / src, out)
    for p in pages:
        pdf = print_pdf(p)
        print(p, "->", pdf)
        if p.name == "slides.html":
            print("slides one by one ->", slide_images(pdf))


if __name__ == "__main__":
    main()
