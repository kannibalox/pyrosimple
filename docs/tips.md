---
title: Tips & Tricks
---

# Tip & Tricks

## Find orphaned files

Since Jinja2 is more sandboxes than the original Tempita templating system, the `orphans.txt` template file from pyrocore no longer works. However, we can replicate the functionality with a little fancy scripting. The following command will list the orphan files along with their sizes:
```bash
target_dir=/mnt/test
comm -13 \
  <(rtcontrol -o filesize "path=${target_dir}*" | sort) \
  <(find "$target_dir" -type f | sort) \
  | tr '\n' '\0' | xargs -0 du -hsc
```

To clean up the files (after ensuring the list is accurate!), we can just change the final command from `du` to `rm`. Note that this example uses `echo rm` to ensure nothing is deleted accidentally:

```bash
comm -13 \
  <(rtcontrol -o filesize path=/mnt/local/Torrents/Downloading/\* | sort) \
  <(find /mnt/local/Torrents/Downloading/ -type f | sort) \
  | tr '\n' '\0' | xargs -0 echo rm
```
