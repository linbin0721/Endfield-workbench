import type { SVGProps } from "react";

// Self-drawn tool marks in the same 20px stroke style as src/ui/icons.
type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...rest }: IconProps) {
  return <svg
    width="20"
    height="20"
    viewBox="0 0 20 20"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    focusable="false"
    {...rest}
  >{children}</svg>;
}

export const BalloonIcon = (props: IconProps) => <Icon {...props}>
  <path d="M10 2.8a4.7 4.7 0 0 1 4.7 4.7c0 3-2.6 5.4-4.7 6.3-2.1-.9-4.7-3.3-4.7-6.3A4.7 4.7 0 0 1 10 2.8z" />
  <path d="M9 13.9h2M10 13.9c0 1.2-1.4 1.8-1.4 3.3" />
</Icon>;

export const CircuitIcon = (props: IconProps) => <Icon {...props}>
  <rect x="6" y="6" width="8" height="8" />
  <path d="M8.5 3v3M11.5 3v3M8.5 14v3M11.5 14v3M3 8.5h3M3 11.5h3M14 8.5h3M14 11.5h3" />
</Icon>;

export const CalculatorIcon = (props: IconProps) => <Icon {...props}>
  <path d="M3.5 16.5h13" />
  <path d="M5.5 13.5v-3M9 13.5V6M12.5 13.5v-5M16 13.5V3.5" />
</Icon>;
