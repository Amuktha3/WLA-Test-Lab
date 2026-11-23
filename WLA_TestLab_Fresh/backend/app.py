from pathlib import Path
import io, json, uuid
from datetime import datetime
from typing import Optional
import numpy as np
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
SYN_ROOT = ROOT / 'data' / 'synthetic' / 'wla_synthetic_test_pack'
APP = FastAPI(title='WLA Detector Test Lab', version='0.2.0')
STATE = {'dataset': None, 'source': 'synthetic', 'name': 'Synthetic test pack', 'scenario_id': 'stable_noise',
         'config': {'reset_threshold':30, 'anomaly_threshold':50, 'persistence':2, 'direction':'upward_only'},
         'runs':[], 'latest_run':None}
REQUIRED = ['country','product_id','day','lowest_price']


def find_real_dataset():
    candidates=[ROOT.parent/'phase6c1_arrow_inspection'/'daily_prices_europe-retail-price-history-5-countries-train_FULL.csv', ROOT/'phase6c1_arrow_inspection'/'daily_prices_europe-retail-price-history-5-countries-train_FULL.csv']
    for c in candidates:
        if c.exists(): return c
    try:
        for c in ROOT.parent.glob('*/phase6c1_arrow_inspection/daily_prices_europe-retail-price-history-5-countries-train_FULL.csv'):
            if c.exists(): return c
    except Exception: pass
    return None

def pack_file(name):
    direct=SYN_ROOT/'data'/name
    if direct.exists(): return direct
    hits=list((ROOT/'data'/'synthetic').rglob(name))
    return hits[0] if hits else None

def load_synthetic():
    p=pack_file('synthetic_daily_prices.csv')
    if not p: raise RuntimeError('Synthetic pack is missing. Check the data/synthetic folder.')
    return pd.read_csv(p)
def catalog():
    p=pack_file('scenario_catalog.csv')
    return pd.read_csv(p).fillna('').to_dict('records') if p else []
def expectations():
    p=pack_file('synthetic_scenario_expectations.csv')
    return pd.read_csv(p).fillna('').to_dict('records')
def scenario_product_id(sid):
    for i,x in enumerate(catalog(),1):
        if str(x.get('scenario_id'))==str(sid): return f'SYN-{i:03d}'
    return None
def current_df():
    if STATE['dataset'] is not None: return STATE['dataset'].copy()
    df=load_synthetic(); pid=scenario_product_id(STATE['scenario_id'])
    return df[df.product_id.astype(str)==str(pid)].copy()
def normalized_df(df):
    df=df.copy()
    aliases={'country':['country','nation'],'product_id':['product_id','product','sku'],'day':['day','date','datetime'],'lowest_price':['lowest_price','price','amount'],'shop':['shop','store','retailer']}
    lower={str(c).lower():c for c in df.columns}; mapping={}
    for target,options in aliases.items():
        for o in options:
            if o in lower: mapping[lower[o]]=target; break
    df=df.rename(columns=mapping)
    missing=[x for x in REQUIRED if x not in df.columns]
    if missing: raise ValueError('Missing required columns: '+', '.join(missing))
    if 'shop' not in df: df['shop']='Unknown'
    df['day']=pd.to_datetime(df.day,errors='coerce')
    df['lowest_price']=pd.to_numeric(df.lowest_price,errors='coerce')
    return df
def schema_stats(df):
    try: valid=normalized_df(df)
    except Exception: valid=df.copy()
    stats={'rows':len(df),'countries':int(df.country.nunique()) if 'country' in df else 0,'products':int(df.product_id.nunique()) if 'product_id' in df else 0,
           'missing_values':int(df.isna().sum().sum()),'invalid_dates':int(valid.day.isna().sum()) if 'day' in valid else None,
           'invalid_prices':int((valid.lowest_price.isna() | (valid.lowest_price<=0)).sum()) if 'lowest_price' in valid else None,
           'schema_missing':[x for x in REQUIRED+['shop'] if x not in df.columns],
           'date_min':str(valid.day.min().date()) if 'day' in valid and valid.day.notna().any() else None,
           'date_max':str(valid.day.max().date()) if 'day' in valid and valid.day.notna().any() else None,
           'price_median':float(valid.lowest_price.median()) if 'lowest_price' in valid else None,
           'price_min':float(valid.lowest_price.min()) if 'lowest_price' in valid else None,
           'price_max':float(valid.lowest_price.max()) if 'lowest_price' in valid else None}
    return stats

