"""Build a lesson_kit or a test into PDFs (HTML with KaTeX + mhchem, printed by Chrome).

Usage:
    python build_kit.py <content_root> kits/oge/<kit>/kit.md
    python build_kit.py <content_root> tests/<test>.md

Only PDFs land in <content_root>/build; the HTML is printed from a temporary folder.
A kit `oge/<topic>-<N>` of topic T goes to build/oge/<TT>-<topic>-<N>/:
«Тема T.N — занятие.pdf» (notes, lesson exercises, homework), «— решения.pdf»
(the same exercises with solutions, for the student's self-check), «— преподавателю.pdf»
(plan, must_know, solutions, sources, flags) and, if the kit has `entry_check`,
«— входная проверка.pdf» (16:9 slides on this kit's homework, held at the next lesson).
A test goes to build/tests/<title>.pdf (16:9, one question per slide, key at the end).

`theory_block` entries may pick sections: `notes/<id>.md#1-3` or `notes/<id>.md#4,6-8`.
Sections marked `<!-- exams: ЕГЭ -->` are left out of kits for other exams (ADR 0007).

Sources keep the notes numbering; the builder renumbers at render time. Each `theory_block`
entry (a part) restarts at 1, and every «Раздел N» the PDF shows follows: headings, references
inside the notes, the kit text and the attached entry check (#18).
"""

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown
import yaml

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"

MATH_RE = re.compile(r"\$\$.+?\$\$|\$[^$\n]+?\$", re.S)
FIG_RE = re.compile(r"^!\[\]\(([^)]+\.svg)\)\s*$", re.M)
SECTION_RE = re.compile(r"^## (\d+)\.", re.M)
REF_NUM = r"\d+(?:\s*[–-]\s*\d+)?"
REF_RE = re.compile(rf"([Рр]аздел(?:ы|а|е|у|ом|ов|ах|ам|ами)?\s+)({REF_NUM}(?:(?:,\s*|\s+и\s+){REF_NUM})*)")
EXAMS_RE = re.compile(r"<!--\s*exams:\s*([^>]*?)\s*-->")
EXAM_NAMES = {"OGE": "ОГЭ", "EGE": "ЕГЭ"}


def read_md(path):
    """Split a Markdown file into (front matter dict, body)."""
    return parse_md(Path(path).read_text(encoding="utf-8"))


def parse_md(text):
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
.fig {{ margin:2mm 0; break-inside:avoid; }}
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


def parse_numbers(spec):
    """'4,6-8' -> {4, 6, 7, 8}."""
    numbers = set()
    for part in spec.split(","):
        first, _, last = part.strip().partition("-")
        numbers.update(range(int(first), int(last or first) + 1))
    return numbers


def renumber_refs(text, mapping, where, first_line=1):
    """Replace section numbers after «Раздел…» by mapping {old: new}; stop on a number outside it."""
    def fix(m):
        line = first_line + text.count("\n", 0, m.start())

        def check(old):
            if old not in mapping:
                sys.exit(f"{where}:{line}: «{m.group(0)}» points to section {old}, which is not in this kit "
                         f"(sections of the kit: {sorted(mapping)})")
            return str(mapping[old])

        def item(n):
            first, last = n.group(0), None
            ends = re.split(r"(\s*[–-]\s*)", first)
            if len(ends) == 3:  # a range: every section inside must be in the kit
                for old in range(int(ends[0]), int(ends[2]) + 1):
                    check(old)
            return "".join(check(int(e)) if e.isdigit() else e for e in ends)

        return m.group(1) + re.sub(REF_NUM, item, m.group(2))

    return REF_RE.sub(fix, text)


