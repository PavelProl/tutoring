"""Section renumbering in tools/build_kit.py (#18). Run: .venv/bin/python -m unittest discover tests"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_kit  # noqa: E402


def notes(title, sections):
    """sections: {number: body}; the front matter is two lines so line numbers are easy to count."""
    return f"---\ntitle: {title}\n---\n\n" + "\n\n".join(f"## {n}. Name {n}\n\n{b}" for n, b in sections.items()) + "\n"


class Content:
    """A throwaway content root with one exercise, two notes files and a course map."""

    def __init__(self, tmp):
        self.root = Path(tmp)
        (self.root / "notes").mkdir()
        (self.root / "kits" / "oge" / "topic-a-1").mkdir(parents=True)
        (self.root / "exercises" / "src").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "course-map.md").write_text("| 2 | `topic-a` | x |\n| 1 | `topic-b` | y |\n", encoding="utf-8")
        (self.root / "exercises" / "src" / "p1.md").write_text("---\nanswer: '1'\n---\nУсловие\n", encoding="utf-8")

    def write(self, rel, text):
        path = self.root / rel
        path.write_text(text, encoding="utf-8")
        return path

    def kit(self, theory, reading="Перечитать.", plan="План.", entry_check=None, kit_id="oge/topic-a-1"):
        blocks = "".join(f"  - {t}\n" for t in theory)
        check = f"entry_check: {entry_check}\n" if entry_check else ""
        text = (f"---\nid: {kit_id}\ntitle: Kit\nexam: OGE\nmain_topic: topic-a\ntheory_block:\n{blocks}"
                f"lesson:\n  - {{id: src/p1}}\n{check}homework:\n  reading: \"{reading}\"\n  exercises: [src/p1]\n---\n\n{plan}\n")
        return self.write(f"kits/{kit_id}/kit.md", text)

    def pages(self, kit_path):
        return {path.name.split(" — ")[-1]: html for html, path in build_kit.build_kit(self.root, kit_path)}


def headings(html):
    return re.findall(r"<h2>([^<]*)</h2>", html)


class RenumberTextTest(unittest.TestCase):
    def renumber(self, text, mapping):
        return build_kit.renumber_refs(text, mapping, "f.md")

    def test_word_forms(self):
        for form in ["Раздел", "Раздела", "Разделе", "Разделу", "Разделом", "Разделы", "Разделов", "Разделах", "раздел"]:
            self.assertEqual(self.renumber(f"{form} 8", {8: 1}), f"{form} 1")

    def test_range_keeps_dash(self):
        self.assertEqual(self.renumber("Перечитать Разделы 8–9.", {8: 1, 9: 2}), "Перечитать Разделы 1–2.")
        self.assertEqual(self.renumber("Разделы 8-9", {8: 1, 9: 2}), "Разделы 1-2")

    def test_list_and_conjunction(self):
        self.assertEqual(self.renumber("Разделов 4, 6", {4: 1, 6: 2}), "Разделов 1, 2")
        self.assertEqual(self.renumber("Разделы 4 и 7", {4: 1, 7: 2}), "Разделы 1 и 2")
        self.assertEqual(self.renumber("Разделы 4, 6–7 и 9", {4: 1, 6: 2, 7: 3, 9: 4}), "Разделы 1, 2–3 и 4")

    def test_text_without_numbers_untouched(self):
        text = "В разделе «Что нужно знать» и Раздел без числа; 8 класс, 8–9 штук."
        self.assertEqual(self.renumber(text, {8: 1}), text)

    def test_reference_outside_kit_names_file_and_line(self):
        with self.assertRaises(SystemExit) as err:
            build_kit.renumber_refs("a\nb Раздел 3\n", {8: 1}, "notes/x.md", first_line=10)
        self.assertIn("notes/x.md:11", str(err.exception))
        self.assertIn("3", str(err.exception))

    def test_range_with_gap_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.renumber("Разделы 4–6", {4: 1, 6: 2})


class KitTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.c = Content(tmp.name)

    def test_one_part_starts_from_one_everywhere(self):
        self.c.write("notes/a.md", notes("Notes A", {
            1: "Intro.", 2: "Text. Формула из Раздела 8.", 8: "Eight.", 9: "Nine, see Разделы 8–9."}))
        kit = self.c.kit(["notes/a.md#8-9"], reading="Перечитать Разделы 8–9.", plan="| Раздел 8: закон | 1 |\nРаздел 9.")
        pages = self.c.pages(kit)
        student, answers, teacher = pages["занятие.pdf"], pages["решения.pdf"], pages["преподавателю.pdf"]
        self.assertEqual([h for h in headings(student) if re.match(r"\d+\.", h)], ["1. Name 8", "2. Name 9"])
        self.assertIn("Nine, see Разделы 1–2.", student)
        self.assertIn("Перечитать Разделы 1–2.", student)
        self.assertIn("Раздел 1: закон", teacher)
        self.assertIn("Раздел 2.", teacher)
        self.assertNotIn("Раздел", answers.replace("Решения", ""))

    def test_reference_to_section_outside_the_kit_is_an_error(self):
        self.c.write("notes/a.md", notes("Notes A", {8: "Eight, see Раздел 3.", 9: "Nine."}))
        with self.assertRaises(SystemExit) as err:
            self.c.pages(self.c.kit(["notes/a.md#8-9"]))
        self.assertIn("notes/a.md:7", str(err.exception))

    def test_kit_text_reference_outside_the_kit_is_an_error(self):
        self.c.write("notes/a.md", notes("Notes A", {8: "Eight.", 9: "Nine."}))
        kit = self.c.kit(["notes/a.md#8-9"], plan="Раздел 5: что-то.")
        with self.assertRaises(SystemExit) as err:
            self.c.pages(kit)
        self.assertIn("kit.md", str(err.exception))

    def test_two_parts_restart_from_one_each(self):
        self.c.write("notes/a.md", notes("Notes A", {4: "Four, see Раздел 5.", 5: "Five."}))
        self.c.write("notes/b.md", notes("Notes B", {7: "Seven.", 8: "Eight, see Раздел 7."}))
        student = self.c.pages(self.c.kit(["notes/a.md#4-5", "notes/b.md#7-8"]))["занятие.pdf"]
        self.assertEqual([h for h in headings(student) if re.match(r"\d+\.", h)],
                         ["1. Name 4", "2. Name 5", "1. Name 7", "2. Name 8"])
        self.assertIn("Four, see Раздел 2.", student)
        self.assertIn("Eight, see Раздел 1.", student)

    def test_two_parts_numeric_reference_in_kit_text_is_ambiguous_when_numbers_change(self):
        self.c.write("notes/a.md", notes("Notes A", {4: "Four.", 5: "Five."}))
        self.c.write("notes/b.md", notes("Notes B", {1: "One."}))
        kit = self.c.kit(["notes/a.md#4-5", "notes/b.md"], reading="Перечитать Раздел 4.")
        with self.assertRaises(SystemExit) as err:
            self.c.pages(kit)
        self.assertIn("kit.md", str(err.exception))
        self.assertIn("section name", str(err.exception))

    def test_two_parts_without_numeric_reference_build(self):
        self.c.write("notes/a.md", notes("Notes A", {4: "Four."}))
        self.c.write("notes/b.md", notes("Notes B", {1: "One."}))
        self.c.pages(self.c.kit(["notes/a.md#4", "notes/b.md"], reading="Перечитать Конспект.", plan="План."))

    def test_entry_check_checks_are_renumbered(self):
        self.c.write("notes/a.md", notes("Notes A", {4: "Four.", 5: "Five."}))
        self.c.write("tests/e.md", "---\ntitle: T\nsubtitle: S\nnote: \"см. Раздел 4\"\nquestions:\n"
                     "  - q: Q\n    options: [a, b]\n    answer: 1\n    checks: \"чтение ДЗ, Раздел 5\"\n---\n")
        pages = self.c.pages(self.c.kit(["notes/a.md#4-5"], entry_check="tests/e.md"))
        self.assertIn("чтение ДЗ, Раздел 2", pages["входная проверка.pdf"])

    def test_kit_one_shape_is_unchanged(self):
        """Parts 1–3 and 1–7: renumbering keeps every number, so the output is the plain notes."""
        a = notes("Notes A", {1: "One.", 2: "Two.", 3: "Three.", 4: "Four."})
        b = notes("Notes B", {n: f"Text {n}." + (" Подробнее в Разделе 4." if n == 6 else "") for n in range(1, 8)})
        self.c.write("notes/a.md", a)
        self.c.write("notes/b.md", b)
        reading = "Перечитать Конспект целиком; выучить таблицу из Раздела 6 и правило (Раздел 7)."
        kit = self.c.kit(["notes/a.md#1-3", "notes/b.md"], reading=reading, plan="| Разделы 5–6 | x |")
        student = self.c.pages(kit)["занятие.pdf"]
        part = lambda title, body: f'<div class="part">Часть {title}</div>\n' + build_kit.md(body)
        self.assertIn(part("1. Notes A", build_kit.read_md(self.c.root / "notes/a.md")[1].split("## 4.")[0].strip()), student)
        self.assertIn(part("2. Notes B", build_kit.read_md(self.c.root / "notes/b.md")[1]), student)
        self.assertIn("правило (Раздел 7)", student)
        teacher = self.c.pages(kit)["преподавателю.pdf"]
        self.assertIn("Разделы 5–6", teacher)


if __name__ == "__main__":
    unittest.main()
