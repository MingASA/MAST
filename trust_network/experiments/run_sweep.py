"""Run the six protocol/objective combinations on both baseline scenarios."""
import argparse
import csv
import json
from dataclasses import asdict,dataclass
from pathlib import Path
import numpy as np
from trust_network.scenarios.synthetic import synthetic_random,SyntheticConfig
from trust_network.scenarios.letter_of_credit import letter_of_credit
from trust_network.solve.global_dp import GlobalDP,DPConfig
from trust_network.solve.decentralized_game import DecentralizedGame,GameConfig,PROTOCOLS,price_of_anarchy
from trust_network.solve.attribution import monte_carlo_validation
from trust_network.solve.verification_metrics import expected_checks,planner_metrics,over_check_ratio


@dataclass(frozen=True)
class SweepRow:
    scenario: str
    seed: int
    protocol: str
    objective: str
    converged: bool
    converged_starts: int
    starts: int
    rounds: int
    equilibrium_cost: float
    social_optimum: float
    observed_poa: float | None
    exploitability: float
    tree_nodes: int
    equilibrium_checks: float
    optimal_checks: float
    over_check_ratio: float


def centralized_value(game):
    values=np.zeros(len(game.tree))
    for i in range(len(game.tree)-1,-1,-1):
        node=game.tree[i]
        values[i]=sum(node.immediate)
        if node.actor is not None: values[i]+=min(values[c] for _,c in node.children)
        else: values[i]+=sum(p*values[c] for p,c in node.children)
    return float(values[0])


def run(out: Path, seeds: tuple[int,...]=(7,), budget: float=1.2, starts: int=2):
    if starts<1: raise ValueError('starts must be positive')
    if (out/'poa.csv').exists(): raise FileExistsError('use a new versioned output directory')
    out.mkdir(parents=True,exist_ok=True)
    rows=[]; details=[]; start_rows=[]
    scenarios=[('synthetic',seed,synthetic_random(SyntheticConfig(seed=seed))) for seed in seeds]
    scenarios.append(('letter_of_credit',0,letter_of_credit()))
    for name,seed,graph in scenarios:
        dp=GlobalDP(graph,DPConfig(budget,10001))
        for protocol in PROTOCOLS:
            for objective in ('selfish','resp'):
                game=DecentralizedGame(graph,GameConfig(budget,protocol,objective))
                optimum=centralized_value(game)
                if abs(dp.value()-optimum)>=1e-3:
                    raise AssertionError(f'DP/tree mismatch: {dp.value()} versus {optimum}')
                results=[]
                rng=np.random.default_rng(seed)
                for start in range(starts):
                    initial={k:(start if start<2 else int(rng.integers(2))) for k in game.keys}
                    results.append(game.solve(initial))
                equilibria=[r for r in results if r.converged and r.exploitability<1e-8]
                result=max(equilibria or results,key=lambda r:r.social)
                ratio=price_of_anarchy(result.social,optimum) if equilibria else None
                optimal_checks=planner_metrics(game).expected_checks
                checks=expected_checks(game,dict(result.strategy))
                row=SweepRow(name,seed,protocol,objective,bool(equilibria),len(equilibria),starts,result.rounds,result.social,optimum,ratio,result.exploitability,result.tree_nodes,checks,optimal_checks,over_check_ratio(checks,optimal_checks))
                rows.append(row)
                for start,item in enumerate(results):
                    item_checks=expected_checks(game,dict(item.strategy))
                    start_rows.append({'scenario':name,'seed':seed,'protocol':protocol,'objective':objective,
                        'start':start,'converged':item.converged,'social_cost':item.social,
                        'observed_poa':price_of_anarchy(item.social,optimum) if item.converged else None,
                        'expected_checks':item_checks,'optimal_checks':optimal_checks,
                        'over_check_ratio':over_check_ratio(item_checks,optimal_checks)})
                details.append({'scenario':name,'protocol':protocol,'objective':objective,'seed':seed,
                                'starts':[{'converged':r.converged,'cost':r.social,'rounds':r.rounds,
                                           'oscillation':r.oscillation,'net':r.net,
                                           'expected_checks':expected_checks(game,dict(r.strategy)),
                                           'over_check_ratio':over_check_ratio(expected_checks(game,dict(r.strategy)),optimal_checks)} for r in results]})
                print(f'{name:17} {protocol:21} {objective:7} cost={result.social:.6f} optimum={optimum:.6f} observed_PoA={ratio} converged={len(equilibria)}/{starts}',flush=True)
    with (out/'poa.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(asdict(rows[0])))
        writer.writeheader(); writer.writerows(asdict(row) for row in rows)
    (out/'sweep_details.json').write_text(json.dumps(details,indent=2))
    with (out/'by_start.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(start_rows[0])); writer.writeheader(); writer.writerows(start_rows)
    calibration=monte_carlo_validation()
    (out/'attribution_calibration.json').write_text(json.dumps(asdict(calibration),indent=2))
    lines=['# 可复现实验摘要','',
           '所有参数均为 synthetic。Observed PoA 为多个初始策略找到的纯策略均衡中最差成本与全信息社会最优之比；不是对所有均衡的穷举，也不是一般博弈的全局 PoA 证明。',
           '分母由精确观测树求解，并与 10001 点 DP 对照，误差必须小于 1e-3。协议0的路由和共享预算可见，跨组织检查记录隐藏。','',
           '| 场景 | 协议 | 目标 | 均衡成本 | 社会最优 | Observed PoA | 检查比 | 收敛起点 |',
           '|---|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        ratio='N/A' if r.observed_poa is None else f'{r.observed_poa:.4f}'
        lines.append(f'| {r.scenario} ({r.seed}) | {r.protocol} | {r.objective} | {r.equilibrium_cost:.4f} | {r.social_optimum:.4f} | {ratio} | {r.over_check_ratio:.6f} | {r.converged_starts}/{r.starts} |')
    lines.extend(['',f'归因校验 N={calibration.samples}；条件 KL={calibration.conditional_kl:.6f}；top-1={calibration.top1_accuracy:.6f}。',
                  '', '这些结果检验指定参数下的机制行为。责任规则不保证改善均衡；协议1/2在无伪造模型下应一致。'])
    (out/'summary.md').write_text('\n'.join(lines)+'\n')
    return rows


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,default=Path('results/sweep_v2_baseline'))
    parser.add_argument('--seeds',type=int,nargs='+',default=[7]); parser.add_argument('--budget',type=float,default=1.2)
    parser.add_argument('--starts',type=int,default=2); args=parser.parse_args()
    run(args.out,tuple(args.seeds),args.budget,args.starts)


if __name__=='__main__': main()
