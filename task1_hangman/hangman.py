"""
Hangman - a terminal word-guessing game.

Guess the hidden word letter by letter before the stickman loses all his parts.

Features
--------
* ASCII gallows art that updates with every mistake (6 wrong guesses allowed)
* Repeated guesses are detected and never cost a life
* Three difficulty levels based on word length
* One hint per round (reveals a letter, costs a life)
* Whole-word guesses (a wrong one costs a life)
* Loads words from words.txt if present, otherwise uses a built-in list
* Score, win streak and best streak across rounds
* Optional colour output (disabled automatically when not supported)

Run:  python hangman.py
"""

import os
import random
import string
import sys
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
MAX_WRONG = 6
WORDS_FILE = Path(__file__).with_name("words.txt")

# key -> (label, min word length, max word length)
DIFFICULTIES = {
    "1": ("Easy", 4, 5),
    "2": ("Medium", 6, 7),
    "3": ("Hard", 8, 12),
}

# Built-in fallback words (used when words.txt is missing or unusable).
FALLBACK_WORDS = [
    # 4-5 letters
    "moon", "wolf", "fire", "sand", "bear", "gold", "wind", "rain",
    "bloom", "flame", "storm", "crown", "feast", "grove", "haven", "jewel",
    "magic", "noble", "quest", "reign", "sworn", "tower", "unity", "valor",
    "wrath", "arena", "blaze", "charm", "drift", "ember", "frost", "gleam",
    "haste", "ivory", "karma", "lunar", "nexus", "omega", "prism", "realm",
    "surge", "titan",
    # 6-7 letters
    "python", "garden", "school", "bridge", "castle", "planet", "rocket",
    "forest", "market", "silver", "orange", "purple", "dragon", "knight",
    "shield", "candle", "breeze", "temple", "pirate", "anchor", "hammer",
    "velvet", "falcon", "jungle", "palace", "throne", "zombie", "frozen",
    "guitar", "violin", "tunnel", "meadow", "harbor", "sphinx", "quartz",
    "galaxy", "empire", "voyage", "legend", "shadow", "riddle", "cipher",
    "mystic", "network", "journey", "library", "thunder", "compass",
    # 8+ letters
    "mountain", "universe", "elephant", "treasure", "champion", "keyboard",
    "waterfall", "telescope", "nightmare", "adventure", "chemistry",
    "labyrinth", "dinosaur", "football", "computer", "sunshine",
]

# ──────────────────────────────────────────────
# ASCII Hangman stages (0 mistakes -> 6 mistakes)
# Man starts complete; on each failed attempt, he loses a part.
# ──────────────────────────────────────────────
HANGMAN_STAGES = [
    # Stage 0 - no mistakes (complete man)
    r"""
      ┌───────┐
      │       │
      │       O
      │      /│\
      │      / \
      │
    ──┴──
    """,
    # Stage 1 - loses right leg
    r"""
      ┌───────┐
      │       │
      │       O
      │      /│\
      │      /
      │
    ──┴──
    """,
    # Stage 2 - loses left leg
    r"""
      ┌───────┐
      │       │
      │       O
      │      /│\
      │
      │
    ──┴──
    """,
    # Stage 3 - loses right arm
    r"""
      ┌───────┐
      │       │
      │       O
      │      /│
      │
      │
    ──┴──
    """,
    # Stage 4 - loses left arm
    r"""
      ┌───────┐
      │       │
      │       O
      │       │
      │
      │
    ──┴──
    """,
    # Stage 5 - loses torso
    r"""
      ┌───────┐
      │       │
      │       O
      │
      │
      │
    ──┴──
    """,
    # Stage 6 - loses head (game over, nothing left)
    r"""
      ┌───────┐
      │       │
      │
      │
      │
      │
    ──┴──
    """,
]

# ──────────────────────────────────────────────
# Colour helpers (ANSI) - disabled when unsupported
# ──────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
if USE_COLOR and os.name == "nt":
    os.system("")  # enables ANSI escape handling on Windows terminals

GREEN, RED, YELLOW, CYAN, BOLD = "32", "31", "33", "36", "1"


def paint(text: str, code: str) -> str:
    """Wrap text in an ANSI colour code if colour output is enabled."""
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


# ──────────────────────────────────────────────
# Game logic (pure functions - easy to test)
# ──────────────────────────────────────────────
def load_words(path: Path = WORDS_FILE, min_len: int = 4, max_len: int = 12) -> list:
    """Load words from a text file, falling back to the built-in list.

    Only alphabetic words whose length is between min_len and max_len are kept.
    """
    try:
        with open(path, encoding="utf-8") as f:
            words = [line.strip().lower() for line in f]
        words = [w for w in words if w.isascii() and w.isalpha()
                 and min_len <= len(w) <= max_len]
        if words:
            return words
    except OSError:
        pass
    return list(FALLBACK_WORDS)


def choose_word(words: list, min_len: int, max_len: int) -> str:
    """Pick a random word within the given length range."""
    pool = [w for w in words if min_len <= len(w) <= max_len]
    return random.choice(pool or words).lower()


def display_word(word: str, guessed: set) -> str:
    """Return the word with unguessed letters shown as underscores."""
    return " ".join(ch.upper() if ch in guessed else "_" for ch in word)


def is_won(word: str, guessed: set) -> bool:
    """True when every letter of the word has been guessed."""
    return all(ch in guessed for ch in word)


def wrong_letters(word: str, guessed: set) -> list:
    """Sorted list of guessed letters that are not in the word."""
    return sorted(guessed - set(word))


