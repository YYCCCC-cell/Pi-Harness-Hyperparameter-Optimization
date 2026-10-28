"""Assemble the dated diagnostic evidence and reports without model calls."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pilot.config import canonical_json

def read(path):return json.loads((ROOT/path).read_text())
def money(value):return Decimal(str(value)).quantize(Decimal('0.00000001'))

old=read('runs/pi-diagnostic-real-20261027-remaining/diagnostic-review.json')
tail=read('runs/pi-diagnostic-completion-20261027/summary.json')
early=read('runs/pi-early-diagnostic-real-20261027/summary.json')
pressure=read('runs/compaction-live-diagnostic-20261027-v5/result.json')
key=read('runs/pi-diagnostic-readonly-final-20261027-v2/key-usage-after.json')
checks=read('runs/pi-diagnostic-readonly-final-20261027-v2/generation-checks.json')
assert tail['status']=='completed_diagnostic_tail' and early['status']=='completed_live_v2_diagnostic'
assert pressure['status']=='completed_live_mechanism_diagnostic'
assert len(checks)==10 and all('generation' in c for c in checks)
for c in checks:
    assert abs(money(c['generation']['total_cost'])-money(c['expected_request_cost_usd']))<=money('0.00000001')
generations={c['generation']['id']:c['generation'] for c in checks}
rows=[]
for folder,segment in [('runs/pi-diagnostic-completion-20261027',tail),('runs/pi-early-diagnostic-real-20261027',early)]:
    for r in segment['attempts']:
        result,e=r['result'],r['evidence'];path=folder+'/attempts/'+r['id']
        assert result.get('measurement_error') is None and e['settings_and_model_verified']
        assert e['compaction']['agent_settled'] and read(path+'/cleanup.json')['verified']
        assert e['context']['model_context_window']==400000
        charges=[];resolved=[]
        for call in read(path+'/provider-calls.json'):
            assert call['event']=='success'
            cost=call['usage'].get('cost')
            if cost is None:
                receipt=generations[call['response_id']]
                cost=receipt['total_cost'];resolved.append(receipt['id'])
            charges.append(money(cost))
        total=sum(charges)
        assert abs(total-money(result['estimated_cost_usd']))<=money('0.00000001')
        rows.append({'id':r['id'],'source':path,'settings':r['settings'],
            'official_reward':result['raw_reward'],'wall_seconds':result['wall_time_seconds'],
            'provider_reconciled_request_cost_usd':str(total),
            'cost_source':'usage.cost plus generation records for missing summary charges',
            'summary_cost_generation_ids':resolved,'compaction':e['compaction'],
            'context':e['context'],'thinking':e['thinking']})
new_task=sum(money(r['provider_reconciled_request_cost_usd']) for r in rows)
new_total=new_task+money(pressure['known_provider_cost_usd'])+money('0.0000795')
known=money(old['known_cost_including_probe_usd'])+new_total
key_delta=money(key['usage'])-money('0.63111865')
assert known==key_delta
compactions=[{'attempt':r['id'],**e['result']} for r in rows for e in r['compaction']['ends'] if e.get('completed') and not e.get('aborted')]
assert len(compactions)==2
record={'recorded_at':datetime.now(timezone.utc).isoformat(),'status':'diagnostic_work_completed_with_evidence_limits',
    'original_plan_attempts_executed':8,'additional_real_calibration_attempts':3,'total_real_task_attempts':11,
    'new_real_attempts':rows,'new_real_attempts_fully_metered':5,'all_full_cost_task_attempts':8,
    'new_task_provider_reconciled_cost_usd':str(new_task),'new_known_cost_including_pressure_and_availability_usd':str(new_total),
    'cumulative_known_request_cost_usd':str(known),'whole_campaign_invoice_cost_known':False,
    'historical_unknown_task_costs_reclassified':False,'pressure_failed_requests_cost_known':False,
    'historical_task_unknown_cost_holdback_usd':3,'pressure_unknown_cost_holdback_usd':0.82,
    'key_usage_snapshot':key,'whole_key_usage_delta_since_original_baseline_usd':str(key_delta),
    'key_delta_matches_known_requests':True,'generation_check_count':10,'generation_checks_match':True,
    'real_task_compaction_events':compactions,'controlled_pressure_context_budget':128000,
    'official_task_model_context_window':400000,'pressure_is_benchmark_score':False,
    'quality_gain_established':False,'all_new_official_rewards_zero':all(r['official_reward']==0 for r in rows),
    'formal_experiment_launched':False,
    'limits':['All complete task cost samples still come from one validation task; not a representative task-cost distribution.',
      'Provider request records and a matching aggregate key delta are not a complete invoice or proof that failed/cancelled requests were free.',
      'Controlled pressure used an explicit 128k budget; real tasks and the live-v2 profile retained the advertised 400k window.',
      'Different nondeterministic trajectories do not establish a causal quality ranking.'],
    'evidence_paths':['runs/pi-diagnostic-real-20261027-remaining/diagnostic-review.json','runs/pi-diagnostic-completion-20261027/summary.json',
      'runs/pi-early-diagnostic-real-20261027/summary.json','runs/compaction-live-diagnostic-20261027-v5/result.json',
      'runs/pi-diagnostic-readonly-final-20261027-v2/generation-checks.json','docs/run_review_20261027/run_manifest.v2.proposal.json']}
record['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in record['evidence_paths']}
out=ROOT/'runs/pi-diagnostic-closure-20261027';out.mkdir(mode=0o700,exist_ok=False)
(out/'review.json').write_text(canonical_json(record))
lines=['# 第 2 步诊断闭环与第 3 步实验规划','',
 '2026-10-27 更新。原计划 **8/8 项已执行**，另完成 **3 项真实任务范围校准**。三档 thinking 的真实请求已核验；原压缩范围在这些任务中未触发，新版范围已在原模型、原 400k 任务窗口中观测到 **2 次自动压缩**。第 2 步的工程诊断已完成；尚未证明任何配置提高任务通过率。','',
 '## 本轮新增真实任务','',
 '以下五次均有正常 agent settled、完整请求计量、官方判分和资源清理记录。前三次历史费用不完整的尝试仍保持原判定。','',
 '| 尝试 | reserve / keepRecent | 官方 reward | USD 请求计量 | 全程秒数 | 完成压缩 |','|---|---|---:|---:|---:|---:|']
for r in rows:
    c=r['settings']['compaction']
    lines.append(f"| {r['id']} | {c['reserveTokens']} / {c['keepRecentTokens']} | {r['official_reward']:g} | {r['provider_reconciled_request_cost_usd']} | {r['wall_seconds']:.1f} | {r['compaction']['completed_count']} |")
lines += ['', '原计划尾部使用原空间；最后三项使用显式选择的 `early_compaction_v2`，均为 `llm-prefix-cache-replay`、thinking=medium。原报告保留为[历史记录](pi_diagnostic_real_20261027.md)。','',
 '## 三个参数的证据','',
 '- **thinking**：low / medium / high 均已核对 Pi 状态与供应商 `reasoning_effort`；不据此推断供应商内部推理预算或质量收益。',
 '- **reserveTokens**：375000 对应严格超过 25000 时触发，实际事件为 27673 → 1869 tokens；360000 对应严格超过 40000，实际事件为 42533 → 2883。两次都是原生 threshold 自动压缩，均完成、无重试、无中止。20k 保留配置的那次轨迹最大快照只有 19793，未触发符合条件。',
 '- **keepRecentTokens**：原计划的 10000 / 20000 / 40000 均已装载于真实任务；同一合成历史的独立真实摘要对照中，10000 / 40000 分别保留估算 10026 / 40026 tokens，边界不同。新版 4000 已在真实任务的两次压缩中使用。不同任务轨迹的费用或分数不能冒充同历史因果对照。','',
 '新版空间见 [hpo_space.live-v2.json](../configs/hpo_space.live-v2.json)：thinking=[low,medium,high]，reserve=[16384,360000,375000]，keepRecent=[4000,10000,20000]，仍为 27 个候选，原生默认 medium/16384/20000 保留在网格中。只有显式设置 `live.space_profile=early_compaction_v2` 才使用新版；原空间与 mock 复现保持不变。','',
 '新版分别检查“保留内容 + 4096 < 压缩阈值”和“保留内容 + 模型输出上限 + 4096 < 模型窗口”。Pi 按剩余窗口动态限制输出；reserve 决定触发时机，并不是摘要长度上限。消息粒度和摘要长度仍需逐次日志检查。本次两次压缩后的估算值均显著低于触发阈值，未出现连续空转压缩。','',
 '## 压力测试的边界','',
 '独立压力测试由 Pi 直接访问原 OpenRouter 模型，真实任务则经 BenchFlow 代理。第一次字符填充探针被本地输出额度检查拦住，未发请求；之后本地 o200k_base 估算约 378k 的输入被上游以超出窗口拒绝，另有一次连接错误。公开[端点目录](https://openrouter.ai/api/v1/models/openai/gpt-5.4-mini/endpoints)仍列 400k；失败请求未返回实际 tokens，不能据此宣称目录错误或测出了模型精确上限。','',
 '最终独立探针显式使用 128k 诊断预算，供应商返回实际上下文 105116 tokens；两个摘要正常完成。它是机制证据，不是 SkillsBench 成绩。所有真实任务和新版搜索空间的模型窗口仍为 400k，未修改上游源码或供应商路由选择。','',
 '## 费用、耗时与核验','',
 f'- 本轮新增真实任务已记录费用 **${new_task}**；加上压力/可用性调用，新增已知请求费用 **${new_total}**。五次真实任务墙钟合计约 {sum(r["wall_seconds"] for r in rows)/60:.2f} 分钟。',
 f'- 累计已知请求费用 **${known}**，与延后查询的整把 key 用量增量一致。10 个抽查 generation 费用相符，包含两次回调缺少供应商费用字段的原生摘要；这两笔由 generation 记录补证，未改写原始回调。',
 f'- key 查询时间 `{key["recorded_at"]}`，用量 ${key["usage"]}，key 限额 $10，剩余额度约 ${key["limit_remaining"]:.6f}。这是 key 限额，不是账户钱包总余额。',
 '- 历史 3 次任务及压力失败请求的完整费用仍未确证，分别保留 $3 / $0.82 的预留口径。已知费用不是完整账单；匹配的 key 增量不能证明每个失败请求免费。',
 '- 官方 reward 全部仍为 0；目前没有最优配置或性能改善结论。',
 '- 全套 147 项测试：131 通过、16 项运行时依赖跳过；独立运行时测试 8 项通过。四个上游 checkout 与锁定提交一致且干净。最终清理和密钥扫描见验证记录。','',
 '## 第 3 步','',
 '已据此制定 **8 个验证任务 + 16 个留出任务、四个搜索方法各 10 组配置、1 个搜索种子，共 408 次尝试** 的[正式实验方案](run_review_20261027/README.md)，建议 API 发起预算 **$255**。正式实验尚未启动；方案明确列出子集接入、独立留出执行和预算批准门槛。没有启动旧草案的 4827 次尝试。','',
 '证据：[闭环数据](../runs/pi-diagnostic-closure-20261027/review.json)、[新范围真实运行](../runs/pi-early-diagnostic-real-20261027/summary.json)、[独立压力实验](../runs/compaction-live-diagnostic-20261027-v5/result.json)、[只读费用核对](../runs/pi-diagnostic-readonly-final-20261027-v2/generation-checks.json)、[最终验证](../runs/pi-diagnostic-closure-20261027/final-verification.json)。','']
(ROOT/'docs/pi_diagnostic_completion_20261027.md').write_text('\n'.join(lines))
print({'new_known_cost_usd':str(new_total),'cumulative_known_usd':str(known),'real_compactions':len(compactions)})
