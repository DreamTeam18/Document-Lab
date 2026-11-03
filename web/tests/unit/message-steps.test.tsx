import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import { MessageSteps } from "@/components/chat/message-steps";
import type { ChatStep } from "@/core/chat/types";

it.each([
  ["failed", "Evidence checked — failed"],
  ["stopped", "Evidence checked — stopped"],
  ["complete", "Evidence checked"],
] as const)("renders %s progress explicitly", (status, label) => {
  const step: ChatStep = { id: "assess", kind: "search", label: "Evidence checked", status };
  render(<MessageSteps steps={[step]} />);
  expect(screen.getByText(label)).toBeInTheDocument();
});

it("replaces a failed stage with a successful retry", () => {
  const step: ChatStep = { id: "assess", kind: "search", label: "Evidence checked", status: "failed" };
  const { rerender } = render(<MessageSteps steps={[step]} />);
  rerender(<MessageSteps steps={[{ ...step, status: "complete" }]} />);
  expect(screen.queryByText("Evidence checked — failed")).not.toBeInTheDocument();
  expect(screen.getAllByText("Evidence checked")).toHaveLength(1);
});
