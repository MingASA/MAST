"""Synthetic private supply, transport and buyer constraints for human tasks."""
from pathlib import Path
import argparse
import copy
import json

PRIVATE={
    'supplier':{'lots':{
        'early':{'model':'MX-40B','quantity':4,'ready_day':1},
        'later':{'model':'MX-40B','quantity':6,'ready_day':3}}},
    'carrier':{'services':{
        'air':{'capacity':4,'dispatch_day':1,'arrival_day':2,'price':1500},
        'road':{'capacity':6,'dispatch_day':3,'arrival_day':5,'price':600},
        'bulk':{'capacity':10,'dispatch_day':3,'arrival_day':5,'price':900}}},
    'buyer':{'model_approvals':{'MX-40B':True},'quantity':10,'latest_day':5,'freight_cap':2400,
             'preferences':{'early_quantity':4,'early_day':2,'priority':'restore_production'}}}

DOSSIERS={
    'supplier':'你代表供应商。解释备货限制，提出可行供货方案；可以分批发货。只承诺自己的库存和时间，不替物流商确定班次，也不替买方批准型号。',
    'carrier':'你代表物流商。根据供货时间匹配班次和报价，可以提出替代方案。多个批次合用同一班次时容量合计、报价只收一次。不能承诺不存在的运力。',
    'buyer':'你代表买方采购。结合供应和运输方案权衡复产紧迫性与运费。到齐时限、费用上限和型号正式批准是硬条件；早期到货是偏好。选择和解释方案，不要求只有一个正确答案。'}


def generate(out):
    out.mkdir(parents=True,exist_ok=False)
    for name,approved,priority in (('urgent',True,'restore_production'),
                                    ('economy',True,'minimize_freight'),
                                    ('not_approved',False,'restore_production')):
        case=out/name; case.mkdir()
        public={'transaction':'PROCUREMENT-017','model':'MX-40B','quantity':10,
                'request':'请供应商、买方和物流商协商可接受的备件交付方案。'}
        (case/'public.json').write_text(json.dumps(public,ensure_ascii=False,indent=2))
        for org,record in PRIVATE.items():
            folder=case/org; folder.mkdir()
            value=copy.deepcopy(record)
            if org=='buyer':
                value['model_approvals']['MX-40B']=approved
                value['preferences']['priority']=priority
            (folder/'state.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
            (folder/'private.md').write_text(DOSSIERS[org])


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    generate(parser.parse_args().out)
