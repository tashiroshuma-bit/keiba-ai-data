import json,base64,zlib,re,pathlib
p=pathlib.Path('/mnt/data/files/JRA重賞3年分_予測システム_v6.ipynb')
nb=json.loads(p.read_text());src=''.join(nb['cells'][1]['source']); encoded=re.search(r"b64decode\('([^']+)'\)",src).group(1)
BUNDLE=json.loads(zlib.decompress(base64.b64decode(encoded)));DATA=BUNDLE['data'];REPORT=BUNDLE['report']
exec(''.join(nb['cells'][2]['source']))
original=REPORT['test_2025']; fresh=train_and_evaluate(DATA)['test_2025']
diffs={k:abs(original[k]-fresh[k]) for k in ['log_loss','top1_hit','brier_sum','top3_winner_hit','flat_win_return_rate']}
result={'original':original,'reproduced':fresh,'absolute_differences':diffs,'passed':all(x<1e-6 for x in diffs.values())}
pathlib.Path('/mnt/data/keiba_v48_audit_20261019/reproduction_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))

