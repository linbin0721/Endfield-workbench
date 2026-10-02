import { gameData } from "./data.ts";
import { searchBuilds } from "./search.ts";
import type { WorkerRequest, WorkerResponse } from "./types.ts";

const send = (message: WorkerResponse) => self.postMessage(message);
self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  if (event.data.type !== "search") return;
  try {
    const result = searchBuilds(gameData, event.data.request, phase => send({type: "progress", phase}));
    send({type: "done", result});
  } catch (error) {
    send({type: "error", message: error instanceof Error ? error.message : "计算失败，请重试"});
  }
};
