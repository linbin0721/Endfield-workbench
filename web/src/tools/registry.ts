import type { ComponentType, SVGProps } from "react";
import type { Namespace } from "../i18n";
import { BalloonIcon, CalculatorIcon, CircuitIcon } from "./icons";

export type ToolId = "balloon" | "circuit" | "calculator";

export type ToolEntry = {
  id: ToolId;
  /** Route segment below /:locale; the unprefixed form is the legacy redirect. */
  segment: string;
  /** Bundles loaded before the page mounts (`common` is always loaded). */
  namespaces: Namespace[];
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Keys in the `common` namespace. */
  navKey: string;
  nameKey: string;
  descriptionKey: string;
  /** Short English label on the home card. */
  tagKey: string;
};

/**
 * Every tool of the workbench, in display order. Navigation, home cards and
 * routes are generated from this list. Page components are mapped in App.tsx,
 * so this module never pulls a page (or the lazy 325 bundle) into shared code.
 * A new tool also needs its route namespaces in i18n/core.ts namespacesForPath.
 */
export const TOOLS: readonly ToolEntry[] = [
  {
    id: "balloon",
    segment: "balloon",
    namespaces: ["balloon", "messages"],
    icon: BalloonIcon,
    navKey: "nav.balloon",
    nameKey: "home.balloon.name",
    descriptionKey: "home.balloon.description",
    tagKey: "home.balloon.tag",
  },
  {
    id: "circuit",
    segment: "circuit",
    namespaces: ["circuit", "messages"],
    icon: CircuitIcon,
    navKey: "nav.circuit",
    nameKey: "home.circuit.name",
    descriptionKey: "home.circuit.description",
    tagKey: "home.circuit.tag",
  },
  {
    id: "calculator",
    segment: "325",
    namespaces: ["calculator", "messages", "names"],
    icon: CalculatorIcon,
    navKey: "nav.calculator",
    nameKey: "home.calculator.name",
    descriptionKey: "home.calculator.description",
    tagKey: "home.calculator.tag",
  },
];
