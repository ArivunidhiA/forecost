import { forwardRef, InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helper?: string;
  icon?: React.ReactNode;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, helper, icon, type = "text", ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={props.id}
            className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400 dark:text-slate-600">
              {icon}
            </div>
          )}
          <input
            type={type}
            className={cn(
              "w-full px-4 py-2 rounded-lg border transition-colors duration-200",
              "text-slate-900 dark:text-slate-50 placeholder-slate-400 dark:placeholder-slate-500",
              "bg-white dark:bg-slate-900",
              "border-slate-300 dark:border-slate-600",
              "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              error && "border-red-500 focus:ring-red-500 dark:border-red-500",
              !!icon && "pl-10",
              className
            )}
            ref={ref}
            {...props}
          />
        </div>
        {error && (
          <p className="mt-1 text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
        {helper && !error && (
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {helper}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";

export default Input;
