import { imageSrc } from "../kit";
import { Thumb } from "../reader/Thumb";
import type { Change, Marked, PagePair } from "./changes";
import { pageLabel } from "./changes";

export type Sizes = Array<[number, number]>;
export const A4: [number, number] = [595, 842];

export interface RowCtx {
  mode: "text" | "visual";
  fileA: string;
  fileB: string;
  passwordA?: string;
  passwordB?: string;
  sizesA: Sizes;
  sizesB: Sizes;
  colWidth: number;
  active: Change | null;
}

const sizeOf = (sizes: Sizes, page: number | null): [number, number] => (page === null ? A4 : sizes[page] ?? A4);

/** Height in px of one row of the result list. */
export function rowHeight(pair: PagePair, ctx: Pick<RowCtx, "sizesA" | "sizesB" | "colWidth" | "mode">): number {
  const [wa, ha] = sizeOf(ctx.sizesA, pair.page_a);
  const [wb, hb] = sizeOf(ctx.sizesB, pair.page_b);
  if (ctx.mode === "visual") return (Math.max(ha, hb) / Math.max(wa, wb)) * ctx.colWidth + 30;
  return Math.max(ha * (ctx.colWidth / wa), hb * (ctx.colWidth / wb)) + 30;
}

function Marks({ marks, size, kind, active, row }: { marks: Marked[]; size: [number, number]; kind: string; active: string | null; row: number }) {
  return (
    <>
      {marks.map((m, i) => (
        <i
          class={`mark mark-${kind}${active === `${kind === "added" ? "a" : "r"}${row}-${i}` ? " now" : ""}`}
          title={m.text}
          style={{
            left: `${(m.rect[0] / size[0]) * 100}%`, top: `${(m.rect[1] / size[1]) * 100}%`,
            width: `${((m.rect[2] - m.rect[0]) / size[0]) * 100}%`, height: `${((m.rect[3] - m.rect[1]) / size[1]) * 100}%`,
          }}
        />
      ))}
    </>
  );
}

interface SideProps {
  file: string;
  page: number | null;
  size: [number, number];
  width: number;
  password?: string;
  marks?: Marked[];
  kind: "added" | "removed";
  active: string | null;
  row: number;
}

function Side({ file, page, size, width, password, marks, kind, active, row }: SideProps) {
  const height = size[1] * (width / size[0]);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (page === null) {
    return <div class="cmp-missing" style={{ width: `${width}px`, height: `${height}px` }}>This page is not in this file</div>;
  }
  return (
    <div class="cmp-page" style={{ width: `${width}px`, height: `${height}px` }}>
      <Thumb file={file} page={page} width={Math.max(200, Math.round((width * dpr) / 100) * 100)} password={password} />
      <Marks marks={marks ?? []} size={size} kind={kind} active={active} row={row} />
    </div>
  );
}

export function PairRow({ pair, row, ctx }: { pair: PagePair; row: number; ctx: RowCtx }) {
  const here = ctx.active && ctx.active.row === row ? ctx.active.key : null;
  if (ctx.mode === "visual") {
    const [wa, ha] = sizeOf(ctx.sizesA, pair.page_a);
    const [wb, hb] = sizeOf(ctx.sizesB, pair.page_b);
    const ratio = Math.max(ha, hb) / Math.max(wa, wb);
    const width = ctx.colWidth;
    return (
      <div class={here ? "cmp-row now" : "cmp-row"}>
        <div class="cmp-label">{pageLabel(pair)}{pair.changed ? "" : " (no differences)"}</div>
        <div class="cmp-pair"><div class="cmp-page" style={{ width: `${width}px`, height: `${width * ratio}px` }}>
          {pair.image ? <img src={imageSrc(pair.image)} alt={`Differences on ${pageLabel(pair)}`} draggable={false} /> : null}
        </div></div>
      </div>
    );
  }
  return (
    <div class={pair.changed ? "cmp-row changed" : "cmp-row"}>
      <div class="cmp-label">{pageLabel(pair)}{pair.changed ? "" : " (no differences)"}</div>
      <div class="cmp-pair">
        <Side file={ctx.fileA} page={pair.page_a} size={sizeOf(ctx.sizesA, pair.page_a)} width={ctx.colWidth}
          password={ctx.passwordA} marks={pair.removed} kind="removed" active={here} row={row} />
        <Side file={ctx.fileB} page={pair.page_b} size={sizeOf(ctx.sizesB, pair.page_b)} width={ctx.colWidth}
          password={ctx.passwordB} marks={pair.added} kind="added" active={here} row={row} />
      </div>
    </div>
  );
}