def notes_sections(root, entry, exam):
    """A theory_block entry -> (notes title, Markdown of the picked sections renumbered from 1, {old: new})."""
    path, _, spec = entry.partition("#")
    meta, body = read_md(root / path)
    text = (root / path).read_text(encoding="utf-8")
    body_line = text.count("\n", 0, text.index(body)) + 1
    starts = [m.start() for m in SECTION_RE.finditer(body)]
    chunks = [(a, body[a:b]) for a, b in zip(starts, starts[1:] + [len(body)])]
    sections = {int(SECTION_RE.match(c).group(1)): (a, c) for a, c in chunks}
    wanted = parse_numbers(spec) if spec else set(sections)
    if wanted - set(sections):
        sys.exit(f"{entry}: no sections {sorted(wanted - set(sections))}")
    kept = []
    for n in sorted(wanted):
        offset, chunk = sections[n]
        marker = EXAMS_RE.search(chunk)
        if marker and EXAM_NAMES[exam] not in marker.group(1):
            continue
        kept.append((n, offset, chunk))
    mapping = {n: i for i, (n, _, _) in enumerate(kept, 1)}
    picked = []
    for n, offset, chunk in kept:
        first_line = body_line + body.count("\n", 0, offset)
        chunk = SECTION_RE.sub(lambda m: f"## {mapping[n]}.", chunk, count=1)
        picked.append(renumber_refs(chunk, mapping, path, first_line))
    return meta["title"], "\n\n".join(picked), mapping


def renumber_kit_text(text, mappings, where, skip=None):
    """Renumber «Раздел N» in the kit's own text (or its entry check).

    One part: its mapping. Several parts: a numeric reference is ambiguous, so it is an error,
    but only when renumbering changes some number; otherwise the text stays as it is.
    """
    if all(all(old == new for old, new in m.items()) for m in mappings) and len(mappings) > 1:
        return text
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if skip and skip(line):
            continue
        if len(mappings) > 1:
            found = REF_RE.search(line)
            if found:
                sys.exit(f"{where}:{i + 1}: «{found.group(0)}» is ambiguous in a kit with several parts "
                         "whose numbers change; write the section name instead of the number")
        else:
            lines[i] = renumber_refs(line, mappings[0], where, first_line=i + 1)
    return "\n".join(lines)


def kit_label(root, kit):
    """'Тема 2.1' and the build folder 'oge/02-basic-concepts-1' from the kit id and course map."""
    exam_dir, name = kit["id"].split("/")
    topic = topic_number(root, kit["main_topic"])
    kit_n = name.rsplit("-", 1)[1]
    return f"Тема {topic}.{kit_n}", Path(exam_dir) / f"{int(topic):02d}-{name}"


def build_kit(root, kit_path):
    kit_text = Path(kit_path).read_text(encoding="utf-8")
    kit, _ = parse_md(kit_text)
    parts = [notes_sections(root, entry, kit["exam"]) for entry in kit["theory_block"]]
    mappings = [mapping for _, _, mapping in parts]
    where = str(Path(kit_path).relative_to(root)) if Path(kit_path).is_relative_to(root) else str(kit_path)
    kit, plan = parse_md(renumber_kit_text(kit_text, mappings, where))
    lesson = [(item, load_exercise(root, item["id"])) for item in kit["lesson"]]
    homework = [load_exercise(root, ex_id) for ex_id in kit["homework"]["exercises"]]
    title = f'Тема {topic_number(root, kit["main_topic"])}. {kit["title"]}'
    head = (f'<div class="label">{{label}}</div><h1>{html.escape(title)}</h1>'
            f'<div class="sub">{html.escape(kit.get("subtitle", ""))}</div>')

    notes = []
    for i, (notes_title, body, _) in enumerate(parts, 1):
        notes.append(f'<div class="part">Часть {i}. {html.escape(notes_title)}</div>')
        notes_path = root / kit["theory_block"][i - 1].partition("#")[0]
        notes.append(md(body, base=notes_path.parent))

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

    label, folder = kit_label(root, kit)
    out = root / "build" / folder
    pages = [(page(kit["title"], student), out / f"{label} — занятие.pdf"),
             (page(kit["title"] + " — решения", answers), out / f"{label} — решения.pdf"),
             (page(kit["title"] + " — преподавателю", teacher), out / f"{label} — преподавателю.pdf")]
    if kit.get("entry_check"):
        check, _ = build_test(root / kit["entry_check"], "Входная проверка", mappings)[0]
        pages.append((check, out / f"{label} — входная проверка.pdf"))
    return pages


