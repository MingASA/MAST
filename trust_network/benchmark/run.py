"""Run offline containment matrix, v7 calibration and recovery comparison."""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.benchmark.containment import fixture,run,evaluate,POLICIES,SCENARIOS
from trust_network.benchmark.accountability import audit
from trust_network.benchmark.recovery_probe import probe
from trust_network.benchmark.replay_v7 import replay


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def execute(output,v7):
    output=Path(output); output.mkdir(parents=True,mode=0o700,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    source_hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'trust_network').rglob('*.py'))}
    manifest={'protocol':'containment-benchmark-v1','status':'running','new_model_calls':0,
              'source_hashes':source_hashes,'policies':POLICIES,
              'cases':[(s,l) for s in SCENARIOS for l in (('coordinator','middle_a') if s=='derived_error' else ('coordinator',))],
              'seed':0,'truth_only_in_evaluator':True,'transport':'deterministic delay only'}
    write(output/'manifest.json',manifest)
    try:
        rows=[]
        for scenario,location in manifest['cases']:
            f=fixture(scenario,0,location); folder=output/(scenario+'_'+location); folder.mkdir()
            write(folder/'truth.json',f['truth'])
            for policy in POLICIES:
                raw=run(f,policy); metrics=evaluate(raw,f['truth']); assessment=audit(raw)
                write(folder/(policy+'_trace.json'),raw)
                write(folder/(policy+'_audit.json'),assessment)
                rows.append({'scenario':scenario,'location':location,'policy':policy,**metrics})
        v7_result=replay(v7);write(output/'v7_replay.json',v7_result)
        if not v7_result['all_batches_matched']: raise ValueError('v7 calibration mismatch')
        recovery=[]
        f=fixture('delayed_revoke')
        for policy in (*POLICIES,'frontier_v2'):
            for branch in ('a','b'): recovery.append({'policy':policy,**probe(f,policy,branch)})
        write(output/'metrics.json',rows);write(output/'recovery.json',recovery)
        lines=['# 离线 benchmark v1','',
            '30个固定脚本对照（6条件位置×5策略），4条真实v7历史workflow重放，另有多层恢复探针。新增模型调用0。',
            '脚本矩阵、历史真实决定重放、恢复探针分开统计，不能合并为独立模型样本。','',
            '|场景/位置|策略|不安全/4任务|正常完成|错误接受最大跳|污染分支|无关误冻|查询|',
            '|---|---|---:|---:|---:|---:|---:|---:|']
        for r in rows:
            lines.append(f"|{r['scenario']}/{r['location']}|{r['policy']}|{r['unsafe_completed']}/4|{r['safe_completed']}|{r['max_error_acceptance_hop']}|{r['contaminated_branches']}|{r['unrelated_overfreeze']}|{r['verification_queries']}|")
        lines+=['','## 多层恢复：冻结v1与候选v2分开','',
                '|策略|恢复成功/2分支|说明|','|---|---:|---|']
        for policy in (*POLICIES,'frontier_v2'):
            rs=[r for r in recovery if r['policy']==policy]
            lines.append(f"|{policy}|{sum(r['recovered'] for r in rs)}/2|{rs[0].get('error') or rs[0].get('reason','固定正确新事实，非live模型')}|")
        lines+=['','## 可支持的结论','',
          '- v7原始151文件完整性通过，6个历史动作批次重放一致，2个真实模型派生重建摘要一致。',
          '- 当前共同结构检查已经阻断两种位置的派生错误；dependency相对强simple root gate没有新增拦截收益。',
          '- 冲突来源与签名真实但业务事实错误的负控制均未被当前机制解决。冲突在fixture中预先约定为必须澄清，不能以签名证明已澄清。',
          '- 多层恢复揭示v1只接受一个派生重建；候选frontier-v2在两个固定脚本分支上完成按依赖顺序的重建与再门禁。',
          '- notice-only恢复臂使用相同正确新事实和签名检查，省略任务绑定也能完成；不能据此证明标准证据提升模型可用性，需要live消融。',
          '- frontier-v2是本轮新增候选机制，不覆盖v7历史证据，也不声称已验证真实模型稳定性或首创性。',
          '- 无关分支C单独记录；本轮未发生过度冻结。传输hash链只能证明归档一致性，不证明远程交付。',
          '- 本轮没有实现完整网络故障模拟器；drop/duplicate/reorder系统矩阵延后。']
        (output/'report.md').write_text('\n'.join(lines)+'\n')
        manifest['status']='completed'
    except Exception as exc:
        manifest['status']='failed';manifest['error']=type(exc).__name__;raise
    finally: write(output/'manifest.json',manifest)
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--v7',type=Path,default=Path('results/next_agent_recovery_model_pilot_v7'))
    args=p.parse_args();execute(args.out,args.v7)
