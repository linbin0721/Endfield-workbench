import { createContext, useContext, type ComponentPropsWithoutRef, type ElementType, type ReactNode } from "react";

export type SurfaceName = "dark" | "light";

const SurfaceContext = createContext<SurfaceName>("dark");

/** Surface of the nearest <Surface>; portal content must set data-surface from this. */
export function useSurface(): SurfaceName {
  return useContext(SurfaceContext);
}

type SurfaceProps<T extends ElementType> = {
  as?: T;
  surface: SurfaceName;
} & Omit<ComponentPropsWithoutRef<T>, "as">;

/** Context only, for elements that set data-surface themselves (e.g. Radix portal content). */
export function SurfaceScope({ surface, children }: { surface: SurfaceName; children: ReactNode }) {
  return <SurfaceContext.Provider value={surface}>{children}</SurfaceContext.Provider>;
}

/** Applies a surface's tokens to a subtree and tells portals which surface they belong to. */
export function Surface<T extends ElementType = "div">({ as, surface, ...rest }: SurfaceProps<T>) {
  const Component = (as ?? "div") as ElementType;
  return <SurfaceContext.Provider value={surface}>
    <Component data-surface={surface} {...rest} />
  </SurfaceContext.Provider>;
}