def build_test(test_path, label="Тест", mappings=None):
    """`mappings` are the section maps of the kit this test is attached to; its numbers follow the kit's PDF."""
    text = Path(test_path).read_text(encoding="utf-8")
    if mappings:
        text = renumber_kit_text(text, mappings, str(test_path), skip=lambda line: line.startswith("note:"))
    test, _ = parse_md(text)
    qs = test["questions"]
    slides = [f'<section class="slide"><div class="label">{label} · Химия</div><h1>{html.escape(test["title"])}</h1>'
              f'<div class="q" style="font-size:16pt;font-weight:400">{html.escape(test["subtitle"])}</div>'
              '<div class="q" style="font-size:16pt;font-weight:400">В каждом вопросе один верный ответ. Записывай номер вопроса и номер ответа.</div></section>']
    for n, q in enumerate(qs, 1):
        opts = "".join(f"<div><b>{k}</b>{md(o, inline=True)}</div>" for k, o in enumerate(q["options"], 1))
        slides.append(f'<section class="slide"><div class="label">Вопрос {n} из {len(qs)}</div>'
                      f'<div class="q">{md(q["q"], inline=True)}</div><div class="opts">{opts}</div></section>')
    with_checks = any(q.get("checks") for q in qs)  # «Что проверяет» is for the teacher; shown only if given
    key = "".join(f"<tr><td>{n}</td><td><b>{q['answer']}</b></td>"
                  + (f"<td>{html.escape(q.get('checks', ''))}</td>" if with_checks else "") + "</tr>"
                  for n, q in enumerate(qs, 1))
    scale = "".join(f"<tr><td><b>{s['range']}</b></td><td>{html.escape(s['meaning'])}</td></tr>"
                    for s in test.get("scale", []))
    scale_table = f'<table><tr><th>Баллы</th><th>Что это значит</th></tr>{scale}</table>' if scale else ""
    slides.append('<section class="slide"><h1>Ответы</h1>'
                  f'<div style="display:flex;gap:10mm"><table><tr><th>№</th><th>Ответ</th>{"<th>Что проверяет</th>" if with_checks else ""}</tr>{key}</table>'
                  f'{scale_table}</div></section>')
    for n, q in enumerate(qs, 1):
        if q.get("explain"):
            items = "".join(f'<li style="margin:2mm 0">{md(e, inline=True)}</li>' for e in q["explain"])
            slides.append(f'<section class="slide"><div class="label">Разбор вопроса {n}</div>'
                          f'<div class="q" style="font-size:18pt;margin:2mm 0 4mm">{md(q["q"], inline=True)}</div>'
                          f'<ul style="font-size:13.5pt;line-height:1.45;padding-left:6mm;margin:0">{items}</ul></section>')
    return [(page(test["title"], "\n".join(slides), slides=True), f'{test["title"]}.pdf')]


def print_pdf(html_text, pdf, tmp):
    """Print one HTML page to PDF via a temporary file; only the PDF is kept."""
    html_path = Path(tmp) / "page.html"
    html_path.write_text(html_text, encoding="utf-8")
    pdf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--virtual-time-budget=20000", f"--print-to-pdf={pdf}", html_path.as_uri()],
                   check=True, capture_output=True)
    return pdf


def main():
    root, src = Path(sys.argv[1]), Path(sys.argv[2])
    if src.parts[0] == "tests":
        pages = [(text, root / "build" / "tests" / name) for text, name in build_test(root / src)]
    else:
        pages = build_kit(root, root / src)
    with tempfile.TemporaryDirectory() as tmp:
        for text, pdf in pages:
            print(print_pdf(text, pdf, tmp))


if __name__ == "__main__":
    main()
