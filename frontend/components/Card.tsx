import { ReactNode, HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  variant?: "default" | "elevated";
}

export const Card = ({
  className,
  variant = "default",
  children,
  ...props
}: CardProps) => {
  const variants = {
    default:
      "rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-sm",
    elevated:
      "rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-md hover:shadow-lg transition-shadow duration-200",
  };

  return (
    <div
      className={cn(variants[variant], className)}
      {...props}
    >
      {children}
    </div>
  );
};

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
  title?: string;
  subtitle?: string;
}

export const CardHeader = ({
  className,
  title,
  subtitle,
  children,
  ...props
}: CardHeaderProps) => (
  <div className={cn("px-6 py-4 border-b border-slate-200 dark:border-slate-700", className)} {...props}>
    {title ? (
      <>
        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-50">
          {title}
        </h3>
        {subtitle && (
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {subtitle}
          </p>
        )}
      </>
    ) : (
      children
    )}
  </div>
);

interface CardBodyProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export const CardBody = ({
  className,
  children,
  ...props
}: CardBodyProps) => (
  <div className={cn("px-6 py-4", className)} {...props}>
    {children}
  </div>
);

interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export const CardFooter = ({
  className,
  children,
  ...props
}: CardFooterProps) => (
  <div
    className={cn(
      "px-6 py-4 border-t border-slate-200 dark:border-slate-700 flex items-center justify-end gap-3",
      className
    )}
    {...props}
  >
    {children}
  </div>
);

export default Card;
