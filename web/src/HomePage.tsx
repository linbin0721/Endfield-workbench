import { useEffect } from "react";
import { Link } from "react-router-dom";

export default function HomePage() {
  useEffect(() => { document.title = "终末地工具台"; }, []);
  return <div className="landing-page">
    <div className="intro home-intro">
      <span className="eyebrow">玩家工具 / WORKBENCH</span>
      <h1>选择要用的工具</h1>
      <p>选择解谜工具或养成计算器，进入对应页面。</p>
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
      <Link className="puzzle-card available" to="/325">
        <span className="puzzle-card-status">可用</span>
        <h2>325 挑战</h2>
        <p>为干员寻找面板属性达到 325 的养成方案，支持多属性同时达标并优先展示。</p>
        <span className="puzzle-card-action">进入工具</span>
      </Link>
    </div>
  </div>;
}
