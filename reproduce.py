"""Portable offline reproduction: archived model/MAT scoring, sensitivity and statistics.
No agent imports, network requests, model generation, compiler or simulator calls.
"""
from pathlib import Path
import argparse,csv,json,hashlib,gzip,shutil,math,sys,collections,functools,random,tempfile
ROOT=Path(__file__).resolve().parent
if not (ROOT/'VERSION.json').exists():ROOT=ROOT.parent
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return list(csv.DictReader(Path(p).open(encoding='utf-8-sig',newline='')))
def csvfile(folder,prefix):return next((ROOT/folder).glob(prefix+'*.csv'))
def dump(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),'utf-8')
def writecsv(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def verify(out):
    manifest=ROOT/'MANIFEST.sha256';lines=manifest.read_text('utf-8').splitlines()
    for line in lines:
        h,name=line.split('  ',1);p=ROOT/name
        if not p.is_file()or sha(p)!=h:raise ValueError('Manifest mismatch '+name)
    dump(out/'verification.json',{'verdict':'PASS','files':len(lines),'manifest_sha256':sha(manifest),'release':read(ROOT/'VERSION.json')})
    return len(lines)
def scoring_modules():
    sys.path.insert(0,str(ROOT/'evaluation/original_acceptance'))
    import experiment_metrics as em
    # Cache MAT objects only; all original parsing, interpolation, assertions and arithmetic stay unchanged.
    if not hasattr(em.DyMatFile,'cache_info'):em.DyMatFile=functools.lru_cache(maxsize=3)(em.DyMatFile)
    import independent_acceptance as ia
    return em,ia
@functools.lru_cache(maxsize=None)
def resolve(asset):
    if not asset:return None
    p=ROOT/asset
    if p.suffix!='.gz':return str(p)
    dest=ROOT/'.cache/mat'/p.name.removesuffix('.gz');dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        with gzip.open(p,'rb')as a,dest.open('wb')as b:shutil.copyfileobj(a,b,2**20)
    assert sha(dest)==p.name.split('.')[0],'Restored MAT fingerprint mismatch: '+asset
    return str(dest)
def score(out,scope='endpoints',limit=None):
    em,ia=scoring_modules();manifest=read(ROOT/'benchmark/reference_models/manifest.json')['cases']
    index=rows(ROOT/'experiments'/('endpoint_index.csv'if scope=='endpoints'else'checkpoint_index.csv'))
    frozen={(r['run_id'],r['stage']):r for r in rows(csvfile('data/统一主数据','U02'))}
    cache={};records=[];conflicts=[];specs={};refcode={}
    for n,row in enumerate(index if limit is None else index[:limit]):
        inp=read(ROOT/row['input_path']);case=inp['case'];meta=inp['run_meta'];asset=inp['result_asset']
        key=hashlib.sha256(json.dumps([case,inp['models'],meta.get('applied_overrides')or meta.get('overrides'),asset],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if key not in cache:
            if case not in specs:
                sp=em.find_case_spec(str(ROOT/'benchmark/acceptance_specs'),case,case)
                sp['expected_stop_time']=sp['contract']['simulation_settings']['stop_time'];specs[case]=sp
                f=ROOT/'benchmark/reference_models'/manifest[case]['source'];refcode[case]={f.name:f.read_text('utf-8')}
            ev=ia.evaluate_artifact(model_code=inp['models'],run_meta=meta,result_mat=resolve(asset),spec=specs[case],reference_result=str(ROOT/'benchmark/reference_trajectories'/f'{case}.mat'),reference_model_code=refcode[case],reference_authorship=manifest[case].get('authorship'))
            cache[key]=ev
        ev=cache[key];old=inp['expected'];ac=old.get('independent_acceptance',old.get('semantic_acceptance',{}));nm=ev['reference_nrmse'];onm=old['reference_nrmse']
        tests={'original':ev['technical_acceptance']==old['technical_acceptance'],'source_contract':ev['parameter_and_simulation_contract']['pass']==old['parameter_and_simulation_contract']['pass'],'metadata':ev['metadata_target_contract']['pass']==old['metadata_target_contract']['pass'],'behavior':ev['semantic_acceptance']['ok']==ac['ok'],'reference_readable':nm['ok']==onm['ok']}
        a,b=nm.get('max_nrmse'),onm.get('max_nrmse');tests['nrmse']=(a is None and b is None)or(a is not None and b is not None and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12))
        for var,v in nm.get('variables',{}).items():
            ov=onm.get('variables',{}).get(var,{})
            if v.get('ok')and ov.get('ok'):
                tests['reference_scale:'+var]=math.isclose(v['reference_scale'],ov['reference_scale'],rel_tol=1e-12,abs_tol=1e-12)
        failed=[k for k,v in tests.items()if not v]
        if failed:conflicts.append({'row':row,'differences':failed,'recomputed_nrmse':a,'archived_nrmse':b})
        cc=ev['parameter_and_simulation_contract']['conflicts'];rest=[c for c in cc if c['kind']!='initial_condition_not_fixed']
        other=bool(ev['metadata_target_contract']['pass']and ev['reference_model_parameter_contract']['pass']and ev['semantic_acceptance']['ok']and nm['ok']and a is not None and math.isfinite(a)and a<=ev['max_nrmse_limit'])
        rec={**row,'original':int(ev['technical_acceptance']),'sensitivity':int(other and not rest),'behavior_and_trajectory':int(ev['semantic_acceptance']['ok']and nm['ok']and a is not None and a<=ev['max_nrmse_limit']),'max_nrmse':a,'contract_conflicts_json':json.dumps(cc,ensure_ascii=False),'verified':not failed}
        if scope=='endpoints':assert rec['original']==int(frozen[row['run_id'],row['stage']]['technical_acceptance']=='True')
        records.append(rec)
        if n%120==0:print('SCORE',scope,n,'/',len(index),'unique evaluations',len(cache),flush=True)
    writecsv(out/('rescored_'+scope+'.csv'),records);dump(out/('score_'+scope+'_report.json'),{'verdict':'PASS'if not conflicts else'FAIL','rows':len(records),'unique_evaluations':len(cache),'differences':conflicts,'scope':scope,'no_new_simulation':True,'cache':'MAT-object cache; unchanged frozen scoring source'})
    if conflicts:raise ValueError('Re-scoring differs from archive; see report. Original data not changed.')
    return records
def sensitivity(out):
    idx=rows(ROOT/'experiments/endpoint_index.csv');expected={(r['run_id'],r['stage']):r for r in rows(csvfile('data/审计统计','S01'))};result=[]
    for row in idx:
        e=read(ROOT/row['input_path'])['expected'];c=e['parameter_and_simulation_contract'];remaining=[v for v in c['conflicts']if v['kind']!='initial_condition_not_fixed'];n=e['reference_nrmse'];ac=e.get('semantic_acceptance',e.get('independent_acceptance'));old=expected[row['run_id'],row['stage']]
        other=old['other_required_components_pass']=='True'
        relaxed=int(other and not remaining);assert relaxed==int(old['without_fixed_spelling'])and int(e['technical_acceptance'])==int(old['original'])
        result.append({**row,'original':int(e['technical_acceptance']),'sensitivity':relaxed,'gain':relaxed-int(e['technical_acceptance'])})
    writecsv(out/'sensitivity_endpoints.csv',result)
    # If fresh scoring exists, it must yield exactly the same post-hoc scores.
    sp=out/'rescored_endpoints.csv'
    if sp.exists():
        lookup={(r['run_id'],r['stage']):r for r in result}
        for r in rows(sp):assert int(r['sensitivity'])==lookup[r['run_id'],r['stage']]['sensitivity']
    dump(out/'sensitivity_report.json',{'verdict':'PASS','rows':len(result),'removed_only':'initial_condition_not_fixed','analysis':'post_hoc_exploratory; not a new correctness oracle'})
    return result
def signflip(values):
    dist=collections.Counter({0:1})
    for v in values:
        nd=collections.Counter()
        for k,n in dist.items():nd[k+v]+=n;nd[k-v]+=n
        dist=nd
    return sum(n for k,n in dist.items()if abs(k)>=abs(sum(values)))/2**len(values)
def holm(ps):
    out=[0.]*len(ps);last=0
    for j,i in enumerate(sorted(range(len(ps)),key=lambda i:ps[i])):last=max(last,min(1.,ps[i]*(len(ps)-j)));out[i]=last
    return out
def statistics(out):
    import numpy as np
    sens=rows(out/'sensitivity_endpoints.csv');final=[r for r in sens if r['stage']=='final'];cond=rows(ROOT/'experiments/conditions.csv');groups={(r['study'],r['condition']):[v for v in final if v['study']==r['study']and v['condition']==r['condition']]for r in cond}
    drawsH=np.random.default_rng(20261017).integers(0,20,(100000,20));drawsS=np.random.default_rng(20261021).integers(0,20,(100000,20));rng=random.Random(20261018);drawsN=np.array([rng.choices(range(20),k=20)for _ in range(100000)],dtype=np.int16)
    def ci(vals,draws):return [float(v)for v in np.quantile(np.array(vals)[draws].mean(axis=1),[.025,.975])]
    marg=[];paired=[]
    for (study,c),rr in groups.items():
        assert len(rr)==60
        for metric in ['original','sensitivity']:
            tasks=sorted({r['case']for r in rr})if study!='历史矩阵'and metric=='original'else[f'C{i}'for i in range(1,21)]
            draws=drawsS if metric=='sensitivity'else drawsH if study=='历史矩阵'else drawsN
            vals=[sum(int(r[metric])for r in rr if r['case']==t)/3 for t in tasks];l,h=ci(vals,draws)
            marg.append({'study':study,'condition':c,'metric':metric,'count':sum(int(r[metric])for r in rr),'n':60,'low':l,'high':h})
    for study,base in [('历史矩阵','full'),('新增受控实验','fixed_full')]:
        controls=[c['condition']for c in cond if c['study']==study and c['condition']!=base]if study=='历史矩阵'else['fixed_quick','fixed_generic','fixed_self','fixed_deterministic']
        for metric in ['original','sensitivity']:
            family=[];a={(r['case'],r['repeat']):int(r[metric])for r in groups[study,base]}
            for c in controls:
                b={(r['case'],r['repeat']):int(r[metric])for r in groups[study,c]};assert a.keys()==b.keys();keys=list(a)
                tasks=sorted({k[0]for k in keys})if study!='历史矩阵'and metric=='original'else[f'C{i}'for i in range(1,21)]
                d=[sum(a[k]-b[k]for k in keys if k[0]==t)for t in tasks];draws=drawsS if metric=='sensitivity'else drawsH if study=='历史矩阵'else drawsN;l,h=ci(np.array(d)/3,draws)
                family.append({'study':study,'metric':metric,'a':base,'b':c,'difference':sum(d)/60,'low':l,'high':h,'a_only':sum(a[k]and not b[k]for k in keys),'b_only':sum(b[k]and not a[k]for k in keys),'both_pass':sum(a[k]and b[k]for k in keys),'both_fail':sum(not a[k]and not b[k]for k in keys),'p':signflip(d),'family_size':len(controls)})
            for r,p in zip(family,holm([r['p']for r in family])):r['holm_p']=p;paired.append(r)
    # Compare every archived key CI, count, discordance and corrected test, never choose favorable values.
    diffs=[]
    def compare(actual,expected,fields,label):
        for a,b in fields:
            if not math.isclose(float(actual[a]),float(expected[b]),rel_tol=1e-10,abs_tol=1e-12):diffs.append({'row':label,'field':a,'actual':actual[a],'expected':expected[b]})
    for r in marg:
        if r['metric']=='original'and r['study']=='新增受控实验':
            e=next(x for x in rows(ROOT/'data/新增实验统计/marginal_rates.csv')if x['condition']==r['condition']);compare(r,e,[('count','pass_count'),('low','cluster_ci_low'),('high','cluster_ci_high')],r['condition'])
        elif r['metric']=='sensitivity':
            e=next(x for x in rows(csvfile('data/审计统计','S02'))if x['condition']==r['condition']);compare(r,e,[('count','relaxed_count'),('low','cluster_ci_low'),('high','cluster_ci_high')],r['condition'])
        else:
            e=next(x for x in rows(csvfile('data/统计表','01_'))if x['条件']==r['condition']);compare(r,e,[('count','通过数'),('low','聚类区间下限'),('high','聚类区间上限')],r['condition'])
    for r in paired:
        if r['metric']=='sensitivity':
            e=next(x for x in rows(csvfile('data/审计统计','S03'))if x['study']==r['study']and x['b']==r['b']);fields=[('difference','difference'),('low','cluster_ci_low'),('high','cluster_ci_high'),('a_only','a_only'),('b_only','b_only'),('holm_p','holm_p')]
        elif r['study']=='新增受控实验':
            e=next(x for x in rows(ROOT/'data/新增实验统计/paired_fixed_conditions.csv')if x['b']==r['b']);fields=[('difference','difference'),('low','cluster_ci_low'),('high','cluster_ci_high'),('a_only','a_only'),('b_only','b_only'),('holm_p','holm_p_planned_family')]
        else:
            e=next(x for x in rows(csvfile('data/统计表','02_'))if x['条件']==r['b']);fields=[('difference','五专员减对照'),('low','聚类区间下限'),('high','聚类区间上限'),('a_only','五专员独有通过'),('b_only','对照独有通过'),('holm_p','Holm校正P')]
        compare(r,e,fields,r['study']+'/'+r['metric']+'/'+r['b'])
    writecsv(out/'marginal_rates.csv',marg);writecsv(out/'paired_comparisons.csv',paired);dump(out/'statistics_report.json',{'verdict':'PASS'if not diffs else'FAIL','marginals':len(marg),'paired':len(paired),'bootstrap':100000,'seeds':[20261017,20261018,20261021],'differences':diffs})
    if diffs:raise ValueError('Statistics differs from archive: '+str(diffs[:3]))
def audit(out):
    import xml.etree.ElementTree as ET
    em,_=scoring_modules();audits=rows(ROOT/'initialization_audit/audit_25_models.csv');assert collections.Counter(r['classification']for r in audits)=={'合法替代':5,'实现依赖':20}
    endpoints=rows(ROOT/'experiments/endpoint_index.csv');count=0;tasks=set()
    for r in audits:
        jid=r['job_id'];folder=ROOT/'initialization_audit/evidence'/jid;c=read(folder/'审计判定.json');tasks.add(jid.split('__')[-1])
        for f,h in c['source_hash'].items():assert sha(folder/f)==h
        if (folder/'初始化证据链.json').exists():
            for f,h in read(folder/'初始化证据链.json')['input_sha256'].items():assert sha(folder/f)==h
        compiled=read(next(folder.glob('*_info.json')))['equations'];xml=ET.parse(next(folder.glob('*_init.xml'))).getroot();xmlvars={v.get('name'):v for v in xml.iter('ScalarVariable')}
        idx=next(x for x in endpoints if x['run_id']=='N::'+jid and x['stage']=='final');inp=read(ROOT/idx['input_path']);mat=resolve(inp['result_asset'])
        for ev in c['variables']:
            variable=ev['variable'];_,t,y,error=em._read_series(mat,variable);assert not error and t and t[0]==0 and math.isclose(y[0],float(ev['actual_initial_value']),rel_tol=1e-9,abs_tol=1e-9)
            assert math.isclose(y[0],float(ev['expected_initial_value']),rel_tol=1e-9,abs_tol=1e-9)
            for eq in json.loads(ev['compiled_initial_equations']):assert eq in compiled,(jid,variable,'compiled equation')
            evidence=ev.get('xml_alias_evidence')
            if evidence:
                a=ET.fromstring(evidence);b=xmlvars[a.get('name')];assert a.attrib==b.attrib
                for child in a:assert child.tag in [v.tag for v in b] and child.attrib==b.find(child.tag).attrib
            count+=1
    assert count==41 and len(tasks)==15
    dump(out/'audit_report.json',{'verdict':'PASS','models':25,'tasks':15,'variables':41,'effective_alternative':5,'implementation_dependent':20,'scope':'核查已有分类的证据身份与保存初值，不是新的独立语义标注；对应初始化诊断缺失状态保留'})
def resources(out):
    import statistics as st
    idx=[r for r in rows(ROOT/'experiments/endpoint_index.csv')if r['stage']=='final'and r['study']=='新增受控实验'];group=collections.defaultdict(list)
    for r in idx:
        p=ROOT/read(ROOT/r['input_path'])['source_record'];group[r['condition']].append(read(p.parent/'workflow.json'))
    expected=rows(csvfile('data/统一主数据','N15'));res=[]
    for c,rr in group.items():
        costs=[float(r['estimated_cost_usd'])for r in rr if r['cost_complete']]
        e=next(r for r in expected if r['condition']==c)
        row={'condition':c,'n':len(rr),'mean_api_calls':st.mean(r['llm_api_calls']for r in rr),'mean_wall_seconds':st.mean(r['case_wall_time_seconds']for r in rr),'mean_cost_complete_cases':st.mean(costs),'complete_cost_n':len(costs),'known_input_tokens_per_run':sum(r['token_usage'].get('input_tokens')or 0 for r in rr)/60,'known_output_tokens_per_run':sum(r['token_usage'].get('output_tokens_including_reasoning')or 0 for r in rr)/60,'missing_usage_calls':sum(r.get('token_usage_missing_calls',0)for r in rr)}
        for f in ['n','mean_api_calls','mean_wall_seconds','mean_cost_complete_cases','complete_cost_n']:assert math.isclose(row[f],float(e[f]),rel_tol=1e-10,abs_tol=1e-10),(c,f)
        role=[x for x in rows(csvfile('data/统一主数据','N02'))if x['condition']==c]
        for target,source in [('known_input_tokens_per_run','input_tokens'),('known_output_tokens_per_run','output_tokens')]:assert math.isclose(row[target],sum(float(x[source]or 0)for x in role)/60,rel_tol=1e-12,abs_tol=1e-9),(c,target)
        res.append(row)
    attempts=rows(ROOT/'resources/attempt_inventory.csv');assert len(attempts)==366
    incomplete=[r for r in attempts if r['selected_completed_attempt']!='True'];assert len(incomplete)==6
    ledger=[r for r in rows(ROOT/'resources/N16_simulation_event_ledger.csv')if r['selected_completed_attempt']=='True'];categories=collections.Counter(r['diagnostic_category']for r in ledger)
    assert len(ledger)==1683 and categories=={'success':1645,'model_translation_error':27,'source_syntax_error':5,'equation_system_error':4,'model_loading_error':1,'compiler_internal_error':1}
    writecsv(out/'resources.csv',res);dump(out/'resources_report.json',{'verdict':'PASS','workflows':360,'attempts':366,'incomplete_attempts':6,'known_incomplete_api_calls':sum(float(r['known_api_calls']or 0)for r in incomplete),'simulation_events':len(ledger),'simulation_categories':dict(categories),'cost_denominator':'complete cost records only; unknown usage not zero','source':'archived workflows and actual attempt ledger'})
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['verify','score','sensitivity','statistics','audit','resources','all']);p.add_argument('--out',default='reproduced');p.add_argument('--scope',choices=['endpoints','checkpoints'],default='endpoints');p.add_argument('--limit',type=int);a=p.parse_args();out=ROOT/a.out
    if a.command in ['verify','all']:print('VERIFIED',verify(out),flush=True)
    if a.command in ['score','all']:score(out,a.scope,a.limit)
    if a.command in ['sensitivity','all']:sensitivity(out)
    if a.command in ['statistics','all']:statistics(out)
    if a.command in ['audit','all']:audit(out)
    if a.command in ['resources','all']:resources(out)
    print('PASS',a.command,flush=True)
if __name__=='__main__':main()
