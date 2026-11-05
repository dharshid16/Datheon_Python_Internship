"""Unit tests for organizer.py - run with:  python -m unittest -v"""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import organizer


def make_files(folder: Path, names, content="x"):
    for name in names:
        (folder / name).write_text(content, encoding="utf-8")


class TestHelpers(unittest.TestCase):
    def test_known_extensions(self):
        self.assertEqual(organizer.get_category("a.pdf"), "Documents")
        self.assertEqual(organizer.get_category("a.JPG"), "Images")
        self.assertEqual(organizer.get_category("a.mp4"), "Videos")
        self.assertEqual(organizer.get_category("a.zip"), "Archives")
        self.assertEqual(organizer.get_category("a.py"), "Code")

    def test_unknown_and_no_extension(self):
        self.assertEqual(organizer.get_category("a.xyz"), "Others")
        self.assertEqual(organizer.get_category("README"), "Others")

    def test_human_size(self):
        self.assertEqual(organizer.human_size(500), "500 B")
        self.assertEqual(organizer.human_size(1536), "1.5 KB")
        self.assertEqual(organizer.human_size(5 * 1024 * 1024), "5.0 MB")

    def test_free_name_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(organizer.unique_destination(Path(tmp), "a.pdf"), Path(tmp) / "a.pdf")

    def test_collision_gets_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make_files(folder, ["a.pdf", "a_1.pdf"])
            self.assertEqual(organizer.unique_destination(folder, "a.pdf"), folder / "a_2.pdf")


class TestOrganize(unittest.TestCase):
    def test_files_are_moved_to_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["cv.pdf", "pic.png", "clip.mp4", "data.zip", "app.py", "notes.xyz"])
            summary = organizer.organize(root)
            self.assertEqual(sum(summary["moved"].values()), 6)
            self.assertEqual(len(summary["moves"]), 6)
            self.assertTrue((root / "Documents" / "cv.pdf").exists())
            self.assertTrue((root / "Images" / "pic.png").exists())
            self.assertTrue((root / "Videos" / "clip.mp4").exists())
            self.assertTrue((root / "Archives" / "data.zip").exists())
            self.assertTrue((root / "Code" / "app.py").exists())
            self.assertTrue((root / "Others" / "notes.xyz").exists())

    def test_sizes_are_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["a.pdf", "b.pdf"], content="12345")
            summary = organizer.organize(root)
            self.assertEqual(summary["sizes"]["Documents"], 10)

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["cv.pdf", "pic.png"])
            summary = organizer.organize(root, dry_run=True)
            self.assertEqual(sum(summary["moved"].values()), 2)
            self.assertEqual(summary["moves"], [])
            self.assertTrue((root / "cv.pdf").exists())
            self.assertFalse((root / "Documents").exists())

    def test_collision_keeps_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Documents").mkdir()
            (root / "Documents" / "cv.pdf").write_text("old")
            (root / "cv.pdf").write_text("new")
            organizer.organize(root)
            self.assertEqual((root / "Documents" / "cv.pdf").read_text(), "old")
            self.assertEqual((root / "Documents" / "cv_1.pdf").read_text(), "new")

    def test_subfolders_hidden_and_partial_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "MyFolder").mkdir()
            make_files(root, [".hidden.txt", "movie.crdownload", "ok.txt"])
            summary = organizer.organize(root)
            self.assertEqual(sum(summary["moved"].values()), 1)
            self.assertEqual(summary["skipped"], 2)
            self.assertTrue((root / "MyFolder").is_dir())
            self.assertTrue((root / ".hidden.txt").exists())

    def test_running_twice_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["a.pdf"])
            organizer.organize(root)
            second = organizer.organize(root)
            self.assertEqual(sum(second["moved"].values()), 0)
            self.assertTrue((root / "Documents" / "a.pdf").exists())

    def test_by_date_creates_month_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["a.pdf"])
            stamp = datetime(2025, 3, 15).timestamp()
            os.utime(root / "a.pdf", (stamp, stamp))
            organizer.organize(root, by_date=True)
            self.assertTrue((root / "Documents" / "2025-03" / "a.pdf").exists())


class TestUndo(unittest.TestCase):
    def run_and_save(self, root, **kwargs):
        summary = organizer.organize(root, **kwargs)
        organizer.save_history(root, [{"time": "t", "moves": summary["moves"]}])
        return summary

    def test_undo_restores_files_and_removes_empty_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["cv.pdf", "pic.png"])
            self.run_and_save(root)
            result = organizer.undo_last_run(root)
            self.assertEqual(result["restored"], 2)
            self.assertTrue((root / "cv.pdf").exists())
            self.assertTrue((root / "pic.png").exists())
            self.assertFalse((root / "Documents").exists())
            self.assertFalse((root / organizer.HISTORY_FILE).exists())

    def test_undo_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["cv.pdf"])
            self.run_and_save(root)
            organizer.undo_last_run(root, dry_run=True)
            self.assertTrue((root / "Documents" / "cv.pdf").exists())

    def test_undo_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["cv.pdf"])
            self.run_and_save(root)
            (root / "Documents" / "cv.pdf").unlink()
            self.assertEqual(organizer.undo_last_run(root)["missing"], 1)

    def test_undo_with_no_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = organizer.undo_last_run(Path(tmp))
            self.assertEqual(result["restored"], 0)

    def test_undo_does_not_overwrite_new_file_with_same_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["cv.pdf"], content="original")
            self.run_and_save(root)
            (root / "cv.pdf").write_text("brand new")
            organizer.undo_last_run(root)
            self.assertEqual((root / "cv.pdf").read_text(), "brand new")
            self.assertEqual((root / "cv_1.pdf").read_text(), "original")


class TestMain(unittest.TestCase):
    def test_invalid_folder_returns_error(self):
        self.assertEqual(organizer.main(["definitely_not_a_folder_123"]), 1)

    def test_end_to_end_organise_then_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_files(root, ["a.pdf", "b.jpg"])
            self.assertEqual(organizer.main([str(root)]), 0)
            self.assertTrue((root / "Documents" / "a.pdf").exists())
            self.assertEqual(organizer.main([str(root), "--undo"]), 0)
            self.assertTrue((root / "a.pdf").exists())
            self.assertTrue((root / "b.jpg").exists())


if __name__ == "__main__":
    unittest.main()