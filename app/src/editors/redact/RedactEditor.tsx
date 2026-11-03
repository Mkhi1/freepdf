import { useState } from "preact/hooks";
import { Loader, Search, SquareDashed, TriangleAlert, X } from "lucide-preact";
import { engineCall } from "../kit";
import { Group, Toggle } from "../../ui/fields";
import { DocGate, EditorShell } from "../canvas/EditorShell";
import { fromRect, toRect } from "../canvas/geometry";
import type { Box } from "../canvas/geometry";
import { ToolButton } from "../canvas/ToolButton";
import { newId } from "../canvas/types";
import type { DocView, Gesture, Item } from "../canvas/types";
import { useEditorDoc } from "../canvas/useEditorDoc";
import { useEditorRun } from "../canvas/useEditorRun";
import { useItemsEditor } from "../canvas/useItemsEditor";

type Area = Item;
interface Term { text: string; total: number; byPage: Record<number, Box[]> }

async function findTerm(doc: DocView, text: string): Promise<Term> {
  const r = await engineCall("search", { file: doc.file, query: text, ...(doc.password ? { password: doc.password } : {}) });
  const byPage: Record<number, Box[]> = {};
  for (const hit of r.summary.hits as Array<{ page: number; rects: number[][] }>) byPage[hit.page] = hit.rects.map(fromRect);
  return { text, total: Number(r.summary.total ?? 0), byPage };
}

function Hits({ boxes, scale, solid }: { boxes: readonly Box[]; scale: number; solid: boolean }) {
  return (
    <>
      {boxes.map((b) => (
        <div
          class="ed-hit"
          style={{
            left: `${b.x * scale}px`, top: `${b.y * scale}px`, width: `${b.w * scale}px`, height: `${b.h * scale}px`,
            background: solid ? "rgba(0,0,0,.78)" : undefined, outlineStyle: solid ? "solid" : "dashed",
          }}
        />
      ))}
    </>
  );
}

function RedactBody({ doc }: { doc: DocView }) {
  const ed = useItemsEditor<Area>(doc.sizes);
  const run = useEditorRun("redact");
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState<Term | null>(null);
  const [terms, setTerms] = useState<Term[]>([]);
  const [busy, setBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [clean, setClean] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const { history } = ed;

  const find = async () => {
    const text = query.trim();
    if (!text) return;
    setBusy(true);
    setSearchError(null);
    try {
      setPending(await findTerm(doc, text));
    } catch (e) {
      setSearchError((e as { message?: string }).message ?? "The search failed.");
    } finally {
      setBusy(false);
    }
  };
  const markAll = () => {
    if (!pending || pending.total === 0) return;
    setTerms((t) => [...t.filter((x) => x.text !== pending.text), pending]);
    setPending(null);
    setQuery("");
  };

  const draw = (g: Gesture) => {
    if (g.type === "rect" && g.box.w > 3 && g.box.h > 3) ed.add({ id: newId(), page: g.page, box: g.box });
  };

  const totalMarks = ed.items.length + terms.reduce((n, t) => n + t.total, 0);
  const args = {
    file: doc.file, ...(doc.password ? { password: doc.password } : {}),
    items: [
      ...ed.items.map((a) => ({ type: "area", page: a.page, rect: toRect(a.box) })),
      ...terms.map((t) => ({ type: "search", text: t.text })),
    ],
    clean_metadata: clean,
  };
  const underlay = (scale: number) => (
    <>
      {terms.map((t) => <Hits key={t.text} boxes={t.byPage[ed.page] ?? []} scale={scale} solid />)}
      {pending ? <Hits boxes={pending.byPage[ed.page] ?? []} scale={scale} solid={false} /> : null}
    </>
  );

  const sidebar = (
    <>
      <p class="ed-warn" role="note">
        <TriangleAlert size={16} />
        <span>Redaction cannot be undone after saving. The text and pixels under each mark are removed for good from the new copy. Your original file is not changed.</span>
      </p>
      <Group title="Find text">
        <form class="searchbox" style={{ width: "auto" }} onSubmit={(e) => { e.preventDefault(); void find(); }}>
          <Search size={16} aria-hidden="true" />
          <input type="search" dir="auto" placeholder="Word or phrase" aria-label="Text to find" value={query} onInput={(e) => { setQuery(e.currentTarget.value); setPending(null); }} />
        </form>
        <div class="btn-row">
          <button type="button" class="btn small" disabled={!query.trim() || busy} onClick={() => void find()}>
            {busy ? <Loader size={14} class="spin" /> : null} Find
          </button>
          <button type="button" class="btn small primary" disabled={!pending || pending.total === 0} onClick={markAll}>
            Mark all{pending ? ` (${pending.total})` : ""}
          </button>
        </div>
        {searchError ? <p class="ed-warn" role="alert">{searchError}</p> : null}
        {pending && pending.total === 0 ? <p class="hint">No matches for "{pending.text}".</p> : null}
        <ul class="ed-list">
          {terms.map((t) => (
            <li key={t.text}>
              <span dir="auto">{t.text}</span>
              <small class="field-hint">{t.total} {t.total === 1 ? "match" : "matches"}</small>
              <button type="button" class="icon-btn" aria-label={`Unmark ${t.text}`} onClick={() => setTerms((l) => l.filter((x) => x !== t))}><X size={14} /></button>
            </li>
          ))}
        </ul>
      </Group>
      <Group title="Areas">
        <p class="hint">Drag on the page to mark an area. {ed.items.length} marked.</p>
        <button type="button" class="btn small" disabled={!ed.selected} onClick={() => ed.selectedId && ed.remove(ed.selectedId)}>Remove selected area</button>
      </Group>
      <Group title="Cleaning">
        <Toggle checked={clean} label="Clear document details" hint="Removes author, title and other hidden information" onChange={setClean} />
      </Group>
    </>
  );

  const confirmAction = confirming
    ? { label: "Yes, redact for good", disabled: false, hint: "This cannot be undone once saved.", onClick: () => { setConfirming(false); void run.start("redact", args); } }
    : { label: "Apply redactions", disabled: totalMarks === 0, hint: totalMarks === 0 ? "Mark an area or find some text first." : `${totalMarks} ${totalMarks === 1 ? "mark" : "marks"} to remove.`, onClick: () => setConfirming(true) };

  return (
    <EditorShell<Area>
      toolId="redact"
      doc={doc}
      page={ed.page}
      onPage={(p) => { ed.setPage(p); setConfirming(false); }}
      counts={ed.counts.map((c, p) => c + terms.reduce((n, t) => n + (t.byPage[p]?.length ?? 0), 0))}
      tools={<ToolButton icon={SquareDashed} label="Mark area" on={true} onClick={() => undefined} title="Drag on the page to mark an area" />}
      canUndo={history.canUndo}
      canRedo={history.canRedo}
      onUndo={history.undo}
      onRedo={history.redo}
      run={run}
      action={confirmAction}
      sidebar={sidebar}
      status={ed.items.length ? `${ed.items.length} ${ed.items.length === 1 ? "area" : "areas"} marked` : undefined}
      canvas={{
        items: ed.items,
        selectedId: ed.selectedId,
        onSelect: ed.select,
        onBegin: history.checkpoint,
        onChange: history.live,
        render: () => <div style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,.78)", outline: "1.5px solid #e11d48" }} />,
        mode: "rect",
        itemsFirst: true,
        onDraw: draw,
        underlay,
      }}
    />
  );
}

export default function RedactEditor() {
  const state = useEditorDoc();
  return <DocGate state={state}>{(doc) => <RedactBody key={doc.file} doc={doc} />}</DocGate>;
}
