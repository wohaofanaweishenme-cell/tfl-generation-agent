"""Retrieval over SAP text blocks: diversified keyword/BM25 search + neighbor blocks."""
import re
from collections import Counter
import math

class BM25Okapi:
    """Small self-contained BM25 implementation (no external search service)."""
    def __init__(self, corpus, k1=1.5, b=0.75):
        self.corpus=[Counter(x) for x in corpus]
        self.n=len(corpus); self.k1=k1;self.b=b
        self.lengths=[sum(x.values()) for x in self.corpus]
        self.avg=sum(self.lengths)/max(1,self.n)
        df=Counter()
        for d in self.corpus:df.update(d.keys())
        self.idf={term:math.log(1+(self.n-freq+.5)/(freq+.5)) for term,freq in df.items()}
    def get_scores(self, query):
        out=[]
        for d,l in zip(self.corpus,self.lengths):
            norm=self.k1*(1-self.b+self.b*l/max(self.avg,1e-9))
            out.append(sum(self.idf.get(w,0)*d.get(w,0)*(self.k1+1)/(d.get(w,0)+norm) for w in set(query)))
        return out


def tokenize(text):
    return re.findall(r'[a-z0-9]+(?:[-.][a-z0-9]+)*',text.lower())

SYNONYMS={'overall survival':['overall survival','survival analysis','kaplan meier','intention to treat','survival time','censoring'],
          'progression-free survival':['progression free survival','progression-free survival','kaplan meier','progression'],
          'adverse events':['adverse event','safety population','treatment emergent']}

class SAPIndex:
    def __init__(self,sap):
        self.blocks=sap['blocks']
        self.corpus=[tokenize(b['text']) for b in self.blocks]
        self.model=BM25Okapi([c or ['_empty_'] for c in self.corpus])
        self.lookup={b['block_id']:b for b in self.blocks}
    def search(self,queries,top_k=20):
        # Round-robin across queries prevents a single frequent phrase crowding out other topics.
        queries=[q for q in queries if isinstance(q,str) and q.strip()]
        pools=[]
        for q in queries:
            tokens=tokenize(q)
            if not tokens: continue
            scores=self.model.get_scores(tokens)
            matching=[(i,float(scores[i])) for i in range(len(scores)) if scores[i]>0]
            matching.sort(key=lambda x:x[1],reverse=True)
            pools.append(matching[:max(4,top_k//3)])
        selected=[]; seen=set()
        for level in range(max(map(len,pools),default=0)):
            for pool in pools:
                if level>=len(pool): continue
                i,_=pool[level]
                if i not in seen: selected.append(i);seen.add(i)
                if len(selected)>=top_k:break
            if len(selected)>=top_k:break
        # Neighbor blocks on same page, to preserve headings/continuation text.
        expanded=set(selected)
        for i in selected:
            for neighbor in [i-1,i+1]:
                if 0<=neighbor<len(self.blocks) and self.blocks[neighbor]['page']==self.blocks[i]['page']:
                    expanded.add(neighbor)
        return [self.blocks[i] for i in sorted(expanded)]

def baseline_queries(tfl):
    title=tfl['title']; lower=title.lower()
    qs=[title,'analysis population','statistical analysis methods','treatment groups','statistics summary','footnotes']
    for key, synonyms in SYNONYMS.items():
        if key in lower: qs.extend(synonyms)
    return list(dict.fromkeys(qs))
