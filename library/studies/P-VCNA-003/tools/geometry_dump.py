import json,sys
p=json.load(open('Study_P-VCNA-003/checkpoints/PDFKit_Word_Regions.json'))
for n in map(int,sys.argv[1:]):
 print('\nPAGE',n);rows=[]
 for w in sorted(p[n-1]['words'],key=lambda w:(round(w['bbox'][1],1),w['bbox'][0])):
  y=w['bbox'][1];row=next((r for r in rows if abs(r[0]-y)<2),None)
  if row is None:row=[y,[]];rows.append(row)
  row[1].append(w)
 for y,ws in rows:
  if y<60 or y>510:continue
  segs=[]
  for w in sorted(ws,key=lambda w:w['bbox'][0]):
   if not segs or w['bbox'][0]-segs[-1][-1]['bbox'][2]>9:segs.append([w])
   else:segs[-1].append(w)
  print(round(y,1),' | '.join(f"{s[0]['bbox'][0]:.0f}:"+' '.join(w['text'] for w in s) for s in segs))