# Research implementation copied from wla_sensitivity_experiment.py and adapted to reusable functions.
def symmetric_pct_difference(a,b):
    a,b=abs(float(a)),abs(float(b)); denominator=(a+b)/2
    return 0 if denominator==0 else abs(a-b)/denominator*100
def pct_change(new,old):
    return np.nan if old==0 else (new-old)/old*100
def flag_anomalies(prices,threshold,window=3,tolerance=15):
    prices=np.asarray(prices,dtype=float); flags=np.zeros(len(prices),dtype=bool)
    for i in range(window,len(prices)-window):
        before=prices[i-window:i]; after=prices[i+1:i+1+window]
        mb=np.median(before); ma=np.median(after); current=prices[i]
        db=symmetric_pct_difference(current,mb); da=symmetric_pct_difference(current,ma); nd=symmetric_pct_difference(mb,ma)
        if db>=threshold and da>=threshold and nd<=tolerance: flags[i]=True
    return flags
def replace_anomalies(prices,flags,window=3):
    original=np.asarray(prices,dtype=float); robust=original.copy()
    for i in np.where(flags)[0]:
        left=max(0,i-window); right=min(len(original),i+window+1)
        neighbors=[j for j in range(left,right) if j!=i and not flags[j]]
        if neighbors: robust[i]=np.median(original[neighbors])
    return robust
def detect_resets(dates,prices,threshold,persistence=2,direction='upward_only'):
    dates=np.asarray(dates); prices=np.asarray(prices,dtype=float); events=[]
    for i in range(1,len(prices)):
        old=float(prices[i-1]); new=float(prices[i])
        if old<=0: continue
        change=pct_change(new,old)
        if direction=='upward_only':
            if change<threshold: continue
            dir_label='up'
            predicate=lambda p: pct_change(float(p),old)>=threshold
        else:
            if abs(change)<threshold: continue
            dir_label='up' if change>0 else 'down'
            predicate=(lambda p: pct_change(float(p),old)>=threshold) if change>0 else (lambda p: pct_change(float(p),old)<=-threshold)
        end_index=i+1+persistence
        if end_index>len(prices): continue
        future=prices[i+1:end_index]
        sustained=sum(bool(predicate(p)) for p in future)
        if sustained>=persistence:
            events.append({'event_date':pd.Timestamp(dates[i]),'previous_price':old,'reset_price':new,'pct_change':float(change),'direction':dir_label,'index':i})
    return events
def match_events(expected,detected,tolerance_days=3):
    unused=set(range(len(detected))); pairs=[]; unmatched_expected=[]
    for exp in sorted(expected,key=lambda x:x['date']):
        candidates=[]
        for j in unused:
            d=detected[j]
            if exp['direction']!=d['direction']: continue
            delta=abs((exp['date']-d['date']).days)
            if delta<=tolerance_days: candidates.append((delta,j))
        if candidates:
            candidates.sort(); delta,j=candidates[0]; unused.remove(j); pairs.append((exp,detected[j],delta))
        else: unmatched_expected.append(exp)
    return pairs,unmatched_expected,[detected[j] for j in unused]
def run_series(group,cfg):
    group=group.sort_values('day').copy(); dates=group.day.to_numpy(); raw=np.asarray(group.lowest_price,dtype=float)
    flags=flag_anomalies(raw,cfg['anomaly_threshold'],window=3,tolerance=15)
    flag_only=raw.copy(); robust=replace_anomalies(raw,flags,window=3)
    raw_events=detect_resets(dates,raw,cfg['reset_threshold'],cfg['persistence'],cfg['direction'])
    flag_events=detect_resets(dates,flag_only,cfg['reset_threshold'],cfg['persistence'],cfg['direction'])
    robust_events=detect_resets(dates,robust,cfg['reset_threshold'],cfg['persistence'],cfg['direction'])
    return {'dates':dates,'prices':raw,'robust_prices':robust,'flags':flags,'raw_events':raw_events,'flag_only_events':flag_events,'robust_events':robust_events}
