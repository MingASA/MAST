"""Plot archived scripted results, without running a model or changing data."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,default=Path('results/fact_basis_v1_offline/metrics.json'))
p.add_argument('--out',type=Path,default=Path('results/fact_basis_v1_figures_20260910'))
a=p.parse_args();rows=json.loads(a.source.read_text());a.out.mkdir(parents=True,exist_ok=False)
policies=['closure_only','conflict_triggered','verify_all','selective']
cases=['confirmed_basis','unconfirmed_settlement_basis','conflicting_basis','authority_unknown']
case_labels=['Confirmed','Hidden mismatch','Public conflict','Authority unknown']
labels=['Closure only','Conflict-triggered','Verify all facts','Selective facts']
fields=['unsafe_completed','error_accepting_organizations','fact_queries']
ylabels=['Unsupported completions / 4 tasks','Organizations accepting bad evidence','Fact verification queries']
colors=['#607d8b','#d99426','#3274a1','#238b68']
fig,axes=plt.subplots(1,3,figsize=(15,4.7))
for ax,field,title in zip(axes,fields,ylabels):
 for i,(policy,label,color) in enumerate(zip(policies,labels,colors)):
  vals=[next(r[field] for r in rows if r['case']==case and r['policy']==policy) for case in cases]
  bars=ax.bar([x+(i-1.5)*.2 for x in range(4)],vals,.19,label=label,color=color)
  ax.bar_label(bars,padding=2,fontsize=7)
 ax.set_xticks(range(4),case_labels,rotation=22,ha='right');ax.set_title(title,fontsize=11)
 ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
 ax.set_ylim(0,ax.get_ylim()[1]*1.12+0.2)
fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',ncol=4,bbox_to_anchor=(.5,.92),frameon=False)
fig.suptitle('Four fact-evidence policies: fixed scripted workflows (not live-model results)',fontsize=13)
fig.text(.02,.02,'Each case-policy cell: 1 workflow, 4 tasks. UNKNOWN means execution lacked confirmation, not proof of a false amount.\nSelective verification prevents final unsupported actions here, but can permit wider prior propagation. No population-rate claim.',fontsize=9)
fig.subplots_adjust(top=.77,bottom=.29,wspace=.28)
for suffix in ['png','svg','pdf']:fig.savefig(a.out/('four_policies_three_metrics.'+suffix),dpi=180)
with (a.out/'chart_data.csv').open('w',newline='') as stream:
 writer=csv.DictWriter(stream,fieldnames=['case','policy',*fields,'safe_completed']);writer.writeheader()
 writer.writerows({k:r[k] for k in writer.fieldnames} for r in rows)
(a.out/'provenance.json').write_text(json.dumps({'source':str(a.source),'sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'decision_source':'scripted','new_model_calls':0,'aggregation':'none; each case-policy cell plotted separately'},indent=2))
