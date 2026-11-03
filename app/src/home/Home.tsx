import { useState } from "preact/hooks";
import { pickFiles } from "../engine/files";
import { openDocuments } from "../state/tabs";
import { useWindowDrop } from "../ui/useDrop";
import { HomeFrame } from "./HomeFrame";
import { RecentFiles, RecentTools } from "./Recent";

const PDF_ONLY = ["pdf"];

function OpenZone({ notice }: { notice: string | null }) {
  const [busy, setBusy] = useState(false);
  const choose = async () => {
    setBusy(true);
    try {
      openDocuments(await pickFiles({ accepts: PDF_ONLY, multiple: true, title: "Open PDF files" }));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section class="openzone" aria-label="Open a file">
      <button type="button" class="btn primary" disabled={busy} onClick={() => void choose()}>Open file</button>
      <p>or drag and drop anywhere</p>
      {notice ? <p class="openzone-note">{notice}</p> : null}
    </section>
  );
}

/** The first screen: open a file, or carry on with a recent file or tool. */
export function Home() {
  const drop = useWindowDrop(PDF_ONLY, openDocuments);
  return (
    <HomeFrame active="recents" dragging={drop.hovering}>
      <OpenZone notice={drop.notice} />
      <RecentFiles />
      <RecentTools />
    </HomeFrame>
  );
}
