# Synthetic charges for SYN-2300117's evidence report. 51 charges summing to $96,412.18. All data is synthetic.
import json, random, datetime as dt
from pathlib import Path as _P
S = str(next(p for p in _P(__file__).resolve().parents if (p / 'system').is_dir() and (p / 'tools').is_dir()))  # frontend/design
random.seed(117)
known = [
 dict(id='L-0981', date='2025-10-03', desc='Conference registration', vendor='Example Ocean Sciences Meeting', line='Participant Support Costs', cents=65000, bucket='conflict',
      reason='Approved by the principal investigator, not the program officer.', source='approval_email.eml'),
 dict(id='L-1001', date='2025-11-12', desc='Sediment core liners', vendor='Example Lab Supply Co.', line='Materials and Supplies', cents=124000, bucket='complete',
      reason='Invoice INV-1001 covers it in full. Work in the period.', source='invoice_1001.txt'),
 dict(id='L-1002', date='2026-02-20', desc='Sediment DNA sequencing run 7', vendor='Example Sequencing Core', line='Other Direct Costs', cents=218000, bucket='complete',
      reason='In the period after amendment 01. Invoice SEQ-0207 covers it in full.', source='sequencing_invoice.eml'),
 dict(id='L-1010', date='2026-01-09', desc='Sequencing core, shared run 6', vendor='Example Sequencing Core', line='Other Direct Costs', cents=583333, bucket='human',
      reason="Invoice SEQ-0311 covers two grants; nothing gives this grant's part.", source='invoice_SEQ-0311.pdf'),
 dict(id='L-1015', date='2026-01-14', desc='Field boat rental', vendor='Example Marina', line='Other Direct Costs', cents=148000, bucket='complete',
      reason='Receipt photo covers it in full. Work in the period.', source='boat_rental_receipt.jpg'),
 dict(id='L-1019', date='2026-01-21', desc='Field microscope camera', vendor='Example Optics Supply', line='Materials and Supplies', cents=132500, bucket='human',
      reason='The agent is unsure the cost is for this project.', source='field_camera_receipt.jpg'),
]
TOTAL = 9641218
pools = {
 'Materials and Supplies': (18, 2800000, [('Sediment core liners', 'Example Lab Supply Co.'), ('Sample vials and caps', 'Example Lab Supply Co.'), ('DNA extraction kits', 'Example Chemical Supply'), ('Field sampling gloves', 'Example Field Gear'), ('Cooler and ice packs', 'Example Field Gear'), ('Pipette tips', 'Example Lab Supply Co.'), ('Ethanol, molecular grade', 'Example Chemical Supply'), ('Core sampler parts', 'Example Field Gear')]),
 'Other Direct Costs': (17, 4400000, [('Sediment DNA sequencing', 'Example Sequencing Core'), ('Field boat rental', 'Example Marina'), ('Sample shipping, frozen', 'Example Freight'), ('Library preparation service', 'Example Sequencing Core'), ('Data storage, annual', 'Example Cloud Storage'), ('Open access publication fee', 'Example Journal of Microbial Ecology')]),
 'Participant Support Costs': (10, None, [('Field course stipend', 'Field course participant'), ('Workshop registration, student', 'Example Coastal Science Workshop'), ('Participant lodging, field course', 'Example Bay Field Station'), ('Participant travel, field course', 'Example Regional Transit')]),
}
known_sum = sum(k['cents'] for k in known)
rest = TOTAL - known_sum
ms_target, odc_target = 2800000, 4400000
psc_target = rest - ms_target - odc_target
def split(n, target):
    w = [random.uniform(0.4, 1.6) for _ in range(n)]; s = sum(w)
    a = [int(round(target * x / s / 100.0)) * 100 + random.choice([0, 0, 0, 50, 99, 25]) for x in w]
    a[-1] += target - sum(a); return a
gen = []
start, end = dt.date(2023, 2, 20), dt.date(2025, 9, 20)
for line, (n, _, items) in pools.items():
    tgt = {'Materials and Supplies': ms_target, 'Other Direct Costs': odc_target, 'Participant Support Costs': psc_target}[line]
    for c in split(n, tgt):
        d = start + dt.timedelta(days=random.randint(0, (end - start).days))
        desc, vendor = random.choice(items)
        gen.append(dict(date=d.isoformat(), desc=desc, vendor=vendor, line=line, cents=c, bucket='complete'))
gen.sort(key=lambda g: g['date'])
for i, g in enumerate(gen):
    g['id'] = 'L-%04d' % (100 + i * 19)
    kind = 'Receipt' if g['line'] == 'Materials and Supplies' else 'Invoice'
    if g['line'] == 'Participant Support Costs':
        g['reason'] = 'Participant support in the budget. Receipt covers it in full.'
        g['source'] = 'psc_receipt_%s.pdf' % g['id'][2:]
    else:
        g['reason'] = '%s covers it in full. Work in the period.' % kind
        g['source'] = ('receipt_%s.pdf' if kind == 'Receipt' else 'invoice_%s.pdf') % g['id'][2:]
allc = sorted(gen + known, key=lambda g: g['date'])
assert len(allc) == 51 and sum(c['cents'] for c in allc) == TOTAL, (len(allc), sum(c['cents'] for c in allc))
by = {}
for c in allc: by[c['line']] = by.get(c['line'], 0) + c['cents']
caps = {'Materials and Supplies': 4000000, 'Other Direct Costs': 6000000, 'Participant Support Costs': 2000000}
for k, v in by.items(): assert v <= caps[k], (k, v)
def money(c): return '${:,.2f}'.format(c / 100)
def fdate(s): d = dt.date.fromisoformat(s); return d.strftime('%b ') + str(d.day) + d.strftime(', %Y')
for c in allc: c['amount'] = money(c['cents']); c['dateText'] = fdate(c['date'])
data = dict(grant=dict(award='SYN-2300117', title='Sediment Microbiome Survey of Example Bay', funder='National Science Foundation (NSF)', recipient='Example State University',
  pi='Dr. Robin Example', period='Feb 1, 2023 to Jan 31, 2027', periodNote='End date moved from Jan 31, 2026 by amendment 01, confirmed Apr 10, 2026',
  awarded='$120,000.00', charged=money(TOTAL), asOf='Apr 12, 2026', budget=[dict(line=k, budget=money(caps[k]), charged=money(by[k])) for k in caps]),
  counts=dict(complete=sum(c['bucket']=='complete' for c in allc), conflict=sum(c['bucket']=='conflict' for c in allc), human=sum(c['bucket']=='human' for c in allc), missing=0),
  charges=allc)
open(S + '/system/components/_src/report-data.json', 'w').write(json.dumps(data, indent=1))
open(S + '/system/components/_src/report-data.js', 'w').write('window.FTReportData = ' + json.dumps(data) + ';\n')
print(data['counts'], {k: money(v) for k, v in by.items()}, money(TOTAL), allc[0]['id'], allc[-1]['id'])
