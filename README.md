# distlift

**distlift** is a small command-line helper for people who ship software
packages. If your project lives in **Git** and you use a **version number**
(like 1.2.3) that you bump when you release, distlift can automate the boring
steps: update the version in your project files, refresh a changelog from
recent commits, create a Git commit and tag, and optionally push to your
remote or build and publish installable packages.

You run it from a terminal in your project folder. It is aimed at **Python**
and **JavaScript** projects out of the box; advanced users can extend it with
plugins.

## What you need first

- **Python 3.11 or newer** installed on your computer.
- Your code in a **Git** repository (distlift talks to Git for tags and
  history).
- A habit of running terminal commands from the folder that contains your
  project (the “repo root”).

## Install

Open a terminal and run:

```text
pip install distlift
```

If you use `pip` only for your user account, that is fine. After install, you
should be able to run:

```text
distlift --help
```

If that prints help text, the tool is on your path. You can also run it as
`python -m distlift` if your Python environment prefers that style.

## The simplest workflow

From your project’s root directory, with a clean saved state in Git (no
half-finished edits you are not ready to commit), run:

```text
distlift
```

With **no extra words**, distlift performs a **patch** release: it bumps the
last part of the version (e.g. 1.0.**4** → 1.0.**5**), updates your manifest
(such as `pyproject.toml` or `package.json`), can update `CHANGELOG.md` when
that is enabled, then commits, tags, and pushes according to your settings.

**Practice run (nothing is written to Git):**

```text
distlift --dry-run
```

That only shows what *would* happen—safe when you are learning.

**Skip the changelog for one run:**

```text
distlift --no-changelog
```

**Keep the changelog but do not open an editor to tweak the new entry:**

```text
distlift --no-changelog-editor
```

**After a successful release, build installable files locally:**

```text
distlift --build
```

**Build and upload to a registry** (only when you have publish credentials and
configuration set up):

```text
distlift --publish
```

**More detail in the log:**

```text
distlift -V
```

or

```text
distlift --verbose
```

**Work on another folder without `cd` there:**

```text
distlift --repo-root "C:\path\to\your\repo"
```

(Use the path style your operating system expects.)

## Choosing how big the version jump is

When you want control over **major**, **minor**, or **patch** (or an exact
version), use the **simple release** command instead of the bare `distlift`
shortcut:

```text
distlift release simple --patch
distlift release simple --minor
distlift release simple --major
distlift release simple --version 2.0.0
```

You must pick **exactly one** of those version options. Add `--dry-run` anytime
to rehearse.

## Monorepos (several packages in one repository)

If your repository is configured for **multiple packages**, each with its own
version and tag, use:

```text
distlift release monorepo --all-changed
```

or release specific names:

```text
distlift release monorepo --package my-lib --package my-app
```

There is a `--default-bump` option for the usual bump size when the tool must
guess. Again, `--dry-run` is your friend.

## Changelog commands

distlift can maintain a **Keep a Changelog**-style `CHANGELOG.md` using your
Git history (and conventional commit messages when enabled).

**See what would be added for a version, without saving:**

```text
distlift changelog preview --version 1.2.3
```

**Write or update the changelog file for that version:**

```text
distlift changelog update --version 1.2.3
```

By default this may open your text editor so you can polish the entry; add
`--no-editor` to skip that step.

**Create a starter changelog file if you do not have one:**

```text
distlift changelog init
```

In monorepo setups, many changelog commands accept `--package <name>` so the
right subfolder is used.

## Configuration commands

**Show the settings distlift is actually using** (and where each value came
from):

```text
distlift config show
```

**Check that configuration is valid:**

```text
distlift config validate
```

**Create or open config files** for your user account or the whole machine
(these create starter files or open them in your editor):

```text
distlift config init-user
distlift config edit-user
distlift config init-system
distlift config edit-system
```

System-level files on Windows often live under shared “Program Data” folders
and may need administrator rights to edit.

### Choosing the text editor

Whenever distlift needs to open a file in an editor (when polishing a
generated changelog entry, or when you run `distlift config edit-user` or
`distlift config edit-system`), it looks for a command to launch in this
order:

1. The `GIT_EDITOR` environment variable (the same one Git itself uses for
   commit messages).
2. The `VISUAL` environment variable (the POSIX convention for a
   full-screen editor such as `vim`, `nano`, or `code --wait`).
3. The `EDITOR` environment variable (the older POSIX fallback,
   e.g. `notepad` on Windows).
4. The `editor` setting from your **distlift config** file, or the
   `DISTLIFT_EDITOR` environment variable.

So if none of the standard editor environment variables are set on your
system, you can still tell distlift which editor to use by writing one
line in your user config:

```toml
editor = "code --wait"
```

You can place that in any distlift TOML layer
(`distlift.toml` / `.distlift.toml`, `[tool.distlift]` inside
`pyproject.toml`, your user config file, or the system one). The values
saved by `distlift config init-user` already include a commented-out
example.

`distlift config show` prints the effective editor (or `(unset)` when no
layer provides one).

## Plugins

**List extensions distlift loaded** (built-ins and any you configured):

```text
distlift plugins list
```

## Getting unstuck

Every command accepts `--help`, for example:

```text
distlift changelog --help
distlift release simple --help
```

That lists all flags for that command. If something fails, read the message
in the terminal—distlift usually explains whether the problem is
configuration, Git state, or a missing file.

---

*distlift is release automation for developers; it performs real Git
operations when not in `--dry-run`. Always commit or stash unrelated work,
read `--help` before unfamiliar flags, and use `--dry-run` until you are
comfortable with the plan.*
