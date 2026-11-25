import numpy as np
from alignment_core import features, locate, match_words
rng=np.random.default_rng(8)
x=rng.normal(size=8000*35).astype('float32')*np.repeat(rng.uniform(.01,1,350),800)
f=features(x); t,s,runner=locate(f[160:400],f)
assert abs(t-8)<.06 and s>.95 and s-runner>.07,(t,s,runner)
text='questa è una prova della ricerca delle parole nella trascrizione italiana originale'
words=[dict(word=w,start=i,end=i+.5) for i,w in enumerate(text.split())]
r=match_words(words,[{'cues':[{'text':'altro testo senza una corrispondenza'}]},{'cues':[{'text':text}]}]);assert r[0][1]==1 and r[0][0]>.95
print('OK synthetic audio offset and Italian text localization')
