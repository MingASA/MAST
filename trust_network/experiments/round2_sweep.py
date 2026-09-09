"""Versioned per-start omission sweeps and one-expanded-node role ablations."""
import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass,asdict,replace
from pathlib import Path
from trust_network.core.graph import Graph
from trust_network.scenarios.synthetic import synthetic_random,SyntheticConfig
from trust_network.scenarios.letter_of_credit import (letter_of_credit,role_mismatches,RoleAblationConfig,letter_of_credit_ablation)
from trust_network.solve.settlement import ProportionalWithOmission
from trust_network.solve.decentralized_game import DecentralizedGame,GameConfig,PROTOCOLS,price_of_anarchy
from trust_network.solve.verification_metrics import expected_checks,planner_metrics,over_check_ratio
from trust_network.solve.global_dp import GlobalDP,DPConfig
from trust_network.experiments.run_sweep import centralized_value


@dataclass(frozen=True)
class ExperimentCase:
    name: str
    seed: int
    graph: Graph
    ablation_node: str = ''
    alignment: str = 'baseline'


@dataclass(frozen=True)
class ExperimentTarget:
    name: str
    objective: str
    omission_weight: float | None = None


@dataclass(frozen=True)
class StartRow:
    scenario: str
    seed: int
    ablation_node: str
    alignment: str
    protocol: str
    target: str
    w_omit: float | None
    start: int
    converged: bool
    rounds: int
    social_cost: float
    social_optimum: float
    observed_poa: float | None
    expected_checks: float
    optimal_checks: float
    over_check_ratio: float
    exploitability: float


def write_csv(path,rows):
    with path.open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def evaluate_case(case,targets,budget=1.2):
    rows=[]; witnesses=[]
    numeric=GlobalDP(case.graph,DPConfig(budget,10001)).value()
    for protocol in PROTOCOLS:
        for target in targets:
            rule=None if target.omission_weight is None else ProportionalWithOmission(w_omit=target.omission_weight)
            game=DecentralizedGame(case.graph,GameConfig(budget,protocol,target.objective,allocation=rule))
            optimum=centralized_value(game); planner=planner_metrics(game)
            assert abs(numeric-optimum)<1e-3
            for start in (0,1):
                result=game.solve({k:start for k in game.keys})
                checks=expected_checks(game,dict(result.strategy))
                converged=result.converged and result.exploitability<1e-8
                ratio=price_of_anarchy(result.social,optimum) if converged else None
                row=StartRow(case.name,case.seed,case.ablation_node,case.alignment,protocol,target.name,target.omission_weight,start,
                             converged,result.rounds,result.social,optimum,ratio,checks,planner.expected_checks,
                             over_check_ratio(checks,planner.expected_checks),result.exploitability)
                rows.append(asdict(row))
                if not converged: witnesses.append({'row':asdict(row),'oscillation':result.oscillation})
            print(f'{case.name}/{case.ablation_node}/{case.alignment} {protocol} {target.name}: '+', '.join('cycle' if r['observed_poa'] is None else f"PoA={r['observed_poa']:.5f}, checks={r['over_check_ratio']:.5f}" for r in rows[-2:]),flush=True)
    return rows,witnesses


def aggregate(rows):
    grouped=defaultdict(list)
    for row in rows:
        key=tuple(row[k] for k in ('scenario','seed','ablation_node','alignment','protocol','target'))
        grouped[key].append(row)
    output=[]
    for group in grouped.values():
        equilibria=[r for r in group if r['converged']]
        selected=max(equilibria or group,key=lambda r:r['social_cost'])
        row=dict(selected); row.pop('start')
        row['converged_starts']=len(equilibria); row['starts']=len(group)
        row['check_ratio_min']=min(r['over_check_ratio'] for r in equilibria) if equilibria else None
        row['check_ratio_max']=max(r['over_check_ratio'] for r in equilibria) if equilibria else None
        output.append(row)
    return output


def save(out,rows,witnesses):
    write_csv(out/'by_start.csv',rows)
    summary=aggregate(rows); write_csv(out/'summary.csv',summary)
    (out/'cycles.json').write_text(json.dumps(witnesses,indent=2))
    return summary


