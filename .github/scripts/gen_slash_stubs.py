"""Generate add-trailing-slash stub pages for a teedoc build output.

Qiniu bucket origin + urlRewrite `/<path>` -> `/<path>.html` emulates the COS
static-website behaviour of serving `X.html` for `/X`. For a directory `D/` that
has `D/index.html` but no sibling `D.html`, write `D.html` as a tiny page that
redirects the browser to `D/` (COS used to answer that with a 302).

Usage: python3 gen_slash_stubs.py <out_dir>   (idempotent, never overwrites)
"""
import os, sys

STUB = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="robots" content="noindex">
<title>Redirecting</title>
<script>
(function () {
  var l = window.location, p = l.pathname.replace(/\\.html$/, '');
  l.replace(p + '/' + l.search + l.hash);
})();
</script>
<noscript><meta http-equiv="refresh" content="0;url=./{name}/"></noscript>
</head><body><a href="./{name}/">{name}/</a></body></html>
"""

def main(root):
    root = os.path.abspath(root)
    made = skipped = 0
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x != '.git']
        if d == root or 'index.html' not in fs:
            continue
        stub = d + '.html'
        if os.path.exists(stub):
            skipped += 1
            continue
        name = os.path.basename(d)
        with open(stub, 'w', encoding='utf-8') as f:
            f.write(STUB.replace('{name}', name))
        made += 1
    print('slash stubs: created %d, kept existing %d' % (made, skipped))

if __name__ == '__main__':
    if len(sys.argv) != 2 or not os.path.isfile(os.path.join(sys.argv[1], 'index.html')):
        sys.exit('usage: gen_slash_stubs.py <out_dir containing index.html>')
    main(sys.argv[1])
