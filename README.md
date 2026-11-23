# Datheon Python Programming Internship

Python projects completed as part of the **Datheon Python Programming Internship**.

## Projects

| # | Task | Folder |
|---|------|--------|
| 1 | Hangman Word Guessing Game | [`task1_hangman/`](task1_hangman) |
| 3 | Automated File Organizer & Cleanup Utility | [`task3_organizer/`](task3_organizer) |

---

## Task 1: Hangman Word Guessing Game

A console-based Hangman game where the player guesses a hidden word one letter at a time.

### Features
- Random word selection
- Six incorrect attempts allowed
- ASCII hangman drawing that updates after each wrong guess
- Tracks guessed letters
- Duplicate guesses don't use up an attempt
- Input validation
- Win and game-over messages

### Run
```bash
cd task1_hangman
python hangman.py
```

### Screenshot
![Hangman](screenshots/hangman.png)

---

## Task 3: Automated File Organizer & Cleanup Utility

A utility that organizes files in a folder by file type.

### Features
- Sorts files into category folders (Images, Documents, Videos, etc.)
- Moves files automatically
- Handles duplicate file names safely
- Skips folders and already-organized files

### Run
```bash
cd task3_organizer
python organizer.py
```

### Screenshot
![File Organizer](screenshots/organizer.png)

---

## Repository Structure

```
Datheon_Python_Internship/
├── .vscode/
├── screenshots/
├── task1_hangman/
├── task3_organizer/
└── README.md
```

## Requirements

- Python 3.8 or higher
- Only the Python standard library is used (no extra installs needed)

## Getting Started

```bash
git clone https://github.com/dharshid16/Datheon_Python_Internship.git
cd Datheon_Python_Internship
```

## Skills Practiced

- Loops, functions and conditionals
- String handling and input validation
- File handling with `os`, `shutil` and `pathlib`
- Building command-line applications

## Author

**Dharshi D**
GitHub: [@dharshid16](https://github.com/dharshid16)