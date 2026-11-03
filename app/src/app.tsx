import { lazy, Suspense } from "preact/compat";
import type { ComponentType } from "preact";
import { useEffect, useState } from "preact/hooks";
import { Home } from "./home/Home";
import { Tools } from "./home/Tools";
import { OfferDialog } from "./share/OfferDialog";
import { useRoute } from "./state/router";
import { ToolPage } from "./tools/ToolPage";
import { TabBar } from "./ui/TabBar";
import { UpdateBanner } from "./update/UpdateBanner";

// Screens past the home page load when first needed.
const Workspace = lazy(() => import("./workspace/Workspace").then((m) => ({ default: m.Workspace })));
const Result = lazy(() => import("./result/Result").then((m) => ({ default: m.Result })));
const History = lazy(() => import("./home/History").then((m) => ({ default: m.History })));
const Devices = lazy(() => import("./share/Devices").then((m) => ({ default: m.Devices })));
function Editor({ id }: { id: string }) {
  const [View, setView] = useState<ComponentType<{ id: string }> | null>(null);
  useEffect(() => {
    void import("./editors").then((m) => m.loadEditor(id)).then((mod) => setView(() => mod.default));
  }, [id]);
  return View ? <View id={id} /> : <div class="page" />;
}

export function App() {
  const route = useRoute();
  return (
    <div class="shell">
      <TabBar route={route} />
      <div class="shell-body">
        <Suspense fallback={<div class="page" />}>
          {route.name === "home" ? <Home /> : null}
          {route.name === "tools" ? <Tools category={route.category} /> : null}
          {route.name === "history" ? <History /> : null}
          {route.name === "devices" ? <Devices /> : null}
          {route.name === "tool" ? <ToolPage key={route.id} id={route.id} /> : null}
          {route.name === "work" ? <Workspace key={route.id} id={route.id} /> : null}
          {route.name === "result" ? <Result key={route.id} id={route.id} /> : null}
          {route.name === "editor" ? <Editor key={route.id} id={route.id} /> : null}
        </Suspense>
      </div>
      <OfferDialog />
      <UpdateBanner />
    </div>
  );
}
