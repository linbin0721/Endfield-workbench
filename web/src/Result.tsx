import type { BalloonPuzzle, BalloonSolveResult } from "./puzzle";

type Props = { puzzle: BalloonPuzzle; result: BalloonSolveResult };

export default function Result({ puzzle, result }: Props) {
  if (result.outcome === "unsatisfiable") return <div className="notice warning" role="status">
    <strong>按这张图片识别出的题面没有解。</strong> 请换一张包含完整棋盘和右侧所有气球库存的清晰截图重试。只有搜索穷尽后才显示此结论。
  </div>;
  if (result.outcome === "timeout") return <div className="notice warning" role="status">
    <strong>计算达到{result.limit_reason === "time" ? "时间" : "工作量"}上限。</strong> 尚不能判断是否有解，请稍后重试。
  </div>;
  const solution = result.solution;
  if (!solution) return <div className="notice warning">服务未返回完整答案。</div>;
  const usable = new Set(puzzle.usable_cells.map((cell) => `${cell.row},${cell.column}`));
  const placed = new Map(solution.placements.map((item) => [`${item.row},${item.column}`, item.lift]));
  return <div className="solution">
    <p className="success-line">已找到一组摆放方案。棋盘中的数字是该格气球的升力。</p>
    <div className="board result-board" style={{ gridTemplateColumns: `repeat(${puzzle.columns}, minmax(0, 1fr))` }}>
      {Array.from({ length: puzzle.rows * puzzle.columns }, (_, index) => {
        const row = Math.floor(index / puzzle.columns), column = index % puzzle.columns;
        const key = `${row},${column}`, lift = placed.get(key);
        return <div key={key} className={`cell ${!usable.has(key) ? "blocked" : lift ? "filled" : "empty"}`}
          aria-label={`第 ${row} 行第 ${column} 列，${!usable.has(key) ? "禁用" : lift ? `放置升力 ${lift}` : "留空"}`}>
          {lift != null && <strong>{lift}</strong>}
        </div>;
      })}
    </div>
    <div className="summary">
      <span>已用 {solution.used_count} 个气球</span><span>总升力 {solution.total_lift}</span>
      <span>行力矩 {solution.row_moment}</span><span>列力矩 {solution.column_moment}</span>
    </div>
    <p className="muted small">规则 {result.rule_version}：行、列两方向的加权升力均已平衡。</p>
  </div>;
}
