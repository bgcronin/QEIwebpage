# Manual upload fallback

The preferred route is to grant the connected ChatGPT GitHub app access to `bgcronin/QEIwebpage`, allowing the prepared repository to be pushed directly.

If that connection is unavailable, download `qei-site-clone.bundle` and run:

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

The initial push automatically starts the **Build authorised QEI mirror** GitHub Actions workflow. It crawls the public QEI site from GitHub's runner, sanitises forms and transactions, audits the snapshot, saves an artifact, and—where branch permissions allow—commits the generated `site/` and `reports/` directories.
