import { Link, NavLink, Outlet } from "react-router-dom";

const navClassName = ({ isActive }: { isActive: boolean }) => isActive ? "active" : undefined;

export default function SiteLayout() {
  return <div className="page">
    <header className="site-header">
      <Link className="brand" to="/">终末地工具台</Link>
      <nav className="site-nav" aria-label="主要导航">
        <NavLink to="/" end className={navClassName}>首页</NavLink>
        <NavLink to="/balloon" className={navClassName}>浮空回收</NavLink>
        <NavLink to="/circuit" className={navClassName}>源石电路</NavLink>
        <NavLink to="/325" className={navClassName}>325挑战</NavLink>
      </nav>
    </header>
    <main><Outlet /></main>
    <footer>非官方玩家工具，与游戏官方无关。</footer>
  </div>;
}
