import type { TableSchema } from "../schema/table-schema";
import { generateRecommendations } from "./generate";
import type {
  RecommendationWorkerRequest,
  RecommendationWorkerResponse,
} from "./worker";

interface WorkerScope {
  onmessage:
    | ((event: MessageEvent<RecommendationWorkerRequest>) => void)
    | null;
  postMessage(message: RecommendationWorkerResponse): void;
}

const scope = self as unknown as WorkerScope;

let table: TableSchema | undefined;

scope.onmessage = (event) => {
  const message = event.data;
  if (message.type === "load") {
    table = message.table;
    scope.postMessage({ type: "loaded" });
    return;
  }
  if (message.type === "dispose") {
    table = undefined;
    return;
  }
  if (message.type === "generate") {
    if (!table) {
      scope.postMessage({
        type: "error",
        requestId: message.requestId,
        message: "Recommendations were requested before the table was loaded.",
      });
      return;
    }
    try {
      const recommendations = generateRecommendations(table, message.state);
      scope.postMessage({
        type: "result",
        requestId: message.requestId,
        recommendations,
      });
    } catch (error) {
      scope.postMessage({
        type: "error",
        requestId: message.requestId,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }
};
