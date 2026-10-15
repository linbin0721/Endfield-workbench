import type { ComponentType, SVGProps } from "react";
import { TOOLS } from "../tools/registry";
import { HomeIcon } from "../ui/icons";

export type NavItem = {
  id: string;
  /** App path without the locale prefix. */
  path: string;
  labelKey: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Only the home link must match exactly. */
  end: boolean;
};

/** Home plus every registered tool, shared by the desktop tabs and the mobile menu. */
export const NAV_ITEMS: readonly NavItem[] = [
  { id: "home", path: "/", labelKey: "nav.home", icon: HomeIcon, end: true },
  ...TOOLS.map((tool) => ({ id: tool.id, path: `/${tool.segment}`, labelKey: tool.navKey, icon: tool.icon, end: false })),
];
