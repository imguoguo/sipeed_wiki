#!/usr/bin/env python3
"""Upload the built wiki to a Qiniu bucket, concurrently.

Same file selection as `teedoc-upload --old`: with an old build dir, only new
and modified files are uploaded; never deletes. Non-HTML files go first and
HTML last, so a page never goes live before the assets it references.

`teedoc-upload --cloud qiniu` does the same job one file at a time (~1 s per
file from GitHub runners); this runs 16 uploads in parallel.

Usage:
  QINIU_ACCESS_KEY=... QINIU_SECRET_KEY=... \
    python3 upload_qiniu.py --bucket <bucket> [--old <old_dir>] <new_dir>
Exit code is non-zero if any file fails after retries.
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import qiniu
from teedoc.teedoc_compare import get_changed_files, get_files

RETRIES = 3
WORKERS = 16


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--old", default="")
    ap.add_argument("new_dir")
    args = ap.parse_args()

    ak = os.environ.get("QINIU_ACCESS_KEY", "")
    sk = os.environ.get("QINIU_SECRET_KEY", "")
    if not ak or not sk:
        sys.exit("QINIU_ACCESS_KEY / QINIU_SECRET_KEY not set")
    new_dir = args.new_dir.rstrip("/") or "/"
    if not os.path.isfile(os.path.join(new_dir, "index.html")):
        sys.exit("refusing to upload: %s/index.html not found" % new_dir)

    if args.old:
        old_dir = args.old.rstrip("/") or "/"
        if not os.path.isdir(old_dir):
            sys.exit("old dir not found: %s" % old_dir)
        new, modified, _deleted = get_changed_files(old_dir, new_dir)
        keys = new + modified
    else:
        keys = get_files(new_dir)
    keys = sorted(set(keys), key=lambda k: (k.endswith((".html", ".htm")), k))
    print("%d files need to upload to %s" % (len(keys), args.bucket), flush=True)

    auth = qiniu.Auth(ak, sk)

    def upload(key):
        path = os.path.join(new_dir, key)
        err = None
        for attempt in range(RETRIES):
            try:
                token = auth.upload_token(args.bucket, key, 3600)
                ret, info = qiniu.put_file(token, key, path, version="v2")
                if ret and ret.get("key") == key and ret.get("hash") == qiniu.etag(path):
                    return None
                err = "status %s" % getattr(info, "status_code", "?")
            except Exception as e:  # network errors: retry
                err = str(e)
            time.sleep(2 * (attempt + 1))
        return "%s: %s" % (key, err)

    start = time.time()
    html = [k for k in keys if k.endswith((".html", ".htm"))]
    other = [k for k in keys if not k.endswith((".html", ".htm"))]
    failures = []
    attempted = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        for batch in (other, html):
            attempted += len(batch)
            failures += [r for r in ex.map(upload, batch) if r]
            if failures:
                print("asset upload failed, HTML not uploaded")
                break  # don't publish pages whose assets failed
    print("uploaded %d/%d in %.0fs" % (attempted - len(failures), len(keys), time.time() - start))
    for f in failures[:50]:
        print("FAILED", f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
