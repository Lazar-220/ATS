import "@fontsource-variable/inter/wght.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";

const queryClient = new QueryClient();
const root = document.getElementById("root");
if (root === null) {
  throw new Error("missing #root element");
}
// The design's base styles hang on these two classes.
root.className = "ats app";

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
