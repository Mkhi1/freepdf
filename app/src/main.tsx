import { render } from "preact";
import { App } from "./app";
import { announceReady, startupFile } from "./engine/client";
import { setFiles } from "./state/session";
import "./styles/base.css";
import "./styles/home.css";
import "./styles/work.css";

async function start(): Promise<void> {
  const file = await startupFile();
  if (file) {
    setFiles([file]);
    location.hash = "#/editor/reader";
  }
  render(<App />, document.getElementById("app")!);
  announceReady();
}

void start();
