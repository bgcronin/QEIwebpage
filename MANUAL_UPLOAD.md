# Upload the prepared repository to GitHub

The prepared Git bundle is a complete Git repository, including history, workflow files, tests, and the safe placeholder site.

For an empty `bgcronin/QEIwebpage` repository, download `qei-site-clone.bundle` and run:

```bash
git clone ~/Downloads/qei-site-clone.bundle QEIwebpage
cd QEIwebpage
git remote set-url origin https://github.com/bgcronin/QEIwebpage.git
git push -u origin main
```

If the GitHub repository already contains an unrelated initial README commit, publish the prepared history to a review branch instead:

```bash
git push -u origin main:qei-static-clone
```

Then open a pull request from `qei-static-clone` into the repository's default branch.

The initial push starts **Build authorised QEI mirror**. The workflow discovers public QEI hosts, crawls public pages from a GitHub runner, disables forms and sensitive transaction endpoints, removes configured tracking references, audits the result, uploads a review artifact, and—where branch permissions allow—commits the generated `site/` and `reports/` directories.
