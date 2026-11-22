# Contributing to Phone Trackpad

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting a bug or suggesting a feature

Open an [issue](https://github.com/mttfntn/phone-trackpad/issues/new/choose) and pick a form:

- **Bug report:** say which Phone Trackpad version (shown when the helper starts), which system
  and Python version, which phone and browser, and the steps to reproduce. Paste what the
  helper's window printed.
- **Feature request:** describe what you're trying to do, not only the solution you have in mind.

First, check whether someone has already opened an issue for the same thing, and read the
README's [known limits](https://github.com/mttfntn/phone-trackpad#known-limits).
Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Changing the code

[HANDOVER.md](HANDOVER.md) explains how the project is organised and the pitfalls already found.
Read it before a larger change.

1. **Fork** the repository and create a branch for your change.
2. You need Python 3.10 or newer, the requirements (`pip install -r desktop/requirements.txt`, or
   run a launcher once) and, for the phone page tests, Node.js 18 or newer.
3. Run the tests from the repo root. They never touch your real mouse, keyboard or settings:

   ```
   python tests/run_tests.py
   ```

   Expected result: `166 checks (...), 0 failed` (or more checks).
4. **If you fix a bug,** add a check that fails without your fix.
5. **If you change behaviour on purpose,** compare with the previous version (HANDOVER.md, "How
   to run the tests") and explain every difference in the pull request.
6. **Try it with a real phone** if you change `web/app.js` or `input_backend.py`.
7. **Open a pull request.** The template has a short checklist. CI runs the tests on Windows and
   macOS with Python 3.10 to 3.14, and checks the release zip with the real launchers.

### Style

- The phone page stays plain HTML, CSS and JavaScript, with no build step and no libraries.
- The helper only talks to the local network.
- Comments must say what the code does; check them when you change the code.
- Keep commits small, with messages that explain what changed and how you checked it.

## License

Phone Trackpad is GPL-3.0-or-later. By contributing, you agree that your contribution is released
under the same license.