def json_event(e):
    return {**e,'event_date':pd.Timestamp(e['event_date']).strftime('%Y-%m-%d')}
def evaluate(expected,detected,tolerance_days=3):
    ex=[]
    for e in expected:
        typ=str(e.get('expected_type','')).upper(); direction='up' if typ in ('UP','UPWARD','INCREASE') else 'down' if typ in ('DOWN','DOWNWARD','DECREASE') else None
        if direction and direction in ('up','down'):
            ex.append({'date':pd.Timestamp(e['expected_date']),'direction':direction,'expected_change_pct':float(e.get('expected_change_pct') or 0),'notes':e.get('notes','')})
    # In baseline upward-only mode, downward expectations are intentionally not counted.
    if STATE['config']['direction']=='upward_only': ex=[e for e in ex if e['direction']=='up']
    pairs,miss,fp=match_events(ex,[{'date':pd.Timestamp(d['event_date']),'direction':d['direction'],**d} for d in detected],tolerance_days)
    tp=len(pairs); fn=len(miss); fpn=len(fp)
    precision=tp/(tp+fpn) if tp+fpn else None
    recall=tp/(tp+fn) if tp+fn else None
    f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
    return {'tp':tp,'fp':fpn,'fn':fn,'precision':precision,'recall':recall,'f1':f1,'matched':[{ 'expected_date':p[0]['date'].strftime('%Y-%m-%d'),'detected_date':p[1]['date'].strftime('%Y-%m-%d'),'days_delta':p[2],'direction':p[0]['direction']} for p in pairs],'missed':[{'date':x['date'].strftime('%Y-%m-%d'),'direction':x['direction']} for x in miss],'false_positives':[{'date':x['date'].strftime('%Y-%m-%d'),'direction':x['direction']} for x in fp],'evaluated_expected':len(ex),'excluded_expected':len(expected)-len(ex)}

@APP.get('/api/health')
def health(): return {'status':'online','detector_connected':True,'message':'Research detector adapter loaded and executable.'}
@APP.get('/api/scenarios')
def get_scenarios(): return {'scenarios':catalog(),'expectations':expectations()}
@APP.get('/api/datasets')
def datasets_available():
    p=find_real_dataset(); return {'real_dataset_available':bool(p),'real_dataset_path':str(p) if p else None,'synthetic_scenarios':len(catalog())}
@APP.get('/api/dataset')
def dataset_info():
    df=current_df(); stats=schema_stats(df)
    cat=catalog(); row=next((x for x in cat if str(x.get('scenario_id'))==STATE['scenario_id']),None) if STATE['source']=='synthetic' else None
    return {'source':STATE['source'],'name':STATE['name'],'scenario_id':STATE['scenario_id'],'description':row.get('description','') if row else ('Uploaded dataset' if STATE['source']=='upload' else ''),'expected_behavior':row.get('expected_behavior','') if row else '', 'scenario_design':row.get('design','') if row else '', 'stats':stats,'columns':list(df.columns)}
