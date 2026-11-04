"""Unit tests for hangman.py - run with:  python -m unittest -v"""

import tempfile
import unittest
from pathlib import Path

import hangman


class TestDisplay(unittest.TestCase):
    def test_masked_word(self):
        self.assertEqual(hangman.display_word("cat", {"c", "t"}), "C _ T")

    def test_masked_word_nothing_guessed(self):
        self.assertEqual(hangman.display_word("dog", set()), "_ _ _")

    def test_stage_count_matches_max_wrong(self):
        self.assertEqual(len(hangman.HANGMAN_STAGES), hangman.MAX_WRONG + 1)


class TestGameLogic(unittest.TestCase):
    def test_is_won(self):
        self.assertTrue(hangman.is_won("cat", {"c", "a", "t"}))
        self.assertFalse(hangman.is_won("cat", {"c", "a"}))

    def test_wrong_letters(self):
        self.assertEqual(hangman.wrong_letters("cat", {"c", "z", "b"}), ["b", "z"])

    def test_reveal_hint_returns_unguessed_letter_of_word(self):
        for _ in range(20):
            letter = hangman.reveal_hint("cat", {"c"})
            self.assertIn(letter, {"a", "t"})

    def test_reveal_hint_none_when_complete(self):
        self.assertIsNone(hangman.reveal_hint("cat", {"c", "a", "t"}))


class TestParseGuess(unittest.TestCase):
    def test_valid_letter(self):
        self.assertEqual(hangman.parse_guess(" A ", set()), ("letter", "a"))

    def test_repeated_letter_is_error_not_penalty(self):
        action, _ = hangman.parse_guess("a", {"a"})
        self.assertEqual(action, "error")

    def test_invalid_inputs(self):
        for bad in ["", "5", "a1", "!", "é"]:
            self.assertEqual(hangman.parse_guess(bad, set())[0], "error", bad)

    def test_whole_word(self):
        self.assertEqual(hangman.parse_guess("Python", set()), ("word", "python"))

    def test_hint(self):
        self.assertEqual(hangman.parse_guess("?", set())[0], "hint")


class TestWordLoading(unittest.TestCase):
    def test_missing_file_uses_fallback(self):
        words = hangman.load_words(Path("does_not_exist.txt"))
        self.assertEqual(words, hangman.FALLBACK_WORDS)

    def test_file_is_filtered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "words.txt"
            path.write_text("Apple\nit\nnot-a-word\nbanana\nx1y2z3\n", encoding="utf-8")
            self.assertEqual(hangman.load_words(path, 4, 12), ["apple", "banana"])

    def test_empty_file_uses_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "words.txt"
            path.write_text("", encoding="utf-8")
            self.assertEqual(hangman.load_words(path), hangman.FALLBACK_WORDS)

    def test_choose_word_respects_length(self):
        for _ in range(30):
            word = hangman.choose_word(hangman.FALLBACK_WORDS, 8, 12)
            self.assertTrue(8 <= len(word) <= 12)


if __name__ == "__main__":
    unittest.main()