import { useEffect } from "react";
import { Link } from "react-router-dom";

export default function HomePage() {
  useEffect(() => { document.title = "终末地解谜助手"; }, []);
  return <div className="landing-page">
    <div className="intro home-intro">
      <span className="eyebrow">解谜工具 / WORKBENCH</span>
      <h1>选择要解的谜题</h1>
      <p>选择谜题类型，进入对应的截图识别与求解工具。</p>
    </div>
    <div className="puzzle-cards">
      <Link className="puzzle-card available" to="/balloon">
        <span className="puzzle-card-status">可用</span>
        <h2>浮空回收</h2>
        <p>上传截图自动识别棋盘与气球库存，或按题号查询已记录题面。</p>
        <span className="puzzle-card-action">进入工具</span>
      </Link>
      <Link className="puzzle-card available" to="/circuit">
        <span className="puzzle-card-status">可用</span>
        <h2>源石电路</h2>
        <p>上传截图识别行列约束与库存拼块，或按题号查询已记录的正常变体。</p>
        <span className="puzzle-card-action">进入工具</span>
      </Link>
    </div>
  </div>;
}