@APP.get('/api/series')
def series(country:Optional[str]=None,product:Optional[str]=None):
    df=normalized_df(current_df()).dropna(subset=['day','lowest_price']).sort_values('day')
    countries=sorted(df.country.astype(str).unique()); all_products=sorted(df.product_id.astype(str).unique())
    country_value=country or 'ALL'; product_value=product or 'ALL'
    if country_value!='ALL': df=df[df.country.astype(str)==country_value]
    products=sorted(df.product_id.astype(str).unique())
    if product_value!='ALL': df=df[df.product_id.astype(str)==product_value]
    grouped=[]
    for (c,p),g in df.groupby(['country','product_id']):
        g=g.sort_values('day'); records=g[['day','lowest_price','shop']].copy(); records['day']=records.day.dt.strftime('%Y-%m-%d')
        grouped.append({'country':str(c),'product':str(p),'label':f'{c} · {p}','points':records.to_dict('records')})
    # For all countries, show country comparisons for one selected product by default, avoiding an unreadable 49-product plot.
    if country_value=='ALL' and product_value=='ALL' and len(all_products):
        product_value=all_products[0]
        grouped=[x for x in grouped if x['product']==product_value]
    # Single-country view defaults to that country's first available product when none is selected.
    if country_value!='ALL' and product_value=='ALL' and grouped:
        product_value=grouped[0]['product']; grouped=[x for x in grouped if x['product']==product_value]
    selected_country=country_value if country_value!='ALL' else 'ALL'
    points=grouped[0]['points'] if len(grouped)==1 else []
    return {'country':selected_country,'product':product_value,'points':points,'series':grouped,'countries':countries,'products':products}
@APP.post('/api/select-scenario')
def select_scenario(payload:dict):
    sid=payload.get('scenario_id'); pid=scenario_product_id(sid); df=load_synthetic(); df=df[df.product_id.astype(str)==str(pid)]
    if df.empty: raise HTTPException(404,'Scenario not found in synthetic data pack')
    STATE.update(dataset=None,source='synthetic',name=f'Synthetic · {sid}',scenario_id=sid,latest_run=None)
    return dataset_info()
@APP.post('/api/select-real')
def select_real_dataset():
    p=find_real_dataset()
    if not p: raise HTTPException(404,'Research dataset not found in expected location. Upload it manually.')
    df=pd.read_csv(p); df=normalized_df(df)
    STATE.update(dataset=df,source='real',name=p.name,scenario_id=None,latest_run=None)
    return dataset_info()
@APP.post('/api/upload')
async def upload_dataset(file:UploadFile=File(...)):
    name=file.filename or 'uploaded'; raw=await file.read()
    try:
        if name.lower().endswith('.xlsx'): df=pd.read_excel(io.BytesIO(raw))
        elif name.lower().endswith('.tsv'): df=pd.read_csv(io.BytesIO(raw),sep='\t')
        elif name.lower().endswith('.json'): df=pd.read_json(io.BytesIO(raw))
        else: df=pd.read_csv(io.BytesIO(raw))
        df=normalized_df(df)
    except Exception as e: raise HTTPException(400,str(e))
    STATE.update(dataset=df,source='upload',name=name,scenario_id=None,latest_run=None)
    return dataset_info()
@APP.get('/api/preview')
def preview(limit:int=100):
    df=current_df().head(max(1,min(limit,500))).copy(); df['day']=df.day.astype(str)
    return {'columns':list(df.columns),'rows':df.fillna('').astype(str).to_dict('records')}
@APP.post('/api/config')
def set_config(payload:dict):
    allowed={'reset_threshold','anomaly_threshold','persistence','direction'}; cfg=STATE['config']
    for k,v in payload.items():
        if k not in allowed: continue
        if k=='direction' and v not in ('upward_only','bidirectional'): raise HTTPException(400,'Unsupported direction option')
        if k in ('reset_threshold','anomaly_threshold'):
            try: v=float(v)
            except: raise HTTPException(400,f'{k} must be numeric')
            if v<1 or v>200: raise HTTPException(400,f'{k} must be 1–200')
        if k=='persistence':
            v=int(v)
            if v<1 or v>5: raise HTTPException(400,'persistence must be 1–5')
        cfg[k]=v
    return cfg
