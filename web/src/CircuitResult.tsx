import type { CircuitPuzzle, CircuitSolveResult } from "./api";
import { deriveCircuitAnswer } from "./circuit";
import { CircuitChannelToken } from "./CircuitPuzzlePreview";

type Props = { puzzle: CircuitPuzzle | unknown; result: CircuitSolveResult };

const invalidResult = (message: string) => <div className="notice warning" role="alert">
  <strong>服务返回的答案无效。</strong> {message}
</div>;

export default function CircuitResult({ puzzle, result }: Props) {
  if (result === null || typeof result !== "object" || Array.isArray(result)) {
    return invalidResult("响应结构无法识别，未绘制答案。");
  }
  const value = result as Partial<CircuitSolveResult>;
  if (value.rule_version !== "line-count-v1") return invalidResult("规则版本与当前页面不一致，未绘制答案。");
  if (value.outcome === "unsatisfiable") {
    if (value.solution != null || value.limit_reason != null) return invalidResult("无解响应包含了不应出现的摆放或限额信息。");
    return <div className="notice warning" role="status">
      <strong>按这个题面没有解。</strong> 求解器已经穷尽当前规则下的全部合法摆放。
    </div>;
  }
  if (value.outcome === "timeout") {
    if (value.solution != null || (value.limit_reason !== "time" && value.limit_reason !== "work")) {
      return invalidResult("计算限额响应结构不完整。");
    }
    return <div className="notice warning" role="status">
      <strong>计算达到{value.limit_reason === "time" ? "时间" : "工作量"}上限。</strong> 搜索尚未穷尽，目前不能判断题面是否有解。
    </div>;
  }
  if (value.outcome !== "solved") return invalidResult("结果状态无法识别。");
  const checked = deriveCircuitAnswer(puzzle, value);
  if (!checked.answer) return invalidResult(`${checked.error} 未绘制答案。`);
  const { puzzle: normalized, cells, placements } = checked.answer;

  return <div className="circuit-solution">
    <p className="success-line">已找到并重新校验一组完整摆放。固定格计入对应通道的行列约束。</p>
    <div className="circuit-legend" aria-label="答案通道图例">
      {normalized.channels.map((channel) => <CircuitChannelToken key={channel.index} channel={channel.index} />)}
      <span className="circuit-legend-item fixed">固定 = 题面已有格</span>
      <span className="circuit-legend-item blocked">× 障碍</span>
    </div>
    <div className="circuit-board circuit-answer-board"
      style={{ gridTemplateColumns: `repeat(${normalized.columns}, minmax(0, 1fr))` }}>
      {cells.map((cell) => {
        const channelClass = cell.channel != null ? ` circuit-channel-${cell.channel}` : "";
        const description = cell.kind === "blocked" ? "障碍格" : cell.kind === "fixed"
          ? `固定格 C${cell.channel! + 1}` : cell.kind === "placed"
            ? `拼块 ${cell.pieceIndex! + 1}，C${cell.channel! + 1}` : "空格";
        return <span key={`${cell.row},${cell.column}`} className={`circuit-cell ${cell.kind}${channelClass}`}
          aria-label={`第 ${cell.row + 1} 行第 ${cell.column + 1} 列，${description}`}>
          {cell.kind === "blocked" ? "×" : cell.kind === "fixed"
            ? <><b>C{cell.channel! + 1}</b><small>固定</small></> : cell.kind === "placed"
              ? <><b>C{cell.channel! + 1}</b><small>P{cell.pieceIndex! + 1}</small></> : null}
        </span>;
      })}
    </div>
    <ol className="circuit-placement-list" aria-label="拼块摆放清单">
      {placements.map((placement) => <li key={placement.pieceIndex}>
        <strong>拼块 {placement.pieceIndex + 1}</strong>
        <CircuitChannelToken channel={placement.channel} />
        <span>锚点：第 {placement.row + 1} 行、第 {placement.column + 1} 列</span>
        <span>{placement.rotation === 0 ? "不旋转" : `顺时针旋转 ${placement.rotation}°`}</span>
      </li>)}
    </ol>
    <p className="muted small">规则 {value.rule_version} · {placements.length} 个库存拼块均已使用</p>
  </div>;
}