def reveal_hint(word: str, guessed: set) -> Optional[str]:
    """Return a random letter of the word that has not been guessed yet."""
    remaining = sorted(set(word) - guessed)
    return random.choice(remaining) if remaining else None


def parse_guess(raw: str, guessed: set) -> tuple:
    """Interpret the player's input.

    Returns (action, value) where action is one of:
      "letter" - a new single letter,
      "word"   - a whole-word guess,
      "hint"   - the player asked for a hint,
      "error"  - invalid or repeated input (value is the message to show).
    """
    guess = raw.strip().lower()
    if guess == "?":
        return "hint", ""
    if not guess or not all(ch in string.ascii_lowercase for ch in guess):
        return "error", "Please enter letters only (a-z), or ? for a hint."
    if len(guess) == 1:
        if guess in guessed:
            return "error", f"You already guessed '{guess.upper()}'. No penalty!"
        return "letter", guess
    return "word", guess


# ──────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────
def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


def lives_bar(wrong: int) -> str:
    """Hearts showing remaining lives, e.g. ♥ ♥ ♥ ♡ ♡ ♡."""
    left = MAX_WRONG - wrong
    return paint("♥ " * left, RED) + "♡ " * wrong


def display_state(word: str, guessed: set, wrong: int, message: str = "") -> None:
    """Draw the full game screen."""
    clear_screen()
    print("=" * 40)
    print(paint("        H A N G M A N", BOLD))
    print("=" * 40)
    print(HANGMAN_STAGES[wrong])
    print(f"  Word   :  {paint(display_word(word, guessed), CYAN)}")
    print(f"  Lives  :  {lives_bar(wrong)}")

    letters = wrong_letters(word, guessed)
    print(f"  Wrong  :  {paint(', '.join(l.upper() for l in letters), RED) if letters else '-'}")
    right = sorted(guessed & set(word))
    print(f"  Correct:  {paint(', '.join(l.upper() for l in right), GREEN) if right else '-'}")
    print("-" * 40)
    if message:
        print(f"  {message}\n")


def show_result(word: str, won: bool) -> None:
    """Print the victory or defeat screen."""
    print("=" * 40)
    if won:
        print(paint(f"  🎉 YOU WIN!  The word was {word.upper()}", GREEN))
    else:
        print(paint(f"  ☠  GAME OVER!  The word was {word.upper()}", RED))
    print("=" * 40)


# ──────────────────────────────────────────────
# Game flow
# ──────────────────────────────────────────────
def play(word: str) -> bool:
    """Run one round. Returns True if the player wins."""
    guessed: set = set()
    wrong = 0
    hint_used = False
    message = ""

    while wrong < MAX_WRONG:
        display_state(word, guessed, wrong, message)
        if is_won(word, guessed):
            show_result(word, True)
            return True

        raw = input("  Guess a letter, the whole word, or ? for a hint: ")
        action, value = parse_guess(raw, guessed)
        message = ""

        if action == "error":
            message = paint(f"⚠  {value}", YELLOW)

        elif action == "letter":
            guessed.add(value)
            if value in word:
                message = paint(f"✔ Nice! '{value.upper()}' is in the word.", GREEN)
            else:
                wrong += 1
                message = paint(f"✘ '{value.upper()}' is not in the word.", RED)

        elif action == "word":
            if value == word:
                guessed.update(word)
            else:
                wrong += 1
                message = paint(f"✘ '{value.upper()}' is not the word.", RED)

        elif action == "hint":
            if hint_used:
                message = paint("⚠  You already used your hint this round.", YELLOW)
            elif wrong >= MAX_WRONG - 1:
                message = paint("⚠  Not enough lives left for a hint.", YELLOW)
            else:
                letter = reveal_hint(word, guessed)
                if letter:
                    guessed.add(letter)
                    wrong += 1
                    hint_used = True
                    message = paint(f"💡 Hint: '{letter.upper()}' is in the word (-1 life).", CYAN)

    display_state(word, guessed, wrong, message)
    show_result(word, False)
    return False


def choose_difficulty() -> tuple:
    """Ask the player for a difficulty. Returns (label, min_len, max_len)."""
    print("\n  Choose difficulty:")
    for key, (label, low, high) in DIFFICULTIES.items():
        print(f"    {key}) {label:<7} ({low}-{high} letters)")
    while True:
        choice = input("\n  Your choice (1/2/3): ").strip()
        if choice in DIFFICULTIES:
            return DIFFICULTIES[choice]
        print("  Please enter 1, 2 or 3.")


def main() -> None:
    """Welcome screen, difficulty selection and replay loop."""
    clear_screen()
    print("=" * 40)
    print(paint("   Welcome to HANGMAN!", BOLD))
    print("   Guess the word before the")
    print("   stickman loses all his parts.")
    print(f"   You have {MAX_WRONG} wrong guesses allowed.")
    print("   Tip: type ? for a hint (-1 life).")
    print("=" * 40)

    label, low, high = choose_difficulty()
    words = load_words(min_len=4, max_len=12)

    wins = games = streak = best_streak = 0
    while True:
        games += 1
        if play(choose_word(words, low, high)):
            wins += 1
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

        print(f"\n  Difficulty: {label}  |  Score: {wins}/{games}  |  "
              f"Streak: {streak}  |  Best streak: {best_streak}")
        again = input("\n  Play again? (y/n): ").strip().lower()
        if again not in ("y", "yes"):
            print(f"\n  Final score: {wins} win(s) out of {games} game(s).")
            print("  Thanks for playing! Goodbye. 👋\n")
            break


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\n  Game interrupted. Goodbye! 👋\n")