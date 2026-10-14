import type { SVGProps } from "react";

// Self-drawn 20px stroke icons; decorative by default (labels come from the control).
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

export const ChevronDownIcon = (props: IconProps) => <Icon {...props}><path d="M5.5 8l4.5 4.5L14.5 8" /></Icon>;
export const ChevronRightIcon = (props: IconProps) => <Icon {...props}><path d="M8 5.5l4.5 4.5L8 14.5" /></Icon>;
export const DoubleChevronIcon = (props: IconProps) => <Icon {...props}><path d="M5 5.5l4.5 4.5L5 14.5M10.5 5.5L15 10l-4.5 4.5" /></Icon>;
export const CheckIcon = (props: IconProps) => <Icon {...props}><path d="M4.5 10.5l3.5 3.5 7.5-8" /></Icon>;
export const CloseIcon = (props: IconProps) => <Icon {...props}><path d="M5.5 5.5l9 9M14.5 5.5l-9 9" /></Icon>;
export const PlusIcon = (props: IconProps) => <Icon {...props}><path d="M10 4.5v11M4.5 10h11" /></Icon>;
export const MinusIcon = (props: IconProps) => <Icon {...props}><path d="M4.5 10h11" /></Icon>;
export const RefreshIcon = (props: IconProps) => <Icon {...props}><path d="M15.5 9.5a5.5 5.5 0 1 1-1.6-3.9M15.5 4v3.6h-3.6" /></Icon>;
export const SearchIcon = (props: IconProps) => <Icon {...props}><circle cx="9" cy="9" r="5" /><path d="M13 13l3.5 3.5" /></Icon>;
export const BanIcon = (props: IconProps) => <Icon {...props}><circle cx="10" cy="10" r="6.5" /><path d="M5.4 14.6l9.2-9.2" /></Icon>;
export const InfoIcon = (props: IconProps) => <Icon {...props}><circle cx="10" cy="10" r="7" /><path d="M10 9v4.5M10 6.5v.1" /></Icon>;
export const WarningIcon = (props: IconProps) => <Icon {...props}><path d="M10 3.5l7 12.5H3z" /><path d="M10 8.5v3.5M10 14v.1" /></Icon>;
export const ImageIcon = (props: IconProps) => <Icon {...props}><rect x="3" y="4" width="14" height="12" rx="1" /><path d="M3.5 13.5l4-4 3 3 2-2 4 4" /><circle cx="13" cy="7.5" r="1" /></Icon>;
export const CaptureIcon = (props: IconProps) => <Icon {...props}><rect x="3" y="4" width="14" height="10" rx="1" /><path d="M7.5 17h5M10 14v3" /><path d="M6 7h2M6 7v2M14 11h-2M14 11V9" /></Icon>;
export const ArrowRightIcon = (props: IconProps) => <Icon {...props}><path d="M4 10h11.5M11 5.5l4.5 4.5-4.5 4.5" /></Icon>;
