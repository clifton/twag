import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center px-1.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-zinc-800 text-zinc-300",
        secondary: "bg-zinc-800/50 text-zinc-400",
        outline: "border border-zinc-700 text-zinc-400",
        high_signal: "bg-green-500/15 text-green-400",
        market_relevant: "bg-cyan-500/15 text-cyan-400",
        news: "bg-violet-500/15 text-violet-400",
        noise: "bg-zinc-800/50 text-zinc-500",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
