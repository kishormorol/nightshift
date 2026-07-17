---
title: "Uninstall"
description: "Three lines, and nothing left behind."
order: 13
---

nightaudit keeps no state anywhere else, so removing it is three lines:

```bash
crontab -e                    # delete the block (see below)
rm -rf ~/.nightaudit          # config, ledger, queue, event logs
pipx uninstall nightshift-cli
```

If you first installed before 0.4.0, your state may still be in `~/.nightshift`
— nightaudit reads it there rather than making you move it. `nightaudit status`
prints the directory it is actually using, which is the one to remove.

`init` fences its crontab lines between two markers — delete them and
everything between:

```
# nightaudit (managed — edit via `nightaudit init`)
...
# end nightaudit
```

Your digests in `~/nightaudit-reports` are yours — delete them or don't.
