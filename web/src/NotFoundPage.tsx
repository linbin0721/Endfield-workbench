import { useEffect } from "react";
import { Link } from "react-router-dom";

export default function NotFoundPage() {
  useEffect(() => { document.title = "页面未找到 | 终末地解谜助手"; }, []);
  return <div className="not-found-page">
    <span className="eyebrow">404 / NOT FOUND</span>
    <h1>页面未找到</h1>
    <p className="muted">这个地址没有对应的工具页面。</p>
    <Link className="button primary" to="/">返回首页</Link>
  </div>;
}
