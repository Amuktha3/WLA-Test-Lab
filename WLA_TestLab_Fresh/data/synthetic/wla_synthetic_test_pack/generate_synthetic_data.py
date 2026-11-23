from pathlib import Path
import pandas as pd, numpy as np, zipfile, json, shutil

out=Path('/mnt/data/wla_synthetic_test_pack')
if out.exists(): shutil.rmtree(out)
(out/'data').mkdir(parents=True)
(out/'scenarios').mkdir()
rng=np.random.default_rng(20261122)
countries=['France','Germany','Italy','Spain','United Kingdom']
currency={'France':'EUR','Germany':'EUR','Italy':'EUR','Spain':'EUR','United Kingdom':'GBP'}
shops=['ShopA','ShopB','ShopC','ShopD','ShopE']
start=pd.Timestamp('2026-01-01'); days=120
rows=[]; catalog=[]; truth=[]
scenario_templates=[
 ('stable_noise','Stable price with small daily jitter', 'NO_RESET', []),
 ('permanent_increase','Permanent price increase after a change date', 'RESET_UP', [('up',45,1.30)]),
 ('permanent_decrease','Permanent markdown', 'RESET_DOWN', [('down',55,0.72)]),
 ('temporary_promotion','Temporary discount then restoration', 'TEMP_PROMO', [('promo',40,0.65,12)]),
 ('single_spike','One-day extreme price spike then reversion', 'ANOMALY_SPIKE', [('spike',35,2.80)]),
 ('shop_switch','Lowest-price shop identity switches while price level stays similar', 'SHOP_SWITCH_ONLY', [('shop',50)]),
 ('gradual_drift','Gradual 18% drift over time', 'SUBTHRESHOLD_DRIFT', [('drift',30,1.18)]),
 ('persistent_noise','Volatile noise without a designed reset', 'NO_RESET_NOISY', []),
 ('gap_then_change','Large price change following an observation gap', 'GAP_CHANGE', [('gap',65),('up',70,1.35)]),
 ('two_resets','Two distinct permanent increases', 'MULTIPLE_RESETS', [('up',30,1.20),('up',78,1.25)]),
 ('short_reversal','Short-lived increase and reversal', 'SHORT_TRANSIENT', [('bump',50,1.35,3)]),
 ('small_change','Small permanent price adjustment below baseline threshold', 'SUBTHRESHOLD_CHANGE', [('up',60,1.12)]),
]
# create 15 series: first 12 patterns and 3 repeats with different scales/countries
for idx,(sid,desc,truth_label,events) in enumerate(scenario_templates[:12]):
    country=countries[idx%5]
    product=f'SYN-{idx+1:03d}'
    base=float(rng.uniform(80,600))
    price=np.full(days,base)
    # smooth small daily noise
    noise=rng.normal(0,0.012,days)
    price=price*(1+noise)
    shop_arr=np.array([shops[int(rng.integers(0,len(shops)))] for _ in range(days)],dtype=object)
    expected=[]
    for ev in events:
        typ=ev[0]; d=ev[1]
        if typ in ('up','down'):
            factor=ev[2]
            price[d:]*=factor
            expected.append({'country':country,'product_id':product,'expected_date':start+pd.Timedelta(days=d),'expected_type':typ.upper(),'expected_change_pct':(factor-1)*100,'scenario_id':sid,'notes':'Synthetic permanent level shift; approximate date.'})
        elif typ=='promo':
            factor,duration=ev[2],ev[3]
            price[d:d+duration]*=factor
            expected.append({'country':country,'product_id':product,'expected_date':start+pd.Timedelta(days=d),'expected_type':'TEMPORARY_DISCOUNT','expected_change_pct':(factor-1)*100,'scenario_id':sid,'notes':f'Temporary discount, reverts after {duration} days.'})
        elif typ=='spike':
            factor=ev[2]
            price[d]*=factor
            expected.append({'country':country,'product_id':product,'expected_date':start+pd.Timedelta(days=d),'expected_type':'SINGLE_DAY_SPIKE','expected_change_pct':(factor-1)*100,'scenario_id':sid,'notes':'One-day injected anomaly; reversion expected.'})
        elif typ=='shop':
            shop_arr[d:]= 'ShopZ'
            price[d:]*=1.015
            expected.append({'country':country,'product_id':product,'expected_date':start+pd.Timedelta(days=d),'expected_type':'SHOP_SWITCH','expected_change_pct':1.5,'scenario_id':sid,'notes':'Shop identity changes; price level approximately stable.'})
        elif typ=='drift':
            factor=ev[2]
            for k in range(d,days):
                frac=(k-d)/(days-d-1)
                price[k]*=(1+(factor-1)*frac)
            expected.append({'country':country,'product_id':product,'expected_date':start+pd.Timedelta(days=d),'expected_type':'GRADUAL_DRIFT','expected_change_pct':(factor-1)*100,'scenario_id':sid,'notes':'Gradual change, not a discrete jump.'})
        elif typ=='gap':
            # omit a stretch of dates to test gap handling
            gap_start=d; gap_end=d+4
            expected.append({'country':country,'product_id':product,'expected_date':start+pd.Timedelta(days=d+5),'expected_type':'OBSERVATION_GAP','expected_change_pct':None,'scenario_id':sid,'notes':'Five-day missing-data gap inserted before the subsequent price change.'})
        elif typ=='bump':
            factor,duration=ev[2],ev[3]
            price[d:d+duration]*=factor
            expected.append({'country':country,'product_id':product,'expected_date':start+pd.Timedelta(days=d),'expected_type':'SHORT_TRANSIENT_MOVE','expected_change_pct':(factor-1)*100,'scenario_id':sid,'notes':f'Transient rise reverts after {duration} days.'})
    # add low-amplitude autocorrelated-ish noise and clamp positive
    price=np.maximum(price,1)
    dates=[start+pd.Timedelta(days=i) for i in range(days)]
    # irregular gap scenario: remove days 65-69, keep price shift from day 70 onward
    if sid=='gap_then_change':
        price[70:]*=1.35
        dates=dates[:65]+dates[70:]
        price=np.concatenate([price[:65],price[70:]])
        shop_arr=np.concatenate([shop_arr[:65],shop_arr[70:]])
    for j,(date,p,shop) in enumerate(zip(dates,price,shop_arr)):
        rows.append({'country':country,'product_id':product,'day':date.strftime('%Y-%m-%d'),'lowest_price':round(float(p),2),'shop':shop})
    catalog.append({'country':country,'product_id':product,'category':['Consumer Electronics','Home Appliance','Small Appliance'][idx%3],'currency':currency[country],'scenario_id':sid,'scenario_description':desc,'base_price':round(base,2),'observations':len(dates)})
    truth.extend(expected)
