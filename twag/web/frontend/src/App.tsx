import { Route, Routes } from "react-router";
import { ContextPage } from "./components/context/ContextPage";
import { FeedPage } from "./components/feed/FeedPage";
import { AppShell } from "./components/layout/AppShell";
import { PromptsPage } from "./components/prompts/PromptsPage";
import { Toaster } from "./components/ui/toaster";

export function App() {
  return (
    <>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<FeedPage />} />
          <Route path="prompts" element={<PromptsPage />} />
          <Route path="context-commands" element={<ContextPage />} />
        </Route>
      </Routes>
      <Toaster />
    </>
  );
}
