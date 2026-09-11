"""Render the v2 topology/timing and responsibility figures from raw metrics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


TOPOLOGY_LABELS = {
    'long_chain_fork': 'long/fork',
    'converge_then_fork': 'merge/fork',
    'reused_org_independent': 'reused/indep',
}
FAULT_LABELS = {'shared_upstream': 'shared', 'branch_middle': 'branch'}
TIMING_LABELS = {'all_before_deadline': 'on-time', 'critical_edge_late': 'late'}
VIEW_LABELS = {
    ('full', 'none'): 'Full clean',
    ('no_receipts', 'none'): 'No receipts',
    ('ordinary_logs', 'none'): 'Ordinary logs',
    ('opaque_relay', 'none'): 'Opaque relay',
    ('full', 'missing_relevant_notice'): 'Missing notice',
    ('full', 'missing_order_node'): 'Missing order',
    ('full', 'reorder'): 'Reorder',
    ('full', 'conflicting_action'): 'Conflict',
}
PROJECTION_ORDER = list(VIEW_LABELS)


def _load(path):
    return json.loads(path.read_text())


def _write_csv(path, rows, fields):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _pct(value):
    return '—' if value is None else f'{value * 100:.0f}%'


def _bar_labels(ax, bars, values, fmt='{:.0f}'):
    for bar, value in zip(bars, values):
        if np.isnan(value):
            continue
        if value == 0:
            continue
        ax.text(bar.get_x() + bar.get_width() / 2, value + 2,
                fmt.format(value), ha='center', va='bottom', fontsize=7)


def render_freeze(rows, out):
    groups = [(topology, fault, timing)
              for topology in ('long_chain_fork', 'converge_then_fork', 'reused_org_independent')
              for fault in ('shared_upstream', 'branch_middle')
              for timing in ('all_before_deadline', 'critical_edge_late')]
    chart_rows = []
    for topology, fault, timing in groups:
        for notice in ('routed', 'broadcast'):
            for scope in ('dependency', 'recipient_workload'):
                row = next(item for item in rows
                           if item['topology'] == topology and item['fault'] == fault
                           and item['timing'] == timing and item['notice_scope'] == notice
                           and item['freeze_scope'] == scope)
                chart_rows.append({
                    'topology': topology, 'fault': fault, 'timing': timing,
                    'notice_scope': notice, 'freeze_scope': scope,
                    'unsafe_completion_rate': row['unsafe_completion_rate'],
                    'overfreeze_rate': row['overfrozen_tasks'] / row['unaffected_task_count'],
                    'unaffected_retention': row['unaffected_retention'],
                    'critical_edge_arrival_tick': row['critical_edge_arrival_tick'],
                    'notice_attempts': row['notice_attempts'],
                    'notice_receipts': row['notice_receipts'],
                    'duplicate_notice_receipts': row['duplicate_notice_receipts'],
                    'critical_edge_late_at_action': row['critical_edge_late_at_action'],
                })
    fields = list(chart_rows[0])
    _write_csv(out / 'freeze_chart_data.csv', chart_rows, fields)

    labels = [f"{TOPOLOGY_LABELS[t]}\n{FAULT_LABELS[f]}\n{TIMING_LABELS[x]}"
              for t, f, x in groups]
    x = np.arange(len(groups))
    width = .36
    colors = {'dependency': '#1b9e77', 'recipient_workload': '#d95f02'}
    fig, axes = plt.subplots(2, 2, figsize=(17, 9), sharex=True)
    for row_index, notice in enumerate(('routed', 'broadcast')):
        for column_index, metric in enumerate(('unsafe_completion_rate', 'overfreeze_rate')):
            ax = axes[row_index, column_index]
            values = {}
            for scope in ('dependency', 'recipient_workload'):
                values[scope] = np.array([
                    next(item for item in chart_rows
                         if item['topology'] == t and item['fault'] == f and item['timing'] == timing
                         and item['notice_scope'] == notice and item['freeze_scope'] == scope)[metric] * 100
                    for t, f, timing in groups
                ])
            bars_d = ax.bar(x - width / 2, values['dependency'], width,
                            color=colors['dependency'], label='dependency')
            bars_w = ax.bar(x + width / 2, values['recipient_workload'], width,
                            color=colors['recipient_workload'], label='recipient workload')
            _bar_labels(ax, bars_d, values['dependency'])
            _bar_labels(ax, bars_w, values['recipient_workload'])
            ax.set_ylim(0, 108)
            ax.set_ylabel('percent')
            ax.set_title(f"{notice}: {'unsafe affected completion' if metric == 'unsafe_completion_rate' else 'unrelated tasks overfrozen'}")
            ax.grid(axis='y', alpha=.25)
            if row_index == 1:
                ax.set_xticks(x, labels, rotation=35, ha='right', fontsize=8)
            else:
                ax.tick_params(axis='x', labelbottom=False)
            if row_index == 0 and column_index == 0:
                ax.legend(loc='upper right')
    fig.suptitle('Freeze contribution across topology and notification timing\n'
                 '48 deterministic runs; late edges are evaluated at the fixed action deadline',
                 fontsize=14)
    fig.text(.5, .01,
             'Dependency scope limits freezing to affected claims. Recipient-workload scope freezes all tasks at a notified organization.\n'
             'Late notification errors remain errors; notification cost is reported separately in the CSV.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=[0, .055, 1, .93])
    for suffix in ('png', 'svg', 'pdf'):
        fig.savefig(out / f'freeze_topology_timing.{suffix}', dpi=180)
    plt.close(fig)
    return chart_rows


def render_responsibility(rows, out):
    aggregate = []
    for view, fault in PROJECTION_ORDER:
        selected = [row for row in rows if row['view'] == view and row['fault'] == fault]
        positives = [row for row in selected if row['case'] == 'own_notice']
        negatives = [row for row in selected if row['case'] != 'own_notice']
        positive_tp = sum(row['duty_violations']['true_positive'] for row in positives)
        positive_expected = sum(row['duty_violations']['expected'] for row in positives)
        false_accusations = sum(row['false_accusations'] for row in negatives)
        negative_actions = sum(row['negative_action_count'] for row in negatives)
        insufficient = [row for row in positives if row['evidence_insufficient_label']]
        undetermined = sum(row['undetermined_when_insufficient'] for row in insufficient)
        aggregate.append({
            'view': view, 'fault': fault, 'label': VIEW_LABELS[(view, fault)],
            'positive_violation_tp': positive_tp,
            'positive_violation_expected': positive_expected,
            'positive_violation_recall': positive_tp / positive_expected if positive_expected else None,
            'negative_false_accusations': false_accusations,
            'negative_actions': negative_actions,
            'negative_false_accusation_rate': false_accusations / negative_actions if negative_actions else None,
            'insufficient_undetermined': undetermined,
            'insufficient_expected': len(insufficient),
            'insufficient_undetermined_rate': undetermined / len(insufficient) if insufficient else None,
            'inapplicable_fault_rows': sum(not row['projection_applicable'] for row in selected if fault != 'none'),
        })
    fields = list(aggregate[0])
    _write_csv(out / 'responsibility_chart_data.csv', aggregate, fields)

    labels = [item['label'] for item in aggregate]
    x = np.arange(len(aggregate))
    recall = np.array([item['positive_violation_recall'] * 100
                       if item['positive_violation_recall'] is not None else np.nan
                       for item in aggregate])
    false_rate = np.array([item['negative_false_accusation_rate'] * 100
                           if item['negative_false_accusation_rate'] is not None else np.nan
                           for item in aggregate])
    undetermined = np.array([item['insufficient_undetermined_rate'] * 100
                             if item['insufficient_undetermined_rate'] is not None else np.nan
                             for item in aggregate])
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.8))
    panels = [
        (axes[0], recall, '#1b9e77', 'positive duty violation recall',
         'denominator: 3 own-notice executions'),
        (axes[1], false_rate, '#7570b3', 'negative false-accusation rate',
         'denominator: 12 negative actions'),
        (axes[2], undetermined, '#e7298a', 'undetermined when evidence is insufficient',
         'denominator: 9 positive fault projections'),
    ]
    for ax, values, color, title, subtitle in panels:
        bars = ax.bar(x, np.nan_to_num(values, nan=0), color=color)
        _bar_labels(ax, bars, values)
        ax.set_ylim(0, 108)
        ax.set_ylabel('percent')
        ax.set_title(title)
        ax.text(.5, 1.01, subtitle, transform=ax.transAxes, ha='center', fontsize=8)
        ax.set_xticks(x, labels, rotation=38, ha='right', fontsize=8)
        ax.grid(axis='y', alpha=.25)
        for index, value in enumerate(values):
            if np.isnan(value):
                ax.text(index, 5, 'N/A', ha='center', va='bottom', fontsize=8, color='#555')
    fig.suptitle('Responsibility evidence ablation with independent labels\n'
                 '15 fixed executions: three actors × five duty cases', fontsize=14)
    fig.text(.5, .01,
             'A violation requires a completed action after the same organization signed receipt of the relevant revocation.\n'
             'Missing or contradictory proof produces an undetermined finding; abstention is not counted as a positive.',
             ha='center', fontsize=9)
    fig.tight_layout(rect=[0, .07, 1, .91])
    for suffix in ('png', 'svg', 'pdf'):
        fig.savefig(out / f'responsibility_evidence_ablation.{suffix}', dpi=180)
    plt.close(fig)
    return aggregate


def _markdown_table(headers, rows):
    lines = ['|' + '|'.join(headers) + '|',
             '|' + '|'.join('---' for _ in headers) + '|']
    lines.extend('|' + '|'.join(str(row.get(header, '')) for header in headers) + '|'
                 for row in rows)
    return '\n'.join(lines)


def write_report(metrics, freeze_chart, responsibility_chart, out):
    freeze = metrics['freeze']
    responsibility = metrics['responsibility']
    before = [row for row in freeze if row['timing'] == 'all_before_deadline']
    late = [row for row in freeze if row['timing'] == 'critical_edge_late']
    dependency = [row for row in freeze if row['freeze_scope'] == 'dependency']
    workload = [row for row in freeze if row['freeze_scope'] == 'recipient_workload']
    inapplicable = [row for row in responsibility if not row['projection_applicable']]
    hold_rows = [row for row in responsibility if row['case'] == 'hold'
                 and row['view'] == 'full' and row['fault'] == 'none']
    route_denominators = sorted({row['routes_verified']['expected'] for row in responsibility})
    source_denominators = sorted({row['source_identity']['expected'] for row in responsibility})
    positive_clean = [row for row in responsibility if row['case'] == 'own_notice'
                      and row['view'] == 'full' and row['fault'] == 'none']
    positive_fault = [row for row in responsibility if row['case'] == 'own_notice'
                      and row['view'] == 'full' and row['fault'] != 'none']
    lines = [
        '# Contribution generalization v2：拓扑时序与责任证据',
        '',
        '来源：本目录的 raw JSON metrics。全部运行使用真实 ClaimGateway、签名交接、通知和 MessageBus；'
        '没有调用 MiniMax，也没有将评分阶段改写成冻结结果。',
        '',
        '## 执行规模与完整性',
        '',
        f"冻结运行 {len(freeze)} 条（应为 48），责任投影 {len(responsibility)} 条（应为 120）；"
        f"模型调用 {metrics['model_calls']}，token {metrics['tokens']}。责任路线分母为 {route_denominators}，"
        f"来源身份分母为 {source_denominators}。三类执行组织为 receiver_a、receiver_b、receiver_c。",
        f"责任投影中 {len(inapplicable)} 条因目标材料不存在而不可比较；它们保留在 raw metrics 中，"
        '没有被当作检测成功。hold 基础执行的完整证据结果只作为不违约/待定行为观察，不计入正例违约召回。',
        '',
        '## 拓扑与时序结果',
        '',
        f"通知全部在动作截止时间前到达的 {len(before)} 条运行中，unsafe completion 为 "
        f"{sum(row['unsafe_completion_count'] for row in before)}/{sum(row['affected_task_count'] for row in before)}；"
        f"其中 dependency 的过度冻结总数为 {sum(row['overfrozen_tasks'] for row in before if row['freeze_scope'] == 'dependency')}，"
        f"recipient_workload 的过度冻结总数为 {sum(row['overfrozen_tasks'] for row in before if row['freeze_scope'] == 'recipient_workload')}。",
        f"关键边晚到的 {len(late)} 条运行中，保留了截止时间前已经发生的错误完成：unsafe completion "
        f"为 {sum(row['unsafe_completion_count'] for row in late)}/{sum(row['affected_task_count'] for row in late)}。"
        '这些错误没有在评分阶段被重标为冻结成功。',
        '四格差异的主要原因是冻结粒度。dependency 在全部拓扑和时序中不冻结无关依赖；'
        'recipient_workload 会冻结收到通知的组织的无关任务，在复用组织拓扑中尤其明显。'
        'broadcast 改变通知次数、字节和部分到达路径，但固定冻结粒度后不改变其语义。',
        '',
        '冻结图：[freeze_topology_timing.png](freeze_topology_timing.png)。逐条结果见 `freeze_*.json` 和 `freeze_chart_data.csv`。',
        '',
        '## 独立责任标签结果',
        '',
        f"三名执行组织各覆盖五种标签。完整 clean 的 own-notice 正例为 "
        f"{sum(row['duty_violations']['true_positive'] for row in positive_clean)}/"
        f"{sum(row['duty_violations']['expected'] for row in positive_clean)}；"
        f"四类 full 证据变化后的正例为 {sum(row['duty_violations']['true_positive'] for row in positive_fault)}/"
        f"{sum(row['duty_violations']['expected'] for row in positive_fault)}，缺 notice、缺顺序节点和冲突记录均进入待定。",
        f"全部责任投影的负例误指控为 {sum(row['false_accusations'] for row in responsibility)}/"
        f"{sum(row['negative_action_count'] for row in responsibility)}。"
        '没有把“未看到通知”推断为无责，也没有把合法的不同 action ID 当成冲突；冲突条件只加入同一 action ID 的矛盾签名记录。',
        f"证据不足的 own-notice 正例中，待定判断为 "
        f"{sum(row['undetermined_when_insufficient'] for row in positive_fault)}/"
        f"{sum(row['evidence_insufficient_label'] for row in positive_fault)}。"
        'ordinary logs 可以保留路线估计，但清除签名包后不再提供可验证来源或本地责任证据。',
        '',
        '责任图：[responsibility_evidence_ablation.png](responsibility_evidence_ablation.png)。逐条结果见 observation/assessment JSON 与 `responsibility_chart_data.csv`。',
        '',
        '## 结论与边界',
        '',
        '结果正向支持两个机制级判断：依赖冻结在长链、汇聚后分叉和组织复用条件下仍能保持局部隔离；'
        '签名交接、来源链和本地顺序证据能把明确的“已签收后仍完成”标成违约，并在证据缺失或冲突时停在 undetermined。',
        '这些是构造执行和独立标签下的受控验证，不是 48 或 120 个独立统计样本；拓扑仍是有限的三类模板，'
        '动作效果由脚本固定，责任正例明确模拟绕过门禁的行为。它们不能推出一般 Agent 错误率、现实网络泛化或法律责任准确率。',
        '',
        '可复现命令：',
        '',
        '```bash',
        '.venv/bin/python -m trust_network.benchmark.contribution.generalization --output results/contribution_generalization_v2',
        '.venv/bin/python scripts/plot_contribution_generalization.py --result results/contribution_generalization_v2',
        '```',
        '',
        '### 冻结关键分组',
        '',
    ]
    compact = []
    for topology in ('long_chain_fork', 'converge_then_fork', 'reused_org_independent'):
        for fault in ('shared_upstream', 'branch_middle'):
            for timing in ('all_before_deadline', 'critical_edge_late'):
                selected = [row for row in freeze
                            if row['topology'] == topology and row['fault'] == fault
                            and row['timing'] == timing and row['notice_scope'] == 'routed']
                by_scope = {row['freeze_scope']: row for row in selected}
                compact.append({
                    'topology': TOPOLOGY_LABELS[topology], 'fault': FAULT_LABELS[fault],
                    'timing': TIMING_LABELS[timing],
                    'dependency unsafe': f"{by_scope['dependency']['unsafe_completion_count']}/{by_scope['dependency']['affected_task_count']}",
                    'workload unsafe': f"{by_scope['recipient_workload']['unsafe_completion_count']}/{by_scope['recipient_workload']['affected_task_count']}",
                    'dependency retain': _pct(by_scope['dependency']['unaffected_retention']),
                    'workload retain': _pct(by_scope['recipient_workload']['unaffected_retention']),
                })
    lines += [_markdown_table(['topology', 'fault', 'timing', 'dependency unsafe',
                               'workload unsafe', 'dependency retain', 'workload retain'], compact),
              '', '以上表只列 routed 作为可读摘要；broadcast 对照和通知开销在图及 CSV 中完整保留。']
    (out / 'report.md').write_text('\n'.join(lines) + '\n')
    summary = {
        'freeze_runs': len(freeze), 'responsibility_projections': len(responsibility),
        'responsibility_executions': len({row['execution_id'] for row in responsibility}),
        'inapplicable_responsibility_projections': len(inapplicable),
        'before_deadline_unsafe_completion': sum(row['unsafe_completion_count'] for row in before),
        'late_unsafe_completion': sum(row['unsafe_completion_count'] for row in late),
        'dependency_overfrozen_tasks': sum(row['overfrozen_tasks'] for row in dependency),
        'recipient_workload_overfrozen_tasks': sum(row['overfrozen_tasks'] for row in workload),
        'responsibility_false_accusations': sum(row['false_accusations'] for row in responsibility),
        'responsibility_negative_actions': sum(row['negative_action_count'] for row in responsibility),
        'positive_clean_violation_recall': sum(row['duty_violations']['true_positive'] for row in positive_clean) /
        sum(row['duty_violations']['expected'] for row in positive_clean),
        'positive_fault_undetermined': sum(row['undetermined_when_insufficient'] for row in positive_fault) /
        sum(row['evidence_insufficient_label'] for row in positive_fault),
        'model_calls': metrics['model_calls'], 'tokens': metrics['tokens'],
    }
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    out = args.out or args.result
    out.mkdir(parents=True, exist_ok=True)
    metrics = _load(args.result / 'metrics.json')
    freeze_chart = render_freeze(metrics['freeze'], out)
    responsibility_chart = render_responsibility(metrics['responsibility'], out)
    summary = write_report(metrics, freeze_chart, responsibility_chart, out)
    artifact_manifest = {}
    for path in sorted(out.rglob('*')):
        if path.is_file() and path.name != 'artifact_manifest.json':
            artifact_manifest[str(path.relative_to(out))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / 'artifact_manifest.json').write_text(
        json.dumps(artifact_manifest, ensure_ascii=False, indent=2) + '\n'
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