@APP.post('/api/run')
def run_detector():
    df=normalized_df(current_df()).dropna(subset=['country','product_id','day','lowest_price']).copy(); df=df[df.lowest_price>0]
    df=df.sort_values(['country','product_id','day']).drop_duplicates(['country','product_id','day'],keep='last')
    cfg=STATE['config'].copy(); raw_count=robust_count=flag_count=anomaly_count=0; all_raw=[]; all_flag=[]; all_robust=[]; eval_rows=[]; series_results=[]
    exp_all=expectations(); sid=STATE['scenario_id']
    for (country,product),g in df.groupby(['country','product_id']):
        result=run_series(g,cfg); raw_count+=len(result['raw_events']); flag_count+=len(result['flag_only_events']); robust_count+=len(result['robust_events']); anomaly_count+=int(result['flags'].sum())
        for mode,evs,target in [('raw',result['raw_events'],all_raw),('flag_only',result['flag_only_events'],all_flag),('robust',result['robust_events'],all_robust)]:
            for e in evs: target.append({'country':str(country),'product_id':str(product),'mode':mode,**json_event(e)})
        if sid:
            exp=[e for e in exp_all if str(e.get('scenario_id'))==str(sid) and str(e.get('product_id'))==str(product) and str(e.get('country'))==str(country)]
            metrics=evaluate(exp,result['robust_events'])
            eval_rows.append({'country':str(country),'product_id':str(product),'metrics':metrics})
        series_results.append({'country':str(country),'product_id':str(product),'observations':len(g),'anomaly_count':int(result['flags'].sum()),'raw_events':len(result['raw_events']),'flag_only_events':len(result['flag_only_events']),'robust_events':len(result['robust_events'])})
    run={'id':uuid.uuid4().hex[:8],'created_at':datetime.now().isoformat(timespec='seconds'),'dataset':STATE['name'],'source':STATE['source'],'scenario_id':STATE['scenario_id'],'config':cfg,'summary':{'series':len(series_results),'observations':len(df),'anomalies':anomaly_count,'raw_events':raw_count,'flag_only_events':flag_count,'robust_events':robust_count},'events':{'raw':all_raw,'flag_only':all_flag,'robust':all_robust},'series':series_results,'evaluation':eval_rows}
    STATE['latest_run']=run; STATE['runs'].insert(0,run); return run