def omission_sweep(out):
    out.mkdir(parents=True,exist_ok=False)
    targets=(ExperimentTarget('selfish','selfish'),ExperimentTarget('resp-Proportional','resp'),
             *(ExperimentTarget(f'resp-Omission@{w:g}','resp',w) for w in (0.,.5,1.,2.)))
    cases=[ExperimentCase('synthetic',s,synthetic_random(SyntheticConfig(seed=s))) for s in (7,11,23)]
    cases.append(ExperimentCase('letter_of_credit',0,letter_of_credit()))
    rows=[]; witnesses=[]
    for case in cases:
        new,cycles=evaluate_case(case,targets); rows+=new; witnesses+=cycles
    summary=save(out,rows,witnesses)
    legacy={}
    with Path('results/poa.csv').open() as stream:
        for row in csv.DictReader(stream): legacy[(row['scenario'],int(row['seed']),row['protocol'],row['objective'])]=row
    historical_starts={}
    for detail in json.loads(Path('results/sweep_details.json').read_text()):
        for start,item in enumerate(detail['starts']):
            historical_starts[(detail['scenario'],detail['seed'],detail['protocol'],detail['objective'],start)]=item['cost']
    comparison=[]
    for row in rows:
        if row['target']!='resp-Omission@0': continue
        old=next(r for r in rows if all(r[k]==row[k] for k in ('scenario','seed','protocol','start')) and r['target']=='resp-Proportional')
        assert row['observed_poa']==old['observed_poa']
        assert row['over_check_ratio']==old['over_check_ratio']
        historical_row=legacy[(row['scenario'],row['seed'],row['protocol'],'resp')]
        historical_cost=historical_starts[(row['scenario'],row['seed'],row['protocol'],'resp',row['start'])]
        historical=historical_cost/float(historical_row['social_optimum'])
        assert old['social_cost']==historical_cost and old['observed_poa']==historical
        comparison.append({k:row[k] for k in ('scenario','seed','protocol','start')} | {
            'historical_poa':historical,'legacy_poa':old['observed_poa'],'omission0_poa':row['observed_poa'],
            'legacy_over_check_ratio_recomputed':old['over_check_ratio'],'omission0_over_check_ratio':row['over_check_ratio'],
            'poa_exact_equal':True,'over_check_exact_equal':True})
    write_csv(out/'zero_weight_regression.csv',comparison)
    for row in summary:
        if row['target']=='resp-Proportional':
            assert row['observed_poa']==float(legacy[(row['scenario'],row['seed'],row['protocol'],'resp')]['observed_poa'])
    trends=[]
    for case in cases:
        for protocol in PROTOCOLS:
            group=[r for r in summary if r['scenario']==case.name and r['seed']==case.seed and r['protocol']==protocol and r['w_omit'] is not None]
            group.sort(key=lambda r:r['w_omit'])
            valid=all(r['converged'] for r in group)
            trends.append({'scenario':case.name,'seed':case.seed,'protocol':protocol,'all_weights_have_equilibrium':valid,
                           'poa_nondecreasing':None if not valid else all(b['observed_poa']>=a['observed_poa']-1e-9 for a,b in zip(group,group[1:])),
                           'poa_nonincreasing':None if not valid else all(b['observed_poa']<=a['observed_poa']+1e-9 for a,b in zip(group,group[1:])),
                           'checks_nondecreasing':None if not valid else all(b['over_check_ratio']>=a['over_check_ratio']-1e-9 for a,b in zip(group,group[1:])),
                           'weights':[r['w_omit'] for r in group],'poa':[r['observed_poa'] for r in group],
                           'over_check_ratio':[r['over_check_ratio'] for r in group]})
    (out/'trends.json').write_text(json.dumps(trends,indent=2))
    return summary


def role_ablation(out):
    out.mkdir(parents=True,exist_ok=False); configs=out/'configs'; configs.mkdir()
    original=letter_of_credit(); mismatches=role_mismatches(original)
    (out/'mismatches.json').write_text(json.dumps([asdict(m) for m in mismatches],indent=2))
    targets=(ExperimentTarget('selfish','selfish'),ExperimentTarget('resp-Proportional','resp'))
    rows=[]; witnesses=[]; cached_baseline=None
    for mismatch in mismatches:
        label=f'{mismatch.node[0]}__{mismatch.node[1]}'
        for alignment in ('baseline','bearer_aligned','fully_aligned'):
            config={'scenario':'letter_of_credit_role_ablation','node':list(mismatch.node),'alignment':alignment,'parameters':{}}
            (configs/f'{label}__{alignment}.json').write_text(json.dumps(config,indent=2))
            graph=letter_of_credit_ablation(RoleAblationConfig(mismatch.node,alignment))
            # Numeric, topology and every non-target node must be exactly intact.
            assert graph.edges==original.edges and graph.source==original.source
            for old,new in zip(original.nodes,graph.nodes):
                if old.id!=mismatch.node: assert old==new
                else: assert replace(new,payer=old.payer,bearer=old.bearer)==old
            case=ExperimentCase('letter_of_credit',0,graph,label,alignment)
            if alignment=='baseline' and cached_baseline is not None:
                new=[dict(r,ablation_node=label) for r in cached_baseline]; cycles=[]
            else:
                new,cycles=evaluate_case(case,targets)
                if alignment=='baseline': cached_baseline=new
            rows+=new; witnesses+=cycles
    return save(out,rows,witnesses)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--priority',choices=['omission','ablation','both'],default='both')
    parser.add_argument('--omission-out',type=Path,default=Path('results/sweep_v2_omission'))
    parser.add_argument('--ablation-out',type=Path,default=Path('results/sweep_v2_roles'))
    args=parser.parse_args()
    if args.priority in ('omission','both'): omission_sweep(args.omission_out)
    if args.priority in ('ablation','both'): role_ablation(args.ablation_out)


if __name__=='__main__': main()