# repeat 3 patterns with alternative countries and scales to bring total to 15 series
for j,src_idx in enumerate([1,3,9]):
    sid,desc,truth_label,events=scenario_templates[src_idx]
    country=countries[(src_idx+2)%5]; product=f'SYN-{13+j:03d}'
    base=float(rng.uniform(120,900)); price=base*(1+rng.normal(0,0.01,days)); shop_arr=np.array([shops[int(rng.integers(0,5))] for _ in range(days)],dtype=object)
    for ev in events:
        typ=ev[0]; d=ev[1]
        if typ in ('up','down'): price[d:]*=ev[2]
        elif typ=='promo': price[d:d+ev[3]]*=ev[2]
        elif typ=='shop': shop_arr[d:]= 'ShopZ'; price[d:]*=1.01
        elif typ=='spike': price[d]*=ev[2]
    for i in range(days): rows.append({'country':country,'product_id':product,'day':(start+pd.Timedelta(days=i)).strftime('%Y-%m-%d'),'lowest_price':round(float(max(1,price[i])),2),'shop':shop_arr[i]})
    catalog.append({'country':country,'product_id':product,'category':'Synthetic Test Series','currency':currency[country],'scenario_id':sid+'-replicate','scenario_description':'Replicate scenario with different price scale and country.','base_price':round(base,2),'observations':days})

# write combined data
raw=pd.DataFrame(rows).sort_values(['country','product_id','day']).reset_index(drop=True)
raw.to_csv(out/'data'/'synthetic_daily_prices.csv',index=False)
pd.DataFrame(catalog).to_csv(out/'data'/'synthetic_products_catalog.csv',index=False)
truthdf=pd.DataFrame(truth)
truthdf.to_csv(out/'data'/'synthetic_scenario_expectations.csv',index=False)
# scenario catalog
sc=pd.DataFrame([{'scenario_id':sid,'description':desc,'expected_behavior':label,'design':json.dumps(ev)} for sid,desc,label,ev in scenario_templates])
sc.to_csv(out/'data'/'scenario_catalog.csv',index=False)
# separate scenario files for ease of manual testing
for item in catalog:
    subset=raw[(raw.country==item['country'])&(raw.product_id==item['product_id'])]
    subset.to_csv(out/'scenarios'/f"{item['product_id']}_{item['scenario_id']}.csv",index=False)
readme='''# WLA Synthetic Prototype Test Pack\n\n**All data in this pack is synthetic. Do not mix it with the real research dataset or report.**\n\n## Files\n- `data/synthetic_daily_prices.csv`: combined dataset using the prototype's raw-price schema (`country, product_id, day, lowest_price, shop`).\n- `data/synthetic_products_catalog.csv`: product/scenario metadata.\n- `data/synthetic_scenario_expectations.csv`: designed scenario transitions; use as test expectations, not ground-truth accuracy claims.\n- `data/scenario_catalog.csv`: scenario descriptions.\n- `scenarios/`: individual per-series CSVs.\n\n## Scenarios represented\nStable series with small noise; permanent price increase; permanent decrease; temporary discount and restoration; one-day spike; lowest-price shop switch with near-stable level; gradual sub-threshold drift; noisy stable series; a gap before a price change; two permanent resets; short transient bump; small sub-threshold change. Several scenarios are replicated at different price scales/countries.\n\n## How to use with WLA\n1. Keep your original `pome` project untouched.\n2. Open `data/synthetic_daily_prices.csv` in the Data Table Explorer (or load it separately for testing data/plots).\n3. Test price-history visualization with `country` + `product_id` filters and date ranges.\n4. Compare your detector's output against `synthetic_scenario_expectations.csv` **manually**. A designed synthetic scenario is useful for checking whether code responds as intended, but it is not a real-world benchmark and does not validate the research claims.\n5. If you want to test the dashboard end-to-end with this pack, a separate synthetic project-root fixture is required because the dashboard reads many Phase 4–7 output files. This pack intentionally does not overwrite or imitate the real final results.\n\n## Reproducibility\nGenerator seed: `20261122`. Date range: 2026-01-01 onward, 120 nominal days.\n'''
(out/'README.md').write_text(readme,encoding='utf-8')
# generator script copy
shutil.copy('/mnt/data/create_wla_synthetic_pack.py',out/'generate_synthetic_data.py')
# archive
zip_path=Path('/mnt/data/WLA_Synthetic_Prototype_Test_Pack.zip')
if zip_path.exists(): zip_path.unlink()
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
 for p in out.rglob('*'):
  if p.is_file(): z.write(p,p.relative_to(out.parent))
# basic checks
print('rows',len(raw),'series',raw[['country','product_id']].drop_duplicates().shape[0], 'scenario expectation rows',len(truthdf))
print('size',zip_path.stat().st_size)
