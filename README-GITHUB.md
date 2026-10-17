# GitHub repository, logo and live dashboard (PyCharm)

The testbed folder becomes one Git repository. After every run you publish its results; GitHub Actions turns
them into a web page with the full dashboard (every page, the evaluation report, paper figures), and you can
preview the same page on your PC before pushing.

```
 testbed PC                                   GitHub
 ───────────────────────────────────          ─────────────────────────────────────────────
 run-all.ps1  ─► results\  results-archive\
 publish-results.ps1
   ├─ tools\build_site.py ─► site\            push ─►  repository (code, results, site\)
   └─ git commit + push   ──────────────────────────►  Actions "Publish dashboard" ─► GitHub Pages
 PyCharm "Preview site" ─► http://localhost:8600        https://<user>.github.io/<repo>/
```

* `site\` is a snapshot: the dashboard's pages plus its data as JSON files, computed from your result files. It
  needs no server, so GitHub Pages (or any web server) can show it. Live progress and logs stay on the PC.
* The logo is in `assets\` (`logo.svg`, `logo-512.png`, wordmarks, `social-preview.png` for the repository card).

> **Decide first: who may see the results?** A GitHub Pages site is public on the internet, also when the
> repository is private, and Pages for a private repository needs a paid GitHub plan (Pro, Team or Enterprise).
> If the results must stay private until the paper is out, keep the repository private and use only the local
> preview (step 5), or publish only at submission time.

## 1. Once: install

* **Git for Windows** (https://git-scm.com/download/win), default options.
* **PyCharm** (Community is enough) with a Python 3.10+ interpreter. The dashboard and the site builder use only
  Python's standard library: nothing to `pip install`.
* A **GitHub account**. In PyCharm: *Settings → Version Control → GitHub → +* → *Log In via GitHub*.

## 2. Once: create the repository from the testbed folder

1. In PyCharm: *File → Open* → the testbed folder (the one with `run-all.ps1`). Choose the Python interpreter
   when asked (*Add New Interpreter → Virtualenv* or your system Python).
2. *VCS → Share Project on GitHub* (newer versions: *Git → GitHub → Share Project on GitHub*).
   * Repository name: `optimusdb-benchmark-observatory` (the README links assume this name; change them if you
     choose another).
   * **Private** or public: see the box above.
   * In the file list, check that nothing from `out\`, `out-local\` or `.src\` is offered (they hold keys and
     tokens; `.gitignore` excludes them). Commit message: `Testbed, dashboard and results`.
3. PyCharm creates the repository, commits and pushes.

The same from a terminal (PowerShell in the testbed folder), if you prefer:

```
git init -b main
git add -A
git commit -m "Testbed, dashboard and results"
git remote add origin https://github.com/georgeGeorgakakos/optimusdb-benchmark-observatory.git
git push -u origin main
```

(create the empty repository on github.com first, without README).

## 3. Once: switch on GitHub Pages and set the logo

1. github.com → the repository → *Settings → Pages* → *Build and deployment → Source:* **GitHub Actions**.
2. *Settings → General → Social preview → Edit → Upload an image* → `assets\social-preview.png` (the card shown
   when the link is shared).
3. Optional: on the repository page, the gear next to *About* → website: the Pages address
   `https://georgegeorgakakos.github.io/optimusdb-benchmark-observatory/`.

## 4. After every run: publish

```
powershell -ExecutionPolicy Bypass -File .\publish-results.ps1 -Message "quick run 8"
```

It builds `site\` (with the testbed's own Python image, so it works even without Python on the PC), commits
`results\`, `results-archive\` and `site\`, and pushes. *Actions → Publish dashboard* on GitHub shows the
deployment; the page is updated about a minute later. Variants:

| Command | Does |
|---|---|
| `.\publish-results.ps1 -BuildOnly` | only rebuilds `site\` (preview before publishing) |
| `.\publish-results.ps1 -NoPush` | builds and commits; push later from PyCharm (*Git → Push*, Ctrl+Shift+K) |
| `.\publish-results.ps1 -NoOps` | leaves out the per-operation drill-downs (smaller site) |

In PyCharm you can also do it by hand: run *Build site (snapshot)*, then *Git → Commit* (Ctrl+K) the changed
`results\`, `results-archive\` and `site\` files, then *Git → Push*.

## 5. Preview on your PC (PyCharm run configurations)

The repository includes three run configurations (top-right drop-down in PyCharm, folder `.run\`):

| Run configuration | What it shows | Address |
|---|---|---|
| **Dashboard (local)** | the live dashboard over `results\` and `results-archive\` (same as `dashboard.ps1`, without Docker) | http://localhost:8501 |
| **Build site (snapshot)** | rebuilds `site\` from the result files | – |
| **Preview site** | exactly what GitHub Pages will show | http://localhost:8600 |

Run *Build site (snapshot)* then *Preview site*, open the address, and you see the page that the next push
publishes. Stop a configuration with the red square.

## What is in the repository, and what is not

| Committed | Not committed (`.gitignore`) |
|---|---|
| testbed scripts, harness, dashboard, docs, `assets\` | `out\`, `out-local\`: WireGuard keys, agent token, generated configs |
| `results\` and `results-archive\`: result CSVs, logs, saved reports, quick and pilot per-operation files | `.src\`: the OptimusDB checkout used for image builds |
| `site\`: the published snapshot | per-operation files and node logs of full campaigns (hundreds of MB; the site does not need them; keep them on the PC and in `save-results.ps1` archives) |

GitHub refuses single files over 100 MB and warns above 50 MB. The campaign's result CSVs are small; only the
per-operation files are large, and they stay on the PC.
