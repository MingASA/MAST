import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(csv_path: Path, out: Path):
    with csv_path.open() as stream: rows=list(csv.DictReader(stream))
    scenarios=sorted({r['scenario'] for r in rows})
    fig,axes=plt.subplots(1,len(scenarios),figsize=(6*len(scenarios),4),squeeze=False)
    protocols=('black_box','certificate','verified_certificate')
    for ax,scenario in zip(axes[0],scenarios):
        for offset,objective in ((-.18,'selfish'),(.18,'resp')):
            means=[]; deviations=[]
            for protocol in protocols:
                vals=[float(r['observed_poa']) for r in rows if r['scenario']==scenario and r['protocol']==protocol and r['objective']==objective and r['observed_poa']]
                means.append(float(np.mean(vals)) if vals else np.nan)
                deviations.append(float(np.std(vals)) if vals else 0.)
            ax.bar(np.arange(3)+offset,means,.36,label=objective,yerr=deviations)
        ax.set_xticks(range(3),['Black box','Certificate','Verified cert.'])
        ax.axhline(1,color='gray',linestyle='--',linewidth=1)
        ax.set_title(scenario); ax.set_ylabel('Observed equilibrium / social optimum'); ax.legend()
    fig.suptitle('Synthetic parameters; sampled pure equilibria (not exhaustive PoA)')
    fig.tight_layout(); out.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(out,dpi=180); fig.savefig(out.with_suffix('.svg')); plt.close(fig)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--csv',type=Path,default=Path('results/poa.csv'))
    parser.add_argument('--out',type=Path,default=Path('results/poa.png')); args=parser.parse_args()
    plot(args.csv,args.out)


if __name__=='__main__': main()
