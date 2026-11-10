# Give every report page the same running head, so Draft and the signed date switch the same way on every page.
import re, sys, glob, os
d = os.path.join(sys.argv[1], 'components/_src')
right = ('<span class="ft-rhead-status"><span class="ft-rdraft">Draft</span> <span class="ft-rasof">As of Apr 12, 2026</span>'
         '<span class="ft-rsigned">Signed off Apr 12, 2026</span></span>')
pat = re.compile(r'(<header class="ft-rpage__head">\s*<span>Evidence report.*?Example Bay</span>)(.*?)(</header>)', re.S)
for f in sorted(glob.glob(os.path.join(d, 'report-*.html'))):
    s = open(f).read(); s2, n = pat.subn(lambda m: m.group(1) + right + m.group(3), s)
    open(f, 'w').write(s2); print(os.path.basename(f), n, 'heads')
