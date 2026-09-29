import { useEffect } from "react";
import { Link } from "react-router-dom";

export default function CircuitPage() {
  useEffect(() => { document.title = "源石电路（开发中） | 终末地解谜助手"; }, []);
  return <div className="placeholder-page">
    <span className="eyebrow">解谜工具 / CIRCUIT</span>
    <h1>源石电路</h1>
    <div className="panel placeholder-panel">
      <span className="status-pill">开发中</span>
      <h2>完整解题页面正在准备</h2>
      <p className="muted">源石电路的截图识别与按题号查询暂未在网页开放。</p>
      <div className="row-actions">
        <Link className="button primary" to="/">返回首页</Link>
        <Link className="button secondary" to="/balloon">使用浮空回收</Link>
      </div>
    </div>
  </div>;
}
