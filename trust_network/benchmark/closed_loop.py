"""Unified offline lifecycle plus explicitly labeled accountability scoring."""
import argparse
import hashlib
import json
from pathlib import Path
from trust_network.benchmark.containment import fixture,run,evaluate,POLICIES,SCENARIOS
from trust_network.benchmark.accountability import audit
from trust_network.benchmark.accountability_cases import evaluate_cases
from trust_network.benchmark.replay_v7 import replay


def execute(output):
    output=Path(output);output.mkdir(parents=True,mode=0o700,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    sources=lambda:{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'trust_network').rglob('*.py'))}
    def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2))
    manifest={'protocol':'containment-closed-loop-v1','status':'running','source_hashes':sources(),
              'policies':[*POLICIES,'frontier_v2'],'new_model_calls':0,
              'revocation_tick':5,'proposal_origin':'scripted','task_count_per_workflow':4}
    write(output/'manifest.json',manifest)
    try:
        rows=[]
        for scenario in SCENARIOS:
            for location in (('coordinator','middle_a') if scenario=='derived_error' else ('coordinator',)):
                f=fixture(scenario,fault_location=location)
                if scenario=='delayed_revoke':f['truth']['invalid_from']=5
                folder=output/(scenario+'_'+location);folder.mkdir()
                write(folder/'truth.json',f['truth'])
                for policy in manifest['policies']:
                    result=run(f,policy,lifecycle=True)
                    metrics=evaluate(result,f['truth']);assessment=audit(result)
                    write(folder/(policy+'_trace.json'),result)
                    write(folder/(policy+'_audit.json'),assessment)
                    rows.append({'scenario':scenario,'location':location,'policy':policy,**metrics,
                                 'errors':[r['error'] for r in result['recovery'] if r['error']]})
        write(output/'metrics.json',rows)
        attribution=evaluate_cases();write(output/'accountability_scores.json',attribution)
        calibration=replay(root/'results/next_agent_recovery_model_pilot_v7');write(output/'v7_replay.json',calibration)
        if not calibration['all_batches_matched']:raise ValueError('v7 calibration failed')
        if sources()!=manifest['source_hashes']:raise ValueError('source changed during run')
        lines=['# 多跳传播—冻结—恢复统一离线结果','',
               '36条脚本workflow，6个条件/位置×6臂。每条含A/C订单×a/b分支，共4个任务；重试不增加任务分母。新增模型调用0。',
               '原有传播矩阵仍保留；本实验在旧证据到达各分支后tick 5撤销，恢复沿用同一批网关和同一消息总线。','',
               '|条件/位置|策略|不安全完成/4|安全完成/4|恢复成功/尝试|无关误冻|查询|',
               '|---|---|---:|---:|---:|---:|---:|']
        for r in rows:
            lines.append(f"|{r['scenario']}/{r['location']}|{r['policy']}|{r['unsafe_completed']}/4|{r['safe_completed']}/4|{r['recovery_successes']}/{r['recovery_attempts']}|{r['unrelated_overfreeze']}|{r['verification_queries']}|")
        lines+=['','## 追溯标签对照','',
                f"- 协议违约检出：{attribution['duty_detection']}",
                f"- 错误指控：{attribution['false_accusations']}",
                f"- 证据不足时不指控：{attribution['evidence_limited_abstention']}",
                f"- 篡改/缺失发现：{attribution['corruption_detection']}",
                f"- 来源/错误转换身份定位：{attribution['localization_accuracy']}",
                '', '这些是极小的预定义协议义务标签，不是生产准确率；来源身份定位不证明事实真假或法律责任。',
                '', '## 结论与限制','',
                '- 同一流程确认：v2可在原状态上完成两层恢复；冻结v1仍受单派生限制。无关C任务继续。',
                '- 普通notice臂在固定正确新事实下也完成恢复，因此没有证据证明v2的模型成功率更高。',
                '- 冲突来源和签名有效但事实错误仍未解决；恢复器不会擅自给这些条件注入修正。',
                '- v7校准仍为4条旧workflow、6个批次结果一致；不把它们当作新拓扑的live样本。',
                '- 延迟撤销可能使已接受的旧声明在本地变为失效。本表不把此前合法接收追认为当时的错误传播；事后错误引用另计。',
                '- 未实施完整live多轮模型pilot，也未进行大规模付费实验。']
        (output/'report.md').write_text('\n'.join(lines)+'\n')
        manifest['status']='completed'
    except Exception as exc:manifest['status']='failed';manifest['error']=str(exc);raise
    finally:write(output/'manifest.json',manifest)
    return rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    execute(p.parse_args().out)
