import sys
def lum(h):
    h=h.lstrip('#'); r,g,b=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    f=lambda c: c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)
def cr(a,b):
    la,lb=sorted([lum(a),lum(b)],reverse=True); return (la+0.05)/(lb+0.05)
T={
'light':dict(paper='#f5f3ec',raised='#fdfcf8',sunken='#ebe8de',rule='#d8d3c4',rule_strong='#8c8676',ink='#1c211d',muted='#575c55',
  ledger='#1f4a3a',ledger_hover='#163a2d',on_ledger='#fdfcf8',ledger_tint='#dce9e1',hl='#f6dd6b',hl_active='#efc93a',on_hl='#1c211d',
  conflict='#a8320f',on_conflict='#fdfcf8',conflict_tint='#fbe3d9',human='#7a4f00',human_tint='#fbecc8',missing='#555d68',missing_tint='#e8eaec',complete='#0b5c8f',complete_tint='#dbeaf5'),
'dark':dict(paper='#141815',raised='#1c211d',sunken='#0f1210',rule='#333a35',rule_strong='#6f776f',ink='#ebe8df',muted='#a7aca3',
  ledger='#86c9a9',ledger_hover='#a3d8bd',on_ledger='#0f1f17',ledger_tint='#1f3a2e',hl='#e9cf5a',hl_active='#f4dc6e',on_hl='#1a1a12',
  conflict='#ff9a76',on_conflict='#2a0f05',conflict_tint='#3d1f15',human='#f2c25c',human_tint='#3a2d12',missing='#b3bac4',missing_tint='#262b30',complete='#7ec0ec',complete_tint='#142c3d'),
}
pairs=[('ink','paper',4.5),('ink','raised',4.5),('ink','sunken',4.5),('muted','paper',4.5),('muted','raised',4.5),('muted','sunken',4.5),
('rule_strong','paper',3),('rule_strong','raised',3),('ledger','paper',4.5),('ledger','raised',4.5),('ledger','sunken',4.5),('on_ledger','ledger',4.5),('on_ledger','ledger_hover',4.5),('ledger','ledger_tint',4.5),('ink','ledger_tint',4.5),
('on_hl','hl',4.5),('on_hl','hl_active',4.5),
('conflict','raised',4.5),('conflict','paper',4.5),('conflict','conflict_tint',4.5),('on_conflict','conflict',4.5),('ink','conflict_tint',4.5),
('human','raised',4.5),('human','paper',4.5),('human','human_tint',4.5),('ink','human_tint',4.5),
('missing','raised',4.5),('missing','paper',4.5),('missing','missing_tint',4.5),
('complete','raised',4.5),('complete','paper',4.5),('complete','complete_tint',4.5),('ledger','raised',3)]
bad=0
for th,c in T.items():
    for a,b,m in pairs:
        r=cr(c[a],c[b]); flag='' if r>=m else '  <-- FAIL'
        if flag: bad+=1
        print(f'{th:5} {a:12} on {b:14} {r:5.2f} (need {m}){flag}')
    print(f'{th} conflict vs complete lightness ratio {cr(c["conflict"],c["complete"]):.2f}; conflict vs human {cr(c["conflict"],c["human"]):.2f}')
print('fails',bad)
