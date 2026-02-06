import { Activity, FileText, Terminal } from "lucide-react";
import { NavLink, Outlet } from "react-router";
import { TooltipProvider } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

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
        <header className="h-10 shrink-0 border-b border-zinc-800">
          <div className="mx-auto flex h-full w-full max-w-2xl items-center px-4">
            <span className="font-mono text-sm font-semibold tracking-tight text-zinc-200">
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
                      "flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium transition-colors",
                      isActive
                        ? "bg-zinc-800 text-zinc-100"
                        : "text-zinc-300 hover:text-zinc-100 hover:bg-zinc-900",
                    )
                  }
                >
                  <item.icon className="h-3.5 w-3.5" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </TooltipProvider>
  );
}
