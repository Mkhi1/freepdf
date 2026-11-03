import { useEffect, useRef, useState } from "preact/hooks";
import { matchesAccepted, watchDrops } from "../engine/files";

export interface DropState {
  hovering: boolean;
  /** Set when a drop held files the tool cannot use. */
  notice: string | null;
}

/** Whole-window drop. Calls onFiles with the dropped paths the tool accepts. */
export function useWindowDrop(accepts: readonly string[], onFiles: (paths: string[]) => void): DropState {
  const [hovering, setHovering] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const latest = useRef(onFiles);
  latest.current = onFiles;

  useEffect(() => {
    return watchDrops(
      (paths) => {
        const usable = paths.filter((p) => matchesAccepted(p, accepts));
        if (usable.length === 0) {
          setNotice(accepts.length ? `Those files do not fit this tool. It takes ${accepts.join(", ").toUpperCase()} files.` : "This tool does not take files.");
          return;
        }
        setNotice(usable.length < paths.length ? "Some files were skipped because this tool cannot use them." : null);
        latest.current(usable);
      },
      setHovering,
    );
  }, [accepts.join(",")]);

  return { hovering, notice };
}
