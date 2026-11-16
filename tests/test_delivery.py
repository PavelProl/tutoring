"""V2 rendering and PDF publication contract; no original lesson content is modified."""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_kit
import deliver_kit


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.root = self.workspace / "content"
        self.root.mkdir()
        (self.root / "course-map.md").write_text('| 1 | `earlier` | x |\n| 5 | `reactions` | x |\n')
        (self.root / "notes").mkdir()
        (self.root / "notes/a.md").write_text('---\ntitle: Notes\n---\n## 4. Core\nTheory\n## 5. Advanced\n<!-- exams: ЕГЭ -->\nAdvanced text\n')
        (self.root / "exercises/src").mkdir(parents=True)
        for n in range(1, 20):
            self.exercise(n)
        self.kit = {
            "format_version": 2, "id": "school/reactions-1", "title": "Химические реакции",
            "main_topic": "reactions", "theory_block": ["notes/a.md#4-5"],
            "lesson": [{"id": "src/p1", "role": "worked_example"}, "src/p2"],
            "homework": {"reading": "Раздел 4.", "exercises": ["src/p3"]},
            "practice": ["src/p4", "src/p5"],
        }

    def exercise(self, n, *, topic="reactions", solution=True, answer=True):
        meta = {"answer": f"ANSWER{n}" if answer else "", "main_topic": topic}
        text = "---\n" + yaml.safe_dump(meta) + f"---\nCONDITION{n}\n"
        if solution:
            text += f"## Решение\nSOLUTION{n}. Ответ: ANSWER{n}.\n"
        (self.root / f"exercises/src/p{n}.md").write_text(text)

    def source(self):
        path = self.root / "kits" / self.kit["id"] / "kit.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n" + yaml.safe_dump(self.kit, allow_unicode=True) + "---\n")
        return path.relative_to(self.root)

    def pages(self, **kwargs):
        return build_kit.build_kit(self.root, self.root / self.source(), **kwargs)

    @staticmethod
    def fake_print(text, pdf, temporary):
        pdf.write_bytes(b"%PDF-1.4\n" + hashlib.sha256(text.encode()).hexdigest().encode())
        return pdf

    def stage(self):
        with patch.object(deliver_kit, "print_pdf", side_effect=self.fake_print):
            return deliver_kit.stage(self.root, self.source(), self.workspace)

    def test_school_pair_has_practice_answers_and_all_solutions(self):
        pages = self.pages()
        self.assertEqual([p.name for _, p in pages], list(deliver_kit.NAMES))
        student, solutions = (text for text, _ in pages)
        self.assertIn('<h2>Задания</h2>', student)
        self.assertIn('font-size:13pt', student)
        self.assertIn('Раздел 1.', student)
        self.assertNotIn('Advanced text', student)
        self.assertNotIn('ОГЭ', student)
        self.assertNotIn('Для преподавателя', student)
        self.assertIn('SOLUTION1', student)
        self.assertNotIn('SOLUTION2', student)
        practice = student[student.index('<h2>Дополнительная практика</h2>'):]
        self.assertLess(practice.index('CONDITION5'), practice.index('Краткие Ответы'))
        for n in [4, 5]:
            self.assertIn(f'ANSWER{n}', practice)
            self.assertNotIn(f'SOLUTION{n}', practice)
        for n in range(1, 6):
            self.assertIn(f'CONDITION{n}', solutions)
            self.assertIn(f'SOLUTION{n}', solutions)

    def test_practice_size_is_not_fixed(self):
        for count in [1, 16]:
            self.kit['practice'] = [f'src/p{n}' for n in range(4, 4 + count)]
            self.assertEqual(len(self.pages()), 2)

    def test_missing_answers_solutions_and_duplicate_practice_fail(self):
        self.exercise(4, solution=False)
        with self.assertRaisesRegex(ValueError, 'detailed solution'):
            self.pages()
        self.exercise(4, answer=False)
        with self.assertRaises(ValueError):
            self.pages()
        self.exercise(4)
        self.kit['practice'] = ['src/p4', 'src/p4']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.pages()

    def test_new_format_rejects_legacy_hidden_outputs_and_unsafe_paths(self):
        for key in ['entry_check', 'spare']:
            self.kit[key] = 'anything'
            with self.assertRaises(ValueError):
                self.pages()
            del self.kit[key]
        self.kit['id'] = 'school/../../outside'
        with self.assertRaises(ValueError):
            build_kit.modern_identity(self.kit)

    def test_review_is_explicit_and_respects_selected_topics(self):
        self.kit = {"format_version": 2, "kind": "review", "id": "school/review-1", "title": "Повторение",
                    "review_topics": ["earlier"], "exercises": ["src/p1"]}
        with self.assertRaisesRegex(ValueError, 'explicit request'):
            self.pages()
        with self.assertRaisesRegex(ValueError, 'selected review_topics'):
            self.pages(review_requested=True)
        self.exercise(1, topic='earlier')
        pages = self.pages(review_requested=True)
        self.assertIn('Краткие Ответы', pages[0][0])
        self.assertIn('SOLUTION1', pages[1][0])
        self.assertIn('Повторение', str(pages[0][1]))

    def test_stage_accept_and_replacement_preserve_ready_until_approval(self):
        draft, revision = self.stage()
        self.assertEqual({p.name for p in draft.iterdir()}, set(deliver_kit.NAMES))
        ready = self.workspace / 'Занятия/Готово/school/reactions-1'
        self.assertFalse(ready.exists())
        with self.assertRaisesRegex(ValueError, 'author approval'):
            deliver_kit.accept(self.root, self.source(), self.workspace, revision=revision)
        deliver_kit.accept(self.root, self.source(), self.workspace, revision=revision, author_approved=True)
        self.assertFalse(draft.exists())
        self.assertEqual(deliver_kit.pair_revision(ready), revision)
        self.kit['title'] = 'Обновлённые реакции'
        draft, new_revision = self.stage()
        self.assertNotEqual(new_revision, revision)
        self.assertEqual(deliver_kit.pair_revision(ready), revision)
        with self.assertRaisesRegex(ValueError, 'reviewed revision'):
            deliver_kit.accept(self.root, self.source(), self.workspace, revision=revision, author_approved=True)
        self.assertEqual(deliver_kit.pair_revision(ready), revision)
        deliver_kit.accept(self.root, self.source(), self.workspace, revision=new_revision, author_approved=True)
        self.assertEqual(deliver_kit.pair_revision(ready), new_revision)
        self.assertFalse(draft.exists())

    def test_failed_render_keeps_previous_draft(self):
        draft, revision = self.stage()
        def fail(text, pdf, temporary):
            raise RuntimeError('printer failed')
        with patch.object(deliver_kit, 'print_pdf', side_effect=fail):
            with self.assertRaises(RuntimeError):
                deliver_kit.stage(self.root, self.source(), self.workspace)
        self.assertEqual(deliver_kit.pair_revision(draft), revision)

    def test_failed_swap_restores_previous_ready(self):
        draft, revision = self.stage()
        ready = self.workspace / 'ready'
        deliver_kit.replace_pair(draft, ready)
        (draft / 'Занятие.pdf').write_bytes(b'%PDF-1.4\nchanged pair content')
        rename = Path.rename
        def fail_new(path, target):
            if path.name == 'new':
                raise OSError('swap failed')
            return rename(path, target)
        with patch.object(Path, 'rename', fail_new):
            with self.assertRaises(OSError):
                deliver_kit.replace_pair(draft, ready)
        self.assertEqual(deliver_kit.pair_revision(ready), revision)

    def test_extra_files_and_invalid_pdf_cannot_be_published(self):
        draft, revision = self.stage()
        (draft / 'teacher.pdf').write_bytes(b'%PDF-extra')
        with self.assertRaises(ValueError):
            deliver_kit.pair_revision(draft)
        (draft / 'teacher.pdf').unlink()
        (draft / 'Решения.pdf').write_text('not a PDF')
        with self.assertRaises(ValueError):
            deliver_kit.pair_revision(draft)

    def test_v1_dispatch_preserves_legacy_outputs(self):
        del self.kit['format_version']
        self.kit.update(id='oge/reactions-1', exam='OGE', lesson=[{'id': 'src/p1'}, {'id': 'src/p2'}])
        old = self.pages()
        self.assertEqual(len(old), 3)
        self.assertIn('преподавателю.pdf', old[-1][1].name)
        self.assertIn('Задания на занятии', old[0][0])
        self.assertIn('font-size:10.5pt', old[0][0])
        self.assertNotIn('Краткие Ответы', old[0][0])
        self.kit['format_version'] = 1
        self.assertEqual(old, self.pages())
        self.kit['format_version'] = 2
        self.assertEqual(len(self.pages()), 2)


if __name__ == '__main__':
    unittest.main()
