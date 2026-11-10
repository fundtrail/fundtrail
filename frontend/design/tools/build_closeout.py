# Build the viewer scripts, the report data and the report pages into the Closeout card, so Preview opens the report in the sheet.
import os, re, sys, json
root = sys.argv[1]
d = os.path.join(root, 'components/_src')
order = ['report-summary.html', 'report-table.html', 'report-sections.html', 'report-signoff.html', 'report-sources.html']
pages = ''.join(open(os.path.join(d, f)).read() for f in order if os.path.exists(os.path.join(d, f)))
js = '\n'.join(open(os.path.join(d, f)).read() for f in ['viewer-frame.js', 'viewer-report.js'])
data = open(os.path.join(d, 'report-data.js')).read()
block = ('<!-- @report-scripts -->\n<script>\n' + data + 'window.FTReportPages = ' + json.dumps(pages).replace('</', '<\\/') + ';\n' + js +
         '\n</script>\n<!-- /report-scripts -->')
p = os.path.join(root, 'components/Closeout/preview.html'); s = open(p).read()
if '<!-- /report-scripts -->' in s:
    s = re.sub(r'<!-- @report-scripts -->.*?<!-- /report-scripts -->', lambda m: block, s, flags=re.S)
else:
    i = s.find('<script'); assert i > 0, 'no script in Closeout'
    s = s[:i] + block + '\n' + s[i:]
open(p, 'w').write(s); print('closeout built', len(pages), 'chars of pages')