@APP.post('/api/experiments')
def run_sensitivity_experiment():
    if STATE['source']!='synthetic':
        raise HTTPException(400,'Sensitivity experiments and ground-truth evaluation are available only for synthetic scenarios. Select a synthetic scenario first.')
    df=normalized_df(current_df()).dropna(subset=['country','product_id','day','lowest_price']).copy(); df=df[df.lowest_price>0]
    exp_all=expectations(); sid=STATE['scenario_id']; baseline=STATE['config'].copy(); results=[]
    for rt in [20,30,40,50]:
      for at in [30,50,70]:
       for pers in [1,2,3]:
        cfg={**baseline,'reset_threshold':rt,'anomaly_threshold':at,'persistence':pers}
        tp=fp=fn=0; total_events=0; evaluated=0
        for (country,product),g in df.groupby(['country','product_id']):
          res=run_series(g,cfg); total_events+=len(res['robust_events'])
          exp=[e for e in exp_all if str(e.get('scenario_id'))==str(sid) and str(e.get('product_id'))==str(product) and str(e.get('country'))==str(country)]
          m=evaluate(exp,res['robust_events']); tp+=m['tp']; fp+=m['fp']; fn+=m['fn']; evaluated+=m['evaluated_expected']
        precision=tp/(tp+fp) if tp+fp else None; recall=tp/(tp+fn) if tp+fn else None
        f1=2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
        results.append({'reset_threshold':rt,'anomaly_threshold':at,'persistence':pers,'robust_events':total_events,'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,'f1':f1,'expected_events_evaluated':evaluated})
    return {'scenario_id':sid,'runs':len(results),'results':results}

@APP.get('/api/latest-run')
def latest_run(): return STATE['latest_run']
@APP.get('/api/runs')
def runs(): return {'runs':STATE['runs']}
@APP.get('/api/export-events')
def export_events(mode:str='robust'):
    run=STATE['latest_run']
    if not run: raise HTTPException(404,'Run detector first')
    if mode not in run['events']: raise HTTPException(400,'Mode must be raw, flag_only, or robust')
    rows=run['events'][mode]
    out=io.StringIO(); fields=['country','product_id','mode','event_date','previous_price','reset_price','pct_change','direction']
    rows=[{k:v for k,v in row.items() if k in fields} for row in rows]
    writer=__import__('csv').DictWriter(out,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    return StreamingResponse(iter([out.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename=wla_{mode}_events.csv'})
@APP.get('/api/expectations')
def get_expectations():
    sid=STATE['scenario_id']; return {'rows':[x for x in expectations() if str(x.get('scenario_id'))==str(sid)]}

@APP.get('/api/scenario-analysis')
def scenario_analysis():
    sid=STATE['scenario_id']
    row=next((x for x in catalog() if str(x.get('scenario_id'))==str(sid)),None)
    exp=[x for x in expectations() if str(x.get('scenario_id'))==str(sid)]
    behavior=str(row.get('expected_behavior','')) if row else ''
    non_reset={'NO_RESET','NO_RESET_NOISY','SUBTHRESHOLD_DRIFT','SUBTHRESHOLD_CHANGE','ANOMALY_SPIKE','SHOP_SWITCH_ONLY','TEMP_PROMO','SHORT_TRANSIENT'}
    latest=STATE.get('latest_run')
    matching=bool(latest and latest.get('source')=='synthetic' and latest.get('scenario_id')==sid)
    robust_count=latest['summary']['robust_events'] if matching else None
    if behavior in non_reset:
        verdict='Expected outcome: no permanent upward reset. A zero-event result is a PASS; any detected event is flagged for inspection.'
        status=('PASS · no reset detected' if matching and robust_count==0 else 'REVIEW · detector produced event(s)' if matching else 'NOT RUN')
    elif behavior=='RESET_DOWN':
        verdict='Expected markdown. The upward-only baseline intentionally excludes this event; use bidirectional mode to test it.'
        status=('EXPECTED · downward reset excluded by baseline' if matching and STATE['config']['direction']=='upward_only' else 'TEST BIDIRECTIONAL · inspect downward event' if matching else 'NOT RUN')
    elif behavior=='GAP_CHANGE':
        verdict='Expected upward shift after a missing-data gap. Detection can be delayed or missed because the series is discontinuous.'
        status=('PASS · expected upward event matched' if matching and latest.get('evaluation') and latest['evaluation'][0]['metrics']['tp']>0 else 'MISS · expected event not matched' if matching else 'NOT RUN')
    elif behavior=='MULTIPLE_RESETS':
        expected_up=sum(1 for e in exp if str(e.get('expected_type','')).upper() in ('UP','UPWARD','INCREASE'))
        tp=latest['evaluation'][0]['metrics']['tp'] if matching and latest.get('evaluation') else 0
        verdict=f'Expected {expected_up} upward level shifts. Check sensitivity: noisy realized jumps may fall below the threshold.'
        status=(f'PARTIAL/PASS · {tp} of {expected_up} expected events matched' if matching and tp>0 else 'MISS · no expected events matched' if matching else 'NOT RUN')
    elif behavior=='RESET_UP':
        tp=latest['evaluation'][0]['metrics']['tp'] if matching and latest.get('evaluation') else 0
        verdict='Expected one permanent upward level shift. Lower reset threshold may reveal it if noise makes the realized jump smaller than the design percentage.'
        status=('PASS · expected upward event matched' if matching and tp>0 else 'MISS · expected upward event not matched' if matching else 'NOT RUN')
    else:
        verdict='Scenario context is unavailable; interpret event output cautiously.'
        status='NOT RUN' if not matching else 'REVIEW'
    return {'scenario_id':sid,'expected_behavior':behavior,'expected_events':exp,'interpretation':verdict,'status':status,'detected_robust_events':robust_count,'direction':STATE['config']['direction'],'reset_threshold':STATE['config']['reset_threshold'],'anomaly_threshold':STATE['config']['anomaly_threshold'],'persistence':STATE['config']['persistence']}
APP.mount('/',StaticFiles(directory=ROOT/'frontend',html=True),name='frontend')
