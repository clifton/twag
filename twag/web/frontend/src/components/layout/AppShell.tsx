import { NavLink, Outlet } from "react-router";
import { Activity, FileText, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import { TooltipProvider } from "@/components/ui/tooltip";

const navItems = [
  { to: "/", label: "Feed", icon: Activity },
  { to: "/prompts", label: "Prompts", icon: FileText },
  { to: "/context-commands", label: "Context", icon: Terminal },
] as const;

export function AppShell() {
  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex h-screen flex-col bg-zinc-950">
        {/* Top bar */}
        <header className="flex h-10 shrink-0 items-center border-b border-zinc-800 px-4">
          <span className="font-mono text-sm font-semibold tracking-tight text-zinc-300">
            twag
          </span>
          <nav className="ml-6 flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded transition-colors",
                    isActive
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900",
                  )
                }
              >
                <item.icon className="h-3.5 w-3.5" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </TooltipProvider>
  );
}
