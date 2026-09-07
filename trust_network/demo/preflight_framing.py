"""Review exact static prompts, costs and historical exposure without API use."""
import argparse
from dataclasses import asdict
from pathlib import Path
import json
from trust_network.demo.run import ROOT,ORGS
from trust_network.demo.worker import SYSTEM
from trust_network.demo.framing import BANK_ORGANIZATIONS,CONDITIONS,objective_text
from trust_network.demo.discrepancy import replay_banks,EXTRACTION_SYSTEM
from trust_network.demo.run_framing import estimate
from trust_network.demo.run_batch import case_hashes


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    case=ROOT/'examples/letter_of_credit'
    prompts={c.name:{org:{'system':SYSTEM+'\n本组织私有档案：\n'+(case/'organizations'/org/'private.md').read_text(),
        'objective':objective_text(c.objective,org),
        'task':'完成你负责的人工业务工作，给出下一步操作。禁止虚构外部数据库查询。'}
        for org in ORGS} for c in CONDITIONS}
    lines=['# 第三轮银行任务原文审查','',
        '以下是两个条件中银行的完整静态system、objective、task原文。动态单据、公开消息和证书仍由原runner生成；初始单据和档案哈希见manifest.json。',
        '旧system和档案本来含有业务检查线索；两组完全相同。只有objective追加责任句，不新增内容线索。','']
    for org in BANK_ORGANIZATIONS:
        for c in CONDITIONS:
            lines += [f'## {org} / {c.name}','','```json',json.dumps(prompts[c.name][org],ensure_ascii=False,indent=2),'```','']
    historical=[]
    for record_path in sorted((ROOT/'results/minimax_batch_v2').rglob('record.json')):
        r=json.loads(record_path.read_text()); folder=record_path.parent
        events=[json.loads(line) for log in list(folder.glob('*.jsonl'))+list(folder.glob('*.jsonl.interrupted')) for line in log.read_text().splitlines()]
        banks=replay_banks(case,events)
        historical.append({k:r[k] for k in ('repetition','combination','status')}|{
            'bank_decisions':len(banks),'exposed_bank_decisions':sum(e.exposed_to_seeded_conflict for e in banks)})
    artifacts={'prompts.json':prompts,'estimate.json':estimate(),
        'historical_bank_exposure.json':historical,
        'manifest.json':{'case_hashes':case_hashes(case),'conditions':[asdict(c) for c in CONDITIONS],
                         'extraction_system':EXTRACTION_SYSTEM,'api_requests_made':0}}
    for filename,data in artifacts.items():
        (out/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    (out/'prompt_review.md').write_text('\n'.join(lines))
    return {'historical_runs':len(historical),'bank_decisions':sum(r['bank_decisions'] for r in historical),
            'exposed_bank_decisions':sum(r['exposed_bank_decisions'] for r in historical),**estimate()}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,default=Path('results/framing_v3_preflight'))
    args=parser.parse_args(); print(json.dumps(prepare(args.out),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
